"""The post-order walk (the `crawl` spec)."""

import importlib
import logging
import os
import threading
import time
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from modama_crawler import cli
from modama_crawler.formats import DIRECTORY, Collection, Dataset, Format
from modama_crawler.store import previous, start_run, store
from modama_crawler.testing import collection_tests_for
from modama_crawler.walk import walk


class Series(Format):
    """A directory with at least two files of the same type is a series; pre-order it collapses on a marker."""

    type = "x/series"
    priority = 70
    reacts_to = frozenset({DIRECTORY})
    collection = True

    def recognize(self, d):
        if d.phase == "pre":
            if d.entry("COLLAPSE"):
                yield Dataset(anchor=d.rel, collapsed=True, basis="COLLAPSE marker")
            return
        files = [e for e in d.entries if e.kind == "file"]
        if len(files) >= 2 and len({e.mime for e in files}) == 1:
            yield Dataset(
                anchor=d.rel,
                members=tuple(e.rel for e in files),
                basis=f"{len(files)} files of one type",
            )


class Bundle(Format):
    """A directory that adopts all of its children's datasets."""

    type = "x/bundle"
    priority = 20
    reacts_to = frozenset({DIRECTORY})
    collection = True

    def recognize(self, d):
        if d.phase == "post" and d.children:
            yield Dataset(
                anchor=d.rel,
                parts=tuple(c.anchor for c in d.children),
                basis="bundle of children",
            )


FORMATS = Collection("t", [Series(), Bundle()]).formats


def test_parent_sees_child_result(tmp_path):
    (tmp_path / "outer" / "inner").mkdir(parents=True)
    (tmp_path / "outer" / "inner" / "1.txt").write_text("a")
    (tmp_path / "outer" / "inner" / "2.txt").write_text("b")
    (tmp_path / "outer" / "note.txt").write_text("n")
    result = walk(tmp_path, FORMATS)
    by_anchor = {d.anchor: d for d in result.datasets}
    assert by_anchor["/outer/inner"].type == "x/series"
    assert by_anchor["/outer/inner"].parent == "/outer"
    assert by_anchor["/outer"].type == "x/bundle" and by_anchor["/outer"].parts == (
        "/outer/inner",
    )
    assert by_anchor["/outer"].parent == "/"
    # The note became a dataset after /outer's formats ran, so the root bundle adopted it, not /outer
    assert by_anchor["/outer/note.txt"].parent == "/"


def test_collapsed_directory_is_not_entered(tmp_path, monkeypatch):
    import modama_crawler.walk as walk_module
    from modama_crawler.formats import Directory

    classified, read = [], []
    real_detect, real_read = walk_module.mime.detect_with_tie, Directory.read
    monkeypatch.setattr(
        walk_module.mime,
        "detect_with_tie",
        lambda path, **kw: (classified.append(path), real_detect(path, **kw))[1],
    )
    monkeypatch.setattr(
        Directory, "read", lambda d, e, n: (read.append(e.path), real_read(d, e, n))[1]
    )
    (tmp_path / "boring" / "deep").mkdir(parents=True)
    (tmp_path / "boring" / "COLLAPSE").write_text("")
    for i in range(50):
        (tmp_path / "boring" / "deep" / f"{i}.bin").write_bytes(b"\0")
    os.symlink("/nonexistent", tmp_path / "boring" / "lib64")  # as in every venv
    os.mkfifo(tmp_path / "boring" / "pipe")
    result = walk(tmp_path, FORMATS)
    assert [d.anchor for d in result.datasets if d.anchor != "/"] == ["/boring"]
    assert result.datasets[-1].collapsed and result.datasets[-1].members == ()
    # Nothing below a collapsed directory is reported, not even skipped entries
    assert result.skipped == [] and result.warnings == []
    # ... nor classified or opened
    assert not [p for p in classified + read if "/boring/" in p]


