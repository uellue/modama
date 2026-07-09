import pytest

import functools
from random import shuffle
from pathlib import Path
from contextlib import contextmanager, suppress

from modama_crawler.dirwalk import (
    crawl,
    outer_key,
    default_key,
    _mk_stable,
    matches_oai_pmh_datestamp_limits,
)


reference_key = functools.partial(outer_key, key=_mk_stable(default_key))


EMPAD = """<root name="acquisition_1">
    <timestamp timestamp="1706883519.18255" isoformat="2024-02-02T15:18:39.182550" />
    <software_version>1.2.2 (2021-08-20)</software_version>
    <raw_file filename="series_x1234.raw" />
</root>
"""


@pytest.fixture(params=["valid", "invalid"])
def test_dir(tmp_path, request):
    if request.param == "valid":
        listing = [
            ("a", "d", "", None),
            ("a/aaa.xml", "f", EMPAD, 1000.0),
            ("a/series_x1234.raw", "f", "", 1010.0),
            ("b.txt", "f", "", 1020.0),
            ("series_x1234.raw", "f", "", 1030.0),
            ("something.txt", "f", "", 1040.0),
            ("something.raw", "f", "", 1050.0),
            ("xxx.xml", "f", EMPAD, 1060.0),
            ("zzz.abc", "f", EMPAD, 1070.0),
        ]
    elif request.param == "invalid":
        listing = [
            ("a", "d", "", None),
            ("a/aaa.xml", "f", EMPAD, 1000.0),
            ("a/series_x1234.raw", "f", "", 1010.0),
            ("b.txt", "f", "", 1020.0),
            ("series_x1234.raw", "f", "", 1030.0),
            ("something.txt", "f", "", 1040.0),
            ("something.raw", "f", "", 1050.0),
            # Two XML files claiming the same raw file
            ("www.xml", "f", EMPAD, 1060.0),
            ("xxx.xml", "f", EMPAD, 1070.0),
            # Don't match
            ("zzz.abc", "f", EMPAD, 1080.0),
        ]
    else:
        raise ValueError(f"{request.param} WTF")

    import os

    for path, kind, content, mtime in listing:
        if kind == "f":
            (tmp_path / Path(path)).write_text(content)
        elif kind == "d":
            (tmp_path / Path(path)).mkdir(exist_ok=True)
            if content != "":
                raise RuntimeError("WTF")
        elif kind == "l":
            target_is_directory = content[-1] == "/"
            (tmp_path / Path(path)).symlink_to(
                content, target_is_directory=target_is_directory
            )
        else:
            raise RuntimeError("WTF")

    # Set deterministic mtimes so tests can assert on ranges. ctime is taken
    # from the actual stat after creation and cannot be set reliably on POSIX.
    # Only record files (not directories) to avoid ctime unpredictability.
    stats = {}
    for path, kind, content, mtime in listing:
        p = tmp_path / Path(path)
        if p.exists() and kind == "f" and mtime is not None:
            os.utime(p, (mtime, mtime))
            stats[str(Path(path))] = p.stat(follow_symlinks=False)

    # Keep original listing order for reproducibility; shuffle for test robustness
    listing_items = [(p, k, c) for p, k, c, _ in listing]
    shuffle(listing_items)
    return (listing_items, tmp_path, request.param, stats)


def test_walk(test_dir):
    listing, tmp_path, param, stats = test_dir
    shuffle(listing)
    if param == "invalid":

        @contextmanager
        def warns():
            with pytest.warns(
                UserWarning, match="Encountered existing handler www.xml"
            ):
                with pytest.warns(
                    UserWarning,
                    match="Encountered member file mismatch between www.xml",
                ):
                    yield
    else:
        warns = suppress
    with warns():
        res, continuation = crawl(root=tmp_path, continuation="", n=len(listing))
    print(res, continuation)

    expected = sorted(list(zip(*listing))[0], key=reference_key)
    # Exhausted the directory, continuation must be None
    assert continuation is None
    expected.remove("series_x1234.raw")
    expected.remove("a/series_x1234.raw")

    found = [str(f) for f in res.keys()]

    print(found)
    print(expected)

    assert found == expected


def test_walk_stepwise(test_dir):
    listing, tmp_path, param, stats = test_dir
    shuffle(listing)

    res = {}
    continuation = ""
    loop = 0
    if param == "invalid":

        @contextmanager
        def warns():
            with pytest.warns(
                UserWarning, match="Encountered existing handler www.xml"
            ):
                with pytest.warns(
                    UserWarning,
                    match="Encountered member file mismatch between www.xml",
                ):
                    yield
    else:
        warns = suppress
    with warns():
        while True:
            piece, continuation = crawl(root=tmp_path, continuation=continuation, n=1)
            print(loop)
            loop += 1
            if piece:
                print(piece, continuation)
                for key in piece.keys():
                    assert key not in res
                res.update(piece)
            if continuation is None:
                print("finished")
                break
    print(res, continuation)

    expected = sorted(list(zip(*listing))[0], key=reference_key)
    expected.remove("series_x1234.raw")
    expected.remove("a/series_x1234.raw")

    found = [str(f) for f in res.keys()]

    print(found)
    print(expected)

    assert found == expected


def test_walk_time_filters(test_dir):
    listing, tmp_path, param, stats = test_dir
    if param == "invalid":
        pytest.skip("skipping 'invalid' fixture for time filters")
    # baseline ordering without any time limits
    baseline_res, _ = crawl(root=tmp_path, continuation="", n=len(listing))
    baseline_keys = list(baseline_res.keys())

    # derive mtime bounds from recorded stats
    m_values = [s.st_mtime for s in stats.values()] if stats else []
    m_min, m_max = (min(m_values), max(m_values)) if m_values else (None, None)

    # Filter to files with mtime in range [m_min + 10, m_min + 30]
    # Note: crawl() returns not only matching files, but also their handler members.
    # So we just verify that all time-matching files are present in the result.
    m_since = m_min + 10
    m_until = m_min + 30
    res, _ = crawl(
        root=tmp_path, continuation="", n=len(listing), m_since=m_since, m_until=m_until
    )

    # Collect files that should match the time filter
    time_matching_paths = []
    for p in baseline_keys:
        st = stats.get(str(p))
        if st is not None and matches_oai_pmh_datestamp_limits(
            st, m_since=m_since, m_until=m_until
        ):
            time_matching_paths.append(p)

    # Make sure the mtime limits are actually effective,
    # i.e. some files pass and some files don't.
    # These files are not directories and not part
    # of a compound dataset that should be found if any
    # of its member files fall into the limits.
    individual_files = ("b.txt", "something.txt", "something.raw")
    some_found = False
    some_skipped = False

    for indv in individual_files:
        if Path(indv) in time_matching_paths:
            some_found = True
        else:
            some_skipped = True

    assert some_found
    assert some_skipped

    # Verify that all time-matching files are in the result
    res_keys = list(res.keys())
    for matching_path in time_matching_paths:
        assert matching_path in res_keys, (
            f"Time-matching file {matching_path} not in results"
        )
