"""Running extractors after recognition (the `extraction` spec), with the stand-in formats of `standin.py`."""

import os
import re
import sys

import pytest
import standin
from conftest import interrupted
from modama_crawler import cli, extraction, identity, mime, selection, store
from modama_crawler.cli import crawl_tree
from modama_crawler.records import build
from modama_crawler.store import end_run, recent_runs, start_run
from modama_crawler.walk import walk


def extract(root, calls, **kwargs):
    """Walk and extract, as a crawl does before storing; returns the result, the report and the datasets by anchor."""
    formats = standin.collection(calls).formats
    result = walk(root, formats)
    report = extraction.extract(result, formats, str(root), identity="h", **kwargs)
    return result, report, {d.anchor: d for d in result.datasets}


def description(dataset) -> str:
    (text,) = build(dataset, {})[1]["description"]
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


INTERRUPTED_EXTRACTION = """
import sys, threading, time
from pathlib import Path
from modama_crawler import extraction, mimedb, selection
from modama_crawler.walk import walk

root, calls, tests, mime = sys.argv[1:]
sys.path.insert(0, tests)
import standin

def ready():
    while len(standin.calls(calls)) < 2:  # one extractor done, one hanging
        time.sleep(0.05)
    print("ready", flush=True)

mimedb.build(selection.discover().values(), Path(mime))
formats = standin.collection(calls).formats
threading.Thread(target=ready, daemon=True).start()
try:
    extraction.extract(walk(root, formats), formats, root, identity="h", workers=2)
except KeyboardInterrupt:
    sys.exit(130)
"""


def test_ctrl_c_during_extraction_is_quiet(tmp_path):
    # Graceful exit on Ctrl-C: no traceback from the extracting processes either
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.stand").write_text("ok alpha")
    (root / "b.stand").write_text("hang")
    (tmp_path / "mime").mkdir()
    status, stderr = interrupted(
        INTERRUPTED_EXTRACTION,
        str(root),
        str(tmp_path / "calls"),
        os.path.dirname(__file__),
        str(tmp_path / "mime"),
    )
    assert (status, stderr) == (130, "")


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


def installation(rosettasciio="0.15.0", dm="a", records="b") -> tuple[str, dict]:
    """An extractor identity and its ingredients, standing in for an installation (identity.ingredients)."""
    ingredients = {
        "python": "cpython 3.14.0",
        "distributions": {"modama-crawler": "0.0.1.dev0", "rosettasciio": rosettasciio},
        "source": {
            "modama_formats_em/dm/__init__.py": dm,
            "modama_crawler/records.py": records,
        },
    }
    return identity.digest(ingredients), ingredients


A = installation()


def crawl(conn, root, calls, rules="r1", installed=A, variant="1"):
    """One crawl of root into the database as `modama-crawler crawl` does it; returns the result and the report.

    `installed` is the extractor identity and its ingredients (None: not
    stored with the run, as for a label from before identities); `variant`
    stands in for the installed code of `Stand` (standin.py), `Other`'s stays.
    """
    formats = standin.collection(calls).formats
    formats[0].variant = variant
    run_id = start_run(conn, str(root))
    result, report, _ = crawl_tree(
        conn, run_id, str(root), formats, selection.Config(), rules, installed=installed
    )
    end_run(
        conn,
        run_id,
        "finished",
        directories=0,
        files=0,
        extraction=report,
        ingredients=installed[1],
    )
    return result, report


def extracted(conn) -> dict[str, dict]:
    return dict(conn.execute("SELECT anchor, extracted FROM datasets").fetchall())


def a_day_back(conn) -> None:
    """Records' datestamps a day back, so that a datestamp written by the next crawl is a new one."""
    conn.execute("UPDATE records SET datestamp = datestamp - interval '1 day'")
    conn.commit()


def changed_records(first: dict, second: dict) -> list[str]:
    return sorted(i.rsplit(":", 1)[1] for i in first if first[i] != second[i])


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


