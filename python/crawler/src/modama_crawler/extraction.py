"""Running the formats' extractors after the walk, in worker processes, with a time limit per dataset (D1).

The walk only recognises; this module runs `Format.extract` on every dataset
whose format has one, unless an earlier extraction of the same extractor and
version on the same state of the files can be reused (D3). An extractor that
raises, kills its process, runs out of its memory budget or runs over the
time limit leaves its dataset with an error and the crawl with a warning;
the crawl goes on (R23). A failure that comes from the environment rather
than from the file (the time limit, a dead process, an OS or import error) is
not reused: the next crawl runs the extractor again.
Provisional: the I/O study may change how this runs, not the interface (D2).
"""

from __future__ import annotations

import json
import multiprocessing
import os
import re
import resource
import time
from collections import deque
from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field, replace

from .formats import Dataset, Extracted, Extraction, Format, Result

TIME_LIMIT = 60.0  # seconds per dataset
MAX_WORKERS = 8  # NFS latency, not the CPU, sets the pace (D1)
# Address space per worker (RLIMIT_AS). A worker with RosettaSciIO and numpy
# imported maps about 0.4 GiB on 8 CPUs, more with more CPUs (thread
# buffers); readers load headers only (D7). Over it, an allocation raises
# MemoryError, which fails that dataset's extraction.
MEMORY = 4 << 30
TASKS_PER_WORKER = 100  # then the worker is replaced, so that leaks don't add up
# An extractor's result is cut to these before it is stored: a summary phrase
# or a value longer than this is not useful in a record, and a reader that
# returns a whole array as a list must not bloat the database.
MAX_STRING = 4096  # characters per string
MAX_ITEMS = 1000  # entries per list or dict
# Failures that come from the environment, not from the file's content: not reused
ENVIRONMENT = (OSError, ImportError)


def default_workers() -> int:
    return min(os.cpu_count() or 1, MAX_WORKERS)


@dataclass
class Report:
    """The crawl's account of extraction (spec `extraction`, "The crawl reports extraction")."""

    run: int = 0
    reused: int = 0
    failed: int = 0
    unchanged: int = 0  # directories taken over from the last crawl
    seconds: dict[str, float] = field(
        default_factory=dict
    )  # per format id, of the runs

    def __str__(self) -> str:
        times = ", ".join(f"{f} {s:.1f} s" for f, s in sorted(self.seconds.items()))
        return (
            f"extraction: {self.run} run, {self.reused} reused, {self.failed} failed; "
            f"{self.unchanged} directories unchanged; time per format: {times or 'none'}"
        )


Stored = Callable[[list[str]], dict[str, Extraction]]


def _no_stored(anchors: list[str]) -> dict[str, Extraction]:
    return {}


def extract(
    result: Result,
    formats: Iterable[Format],
    root: str,
    *,
    stored: Stored = _no_stored,
    workers: int | None = None,
    time_limit: float = TIME_LIMIT,
    memory: int | None = MEMORY,
) -> Report:
    """Set the extraction of every dataset of the result whose format has an extractor; returns the report.

    `stored` gives the extractions of the last crawl by anchor, for the
    datasets that were recognised again; datasets taken over from it carry
    theirs already. A failure, new or reused, becomes a warning of the result.
    `memory` is each worker's address space in bytes, None for no limit.
    """
    by_id = {f.id: f for f in formats if f.has_extractor}
    report = Report(unchanged=result.unchanged)
    wanted = [i for i, d in enumerate(result.datasets) if d.format in by_id]
    earlier = stored(
        [
            result.datasets[i].anchor
            for i in wanted
            if result.datasets[i].extraction is None
        ]
    )
    tasks: list[int] = []
    for i in wanted:
        d = result.datasets[i]
        fmt = by_id[d.format]
        before = d.extraction or earlier.get(d.anchor)
        if (
            before is not None
            and not before.retry
            and (before.extractor, before.version, before.stamp)
            == (fmt.id, fmt.extractor_version, d.stamp)
        ):
            result.datasets[i] = replace(d, extraction=before)
            report.reused += 1
        else:
            tasks.append(i)
    outcomes = _run(
        [(by_id[result.datasets[i].format], result.datasets[i], root) for i in tasks],
        workers or default_workers(),
        time_limit,
        memory,
    )
    for i, (extracted, error, seconds, retry) in zip(tasks, outcomes, strict=True):
        d = result.datasets[i]
        fmt = by_id[d.format]
        result.datasets[i] = replace(
            d,
            extraction=Extraction(
                fmt.id, fmt.extractor_version, d.stamp, extracted, error, seconds, retry
            ),
        )
        report.run += 1
        report.seconds[fmt.id] = report.seconds.get(fmt.id, 0.0) + seconds
    # Datasets of formats without an extractor (any more) carry none
    for i, d in enumerate(result.datasets):
        if d.format not in by_id and d.extraction is not None:
            result.datasets[i] = replace(d, extraction=None)
    for d in result.datasets:
        if d.extraction is not None and d.extraction.error is not None:
            report.failed += 1
            result.warnings.append(
                (d.anchor, f"{d.format} extraction failed: {d.extraction.error}")
            )
    result.warnings.sort()
    return report


