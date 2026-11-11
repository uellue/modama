"""Running extractors after recognition (the `extraction` spec), with the stand-in formats of `standin.py`."""

import os
import sys

import pytest
import standin
from modama_crawler import extraction, mime, selection
from modama_crawler import walk as walk_module
from modama_crawler.cli import crawl_tree
from modama_crawler.records import build
from modama_crawler.store import start_run
from modama_crawler.walk import walk


def extract(root, calls, **kwargs):
    """Walk and extract, as a crawl does before storing; returns the result, the report and the datasets by anchor."""
    formats = standin.collection(calls).formats
    result = walk(root, formats)
    report = extraction.extract(result, formats, str(root), **kwargs)
    return result, report, {d.anchor: d for d in result.datasets}


def description(dataset) -> str:
    (text,) = build(dataset)[1]["description"]
    return text


def test_a_format_with_an_extractor(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.stand").write_text("ok alpha")
    (root / "notes.txt").write_text("hello")
    result, report, by_anchor = extract(root, tmp_path / "calls")
    assert by_anchor["/a.stand"].extraction.extracted.values == {"word": "alpha"}
    assert description(by_anchor["/a.stand"]).startswith("word alpha")
    assert by_anchor["/notes.txt"].extraction is None
    assert "word" not in description(by_anchor["/notes.txt"])
    assert (report.run, report.reused, report.failed) == (1, 0, 0)
    assert result.all_warnings() == []


def test_an_extractor_raises_on_a_broken_file(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "broken.stand").write_text("raise")
    result, report, by_anchor = extract(root, tmp_path / "calls")
    broken = by_anchor["/broken.stand"]
    assert broken.extraction.error and broken.extraction.extracted is None
    assert description(broken).startswith("application/x.stand, 1 file, 5 B, in /")
    ((path, text),) = result.all_warnings()
    assert path == "/broken.stand" and "truncated file" in text
    assert report.failed == 1


def test_an_extractor_kills_its_process(tmp_path):
    # Not a scenario of its own; the requirement names a crashed process. The
    # other datasets in flight at the time are extracted all the same.
    root = tmp_path / "data"
    root.mkdir()
    (root / "crash.stand").write_text("kill")
    for name in "abc":
        (root / f"{name}.stand").write_text(f"ok {name}")
    result, report, by_anchor = extract(root, tmp_path / "calls", workers=2)
    assert [path for path, _ in result.all_warnings()] == ["/crash.stand"]
    assert "process" in result.all_warnings()[0][1]
    for name in "abc":
        assert by_anchor[f"/{name}.stand"].extraction.extracted.values == {"word": name}
    assert (report.run, report.failed) == (4, 1)


def test_an_extractor_hangs(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "slow.stand").write_text("hang")
    (root / "quick.stand").write_text("ok quick")
    # The quick task's time includes starting its process: a margin for a loaded runner
    result, _, by_anchor = extract(root, tmp_path / "calls", time_limit=10.0)
    ((path, text),) = result.all_warnings()
    assert path == "/slow.stand" and "timed out" in text
    assert description(by_anchor["/slow.stand"]).startswith("application/x.stand")
    assert by_anchor["/quick.stand"].extraction.extracted is not None


def test_an_extractor_runs_out_of_memory(tmp_path):
    # Not a scenario of its own: the memory budget per worker (review 2026-11-11, 5)
    root = tmp_path / "data"
    root.mkdir()
    (root / "greedy.stand").write_text("eat")
    (root / "modest.stand").write_text("ok modest")
    result, _, by_anchor = extract(root, tmp_path / "calls", memory=1 << 30)
    ((path, text),) = result.all_warnings()
    assert path == "/greedy.stand" and "MemoryError" in text
    assert by_anchor["/modest.stand"].extraction.extracted is not None


def test_report_after_a_crawl(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.stand").write_text("ok a")
    (root / "b.stand").write_text("raise")
    _, report, _ = extract(root, tmp_path / "calls")
    assert (report.run, report.reused, report.failed) == (2, 0, 1)
    assert str(report).startswith("extraction: 2 run, 0 reused, 1 failed")
    assert "t/stand " in str(report) and " s" in str(report)


# Crawls into the database: unchanged directories and the extractor's identity (D3)

# Files opened by this process while the `opened` fixture watches
OPENED: list[str] = []


def _audit(event, args):
    if event == "open" and OPENED and isinstance(args[0], str | bytes):
        OPENED.append(os.fsdecode(args[0]))


sys.addaudithook(_audit)  # cannot be removed; costs a comparison per event


@pytest.fixture
def opened():
    """Paths this process opens from when the list is reset to ["<watching>"] (the audit hook's "open" event)."""
    yield OPENED
    OPENED.clear()


def crawl(conn, root, calls, rules="r1", version="1"):
    """One crawl of root into the database as `modama-crawler crawl` does it; returns the result and the report.

    `version` is the extractor version of `Stand`; `Other`'s stays.
    """
    formats = standin.collection(calls).formats
    formats[0].extractor_version = version
    run_id = start_run(conn, str(root))
    result, report, _ = crawl_tree(
        conn, run_id, str(root), formats, selection.Config(), rules
    )
    return result, report


def records(conn) -> dict[str, tuple]:
    return {
        identifier: (datestamp, metadata)
        for identifier, datestamp, metadata in conn.execute(
            "SELECT identifier, datestamp, metadata FROM records"
        )
    }


@pytest.fixture
def deep(tmp_path):
    """A tree with stand files at four depths, two of them side by side three levels down."""
    root = tmp_path / "data"
    (root / "a" / "b" / "c").mkdir(parents=True)
    (root / "top.stand").write_text("ok top")
    (root / "a" / "one.stand").write_text("ok one")
    (root / "a" / "b" / "two.stand").write_text("ok two")
    (root / "a" / "b" / "c" / "three.stand").write_text("ok three")
    (root / "a" / "b" / "c" / "sibling.stand").write_text("ok sibling")
    (root / "a" / "b" / "c" / "notes.txt").write_text("hello")
    return root


def test_a_second_crawl_of_an_unchanged_tree(conn, deep, tmp_path, opened):
    calls = tmp_path / "calls"
    crawl(conn, deep, calls)
    first = records(conn)
    assert len(standin.calls(calls)) == 5
    opened[:] = ["<watching>"]
    result, report = crawl(conn, deep, calls)
    seen = list(opened)
    opened.clear()
    # No file of the tree opened in this process, no extractor run in a worker
    assert [p for p in seen if p.startswith(str(deep))] == []
    assert len(standin.calls(calls)) == 5
    assert (report.run, report.reused, report.failed) == (0, 5, 0)
    assert result.unchanged == 4  # /, /a, /a/b, /a/b/c
    assert records(conn) == first


def test_the_audit_hook_sees_the_walk_open_files(deep, tmp_path, opened):
    # The check above would pass vacuously if the hook saw nothing
    opened[:] = ["<watching>"]
    walk(deep, standin.collection(tmp_path / "calls").formats)
    # *.stand matches no glob, so MIME detection reads its content
    assert str(deep / "a" / "b" / "c" / "three.stand") in opened


def test_a_change_deep_in_the_tree(conn, deep, tmp_path):
    calls = tmp_path / "calls"
    crawl(conn, deep, calls)
    first = records(conn)
    (deep / "a" / "b" / "c" / "three.stand").write_text("ok three, longer")
    result, report = crawl(conn, deep, calls)
    assert result.unchanged == 0  # its directory and every one above it again
    assert standin.calls(calls)[5:] == ["/a/b/c/three.stand"]
    assert (report.run, report.reused) == (1, 4)
    second = records(conn)
    changed = [i.rsplit(":", 1)[1] for i in first if first[i] != second[i]]
    assert changed == ["/a/b/c/three.stand"]


def test_a_rewrite_with_the_same_size_and_mtime(conn, tmp_path):
    # Not a scenario of its own: the ctime is part of the listing (review 2026-11-11, 7)
    root = tmp_path / "data"
    (root / "a").mkdir(parents=True)
    f = root / "a" / "x.stand"
    f.write_text("ok aaa")
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    st, dst = os.stat(f), os.stat(root / "a")
    f.write_text("ok bbb")
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))
    os.utime(root / "a", ns=(dst.st_atime_ns, dst.st_mtime_ns))
    result, _ = crawl(conn, root, calls)
    assert standin.calls(calls) == ["/a/x.stand", "/a/x.stand"]
    (d,) = result.datasets
    assert d.extraction.extracted.values == {"word": "bbb"}


