"""Inspecting files of a folder in worker processes (the `recognition` spec, "A format may inspect files of its folder in worker processes"; change hdf5-links, design D5).

The functions handed to the workers are module-level, so that a spawned
process can import them. What happens inside a worker (the counting file
object, the outcome of a read error) is tested in this process, since a
monkeypatch does not reach a spawned worker; the processes are tested for
what only they show (a hang, a crash, one pool).
"""

import errno
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from modama_crawler import extraction, files, inspection
from modama_crawler.formats import (
    NOT_INSPECTED,
    Collection,
    Dataset,
    Directory,
    Entry,
    Format,
)
from modama_crawler.inspection import Inspector
from modama_crawler.walk import walk


def entry_of(path, mime="application/octet-stream"):
    st = os.stat(path)
    name = os.path.basename(path)
    return Entry(name, str(path), f"/{name}", "file", st.st_size, 1, 1, 7, mime)


def directory(tmp_path, entries):
    d = Directory("/", str(tmp_path), list(entries), [], "post", uid=1, mtime=0.5)
    d._format = "t/inspect"
    d._limit = 1024  # the format's read limit per file, as a format call sets it
    return d


# Run in the workers


def ends_and_start(f):
    f.seek(-100, os.SEEK_END)
    end = f.read(100)
    f.seek(0)
    return [end.decode(), f.read(100).decode()]


def fails(f):
    raise ValueError("a bug")


def hangs_if_named_hang(f):
    if f.name.endswith("hang.bin"):
        time.sleep(60)
    return "quick"


def crashes_if_named_crash(f):
    if f.name.endswith("crash.bin"):
        os.abort()
    return "alive"


def pid(f):
    return os.getpid()


def two_reads(f):
    try:
        f.read(10)
    except files.BudgetExceeded:
        pass  # as a library would catch it
    return f.read(1)


def test_reading_a_file_at_any_offset_within_the_budget(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"s" * 100 + b"m" * 1000 + b"e" * 100)
    e = entry_of(tmp_path / "a.bin")
    d = directory(tmp_path, [e])
    got = d.inspect([e], ends_and_start)
    assert got[e.rel].kind == inspection.RESULT
    assert got[e.rel].result == ["e" * 100, "s" * 100]
    assert got[e.rel].read == 200
    assert not d.warnings and not d.retry


def test_an_entry_replaced_by_a_symlink_or_a_fifo_after_the_listing_is_not_read(
    tmp_path,
):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.bin").write_bytes(b"secret")
    folder = tmp_path / "folder"
    folder.mkdir()
    (folder / "link.bin").write_bytes(b"x" * 300)
    (folder / "fifo.bin").write_bytes(b"x" * 300)
    entries = [entry_of(folder / "link.bin"), entry_of(folder / "fifo.bin")]
    (folder / "link.bin").unlink()
    (folder / "link.bin").symlink_to(outside / "secret.bin")
    (folder / "fifo.bin").unlink()
    os.mkfifo(folder / "fifo.bin")
    d = directory(folder, entries)
    start = time.monotonic()
    got = d.inspect(entries, ends_and_start)
    assert time.monotonic() - start < 30  # the FIFO's open did not block
    assert {x.kind for x in got.values()} == {inspection.NOT_REGULAR}
    assert d.unanswered is None and not d.retry


def test_an_entry_replaced_by_a_symlink_is_not_read_for_its_first_bytes(tmp_path):
    (tmp_path / "secret.bin").write_bytes(b"secret")
    (tmp_path / "a.bin").write_bytes(b"x" * 10)
    e = entry_of(tmp_path / "a.bin")
    (tmp_path / "a.bin").unlink()
    (tmp_path / "a.bin").symlink_to(tmp_path / "secret.bin")
    d = directory(tmp_path, [e])
    with pytest.raises(OSError) as raised:
        d.read(e, 6)
    assert isinstance(raised.value, files.NotRegular)
    assert d.unanswered is None  # gone for the crawl, not "did not answer"


