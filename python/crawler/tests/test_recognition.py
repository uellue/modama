import pytest

import functools
from random import shuffle
from pathlib import Path
import bisect

from modama_crawler.dirwalk import crawl, outer_key, default_key, _mk_deterministic


reference_key = functools.partial(outer_key, key=_mk_deterministic(default_key))


EMPAD = """<root name="acquisition_1">
    <timestamp timestamp="1706883519.18255" isoformat="2024-02-02T15:18:39.182550" />
    <software_version>1.2.2 (2021-08-20)</software_version>
    <raw_file filename="series_x1234.raw" />
</root>
"""


@pytest.fixture
def test_dir(tmp_path):
    listing = [
        ('xxx.xml', 'f', EMPAD),
        ('series_x1234.raw', 'f', ''),
        ('a', 'd', ''),
        ('a/aaa.xml', 'f', EMPAD),
        ('a/series_x1234.raw', 'f', ''),
        ('something.txt', 'f', ''),
        ('something.raw', 'f', ''),
    ]

    for path, kind, content in listing:
        if kind == 'f':
            (tmp_path / Path(path)).write_text(content)
        elif kind == 'd':
            (tmp_path / Path(path)).mkdir(exist_ok=True)
            if content != '':
                raise RuntimeError('WTF')
        elif kind == 'l':
            target_is_directory = content[-1] == '/'
            (tmp_path / Path(path)).symlink_to(content, target_is_directory=target_is_directory)
        else:
            raise RuntimeError('WTF')
    shuffle(listing)
    return (listing, tmp_path)


def test_walk(test_dir):
    listing, tmp_path = test_dir
    shuffle(listing)

    res, continuation = crawl(
        root=tmp_path,
        continuation='',
        n=len(listing)
    )
    print(res, continuation)

    expected = sorted(list(zip(*listing))[0], key=reference_key)
    assert continuation == Path(expected[-1])
    expected.remove('series_x1234.raw')
    expected.remove('a/series_x1234.raw')

    found = [str(f) for f in res.keys()]

    print(found)
    print(expected)

    assert found == expected


def test_walk_stepwise(test_dir):
    listing, tmp_path = test_dir
    shuffle(listing)

    res = {}
    continuation = ''

    while True:
        piece, continuation = crawl(
            root=tmp_path,
            continuation=continuation,
            n=1
        )
        if piece:
            for key in piece.keys():
                assert key not in res
            res.update(piece)
        else:
            break
    print(res, continuation)

    expected = sorted(list(zip(*listing))[0], key=reference_key)
    assert continuation == Path(expected[-1])
    expected.remove('series_x1234.raw')
    expected.remove('a/series_x1234.raw')

    found = [str(f) for f in res.keys()]

    print(found)
    print(expected)

    assert found == expected