def test_a_new_extractor_version(conn, deep, tmp_path):
    calls = tmp_path / "calls"
    (deep / "a" / "other.other").write_text("ok other")  # another extractor's dataset
    (deep / "a" / "b" / "versioned.stand").write_text("versioned v")
    crawl(conn, deep, calls)
    # A day back, so that a datestamp written by the next crawl is a new one
    conn.execute("UPDATE records SET datestamp = datestamp - interval '1 day'")
    conn.commit()
    first = records(conn)
    result, report = crawl(conn, deep, calls, version="2")
    assert result.unchanged == 4 and report.run == 6
    again = standin.calls(calls)[7:]
    assert sorted(again) == sorted(c for c in standin.calls(calls)[:7] if "stand" in c)
    # Only the record whose content changed has a new datestamp
    second = records(conn)
    changed = [i.rsplit(":", 1)[1] for i in first if first[i] != second[i]]
    assert changed == ["/a/b/versioned.stand"]
    key = next(i for i in first if i.endswith(":/a/b/versioned.stand"))
    assert second[key][0] > first[key][0]
    versions = {d.format: d.extraction.version for d in result.datasets if d.extraction}
    assert versions == {"t/stand": "2", "t/other": "1"}


def test_a_file_whose_reading_failed_stays_failed_until_something_changes(
    conn, tmp_path
):
    root = tmp_path / "data"
    root.mkdir()
    (root / "broken.stand").write_text("raise")
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    result, report = crawl(conn, root, calls)
    assert standin.calls(calls) == ["/broken.stand"]
    assert (report.run, report.reused, report.failed) == (0, 1, 1)
    ((path, text),) = result.all_warnings()
    assert path == "/broken.stand" and "truncated file" in text


