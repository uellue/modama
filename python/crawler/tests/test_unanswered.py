"""What the file system did not answer (change listing-errors, decision 271): crawl and runs in this process.

The errors are injected for one path: listings through `walk._names`, an
entry's stat through `walk._stat`, a folder's own stat through `os.lstat`,
`access(2)` and the `open(2)` that asks again through `os.access` and
`os.open`, reads through the `open` of `mime` and `files.regular` (review 1:
not `detect_with_tie`, whose fallback hid the error). The formats are the
stand-ins (standin.py), Zarr, and the test formats below.
"""

import errno
import os
import re
import signal
from datetime import UTC, timedelta

import pytest
import standin
import test_trigger
from conftest import CRAWLER, shell
from modama_crawler import cli, files, formats, identity, mime, selection
from modama_crawler import walk as walk_module
from modama_crawler.cli import overdue
from modama_crawler.formats import DIRECTORY, Collection, Dataset, Format
from modama_crawler.records import oai_identifier
from modama_crawler.store import last_finished
from psycopg.rows import dict_row
from test_trigger import crawl_env

airflow = test_trigger.airflow  # the stand-in for Airflow's API, a fixture

P = "adhoc/lib/test-data"
DM = f"/{P}/dm"


def installation(source="a") -> tuple[str, dict]:
    ingredients = {
        "python": "cpython 3.14.0",
        "distributions": {"modama-crawler": "0.0.1.dev0"},
        "source": {"standin.py": source},
    }
    return identity.digest(ingredients), ingredients


A, B = installation(), installation("b")


class Pair(Format):
    """A header naming its raw file, one dataset of both; every read error caught, as the EMPAD format does."""

    type = "application/x.pair"
    reacts_to = frozenset({DIRECTORY})

    def recognize(self, d):
        if d.phase != "post":
            return
        for e in d.entries:
            if e.kind == "file" and e.name.endswith(".head"):
                try:
                    name = d.read(e, 64).decode().strip()
                except Exception as err:  # noqa: BLE001  as empad/__init__.py
                    d.warn(e.rel, f"cannot read the header: {err!r}")
                    continue
                raw = d.entry(name)
                if raw is not None:
                    yield Dataset(anchor=e.rel, members=(raw.rel,), basis="header")


class Marked(Format):
    """Collapses a folder whose MARK file says `collapse`, read in the pre-order call."""

    type = "application/x.marked"
    priority = 90
    reacts_to = frozenset({DIRECTORY})

    def recognize(self, d):
        mark = d.entry("MARK")
        if (
            d.phase == "pre"
            and mark is not None
            and d.read(mark, 16).strip() == b"collapse"
        ):
            yield Dataset(anchor=d.rel, collapsed=True, basis="MARK says collapse")


class Listed(Format):
    """Collapses a folder with MARK and LIST files from its listing alone, at a lower priority than Marked."""

    type = "application/x.listed"
    priority = 10
    reacts_to = frozenset({DIRECTORY})

    def recognize(self, d):
        if d.phase == "pre" and d.entry("MARK") and d.entry("LIST"):
            yield Dataset(anchor=d.rel, collapsed=True, basis="MARK present")


TREE = {
    f"{P}/dm/a.stand": "ok a",
    f"{P}/dm/b.stand": "ok b",
    f"{P}/notes.stand": "ok notes",
    "other/c.stand": "ok c",
    "adhoc/x/a.stand": "ok xa",
    "adhoc/x/b.stand": "ok xb",
    "adhoc/x/notes": "plain words, typed by their content\n",
    "adhoc/x/sub/c.stand": "ok xc",
    "groups/x/a.stand": "ok ga",
    "groups/x/b.stand": "ok gb",
    "adhoc/z.zarr/zarr.json": '{"zarr_format": 3, "node_type": "group"}',
    "adhoc/z.zarr/c/0": "chunk",
    "adhoc/pair/scan.head": "scan.raw",
    "adhoc/pair/scan.raw": "raw bytes",
    "adhoc/marked/MARK": "collapse",
    "adhoc/marked/LIST": "",
    "adhoc/marked/sub/f.txt": "inside",
}


