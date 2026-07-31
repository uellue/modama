import pytest

from pathlib import Path
import os
import time

from xdg.Mime import MIMEtype

from modama_crawler.recognition import (
    EMPAD,
    OctetStream,
    FileHandler,
    Directory,
    Symlink,
    guess,
)


EMPAD_XML = """<root name="acquisition_1">
    <timestamp timestamp="1706883519.18255" isoformat="2024-02-02T15:18:39.182550" />
    <software_version>1.2.2 (2021-08-20)</software_version>
    <raw_file filename="series_x1234.raw" />
</root>
"""


# Skip "invalid" for now until we test repository consistency -- more about
# database consistency now, not individual FileHandler
@pytest.fixture(
    params=[
        "valid",
    ]
)
def test_dir(tmp_path, request):
    if request.param == "valid":
        listing = [
            ("a", "d", "", None, ("inode/directory",)),
            (
                "a/aaa.xml",
                "f",
                EMPAD_XML,
                1000.0,
                ("text/xml", "application/x.empad+xml"),
            ),
            ("a/series_x1234.raw", "f", "", 1010.0, ("application/x.empad-raw",)),
            ("b.txt", "f", "", 1020.0, ("text/plain",)),
            ("c.txt", "l", "b.txt", None, ("inode/symlink",)),
            ("series_x1234.raw", "f", "", 1030.0, ("application/x.empad-raw",)),
            ("something.txt", "f", "", 1040.0, ("text/plain",)),
            ("something.raw", "f", "", 1050.0, tuple()),
            (
                "xxx.xml",
                "f",
                EMPAD_XML,
                1060.0,
                ("text/xml", "application/x.empad+xml"),
            ),
            ("zzz.abc", "f", EMPAD_XML, 1070.0, tuple()),
        ]
    elif request.param == "invalid":
        listing = [
            ("a", "d", "", None, ("inode/directory",)),
            (
                "a/aaa.xml",
                "f",
                EMPAD_XML,
                1000.0,
                ("text/xml", "application/x.empad+xml"),
            ),
            ("a/series_x1234.raw", "f", "", 1010.0, ("application/x.empad-raw",)),
            ("b.txt", "f", "", 1020.0, ("text/plain",)),
            ("series_x1234.raw", "f", "", 1030.0, ("application/x.empad-raw",)),
            ("something.txt", "f", "", 1040.0, ("text/plain",)),
            ("something.raw", "f", "", 1050.0, tuple()),
            # Two XML files claiming the same raw file
            (
                "www.xml",
                "f",
                EMPAD_XML,
                1060.0,
                ("text/xml", "application/x.empad+xml"),
            ),
            (
                "xxx.xml",
                "f",
                EMPAD_XML,
                1070.0,
                ("text/xml", "application/x.empad+xml"),
            ),
            # Don't match
            ("zzz.abc", "f", EMPAD_XML, 1080.0, tuple()),
        ]
    else:
        raise ValueError(f"{request.param} WTF")

    import os

    for path, kind, content, mtime, mime in listing:
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
    for path, kind, content, mtime, mimes in listing:
        p = tmp_path / Path(path)
        if p.exists() and kind == "f" and mtime is not None:
            os.utime(p, (mtime, mtime))
            stats[str(Path(path))] = p.stat(follow_symlinks=False)

    return (listing, tmp_path, request.param, stats)


def test_recognition(test_dir, test_database):
    listing, tmp_path, param, stats = test_dir
    for path, kind, content, mtime, mimes in listing:
        abspath = tmp_path / path
        guesses = guess(abspath)
        for mime in mimes:
            print(mime, path, os.path.isdir(abspath))
            assert MIMEtype(mime) in guesses
        handler = FileHandler.create(
            root=tmp_path, path=path, guesses=guesses, conn=test_database
        )
        if handler.path == path:
            formats = handler.get_formats()
            for mime in mimes:
                assert mime in formats


@pytest.mark.parametrize(
    "path", ("a/aaa.xml", "a/series_x1234.raw", "series_x1234.raw", "xxx.xml")
)
def test_empad(test_dir, path, test_database):
    listing, tmp_path, param, stats = test_dir
    abspath = tmp_path / path
    guesses = guess(abspath)
    print(guesses)
    handler = FileHandler.create(
        root=tmp_path, path=path, guesses=guesses, conn=test_database
    )
    assert isinstance(handler, EMPAD)


@pytest.mark.parametrize("path", ("something.raw", "b.txt"))
def test_not_empad(test_dir, path, test_database):
    listing, tmp_path, param, stats = test_dir
    abspath = tmp_path / path
    guesses = guess(abspath)
    print(guesses)
    handler = FileHandler.create(
        root=tmp_path, path=path, guesses=guesses, conn=test_database
    )
    assert not isinstance(handler, EMPAD)


def test_special(test_dir, test_database):
    listing, tmp_path, param, stats = test_dir
    for path, kind, content, mtime, mimes in listing:
        if kind in ("l", "d"):
            abspath = tmp_path / path
            guesses = guess(abspath)
            print(guesses)
            handler = FileHandler.create(
                root=tmp_path, path=path, guesses=guesses, conn=test_database
            )
            if kind == "l":
                assert isinstance(handler, Symlink)
            elif kind == "d":
                assert isinstance(handler, Directory)


def test_source_mtime():
    # Unix timestamp, 0 is far enough in the past
    max_mtime = 0.0
    now = time.time()
    for cls in FileHandler, OctetStream, Directory, Symlink, EMPAD:
        mtime = cls.source_mtime()
        # Plausibility
        # 16th of July 2026, yesterday at time of writing
        assert mtime >= 1784213173
        assert mtime < now
        print(mtime)
        max_mtime = max(max_mtime, mtime)
    print(max_mtime, FileHandler.youngest_source_mtime(), now)
    assert max_mtime == FileHandler.youngest_source_mtime()


def test_database_mtime(test_database, test_files):
    handler = FileHandler.create(
        root=test_files,
        path=Path("dataset-alpha/file1.txt"),
        guesses=[],
        conn=test_database,
    )
    res = handler.db_mtime
    cur = test_database.cursor()
    cur.execute("SELECT mtime from files where path = %s", (str(handler.abspath),))
    rows = cur.fetchall()
    ref = rows[0]["mtime"]
    assert res == ref