def test_a_timeout_is_retried_on_the_next_crawl(conn, tmp_path, monkeypatch):
    monkeypatch.setitem(extraction.extract.__kwdefaults__, "time_limit", 2.0)
    root = tmp_path / "data"
    root.mkdir()
    (root / "slow.stand").write_text("hang")
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    result, report = crawl(conn, root, calls)
    assert standin.calls(calls) == ["/slow.stand", "/slow.stand"]
    assert (report.run, report.reused, report.failed) == (1, 0, 1)
    ((_, text),) = result.all_warnings()
    assert "timed out" in text


@pytest.mark.parametrize("command", ["kill", "oserror", "import"])
def test_other_failures_of_the_environment_are_retried(conn, tmp_path, command):
    # Not scenarios of their own: like the timeout, they say nothing about the file
    root = tmp_path / "data"
    root.mkdir()
    (root / "x.stand").write_text(command)
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    _, report = crawl(conn, root, calls)
    assert standin.calls(calls) == ["/x.stand", "/x.stand"]
    assert (report.run, report.reused, report.failed) == (1, 0, 1)


def _unreadable(path):
    raise PermissionError(13, "Permission denied", path)


@pytest.mark.parametrize("cause", ["cannot read", "time limit"])
def test_a_directory_whose_recognition_met_the_environment_is_recognised_again(
    conn, tmp_path, monkeypatch, cause
):
    root = tmp_path / "data"
    root.mkdir()
    (root / "x.stand").write_text("ok x")
    calls = tmp_path / "calls"
    with monkeypatch.context() as m:
        if cause == "cannot read":
            m.setattr(mime, "detect_with_tie", _unreadable)
        else:
            m.setattr(walk_module, "TIME_LIMIT", -1.0)
        first, _ = crawl(conn, root, calls)
    assert first.all_warnings() and first.listings["/"].retry
    second, _ = crawl(conn, root, calls)
    assert second.unchanged == 0
    assert second.all_warnings() == []
    assert [d.format for d in second.datasets] == ["t/stand"]