@pytest.fixture
def data(tmp_path):
    root = tmp_path / "data"
    for path, text in TREE.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    return root


@pytest.fixture
def calls(tmp_path):
    return tmp_path / "calls"


@pytest.fixture
def crawl(env, data, calls, monkeypatch):
    """`modama-crawler crawl ARGS` in this process: crawl(*args, installed=, rules=) -> exit status."""
    found = selection.discover()
    enabled = [
        *standin.collection(calls).formats,
        *found["zarr"].formats,
        *Collection("le", [Pair(), Marked(), Listed()]).formats,
    ]

    def run(*args, installed=A, rules="r1", threads=None) -> int:
        def configure(parsed):
            return selection.load_config(parsed.config), enabled, rules

        monkeypatch.setattr(cli, "configure", configure)
        monkeypatch.setattr(cli, "_installed", lambda: installed)
        if threads is not None:
            monkeypatch.setenv("MODAMA_CRAWLER_WALK_THREADS", str(threads))
        handler = signal.getsignal(signal.SIGTERM)
        try:
            return cli.main(["crawl", "--root", str(data), *args])
        finally:
            signal.signal(signal.SIGTERM, handler)

    return run


def error(code: int, path) -> OSError:
    return OSError(code, os.strerror(code), str(path))


def records(conn) -> dict[str, tuple]:
    conn.commit()
    return {
        identifier: (datestamp, metadata)
        for identifier, datestamp, metadata in conn.execute(
            "SELECT identifier, datestamp, metadata FROM records"
        )
    }


def aged(conn) -> dict[str, tuple]:
    """Move every datestamp back a day, so that a record written again shows; the records after that."""
    conn.execute("UPDATE records SET datestamp = datestamp - interval '1 day'")
    conn.commit()
    return records(conn)


def unchanged(before: dict, after: dict, *anchors: str) -> bool:
    return all(
        after.get(oai_identifier(a)) == before[oai_identifier(a)] for a in anchors
    )


def dataset(conn, anchor: str) -> tuple | None:
    conn.commit()
    return conn.execute(
        "SELECT format, basis, collapsed FROM datasets WHERE anchor = %s", (anchor,)
    ).fetchone()


def listed(conn) -> set[str]:
    conn.commit()
    return {p for (p,) in conn.execute("SELECT path FROM directories")}


def touch(path):
    """A newer mtime: the folder is recognised again, so that its files are read."""
    st = os.stat(path)
    os.utime(path, (st.st_atime + 10, st.st_mtime + 10))


def last_run(conn) -> dict:
    conn.commit()
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT * FROM crawl_runs ORDER BY run_id DESC LIMIT 1"
        ).fetchone()


def fail_listing(monkeypatch, data, rel: str, code: int, *more: str):
    real = walk_module._names
    paths = {os.path.join(data, r) for r in (rel, *more)}

    def names(dirpath):
        if dirpath in paths:
            raise error(code, dirpath)
        return real(dirpath)

    monkeypatch.setattr(walk_module, "_names", names)


def fail_stat(monkeypatch, data, rel: str, code: int):
    real = walk_module._stat
    target = os.path.join(data, rel)

    def stat_(path):
        return error(code, path) if path == target else real(path)

    monkeypatch.setattr(walk_module, "_stat", stat_)


def fail_read(monkeypatch, module, data, rel: str, code: int):
    """Opening the file fails in that module (its global `open`; for `formats`, whose
    reader opens through `files.regular`, that); the file is touched, so that it is read."""
    target = os.path.join(data, rel)
    touch(target)

    if module is formats:
        real = files.regular

        def regular(path):
            if os.fspath(path) == target:
                raise error(code, path)
            return real(path)

        monkeypatch.setattr(files, "regular", regular)
        return

    def open_(path, *args, **kwargs):
        if os.fspath(path) == target:
            raise error(code, path)
        return open(path, *args, **kwargs)

    monkeypatch.setattr(module, "open", open_, raising=False)