def test_a_budget_breach_stays_raised(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    f = files.Counted(files.regular(str(tmp_path / "a.bin")), budget=5)
    with pytest.raises(files.BudgetExceeded):
        f.read(10)
    with pytest.raises(files.BudgetExceeded):
        f.read(1)  # within the budget alone, but after a breach
    f.close()
    # In the worker's function: the outcome says so, whatever fn made of it
    kind, *_ = inspection._inspect(two_reads, str(tmp_path / "a.bin"), 5)
    assert kind == inspection.OVER_BUDGET


def test_a_read_error_inside_an_inspection(tmp_path, monkeypatch):
    (tmp_path / "a.bin").write_bytes(b"x" * 100)

    def eio(fd, n, offset):
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(files.os, "pread", eio)
    raw = inspection._inspect(two_reads, str(tmp_path / "a.bin"), None)
    assert raw[0] == inspection.UNANSWERED and raw[4] == errno.EIO
    monkeypatch.undo()

    class Fixed:
        def run(self, fn, paths, budget):
            return [inspection.outcome((raw, None, 0.1))]

    e = entry_of(tmp_path / "a.bin")
    d = directory(tmp_path, [e])
    d.inspector = Fixed()
    got = d.inspect([e], two_reads)
    assert got[e.rel].kind == inspection.UNANSWERED
    assert d.unanswered is not None and d.unanswered[0] == e.rel


def test_the_outcome_of_each_kind():
    ok = (inspection.RESULT, [1], "", 10, None)
    assert inspection.outcome((ok, None, 0.1)).result == [1]
    late = inspection.outcome((None, f"{extraction.TIMED_OUT} 60 s", 60.0))
    assert late.kind == inspection.TIMEOUT
    dead = inspection.outcome((None, f"the extractor's {extraction.DIED}", 0.1))
    assert dead.kind == inspection.DEAD
    odd = inspection.outcome((None, "PicklingError('...')", 0.1))
    assert odd.kind == inspection.FAILED


def test_an_inspection_that_fails(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x")
    e = entry_of(tmp_path / "a.bin")
    d = directory(tmp_path, [e])
    got = d.inspect([e], fails)
    assert got[e.rel].kind == inspection.FAILED
    assert "a bug" in got[e.rel].detail
    assert d.retry
    assert any(NOT_INSPECTED in text for _, text in d.warnings)


def test_an_inspection_that_hangs(tmp_path):
    for name in ("hang.bin", "quick.bin"):
        (tmp_path / name).write_bytes(b"x")
    entries = [entry_of(tmp_path / "hang.bin"), entry_of(tmp_path / "quick.bin")]
    d = directory(tmp_path, entries)
    d.inspector = Inspector(2, time_limit=10.0)
    try:
        got = d.inspect(entries, hangs_if_named_hang)
    finally:
        d.inspector.close()
    assert got["/hang.bin"].kind == inspection.TIMEOUT
    assert got["/quick.bin"].result == "quick"
    assert d.retry
    warned = [text for rel, text in d.warnings if rel == "/hang.bin"]
    assert len(warned) == 1 and NOT_INSPECTED in warned[0]


def test_an_inspection_that_crashes_its_process(tmp_path):
    for name in ("crash.bin", "fine.bin"):
        (tmp_path / name).write_bytes(b"x")
    entries = [entry_of(tmp_path / "crash.bin"), entry_of(tmp_path / "fine.bin")]
    d = directory(tmp_path, entries)
    got = d.inspect(entries, crashes_if_named_crash)
    assert got["/crash.bin"].kind == inspection.DEAD
    assert got["/fine.bin"].result == "alive"
    assert d.retry


PIDS: list[int] = []  # the workers' process ids, from Inspects


class Inspects(Format):
    """Inspects every text file, and makes each a dataset of its own."""

    type = "x/inspected"
    reacts_to = frozenset({"text/plain"})

    def recognize(self, d):
        got = d.inspect(d.of_type("text/plain"), pid)
        PIDS.extend(x.result for x in got.values())
        return [Dataset(anchor=rel) for rel in got]


def test_one_pool_for_the_crawl(tmp_path, monkeypatch):
    for i in range(20):
        (tmp_path / f"f{i}").mkdir()
        for j in range(3):
            (tmp_path / f"f{i}" / f"{j}.txt").write_text("text\n")
    made = []
    get = extraction.Pool.get

    def counted(self):
        if self._pool is None:
            made.append(self)
        return get(self)

    monkeypatch.setattr(extraction.Pool, "get", counted)
    fmt = Inspects()
    Collection("t", [fmt])
    PIDS.clear()
    walk(tmp_path, [fmt], threads=32, processes=2)
    assert len(PIDS) == 60
    assert len(set(PIDS)) <= 2  # one pool of 2 for 20 folders on 32 threads
    assert len(made) == 1
    made.clear()
    (tmp_path / "plain").mkdir()
    walk(tmp_path / "plain", [fmt], processes=2)
    assert made == []  # nothing to inspect, no process


def test_an_inspection_once_the_walk_stops(tmp_path):
    # Second code review, nits: no exception for the runner to log as "failed"
    (tmp_path / "a.bin").write_bytes(b"x")
    e = entry_of(tmp_path / "a.bin")
    d = directory(tmp_path, [e])
    d.inspector = Inspector(2, stopping=lambda: True)
    got = d.inspect([e], pid)
    assert got[e.rel].kind == inspection.STOPPED
    assert not d.warnings and d.retry
    assert not d.inspector.pool.alive  # no process started for it


def test_an_inspection_in_the_pre_order_call_is_refused(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x")
    e = entry_of(tmp_path / "a.bin")
    d = Directory("/", str(tmp_path), [e], [], "pre", uid=1, mtime=0.5)
    with pytest.raises(ValueError, match="post-order"):
        d.inspect([e], pid)


def sleeps(f):
    time.sleep(20)
    return "slept"


class Sleeps(Format):
    """Inspects every text file with a function that takes 20 s."""

    type = "x/slept"
    reacts_to = frozenset({"text/plain"})

    def recognize(self, d):
        d.inspect(d.of_type("text/plain"), sleeps)
        return []


# Run in a process of its own, as the crawl runs: SIGTERM sets a flag that the
# walk's progress and the inspector's check read (cli._terminate); Ctrl-C
# raises KeyboardInterrupt in the main thread
STOPPED = """
import signal, sys, tempfile, threading
from pathlib import Path
sys.path.insert(0, {tests!r})
from modama_crawler import mimedb, selection
from modama_crawler.formats import Collection
from modama_crawler.walk import walk
import test_inspection
database = Path(tempfile.mkdtemp(dir={scratch!r}))
mimedb.build(selection.discover().values(), database)
mimedb.activate(database)
stop = threading.Event()
signal.signal(signal.SIGTERM, lambda *_: stop.set())
class Stopped(Exception):
    pass
def progress(directories, files):
    if stop.is_set():
        raise Stopped
fmt = test_inspection.Sleeps()
Collection("t", [fmt])
print("walking", flush=True)
try:
    walk(Path({tree!r}), [fmt], progress=progress, processes=2, stopping=stop.is_set)
except KeyboardInterrupt:
    sys.exit(130)
except Stopped:
    pass
if stop.is_set():  # as the crawl checks SIGTERM after its walk
    sys.exit(143)
"""


@pytest.mark.parametrize("stop", [signal.SIGTERM, signal.SIGINT])
def test_stopping_does_not_wait_for_the_inspections(tmp_path, stop):
    tree = tmp_path / "tree"
    for i in range(10):
        (tree / f"f{i}").mkdir(parents=True)
        (tree / f"f{i}" / "a.txt").write_text("text\n")
    script = STOPPED.format(
        tests=str(Path(__file__).parent), scratch=str(tmp_path), tree=str(tree)
    )
    run = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert run.stdout.readline() == "walking\n"
    time.sleep(4)  # the first folders inspect, the others wait for the pool
    assert run.poll() is None, "the walk ended before the signal"
    run.send_signal(stop)
    start = time.monotonic()
    try:
        run.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pytest.fail("still walking 30 s after the signal")
    finally:
        run.kill()
    # Ten folders of 20 s on 2 workers, one folder at a time, would take 200 s
    assert time.monotonic() - start < 30
    assert run.returncode == (143 if stop == signal.SIGTERM else 130)
    # Quietly: no task's exception left for asyncio to print (code review 2, nit)
    assert "never retrieved" not in run.stderr.read()