def test_an_unlistable_directory_leaves_its_ancestors_unchanged(conn, tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root lists every directory")
    root = tmp_path / "data"
    (root / "a" / "private").mkdir(parents=True)
    (root / "a" / "x.stand").write_text("ok x")
    (root / "top.stand").write_text("ok top")
    (root / "b").mkdir()
    os.chmod(root / "a" / "private", 0)
    calls = tmp_path / "calls"
    try:
        crawl(conn, root, calls)
        result, _ = crawl(conn, root, calls)
        assert result.unchanged == 3  # /, /a, /b
        assert result.skipped == [
            ("/a/private", "cannot list directory: Permission denied")
        ]
        # Listable again: its parent and the root are recognised again
        os.chmod(root / "a" / "private", 0o755)
        result, _ = crawl(conn, root, calls)
        assert result.unchanged == 1  # /b
    finally:
        os.chmod(root / "a" / "private", 0o755)


@pytest.mark.parametrize("command", ["nan", "nul", "big"])
def test_values_the_database_rejects(conn, tmp_path, command):
    # Not a scenario of its own: an extractor's output is untrusted (R23, review 2026-11-11, 1)
    root = tmp_path / "data"
    root.mkdir()
    (root / "x.stand").write_text(command)
    result, _ = crawl(conn, root, tmp_path / "calls")
    ((stored,),) = conn.execute("SELECT extracted FROM datasets").fetchall()
    x = result.datasets[0].extraction
    if command == "nan":
        assert stored is None and "Out of range float values" in x.error
        assert not x.retry  # the file's own: reused
    elif command == "nul":
        assert x.error is None
        assert stored == {
            "summary": ["detector� A"],
            "subjects": ["�"],
            "values": {"a�": "b�"},
        }
    else:
        assert len(stored["summary"][0]) == extraction.MAX_STRING
        assert len(stored["values"]["list"]) == extraction.MAX_ITEMS


def test_walk_and_extraction_leave_no_transaction_open(conn, tmp_path, monkeypatch):
    # Not a scenario of its own: the main connection idled in a transaction for hours (review 2026-11-11, 8)
    root = tmp_path / "data"
    (root / "a").mkdir(parents=True)
    (root / "a" / "x.stand").write_text("ok x")
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    (root / "a" / "y.stand").write_text("ok y")
    states = []
    real_run = extraction._run

    def run(*args, **kwargs):
        states.append(conn.info.transaction_status.name)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(extraction, "_run", run)
    formats = standin.collection(calls).formats
    run_id = start_run(conn, str(root))
    crawl_tree(
        conn,
        run_id,
        str(root),
        formats,
        selection.Config(),
        "r1",
        progress=lambda *_: states.append(conn.info.transaction_status.name),
    )
    assert set(states) == {"IDLE"}
    assert not conn.autocommit


def test_a_rule_change_recognises_again_and_reuses_extractions(conn, deep, tmp_path):
    # Not a scenario of its own: the rule set is part of "unchanged" (D3)
    calls = tmp_path / "calls"
    crawl(conn, deep, calls)
    result, report = crawl(conn, deep, calls, rules="r2")
    assert result.unchanged == 0
    assert (report.run, report.reused) == (0, 5)