def test_a_stored_record_names_its_format_for_people(conn, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.stand").write_text("ok a")
    crawl(conn, root, tmp_path / "calls")
    ((_, metadata),) = records(conn).values()
    assert metadata["subject"] == ["Stand-in format", "stand technique"]


def test_a_second_crawl_of_an_unchanged_tree(conn, deep, tmp_path, opened):
    calls = tmp_path / "calls"
    crawl(conn, deep, calls)
    first = records(conn)
    assert len(standin.calls(calls)) == 5
    opened[:] = ["<watching>"]
    result, report = crawl(conn, deep, calls)
    seen = list(opened)
    opened.clear()
    # No file of the tree opened in this process; in a worker only the spot check's sample
    assert [p for p in seen if p.startswith(str(deep))] == []
    assert sorted(standin.calls(calls)[5:]) == sorted(standin.calls(calls)[:5])
    assert (report.run, report.reused, report.failed) == (0, 5, 0)
    assert report.lines()[-1].endswith("t/stand 5 of 5 as stored")
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
    # the changed one, and the other four as the spot check's sample
    assert sorted(standin.calls(calls)[5:]) == sorted(standin.calls(calls)[:5])
    assert (report.run, report.reused) == (1, 4)
    assert report.lines()[-1].endswith("t/stand 4 of 4 as stored")
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


def test_a_failed_file_in_an_unchanged_directory(conn, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "broken.stand").write_text("raise")
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    result, _ = crawl(conn, root, calls)
    assert result.unchanged == 1  # taken over without recognising
    assert standin.calls(calls) == ["/broken.stand", "/broken.stand"]


# "Extraction follows the identified extractor"


def test_a_changed_source_file_of_a_format_package(conn, deep, tmp_path):
    calls = tmp_path / "calls"
    (deep / "a" / "other.other").write_text("ok other")  # another extractor's dataset
    (deep / "a" / "b" / "versioned.stand").write_text("versioned v")
    crawl(conn, deep, calls)
    a_day_back(conn)
    first = records(conn)
    changed = installation(dm="edited")
    result, report = crawl(conn, deep, calls, installed=changed, variant="2")
    # every dataset of every format with an extractor
    assert result.unchanged == 4 and report.run == 7
    assert sorted(standin.calls(calls)[7:]) == sorted(standin.calls(calls)[:7])
    # Only the record whose content changed has a new datestamp
    second = records(conn)
    assert changed_records(first, second) == ["/a/b/versioned.stand"]
    key = next(i for i in first if i.endswith(":/a/b/versioned.stand"))
    assert second[key][0] > first[key][0]
    assert {d.extraction.identity for d in result.datasets if d.extraction} == {
        changed[0]
    }


def test_a_change_that_alters_no_output(conn, deep, tmp_path):
    calls = tmp_path / "calls"
    crawl(conn, deep, calls)
    a_day_back(conn)
    first = records(conn)
    _, report = crawl(conn, deep, calls, installed=installation(dm="a comment"))
    assert report.run == 5
    assert records(conn) == first


def test_an_upgraded_dependency(conn, deep, tmp_path):
    calls = tmp_path / "calls"
    crawl(conn, deep, calls)
    _, report = crawl(conn, deep, calls, installed=installation(rosettasciio="0.16.0"))
    assert (report.run, report.reused) == (5, 0)


def test_back_to_an_earlier_installation(conn, deep, tmp_path):
    calls = tmp_path / "calls"
    (deep / "a" / "b" / "versioned.stand").write_text("versioned v")
    crawl(conn, deep, calls)
    first = {i: metadata for i, (_, metadata) in records(conn).items()}
    crawl(conn, deep, calls, installed=installation(dm="experiment"), variant="2")
    assert {i: m for i, (_, m) in records(conn).items()} != first
    _, report = crawl(conn, deep, calls)
    assert report.run == 6
    assert {i: m for i, (_, m) in records(conn).items()} == first


def test_a_file_whose_reading_failed_is_tried_again_on_every_crawl(conn, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "broken.stand").write_text("raise")
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    result, report = crawl(conn, root, calls)
    assert standin.calls(calls) == ["/broken.stand", "/broken.stand"]
    assert (report.run, report.reused, report.failed) == (1, 0, 1)
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
def test_other_failures_are_retried(conn, tmp_path, command):
    # Not scenarios of their own: every failure is tried again, whatever its cause (D9)
    root = tmp_path / "data"
    root.mkdir()
    (root / "x.stand").write_text(command)
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    _, report = crawl(conn, root, calls)
    assert standin.calls(calls) == ["/x.stand", "/x.stand"]
    assert (report.run, report.reused, report.failed) == (1, 0, 1)


def test_a_failure_under_a_lowered_memory_limit(conn, tmp_path, monkeypatch):
    # Also "The crawl reports failures tried again"
    root = tmp_path / "data"
    root.mkdir()
    (root / "big.stand").write_text("eat 1024")
    (root / "small.stand").write_text("ok small")
    calls = tmp_path / "calls"
    monkeypatch.setenv("MODAMA_CRAWLER_EXTRACT_MEMORY", "768")  # MiB
    first, _ = crawl(conn, root, calls)
    ((_, text),) = first.all_warnings()
    assert "MemoryError" in text
    monkeypatch.setenv("MODAMA_CRAWLER_EXTRACT_MEMORY", "4096")
    result, report = crawl(conn, root, calls)
    assert result.all_warnings() == []
    assert (report.run, report.reused, report.failed) == (1, 1, 0)
    assert "t/stand: 1 tried again after a failure, 1 now succeeds" in report.lines()


# "The crawl reports re-extraction and its cause"


def test_a_dependency_upgrade_that_changes_output(conn, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.stand").write_text("versioned a")
    (root / "b.stand").write_text("ok b")
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    _, report = crawl(
        conn, root, calls, installed=installation(rosettasciio="0.16.0"), variant="2"
    )
    assert (
        "t/stand: 2 extracted again for a new identity (rosettasciio 0.15.0 -> 0.16.0), "
        "1 result changed"
    ) in report.lines()
    (latest,) = recent_runs(conn, 1)
    assert "extracted again: t/stand 2 (1 result changed)" in cli._run_line(latest)


def test_a_refactoring_that_changes_no_output(conn, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.stand").write_text("ok a")
    (root / "b.stand").write_text("ok b")
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    _, report = crawl(conn, root, calls, installed=installation(dm="a comment"))
    assert (
        "t/stand: 2 extracted again for a new identity "
        "(source of modama_formats_em.dm changed), 0 results changed"
    ) in report.lines()


def test_a_change_in_building_records_only(conn, tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.stand").write_text("ok a")
    (root / "b.stand").write_text("ok b")
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    a_day_back(conn)
    first = records(conn)

    def fixed_template(d, names):
        identifier, metadata = build(d, names)
        return identifier, {**metadata, "description": ["a fixed typo"]}

    monkeypatch.setattr(store, "build", fixed_template)
    _, report = crawl(conn, root, calls, installed=installation(records="fixed"))
    assert (
        "t/stand: 2 extracted again for a new identity "
        "(source of modama_crawler.records changed), 0 results changed"
    ) in report.lines()
    assert changed_records(first, records(conn)) == ["/a.stand", "/b.stand"]


def test_an_identity_from_before_this_change(conn, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.stand").write_text("ok a")
    (root / "b.stand").write_text("ok b")
    calls = tmp_path / "calls"
    crawl(conn, root, calls, installed=("4", None))  # a label, no ingredients
    _, report = crawl(conn, root, calls)
    assert (
        't/stand: 2 extracted again for a new identity (earlier identity "4", '
        "ingredients unknown), 0 results changed"
    ) in report.lines()


# "Each crawl spot-checks a sample of what it reuses"


def test_everything_as_stored(conn, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.stand").write_text("ok a")
    (root / "b.stand").write_text("ok b")
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    a_day_back(conn)
    first = records(conn)
    _, report = crawl(conn, root, calls)
    assert re.fullmatch(
        r"spot check \(seed [0-9a-f]{16}\): t/stand 2 of 2 as stored",
        report.lines()[-1],
    )
    assert records(conn) == first
    (latest,) = recent_runs(conn, 1)
    assert latest.spot_check["seed"] == f"{report.spot.seed:016x}"


def test_the_same_seed_gives_the_same_sample():
    reused = {"em/dm4": [f"/x/{i:02}.dm4" for i in range(30)], "em/k2is": ["/k.gtg"]}
    one = extraction.sample(0x9F2C41D07A3BE815, reused)
    assert one == extraction.sample(0x9F2C41D07A3BE815, reused)
    assert len(one["em/dm4"]) == 20 and one["em/k2is"] == ["/k.gtg"]
    assert one != extraction.sample(0x1, reused)


def test_nothing_reused(conn, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.stand").write_text("ok a")
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    _, report = crawl(conn, root, calls, installed=installation(dm="edited"))
    assert report.lines()[-1] == "spot check: nothing reused"


# "A spot-check difference is reported, not spread"


def test_a_difference_the_identity_missed(conn, tmp_path, caplog):
    root = tmp_path / "data"
    root.mkdir()
    for i in range(30):
        (root / f"{i:02}.stand").write_text(f"ok w{i:02}")
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    original = extracted(conn)
    # standing in for an influence outside the identity
    conn.execute(
        "UPDATE datasets SET extracted = jsonb_set(extracted, '{values,word}', '\"altered\"')"
    )
    conn.commit()
    _, report = crawl(conn, root, calls)
    line = report.lines()[-1]
    assert ": t/stand 0 of 20 as stored; differs: " in line
    assert line.count("(values: word)") == 5 and line.endswith(", and 15 more")
    after = extracted(conn)
    checked = [a for a in after if after[a] == original[a]]
    assert len(checked) == 20  # the new results replace the stored ones (192)
    assert all(
        after[a]["values"]["word"] == "altered" for a in after if a not in checked
    )
    assert len(standin.calls(calls)) == 50  # the other 10 not extracted
    (latest,) = recent_runs(conn, 1)
    assert "spot check: 20 differ" in cli._run_line(latest)
    assert "values.word: stored 'altered', now 'w" in caplog.text


def test_a_new_failure_does_not_replace_a_stored_success(conn, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.stand").write_text("ok a")
    calls = tmp_path / "calls"
    crawl(conn, root, calls)
    first, stored = records(conn), extracted(conn)
    result, report = crawl(conn, root, calls, variant="raise")
    assert report.lines()[-1].endswith(
        "t/stand 0 of 1 as stored; differs: /a.stand "
        "(now fails: ValueError('the reader now fails'))"
    )
    assert (records(conn), extracted(conn)) == (first, stored)
    assert result.all_warnings() == []


def _unreadable(path, **kw):
    raise PermissionError(13, "Permission denied", path)


def test_a_directory_whose_recognition_met_the_environment_is_recognised_again(
    conn, tmp_path, monkeypatch
):
    root = tmp_path / "data"
    root.mkdir()
    (root / "x.stand").write_text("ok x")
    calls = tmp_path / "calls"
    with monkeypatch.context() as m:
        m.setattr(mime, "detect_with_tie", _unreadable)
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