# What PostgreSQL's JSONB rejects in a string: NUL and lone surrogates
_UNSTORABLE = re.compile("[\x00\ud800-\udfff]")


def _storable(value):
    """The value with NUL and lone surrogates replaced by U+FFFD, strings and collections cut to the limits."""
    if isinstance(value, str):
        return _UNSTORABLE.sub("�", value[:MAX_STRING])
    if isinstance(value, list | tuple):
        return [_storable(v) for v in value[:MAX_ITEMS]]
    if isinstance(value, dict):
        items = list(value.items())[:MAX_ITEMS]
        return {
            (_storable(k) if isinstance(k, str) else k): _storable(v) for k, v in items
        }
    return value


def _work(fmt: Format, dataset: Dataset, root: str) -> Extracted | None:
    """In the worker: the extractor's result, made storable as JSONB; raises if it cannot be."""
    extracted = fmt.extract(dataset, root)
    if extracted is None:
        return None
    if not isinstance(extracted, Extracted):
        raise TypeError(f"extract returned {type(extracted).__name__}, not Extracted")
    extracted = Extracted(
        _storable(extracted.summary),
        _storable(extracted.subjects),
        _storable(extracted.values),
    )
    # NaN and the infinities are not JSON; other types raise TypeError
    json.dumps(
        [extracted.summary, extracted.subjects, extracted.values], allow_nan=False
    )
    return extracted


def _limit_memory(memory: int | None) -> None:
    """The pool's worker initializer."""
    if memory is not None:
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))


# extracted, error, seconds, and whether the failure came from the environment
Outcome = tuple[Extracted | None, str | None, float, bool]


def _run(
    tasks: list[tuple[Format, Dataset, str]],
    workers: int,
    time_limit: float,
    memory: int | None = MEMORY,
) -> list[Outcome]:
    """Run the tasks in a pool of spawned processes; the time limit is enforced from outside.

    At most `workers` tasks are in flight, so each starts when submitted and
    its time counts from then. A task over the limit fails and the pool is
    killed and recreated; the other tasks in flight start again. When a
    process dies, the pool cannot tell whose task killed it: the tasks in
    flight are run again one at a time, and one that kills its process when
    alone fails.
    """
    out: list[Outcome | None] = [None] * len(tasks)
    if not tasks:
        return []
    context = multiprocessing.get_context("spawn")
    queue = deque(range(len(tasks)))
    suspects: deque[int] = deque()  # run alone
    suspected: set[int] = set()
    running: dict = {}  # future -> (task index, start)
    pool: ProcessPoolExecutor | None = None

    def submit(i: int) -> None:
        running[pool.submit(_work, *tasks[i])] = (i, time.monotonic())

    def requeue(indices: Iterable[int]) -> None:
        for i in sorted(indices, reverse=True):
            (suspects if i in suspected else queue).appendleft(i)

    try:
        while queue or suspects or running:
            if pool is None:
                pool = ProcessPoolExecutor(
                    workers,
                    mp_context=context,
                    initializer=_limit_memory,
                    initargs=(memory,),
                    max_tasks_per_child=TASKS_PER_WORKER,
                )
            if suspects:
                if not running:
                    submit(suspects.popleft())
            else:
                while queue and len(running) < workers:
                    submit(queue.popleft())
            deadline = min(start for _, start in running.values()) + time_limit
            done, _ = wait(
                running,
                timeout=max(0.0, deadline - time.monotonic()),
                return_when=FIRST_COMPLETED,
            )
            broken = False
            for future in done:
                i, start = running.pop(future)
                try:
                    out[i] = (future.result(), None, time.monotonic() - start, False)
                except BrokenProcessPool:
                    broken = True
                    running[future] = (i, start)  # handled with the others below
                except Exception as e:  # noqa: BLE001  a failing extractor must not stop the crawl
                    out[i] = (
                        None,
                        repr(e),
                        time.monotonic() - start,
                        isinstance(e, ENVIRONMENT),
                    )
            if broken:
                lost = [i for i, _ in running.values()]
                if len(lost) == 1:
                    out[lost[0]] = (
                        None,
                        "the extractor's process died",
                        time.monotonic() - next(iter(running.values()))[1],
                        True,
                    )
                else:
                    suspected.update(lost)
                    requeue(lost)
                running.clear()
                pool.shutdown(wait=True, cancel_futures=True)
                pool = None
                continue
            now = time.monotonic()
            late = [i for i, start in running.values() if now - start >= time_limit]
            if late:
                for i in late:
                    out[i] = (
                        None,
                        f"timed out after {time_limit:g} s",
                        time_limit,
                        True,
                    )
                requeue(i for i, _ in running.values() if i not in late)
                running.clear()
                pool.kill_workers()
                pool = None
    finally:
        if pool is not None:
            if running:
                pool.kill_workers()
            else:
                pool.shutdown(wait=True)
    return out  # type: ignore[return-value]
