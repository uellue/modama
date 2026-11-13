"""Inspecting files of a folder in worker processes, for a format whose recognition needs a library that parses the file (change hdf5-links, design D5).

A library such as h5py (libhdf5) parses untrusted files: one that crashes or
hangs it must not stop or hang the crawl, and its global lock would
serialise the walk's threads. So the format hands a module-level function
to `Directory.inspect`, which runs it on each file in one pool of worker
processes per crawl, one folder at a time, with a time limit enforced from
outside (the extraction's `_run`). In the worker, the file is opened only
as a regular file, never through a symlink (`files.regular`), and read
through a file object with a byte budget per file (`files.Counted`), closed
after the function returns.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from . import files
from .extraction import (
    DIED,
    MEMORY,
    TIME_LIMIT,
    TIMED_OUT,
    Outcome,
    Pool,
    _run,
    default_workers,
)

# What became of one file's inspection
RESULT = "result"
NOT_REGULAR = "not a regular file"
OVER_BUDGET = "over its budget"
UNANSWERED = "the file system did not answer"
FAILED = "failed"
TIMEOUT = "timed out"
DEAD = "its process died"
STOPPED = "not run, the walk is stopping"
# Tried again next crawl (decision 340)
RETRIED = frozenset({FAILED, TIMEOUT, DEAD})


@dataclass(frozen=True)
class Inspected:
    """The outcome of one file's inspection: its kind, the function's result, why not, the bytes read."""

    kind: str
    result: object = None
    detail: str = ""
    read: int = 0
    errno: int | None = None


def _inspect(fn: Callable, path: str, budget: int | None) -> tuple:
    """In the worker: (kind, result, detail, bytes read, errno) of fn on the file at path.

    The file object is closed after fn returns; fn closes what it opened on
    it first (an unclosed h5py file over a closed file object, or the
    reverse, crashed the interpreter at exit: review of hdf5-links, MUST 1).
    A read past the budget or a read error counts whatever fn made of it.
    """
    try:
        fd = files.regular(path)
    except files.NotRegular as e:
        return (NOT_REGULAR, None, e.strerror, 0, None)
    except OSError as e:
        return (UNANSWERED, None, e.strerror or str(e), 0, e.errno)
    f = files.Counted(fd, budget, path)
    failure: Exception | None = None
    result = None
    try:
        result = fn(f)
    except Exception as e:  # noqa: BLE001  reported as the outcome FAILED
        failure = e
    finally:
        f.close()
    if f.over:
        return (
            OVER_BUDGET,
            None,
            f"over its budget of {budget} bytes",
            f.read_bytes,
            None,
        )
    if f.error is not None:
        e = f.error
        return (UNANSWERED, None, e.strerror or str(e), f.read_bytes, e.errno)
    if failure is not None:
        return (FAILED, None, repr(failure), f.read_bytes, None)
    return (RESULT, result, "", f.read_bytes, None)


def outcome(raw: Outcome) -> Inspected:
    """The outcome of one task of `_run`: the worker's own, or what `_run` says of a task it ended."""
    value, error, _ = raw
    if error is None:
        kind, result, detail, read, errno = value  # type: ignore[misc]
        return Inspected(kind, result, detail, read, errno)
    if error.startswith(TIMED_OUT):
        return Inspected(TIMEOUT, detail=error)
    if DIED in error:
        return Inspected(DEAD, detail=error)
    # _inspect itself raised: a result it cannot send
    return Inspected(FAILED, detail=error)


class Inspector:
    """One pool of worker processes for a crawl's inspections, one folder at a time.

    The pool is made at the first inspection and kept until `close`; the lock
    lets one folder inspect at a time, so that killing a late worker or
    running tasks again after a crash touches that folder's files only. A
    format call waiting for the lock blocks its walk thread (design D5).

    Stopping does not wait for the inspections (code review of hdf5-links,
    M1): `stopping` (whether the crawl got SIGTERM) is asked before a
    folder's inspections start and every second while they run, and `stop`
    (the walk ending, Ctrl-C) does the same; either ends every running and
    waiting `run` at once, its workers killed, every file's outcome STOPPED.
    No exception leaves the walk's thread (second code review, nit: asyncio
    printed every thread's Terminated as "never retrieved"); the walk stops
    where the crawl checks SIGTERM, at its next folder or after it.
    """

    def __init__(
        self,
        workers: int | None = None,
        time_limit: float = TIME_LIMIT,
        memory: int | None = MEMORY,
        stopping: Callable[[], bool] | None = None,
    ):
        self.pool = Pool(workers or default_workers(), memory, keep=True)
        self.time_limit = time_limit
        self._lock = threading.Lock()
        self._stopping = stopping
        self._stopped = threading.Event()

    def _check(self) -> None:
        if self._stopped.is_set() or (self._stopping and self._stopping()):
            raise InspectionStopped("the walk is stopping")

    def run(
        self, fn: Callable, paths: list[str], budget: int | None
    ) -> list[Inspected]:
        tasks = [(fn, path, budget) for path in paths]
        try:
            self._check()
            with self._lock:
                self._check()  # another folder's turn may have ended in a stop
                raw = _run(
                    tasks,
                    self.pool.workers,
                    self.time_limit,
                    self.pool.memory,
                    check=self._check,
                    work=_inspect,
                    pool=self.pool,
                )
        except InspectionStopped:
            return [Inspected(STOPPED) for _ in paths]
        return [outcome(r) for r in raw]

    def stop(self) -> None:
        """Every running and waiting `run` ends at its next check, within a second."""
        self._stopped.set()

    def close(self) -> None:
        self.pool.close()


class InspectionStopped(BaseException):
    """The walk is stopping: no inspection runs or waits any more. A BaseException, so
    that nothing on the way (a format's `except Exception`, the runner's `_call`)
    takes it for a failure; `Inspector.run` turns it into the outcome STOPPED."""