# Requirement: Entries that cannot make a useful record are skipped and logged


def test_permission_denied_removes_a_folder(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    fail_listing(monkeypatch, data, P + "/dm", errno.EACCES)
    assert crawl() == 0
    after = records(conn)
    assert oai_identifier(f"{DM}/a.stand") not in after
    assert last_run(conn)["outcome"] == "finished"


def test_a_folder_that_is_gone(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    fail_listing(monkeypatch, data, P + "/dm", errno.ENOENT)
    assert crawl() == 0
    assert oai_identifier(f"{DM}/a.stand") not in records(conn)
    assert last_run(conn)["outcome"] == "finished"


def test_access_says_no_and_open_says_why(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    target = str(data / "adhoc/x/b.stand")
    real_access, real_open = os.access, os.open
    monkeypatch.setattr(
        os, "access", lambda p, m, **k: p != target and real_access(p, m, **k)
    )

    def open_(path, flags, *args, **kwargs):
        if os.fspath(path) == target:
            raise error(errno.EACCES, path)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", open_)
    assert crawl() == 0
    assert oai_identifier("/adhoc/x/b.stand") not in records(conn)


def test_the_root_does_not_answer(conn, crawl, data, monkeypatch, caplog):
    assert crawl() == 0
    before = aged(conn)
    real = walk_module._names

    def names(dirpath):
        if dirpath == str(data):
            raise error(errno.EIO, dirpath)
        return real(dirpath)

    monkeypatch.setattr(walk_module, "_names", names)
    assert crawl() == 2
    assert str(data) in caplog.text
    assert last_run(conn)["outcome"] == "failed"
    assert records(conn) == before


# Requirement: A folder the file system did not answer keeps its records


@pytest.mark.parametrize("code", [errno.ESTALE, errno.EIO, errno.ENOMEM])
def test_a_folder_that_did_not_answer(conn, crawl, data, monkeypatch, code):
    assert crawl() == 0
    before = aged(conn)
    (data / "other" / "d.stand").write_text("ok d")
    fail_listing(monkeypatch, data, P + "/dm", code)
    assert crawl() == 4
    after = records(conn)
    assert unchanged(before, after, f"{DM}/a.stand", f"{DM}/b.stand")
    assert oai_identifier("/other/d.stand") in after


def test_folders_below_the_one_that_did_not_answer(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    before = aged(conn)
    listings = []
    real = walk_module._names

    def names(dirpath):
        listings.append(dirpath)
        if dirpath == str(data / P):
            raise error(errno.EIO, dirpath)
        return real(dirpath)

    monkeypatch.setattr(walk_module, "_names", names)
    assert crawl() == 4
    after = records(conn)
    assert unchanged(
        before, after, f"/{P}/notes.stand", f"{DM}/a.stand", f"{DM}/b.stand"
    )
    assert str(data / P / "dm") not in listings


def test_the_folders_own_stat_does_not_answer(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    before = aged(conn)
    target = str(data / P / "dm")
    real = os.lstat
    seen = []

    def lstat(path, *args, **kwargs):
        if os.fspath(path) == target:
            seen.append(path)
            if len(seen) == 2:  # the first is the parent's stat of its entry
                raise error(errno.EIO, path)
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", lstat)
    assert crawl() == 4
    assert unchanged(before, records(conn), f"{DM}/a.stand", f"{DM}/b.stand")
    assert last_run(conn)["outcome"] == "finished"


def test_a_collapsed_folder_that_did_not_answer(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    assert dataset(conn, "/adhoc/z.zarr")[2]  # collapsed
    before = aged(conn)
    fail_listing(monkeypatch, data, "adhoc/z.zarr", errno.EIO)
    assert crawl() == 4
    assert unchanged(before, records(conn), "/adhoc/z.zarr")


def test_a_pre_order_read_that_did_not_answer(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    before = aged(conn)
    fail_read(monkeypatch, formats, data, "adhoc/z.zarr/zarr.json", errno.EIO)
    listings = []
    real = walk_module._names
    monkeypatch.setattr(walk_module, "_names", lambda p: listings.append(p) or real(p))
    assert crawl() == 4
    assert unchanged(before, records(conn), "/adhoc/z.zarr")
    assert oai_identifier("/adhoc/z.zarr/c/0") not in records(conn)
    assert str(data / "adhoc/z.zarr/c") not in listings


def test_a_lower_priority_format_would_collapse_the_folder(
    conn, crawl, data, monkeypatch
):
    assert crawl() == 0
    stored = dataset(conn, "/adhoc/marked")
    assert stored == ("le/marked", "MARK says collapse", True)
    before = aged(conn)
    fail_read(monkeypatch, formats, data, "adhoc/marked/MARK", errno.EIO)
    assert crawl() == 4
    assert dataset(conn, "/adhoc/marked") == stored
    assert unchanged(before, records(conn), "/adhoc/marked")


def test_a_folder_below_the_path_of_a_subtree_crawl(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    before = aged(conn)
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    assert crawl("--path", P) == 4
    assert unchanged(before, records(conn), f"{DM}/a.stand", f"{DM}/b.stand")


def test_a_changed_rule_set(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    before = aged(conn)
    fail_listing(monkeypatch, data, P + "/dm", errno.EIO)
    assert crawl(rules="r2") == 4
    assert unchanged(before, records(conn), f"{DM}/a.stand", f"{DM}/b.stand")


# Requirement: A file the file system did not answer keeps its folder's records


def test_the_stat_of_an_entry_does_not_answer(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    before = aged(conn)
    (data / "adhoc/x/sub/d.stand").write_text("ok xd")
    fail_stat(monkeypatch, data, "adhoc/x/b.stand", errno.EIO)
    assert crawl() == 4
    after = records(conn)
    assert unchanged(
        before, after, "/adhoc/x/a.stand", "/adhoc/x/b.stand", "/adhoc/x/sub/c.stand"
    )
    # kept whole: not entered, so the new file comes with the next crawl (code review 1)
    assert oai_identifier("/adhoc/x/sub/d.stand") not in after
    assert not {"/adhoc/x", "/adhoc/x/sub"} & listed(conn)


def test_a_new_store_whose_marker_does_not_answer(conn, crawl, data, monkeypatch):
    # The code review's S5: answered without the marker, the store is not collapsed
    assert crawl() == 0
    (data / "adhoc/n.zarr/c").mkdir(parents=True)
    (data / "adhoc/n.zarr/zarr.json").write_text('{"zarr_format": 3}')
    (data / "adhoc/n.zarr/c/0").write_text("chunk")
    real = walk_module._stat
    monkeypatch.setattr(
        walk_module,
        "_stat",
        lambda p: error(errno.EIO, p) if p.endswith("n.zarr/zarr.json") else real(p),
    )
    assert crawl() == 4
    after = records(conn)
    # nothing stored, nothing kept (Q5): neither the store nor its chunk
    assert oai_identifier("/adhoc/n.zarr/c/0") not in after
    assert oai_identifier("/adhoc/n.zarr") not in after
    monkeypatch.setattr(walk_module, "_stat", real)
    assert crawl() == 0
    after = records(conn)
    assert oai_identifier("/adhoc/n.zarr") in after
    assert oai_identifier("/adhoc/n.zarr/c/0") not in after


def test_the_roots_pre_order_read_does_not_answer(
    conn, crawl, data, monkeypatch, caplog
):
    (data / "MARK").write_text("not this one")  # read by le/marked, no collapse
    assert crawl() == 0
    before = aged(conn)
    listings = listed(conn)
    fail_read(monkeypatch, formats, data, "MARK", errno.EIO)
    assert crawl() == 2
    assert f"cannot read {data / 'MARK'}" in caplog.text
    assert last_run(conn)["outcome"] == "failed"
    assert records(conn) == before and listed(conn) == listings


def test_a_refused_entry_that_held_datasets(conn, crawl, data, monkeypatch, caplog):
    assert crawl() == 0
    fail_stat(monkeypatch, data, "groups/x", errno.EACCES)
    caplog.clear()
    assert crawl() == 0
    (warning,) = [
        r.getMessage()
        for r in caplog.records
        if r.levelname == "WARNING" and r.getMessage().startswith("/groups/x: refused")
    ]
    assert "EACCES" in warning and "2 datasets" in warning


def test_opening_again_neither_blocks_nor_follows(tmp_path):
    import threading

    fifo, link = tmp_path / "fifo", tmp_path / "link"
    os.mkfifo(fifo)
    link.symlink_to(tmp_path / "missing")
    got = []
    t = threading.Thread(
        target=lambda: got.append(walk_module._opens(str(fifo))), daemon=True
    )
    t.start()
    t.join(5)
    assert got == [True], "open(2) of a FIFO blocked"
    assert walk_module._opens(str(link)) is False  # ELOOP: not readable


def test_a_subfolders_stat_does_not_answer(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    before = aged(conn)
    fail_stat(monkeypatch, data, "adhoc/x/sub", errno.EIO)
    assert crawl() == 4
    assert unchanged(
        before,
        records(conn),
        "/adhoc/x/a.stand",
        "/adhoc/x/b.stand",
        "/adhoc/x/sub/c.stand",
    )


def test_access_does_not_answer(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    before = aged(conn)
    target = str(data / "adhoc/x/b.stand")
    real_access, real_open = os.access, os.open
    monkeypatch.setattr(
        os, "access", lambda p, m, **k: p != target and real_access(p, m, **k)
    )

    def open_(path, flags, *args, **kwargs):
        if os.fspath(path) == target:
            raise error(errno.EIO, path)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", open_)
    assert crawl() == 4
    assert unchanged(before, records(conn), "/adhoc/x/b.stand")


def test_a_file_whose_type_cannot_be_read(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    before = aged(conn)
    (data / "adhoc/x/sub/d.stand").write_text("ok xd")
    fail_read(monkeypatch, mime, data, "adhoc/x/notes", errno.EIO)
    assert crawl() == 4
    after = records(conn)
    assert unchanged(before, after, "/adhoc/x/a.stand", "/adhoc/x/notes")
    assert oai_identifier("/adhoc/x/sub/d.stand") in after
    assert "/adhoc/x" not in listed(conn)


def test_a_format_that_catches_the_read_error_itself(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    stored = dataset(conn, "/adhoc/pair/scan.head")
    assert stored[0] == "le/pair"
    before = aged(conn)
    fail_read(monkeypatch, formats, data, "adhoc/pair/scan.head", errno.ESTALE)
    assert crawl() == 4
    after = records(conn)
    assert unchanged(before, after, "/adhoc/pair/scan.head")
    assert oai_identifier("/adhoc/pair/scan.raw") not in after


def test_a_file_that_is_gone_during_detection(data, monkeypatch):
    fail_read(monkeypatch, mime, data, "adhoc/x/notes", errno.ENOENT)
    opened = []
    failing = mime.open
    monkeypatch.setattr(
        mime, "open", lambda p, *a, **k: opened.append(p) or failing(p, *a, **k)
    )
    result = walk_module.walk(data / "adhoc/x", [])
    # the fallback is the name's, without a second read (code review 6)
    assert opened.count(str(data / "adhoc/x/notes")) == 1
    (notes,) = [d for d in result.datasets if d.anchor == "/notes"]
    assert notes.type == "application/octet-stream"
    assert [w for w in result.warnings if w[0] == "/notes"] == [
        ("/notes", "cannot read: No such file or directory")
    ]
    assert result.listings["/"].retry


def test_the_walks_result_is_unchanged(data, monkeypatch):
    # records --verbose walks without the stored state: the walk's own result
    fail_read(monkeypatch, mime, data, "adhoc/x/notes", errno.EIO)
    result = walk_module.walk(data / "adhoc/x", [])
    assert any(d.anchor == "/notes" for d in result.datasets)
    assert ("/notes", "cannot read: Input/output error") in result.warnings
    assert not result.unanswered


# Requirement: A kept folder is tried again by the next crawl


def test_no_listing_is_stored(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    assert crawl() == 0
    clean = last_run(conn)["directories_unchanged"]
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    assert crawl() == 4
    assert DM not in listed(conn)
    # none of /, /adhoc, /adhoc/lib, P, and not the folder itself
    assert last_run(conn)["directories_unchanged"] == clean - 5


def test_the_next_crawl_tries_again(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    before = aged(conn)
    real = walk_module._names
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    assert crawl() == 4
    (data / P / "dm" / "c.stand").write_text("ok c")
    monkeypatch.setattr(walk_module, "_names", real)
    assert crawl() == 0
    after = records(conn)
    assert oai_identifier(f"{DM}/c.stand") in after
    assert unchanged(before, after, f"{DM}/a.stand", f"{DM}/b.stand")
    assert last_run(conn)["unanswered"] is None


def test_two_crawls_in_a_row_that_are_not_answered(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    before = aged(conn)
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    assert crawl() == 4
    assert crawl() == 4
    assert unchanged(before, records(conn), f"{DM}/a.stand", f"{DM}/b.stand")


# Requirement: Kept datasets are not extracted again


def test_a_kept_dataset_under_a_new_identity(conn, crawl, data, calls, monkeypatch):
    assert crawl() == 0
    before = aged(conn)
    calls.unlink()
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    assert crawl(installed=B) == 4
    ran = standin.calls(calls)
    assert f"{DM}/a.stand" not in ran and f"{DM}/b.stand" not in ran
    assert "/other/c.stand" in ran  # the others are extracted again under B
    assert unchanged(before, records(conn), f"{DM}/a.stand", f"{DM}/b.stand")


def test_a_kept_dataset_whose_extraction_failed(
    conn, crawl, data, calls, monkeypatch, caplog
):
    (data / P / "dm" / "a.stand").write_text("raise")
    assert crawl() == 0
    calls.unlink()
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    caplog.clear()
    assert crawl() == 4
    assert f"{DM}/a.stand" not in standin.calls(calls)
    assert last_run(conn)["extractions_failed"] == 0
    assert "extraction failed" not in caplog.text


# Requirement: A refused folder that had datasets is named


def test_a_group_that_the_crawler_lost(conn, crawl, data, monkeypatch, caplog):
    assert crawl() == 0
    fail_listing(monkeypatch, data, "groups/x", errno.EACCES)
    caplog.clear()
    assert crawl() == 0
    assert oai_identifier("/groups/x/a.stand") not in records(conn)
    (warning,) = [
        r.getMessage()
        for r in caplog.records
        if r.levelname == "WARNING" and "/groups/x" in r.getMessage()
    ]
    assert "EACCES" in warning and "2 datasets" in warning
    refused = last_run(conn)["refused"]
    assert refused == {
        "total": 1,
        "removed": 2,
        "folders": [{"folder": "/groups/x", "errno": "EACCES", "removed": 2}],
    }


def test_a_folder_that_was_refused_before(conn, crawl, data, monkeypatch, caplog):
    assert crawl() == 0
    fail_listing(monkeypatch, data, "groups/x", errno.EACCES)
    assert crawl() == 0
    caplog.clear()
    assert crawl() == 0
    assert not [
        r
        for r in caplog.records
        if r.levelname == "WARNING" and "/groups/x" in r.getMessage()
    ]
    assert last_run(conn)["refused"] is None


# crawl-runs: The run records the folders the file system did not answer


def test_the_run_records_the_folder(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    assert crawl() == 4
    run = last_run(conn)
    assert run["outcome"] == "finished"
    # the stored `since` is UTC; started_at comes back in the session's time zone
    since = run["started_at"].astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert run["unanswered"] == {
        "total": 1,
        "kept": 2,
        "by_errno": {"ESTALE": 1},
        "folders": [
            {
                "folder": DM,
                "path": DM,
                "errno": "ESTALE",
                "kept": 2,
                "whole": True,
                "since": since,
                "crawls": 1,
            }
        ],
    }


def test_kept_for_two_crawls(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    assert crawl() == 4
    first = last_run(conn)["unanswered"]["folders"][0]
    assert crawl() == 4
    second = last_run(conn)["unanswered"]["folders"][0]
    assert (second["since"], second["crawls"]) == (first["since"], 2)


def test_kept_below_a_folder_kept_before(conn, crawl, data, monkeypatch):
    # A run counts when it kept a folder above, and subtree crawls elsewhere do not reset it (code review 4)
    assert crawl() == 0
    real = walk_module._names
    fail_listing(monkeypatch, data, P, errno.EIO)
    assert crawl() == 4
    first = last_run(conn)["unanswered"]["folders"][0]
    monkeypatch.setattr(walk_module, "_names", real)
    for _ in range(2):
        assert crawl("--path", "other") == 0
    fail_listing(monkeypatch, data, P + "/dm", errno.EIO)
    assert crawl() == 4
    (folder,) = last_run(conn)["unanswered"]["folders"]
    assert (folder["folder"], folder["since"], folder["crawls"]) == (
        DM,
        first["since"],
        2,
    )


def test_a_file_in_recognition_in_the_run(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    fail_read(monkeypatch, mime, data, "adhoc/x/notes", errno.EIO)
    assert crawl() == 4
    (folder,) = last_run(conn)["unanswered"]["folders"]
    assert (folder["folder"], folder["path"], folder["errno"]) == (
        "/adhoc/x",
        "/adhoc/x/notes",
        "EIO",
    )


def many(data, monkeypatch, n=150):
    for i in range(n):
        (data / "many" / f"f{i:03}").mkdir(parents=True)
        (data / "many" / f"f{i:03}" / "a.stand").write_text("ok")
    fail_listing(
        monkeypatch,
        data,
        "many/f000",
        errno.EIO,
        *(f"many/f{i:03}" for i in range(1, n)),
    )


def test_the_same_record_whatever_the_threads(conn, crawl, data, monkeypatch):
    many(data, monkeypatch)
    assert crawl(threads=1) == 4
    one = last_run(conn)["unanswered"]
    assert crawl(threads=16) == 4
    sixteen = last_run(conn)["unanswered"]

    def without_history(u):
        return {
            **u,
            "folders": [
                {k: v for k, v in f.items() if k not in ("since", "crawls")}
                for f in u["folders"]
            ],
        }

    assert without_history(one) == without_history(sixteen)
    assert one["total"] == 150 and len(one["folders"]) == 100
    assert one["folders"][-1]["folder"] == "/many/f099"


def test_not_visible_is_no_error(conn, crawl, data, monkeypatch):
    fail_listing(monkeypatch, data, "groups/x", errno.EACCES)
    assert crawl() == 0
    run = last_run(conn)
    assert (run["unanswered"], run["refused"]) == (None, None)


# crawl-runs: A crawl that finished with errors says so and exits with status 4


def test_the_error_line_and_the_status(conn, crawl, data, monkeypatch, caplog):
    assert crawl() == 0
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    caplog.clear()
    assert crawl() == 4
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    (line,) = [e for e in errors if e.startswith(f"{DM}:")]
    assert "ESTALE" in line and "2 datasets kept" in line
    assert re.search(r"finished with errors: .*\(ESTALE 1\)", errors[-1])


def test_more_than_100_folders(conn, crawl, data, monkeypatch, caplog):
    many(data, monkeypatch)
    caplog.clear()
    assert crawl() == 4
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert len([e for e in errors if e.startswith("/many/f")]) == 100
    assert any("50 more folders" in e and "EIO 50" in e for e in errors)


def test_a_subtree_crawl_with_errors(conn, crawl, data, monkeypatch):
    assert crawl() == 0
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    assert crawl("--path", P) == 4
    run = last_run(conn)
    assert run["outcome"] == "finished" and run["unanswered"]["total"] == 1


# crawl-runs: The runs command shows a crawl that finished with errors


def three_folders(data, monkeypatch):
    for rel in ("adhoc/a", "adhoc/b", "c/d"):
        (data / rel).mkdir(parents=True)
        (data / rel / "a.stand").write_text("ok")
    real = walk_module._names
    codes = {
        str(data / "adhoc/a"): errno.EIO,
        str(data / "adhoc/b"): errno.EIO,
        str(data / "c/d"): errno.ESTALE,
    }

    def names(dirpath):
        if dirpath in codes:
            raise error(codes[dirpath], dirpath)
        return real(dirpath)

    monkeypatch.setattr(walk_module, "_names", names)


def test_the_report_line(conn, env, crawl, data, monkeypatch):
    three_folders(data, monkeypatch)
    assert crawl() == 4
    run = shell(f"{CRAWLER} runs | head -1", env)
    (line,) = run.stdout.splitlines()
    assert "  finished with errors  " in line
    assert " datasets, " in line and " records changed" in line
    assert (
        "did not answer: 3 folders (EIO 2, ESTALE 1): /adhoc/a, /adhoc/b, /c/d" in line
    )


def test_many_folders_on_the_line(conn, env, crawl, data, monkeypatch):
    many(data, monkeypatch)
    assert crawl() == 4
    (line,) = shell(f"{CRAWLER} runs | head -1", env).stdout.splitlines()
    assert "/many/f000, /many/f001, /many/f002 and 147 more" in line


def test_aligned_columns(conn, env, crawl, data, monkeypatch):
    assert crawl() == 0
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    assert crawl() == 4
    errors, finished = shell(f"{CRAWLER} runs", env).stdout.splitlines()
    end = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
    assert [m.start() for m in end.finditer(errors)][1] == [
        m.start() for m in end.finditer(finished)
    ][1]


def test_following_a_crawl_that_finishes_with_errors(
    conn, env, crawl, data, monkeypatch, capsys
):
    assert crawl() == 0
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    assert crawl() == 4
    capsys.readouterr()
    assert cli.main(["runs", "--follow"]) == 4
    assert "finished with errors" in capsys.readouterr().out.splitlines()[-1]


# crawl-runs: A crawl that finished with errors counts as finished


def test_the_timer_counts_it_as_finished(conn, crawl, data, monkeypatch):
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    assert crawl() == 4
    finished = last_finished(conn)
    assert finished is not None
    assert not overdue(finished, finished + timedelta(hours=1))


def test_a_subtree_crawl_after_a_crawl_with_errors(
    conn, crawl, data, monkeypatch, tmp_path, caplog
):
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    assert crawl() == 4
    other = tmp_path / "other.toml"
    other.write_text('[crawl]\nexclude = [".snapshot/"]\n')
    assert crawl("--config", str(other), "--path", P) == 2
    assert "differs from that of the last crawl" in caplog.text


# harvest-trigger: A crawl that finished with errors starts the harvest


def test_the_harvest_starts_after_errors(conn, env, crawl, data, monkeypatch, airflow):
    url, requests = airflow
    for name, value in crawl_env(env, url).items():
        monkeypatch.setenv(name, value)
    fail_listing(monkeypatch, data, P + "/dm", errno.ESTALE)
    assert crawl() == 4
    assert any(path.endswith("/dagRuns") for path, *_ in requests)


def test_errors_and_a_harvest_that_cannot_be_started(
    conn, env, crawl, data, monkeypatch, airflow, caplog
):
    url, _ = airflow
    for name, value in crawl_env(env, url, password="wrong").items():
        monkeypatch.setenv(name, value)
    fail_listing(monkeypatch, data, P + "/dm", errno.EIO)
    assert crawl() == 4
    assert "the harvest could not be started" in caplog.text


def test_a_refused_folder_alone(conn, env, crawl, data, monkeypatch, airflow):
    url, requests = airflow
    assert crawl() == 0
    for name, value in crawl_env(env, url).items():
        monkeypatch.setenv(name, value)
    fail_listing(monkeypatch, data, "groups/x", errno.EACCES)
    assert crawl() == 0
    assert any(path.endswith("/dagRuns") for path, *_ in requests)