def test_a_collapsed_dataset_is_stamped_with_its_listing(tmp_path):
    # Not a scenario of its own: a constant stamp would let any extraction be reused (review 2026-11-11, 4)
    stamps = []
    for name, extra in (("one", []), ("two", ["more.bin"])):
        (tmp_path / name / "boring").mkdir(parents=True)
        for f in ["COLLAPSE", *extra]:
            (tmp_path / name / "boring" / f).write_text("")
        (d,) = [d for d in walk(tmp_path / name, FORMATS).datasets if d.collapsed]
        stamps.append(d.stamp)
    assert stamps[0] != stamps[1]


def test_dataset_size_is_the_total_of_its_members(tmp_path):
    # From the walk's stat, for the description (D4); no file is opened for it
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "a.txt").write_text("x" * 10)
    (tmp_path / "s" / "b.txt").write_text("y" * 5)
    (tmp_path / "single.bin").write_bytes(b"\0" * 7)
    by_anchor = {d.anchor: d for d in walk(tmp_path, FORMATS).datasets}
    assert by_anchor["/s"].size == 15
    assert by_anchor["/single.bin"].size == 7


def test_entries_carry_both_timestamps(tmp_path):
    f = tmp_path / "old.txt"
    f.write_text("x")
    os.utime(f, (1_000_000_000, 1_000_000_000))
    seen = {}

    class Spy(Format):
        type = "x/spy"
        reacts_to = frozenset({DIRECTORY})

        def recognize(self, d):
            for e in d.entries:
                seen[e.name] = (e.mtime, e.ctime)
            return ()

    walk(tmp_path, Collection("s", [Spy()]).formats)
    mtime, ctime = seen["old.txt"]
    assert mtime == 1_000_000_000 and ctime > mtime


def test_result_does_not_depend_on_listing_order(tmp_path, monkeypatch):
    (tmp_path / "s").mkdir()
    for name in "abc":
        (tmp_path / "s" / f"{name}.txt").write_text(name)
    first = walk(tmp_path, FORMATS).to_json()
    real_scandir = os.scandir

    class Reversed:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            with real_scandir(self.path) as it:
                return iter(sorted(it, key=lambda e: e.name, reverse=True))

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(os, "scandir", Reversed)
    assert walk(tmp_path, FORMATS).to_json() == first
    assert [d["anchor"] for d in first["datasets"] if d["type"] == "x/series"] == ["/s"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read anything")
def test_unreadable_entries_are_skipped_and_logged(tmp_path, caplog):
    (tmp_path / "secret").mkdir()
    (tmp_path / "secret" / "x.txt").write_text("x")
    (tmp_path / "open.txt").write_text("o")
    (tmp_path / "locked.txt").write_text("l")
    (tmp_path / "secret").chmod(0)
    (tmp_path / "locked.txt").chmod(0)
    try:
        with caplog.at_level(logging.INFO, logger="modama_crawler.walk"):
            result = walk(tmp_path, FORMATS)
    finally:
        (tmp_path / "secret").chmod(0o700)
        (tmp_path / "locked.txt").chmod(0o600)
    assert [d.anchor for d in result.datasets] == ["/open.txt"]
    assert result.warnings == []
    assert result.skipped == [
        ("/locked.txt", "not readable"),
        ("/secret", "cannot list directory: Permission denied"),
    ]
    assert "/secret: skipped, cannot list directory: Permission denied" in caplog.text
    assert "/locked.txt: skipped, not readable" in caplog.text


def test_symlinks_and_special_files_are_skipped_and_logged(tmp_path, caplog):
    (tmp_path / "target.txt").write_text("t")
    (tmp_path / "sub").mkdir()
    os.symlink(tmp_path / "target.txt", tmp_path / "link.txt")
    os.symlink(tmp_path / "sub", tmp_path / "linkdir")
    os.symlink("/nonexistent", tmp_path / "dangling")
    os.mkfifo(tmp_path / "pipe")
    seen = []

    class Spy(Format):
        type = "x/spy"
        reacts_to = frozenset({DIRECTORY})

        def recognize(self, d):
            seen.extend(e.kind for e in d.entries)
            return []

    with caplog.at_level(logging.INFO, logger="modama_crawler.walk"):
        result = walk(tmp_path, [Spy()])
    assert [d.anchor for d in result.datasets] == ["/target.txt"]
    assert set(seen) == {"file", "dir"}
    assert result.skipped == [
        ("/dangling", "symlink"),
        ("/link.txt", "symlink"),
        ("/linkdir", "symlink"),
        ("/pipe", "other"),
    ]
    for line in (
        "/link.txt: skipped, symlink",
        "/linkdir: skipped, symlink",
        "/dangling: skipped, symlink",
        "/pipe: skipped, other",
    ):
        assert line in caplog.text


def test_non_utf8_name_is_skipped(tmp_path):
    os.close(os.open(os.fsencode(tmp_path) + b"/latin1-\xe4.txt", os.O_CREAT))
    (tmp_path / "ok.txt").write_text("o")
    result = walk(tmp_path, FORMATS)
    assert [d.anchor for d in result.datasets] == ["/ok.txt"]
    assert result.warnings[0][0] == "/" and "not valid UTF-8" in result.warnings[0][1]


def test_excluded_subtree_is_not_crawled(tmp_path):
    (tmp_path / "scratch" / "deep").mkdir(parents=True)
    (tmp_path / "scratch" / "deep" / "x.txt").write_text("x")
    (tmp_path / "keep.txt").write_text("k")
    result = walk(tmp_path, FORMATS, exclude=["/scratch/**"])
    assert [d.anchor for d in result.datasets] == ["/keep.txt"]


def test_per_path_ignore_keeps_a_format_away(tmp_path):
    (tmp_path / "legacy").mkdir()
    for name in "ab":
        (tmp_path / "legacy" / f"{name}.txt").write_text(name)
    plain = walk(tmp_path, FORMATS, per_path_ignores={"/legacy/**": ["t/series"]})
    assert {d.type for d in plain.datasets if d.anchor.startswith("/legacy/")} == {
        "text/plain"
    }


def test_missing_root(tmp_path):
    with pytest.raises(FileNotFoundError):
        walk(tmp_path / "nope", FORMATS)


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read anything")
def test_unreadable_root_is_an_error(tmp_path):
    tmp_path.chmod(0)
    try:
        with pytest.raises(PermissionError):
            walk(tmp_path, FORMATS)
    finally:
        tmp_path.chmod(0o700)


def test_a_readable_file_costs_no_access_call(tmp_path, monkeypatch):
    # The mode bits grant it; os.access would be one more NFS round trip (parallel-walk D4)
    (tmp_path / "open.txt").write_text("o")
    (tmp_path / "open.txt").chmod(0o644)
    real_access, calls = os.access, []
    monkeypatch.setattr(
        os, "access", lambda *a, **kw: (calls.append(a), real_access(*a, **kw))[1]
    )
    result = walk(tmp_path, FORMATS)
    assert [d.anchor for d in result.datasets] == ["/open.txt"]
    assert calls == []


def _whole(result) -> tuple:
    """Everything a walk returns, in its order."""
    return (
        result.datasets,
        result.warnings,
        result.skipped,
        list(result.listings.items()),
        result.unchanged,
    )


def _fixture_tests_modules() -> list[str]:
    """The tests package of every installed collection (and sub-collection) with fixtures."""
    found = []
    for ep in entry_points(group="modama.formats"):
        base = Path(importlib.import_module(ep.module).__file__).parent
        for manifest in sorted(base.rglob("tests/fixtures.toml")):
            parts = manifest.parent.relative_to(base).parts
            found.append(".".join([ep.module, *parts]))
    return found


@pytest.mark.parametrize("tests_module", _fixture_tests_modules())
def test_one_thread_against_many_on_the_fixture_trees(
    tests_module, mime_database, tmp_path, monkeypatch
):
    import modama_crawler.walk as walk_module

    ct = collection_tests_for(importlib.import_module(tests_module))
    formats = [f for c in mime_database.values() for f in c.formats]
    for name in ct.fixture_names():
        ct.materialise(name, tmp_path)
    # One file without a name a glob decides, so that matching runs in any case
    (tmp_path / "unnamed").write_bytes(b"\x89PNG\r\n\x1a\n")
    one = walk(tmp_path, formats, threads=1)
    assert len(one.datasets) >= len(ct.fixture_names())
    assert _whole(walk(tmp_path, formats, threads=16)) == _whole(one)
    # Magic matching in worker processes (parallel-walk D5)
    real_match_in, matched = walk_module.mime.match_in, []

    def match_in(pool):
        match = real_match_in(pool)
        return lambda data: (matched.append(data), match(data))[1]

    monkeypatch.setattr(walk_module.mime, "match_in", match_in)
    assert _whole(walk(tmp_path, formats, threads=16, processes=2)) == _whole(one)
    assert matched


def test_many_threads_with_the_last_crawls_state(conn, tmp_path, monkeypatch):
    import modama_crawler.walk as walk_module

    if os.geteuid() == 0:
        pytest.skip("root lists every directory")
    root = tmp_path / "data"
    for d in ("a/b/c", "x/y", "x/private", "r"):
        (root / d).mkdir(parents=True)
    for d in ("a", "a/b", "a/b/c", "x", "x/y", "r"):
        for name in ("1.txt", "2.txt"):
            (root / d / name).write_text(name)
    (root / "r" / "unread").write_bytes(b"\0")  # no name a glob decides: read
    real_detect = walk_module.mime.detect_with_tie

    def detect(path, **kw):
        if path.endswith("/unread"):
            raise PermissionError(13, "Permission denied", path)
        return real_detect(path, **kw)

    # The state the review fixes added: an unlistable directory, a listing to retry
    monkeypatch.setattr(walk_module.mime, "detect_with_tie", detect)
    os.chmod(root / "x" / "private", 0)
    try:
        result = walk(root, FORMATS, threads=16)
        store(conn, result, {}, start_run(conn, str(root)), "r1")
        (root / "a" / "b" / "c" / "1.txt").write_text("changed, three levels down")
        stored = previous(conn, "r1")
        one = walk(root, FORMATS, previous=stored, threads=1)
        many = walk(root, FORMATS, previous=stored, threads=16)
    finally:
        os.chmod(root / "x" / "private", 0o755)
    assert one.unchanged == 2  # /x and /x/y; /a/b/c, /a/b, /a, /r and / again
    assert one.listings["/x/private"].digest == walk_module.UNLISTABLE
    assert one.listings["/r"].retry and not one.listings["/x"].retry
    assert _whole(many) == _whole(one)


def test_a_limit_on_reads_in_flight(tmp_path, monkeypatch):
    import modama_crawler.walk as walk_module

    for i in range(50):
        (tmp_path / f"f{i}").write_bytes(b"\0")  # no name a glob decides: read
    real_detect = walk_module.mime.detect_with_tie
    lock, now, most = threading.Lock(), [0], [0]

    def spy(path, **kw):
        with lock:
            now[0] += 1
            most[0] = max(most[0], now[0])
        time.sleep(0.01)
        try:
            return real_detect(path, **kw)
        finally:
            with lock:
                now[0] -= 1

    monkeypatch.setattr(walk_module.mime, "detect_with_tie", spy)
    walk(tmp_path, FORMATS, threads=4)
    assert most[0] == 4  # never more, and not one at a time


def test_the_number_of_threads_is_a_setting(monkeypatch):
    monkeypatch.delenv("MODAMA_CRAWLER_WALK_THREADS", raising=False)
    assert cli._threads() == 32
    monkeypatch.setenv("MODAMA_CRAWLER_WALK_THREADS", "4")
    assert cli._threads() == 4
