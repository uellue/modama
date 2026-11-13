"""Running the formats' extractors after the walk, in worker processes, with a time limit per dataset (D1).

The walk only recognises; this module runs `Format.extract` on every dataset
whose format has one, unless an earlier successful extraction by the same
extractor under the same extractor identity on the same state of the files
can be reused (D3; change `extractor-identity`, D3). An extractor that
raises, kills its process, runs out of its memory budget or runs over the
time limit leaves its dataset with an error and the crawl with a warning;
the crawl goes on (R23). A failure is never reused, whatever its cause: the
next crawl runs the extractor again (D9). Each crawl also extracts a random
sample of what it reuses again and compares (the spot check, D10).
Provisional: the I/O study may change how this runs, not the interface (D2).
"""

from __future__ import annotations

import json
import logging
import multiprocessing
import random
import re
import resource
import signal
import time
from collections import deque
from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from dataclasses import asdict, dataclass, field, replace

from . import cpus
from .formats import Dataset, Extracted, Extraction, Format, Result
from .identity import short

log = logging.getLogger(__name__)

TIME_LIMIT = 60.0  # seconds per dataset
CHECK_INTERVAL = 1.0  # seconds between calls of extract's check (SIGTERM)
MAX_WORKERS = 8  # NFS latency, not the CPU, sets the pace (D1)
# Address space per worker (RLIMIT_AS). A worker with RosettaSciIO and numpy
# imported maps about 0.14 GiB with one BLAS thread, which the crawl sets
# (R43; 0.4 GiB on 8 CPUs with OpenBLAS's default of a thread per CPU);
# readers load headers only (D7). Over it, an allocation raises
# MemoryError, which fails that dataset's extraction.
MEMORY = 4 << 30
TASKS_PER_WORKER = 100  # then the worker is replaced, so that leaks don't add up
# An extractor's result is cut to these before it is stored: a summary phrase
# or a value longer than this is not useful in a record, and a reader that
# returns a whole array as a list must not bloat the database.
MAX_STRING = 4096  # characters per string
MAX_ITEMS = 1000  # entries per list or dict
SAMPLE = 20  # datasets per format that the spot check extracts again (D10)
MAX_NAMED = 5  # differences named per format, then "and N more" (R36)
# A successful extraction over SLOW seconds is warned at its dataset with the
# marker, by which `modama-chain review` lists them (change slow-extractions, @weber 352)
SLOW = 10.0
SLOW_EXTRACTION = "slow extraction"
SLOWEST = 10  # the crawl's slowest extractions in its report and run (352)


def default_workers() -> int:
    """The CPUs this process may use, at most MAX_WORKERS (R43)."""
    return min(cpus.usable().cpus, MAX_WORKERS)


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


@dataclass
class Difference:
    """A dataset whose spot check gave another result than the stored one (D10)."""

    anchor: str
    fields: list[
        tuple[str, object, object]
    ]  # (field, stored, new); empty when it now fails
    error: str | None = (
        None  # the new failure, which did not replace the stored success
    )

    def __str__(self) -> str:
        if self.error is not None:
            return f"{self.anchor} (now fails: {self.error})"
        plain = [f for f, _, _ in self.fields if not f.startswith("values.")]
        values = [
            f.removeprefix("values.") for f, _, _ in self.fields if f not in plain
        ]
        parts = plain + ([f"values: {', '.join(values)}"] if values else [])
        return f"{self.anchor} ({'; '.join(parts)})"

    def to_json(self) -> dict:
        return {
            "dataset": self.anchor,
            "error": self.error,
            "fields": [[f, old, new] for f, old, new in self.fields],
        }


@dataclass
class SpotCheck:
    """The spot check's outcome: per format the datasets compared, and those that differ (D10)."""

    seed: int
    checked: dict[str, int] = field(default_factory=dict)
    differ: dict[str, list[Difference]] = field(default_factory=dict)

    @property
    def differences(self) -> int:
        return sum(len(d) for d in self.differ.values())

    def __str__(self) -> str:
        if not self.checked:
            return "spot check: nothing reused"
        counts = []
        for i, (fid, n) in enumerate(sorted(self.checked.items())):
            same = n - len(self.differ.get(fid, ()))
            counts.append(f"{fid} {same} of {n}" + (" as stored" if i == 0 else ""))
        named = []
        for fid in sorted(self.differ):
            found = self.differ[fid]
            named += [str(d) for d in found[:MAX_NAMED]]
            if len(found) > MAX_NAMED:
                named.append(f"and {len(found) - MAX_NAMED} more")
        line = f"spot check (seed {self.seed:016x}): {', '.join(counts)}"
        return f"{line}; differs: {', '.join(named)}" if named else line

    def to_json(self) -> dict:
        return {
            "seed": f"{self.seed:016x}",
            "checked": dict(sorted(self.checked.items())),
            "differ": {
                # every one, with its stored and new values (192); at most the sample's size
                fid: [d.to_json() for d in found]
                for fid, found in sorted(self.differ.items())
            },
            "differences": self.differences,
        }


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
    identity: str = ""  # the crawl's extractor identity
    # (format id, stored identity) -> [extracted again for a new identity, results changed] (D6)
    reextracted: dict[tuple[str, str], list[int]] = field(default_factory=dict)
    # format id -> [failures tried again, now succeed] (D9)
    retried: dict[str, list[int]] = field(default_factory=dict)
    spot: SpotCheck | None = None  # None: no spot check (no seed given)
    # stored identity -> what differs from the crawl's, set by the caller (identity.differences)
    causes: dict[str, list[str]] = field(default_factory=dict)
    # (anchor, format id, seconds) of the SLOWEST extractions run, slowest first (352)
    slowest: list[tuple[str, str, float]] = field(default_factory=list)

    def __str__(self) -> str:
        times = ", ".join(f"{f} {s:.1f} s" for f, s in sorted(self.seconds.items()))
        line = (
            f"extraction: {self.run} run, {self.reused} reused, {self.failed} failed; "
            f"{self.unchanged} directories unchanged; time per format: {times or 'none'}"
        )
        return f"{line}; identity {short(self.identity)}" if self.identity else line

    def lines(self) -> list[str]:
        """The report: its first line, the slowest extractions, one per format and stored identity extracted again, one per format with failures tried again, the spot check."""
        out = [str(self)]
        if self.slowest:
            out.append(f"slowest extractions: {slowest_text(self.slowest_json())}")
        for (fid, before), (n, changed) in sorted(self.reextracted.items()):
            causes = ", ".join(self.causes.get(before, [f"from {short(before)}"]))
            out.append(
                f"{fid}: {n} extracted again for a new identity ({causes}), "
                f"{_plural(changed, 'result', 'results')} changed"
            )
        for fid, (n, succeed) in sorted(self.retried.items()):
            out.append(
                f"{fid}: {n} tried again after a failure, "
                f"{succeed} now {'succeeds' if succeed == 1 else 'succeed'}"
            )
        if self.spot is not None:
            out.append(str(self.spot))
        return out

    def reextracted_json(self) -> list[dict]:
        """The re-extraction for a new identity as the run keeps it (D8)."""
        return [
            {
                "format": fid,
                "from": before,
                "datasets": n,
                "changed": changed,
                "differences": self.causes.get(before, []),
            }
            for (fid, before), (n, changed) in sorted(self.reextracted.items())
        ]

    def slowest_json(self) -> list[dict]:
        """The slowest extractions as the run keeps them (352)."""
        return [
            {"dataset": anchor, "format": fid, "seconds": seconds}
            for anchor, fid, seconds in self.slowest
        ]

    def retried_json(self) -> dict:
        """The failures tried again per format, as the run keeps them (D9, R45)."""
        return {
            fid: {"tried": n, "succeed": succeed}
            for fid, (n, succeed) in sorted(self.retried.items())
        }


def slowest_text(slowest: list[dict]) -> str:
    """`/a/b.dm4 em/dm4 23.4 s, …`: the slowest extractions as the report and `runs` name them (352)."""
    return ", ".join(
        f"{x['dataset']} {x['format']} {x['seconds']:.1f} s" for x in slowest
    )


def _slow(d: Dataset) -> Dataset:
    """The dataset with the slow-extraction warning of its extraction, and no other (352).

    A dataset taken over from the last crawl carries the warning stored with
    it; set anew here, it follows the extraction, reused or run again.
    """
    x = d.extraction
    warnings = tuple(w for w in d.warnings if not w.endswith(f"; {SLOW_EXTRACTION}"))
    if x is not None and x.error is None and x.seconds > SLOW:
        warnings += (
            f"{d.format} extraction took {x.seconds:.1f} s; {SLOW_EXTRACTION}",
        )
    return d if warnings == d.warnings else replace(d, warnings=warnings)


Stored = Callable[[list[str]], dict[str, Extraction]]


def _no_stored(anchors: list[str]) -> dict[str, Extraction]:
    return {}


def _stored_form(x: Extraction) -> tuple[dict | None, str | None]:
    """An extraction's outcome as the database gives it back (JSONB), for comparing a stored one with a new one."""
    extracted = json.loads(json.dumps(asdict(x.extracted))) if x.extracted else None
    return extracted, x.error


def fields_of(old, new, prefix: str) -> list[tuple[str, object, object]]:
    """(field, old, new) for each field that differs between two parts of results in stored form, dotted below `values`."""
    if isinstance(old, dict) and isinstance(new, dict) and prefix.startswith("values"):
        out = []
        for key in sorted(old.keys() | new.keys(), key=str):
            out += fields_of(old.get(key), new.get(key), f"{prefix}.{key}")
        return out
    return [] if old == new else [(prefix, old, new)]


def _differences(
    before: Extraction, after: Extraction
) -> list[tuple[str, object, object]]:
    (old, _), (new, _) = _stored_form(before), _stored_form(after)
    old, new = old or {}, new or {}
    return [
        d
        for key in ("summary", "subjects", "values")
        for d in fields_of(old.get(key), new.get(key), key)
    ]


def sample(
    seed: int, reused: dict[str, list[str]], size: int = SAMPLE
) -> dict[str, list[str]]:
    """The spot check's sample: per format id, `size` of its reused anchors, or all when fewer (D10).

    Drawn with one random.Random(seed) over the formats in the order of their
    ids and each format's anchors sorted, so that the same seed over the same
    stored datasets gives the same sample.
    """
    rng = random.Random(seed)
    out = {}
    for fid in sorted(reused):
        anchors = sorted(reused[fid])
        out[fid] = (
            anchors if len(anchors) <= size else sorted(rng.sample(anchors, size))
        )
    return out


def extract(
    result: Result,
    formats: Iterable[Format],
    root: str,
    *,
    identity: str,
    stored: Stored = _no_stored,
    workers: int | None = None,
    time_limit: float = TIME_LIMIT,
    memory: int | None = MEMORY,
    check: Callable[[], None] | None = None,
    seed: int | None = None,
    sample_size: int = SAMPLE,
) -> Report:
    """Set the extraction of every dataset of the result whose format has an extractor; returns the report.

    `identity` is the installation's extractor identity (identity.digest):
    a stored success is reused only under the same one, a stored failure
    never. `stored` gives the extractions of the last crawl by anchor, for
    the datasets that were recognised again; datasets taken over from it
    carry theirs already. A failure, new or rerun, becomes a warning of the
    result. With a `seed`, `sample_size` datasets per format of those
    reused are extracted again and compared (the spot check, D10); a new
    success replaces the stored result, a new failure does not.
    `memory` is each worker's address space in bytes, None for no limit.
    `check` is called at least every second while extractors run; what it
    raises ends the extraction, the workers killed (SIGTERM).
    """
    by_id = {f.id: f for f in formats if f.has_extractor}
    report = Report(unchanged=result.unchanged, identity=identity)
    # Datasets kept because the file system did not answer stay as stored (listing-errors D7)
    wanted = [
        i for i, d in enumerate(result.datasets) if d.format in by_id and not d.kept
    ]
    earlier = stored(
        [
            result.datasets[i].anchor
            for i in wanted
            if result.datasets[i].extraction is None
        ]
    )
    tasks: list[int] = []
    befores: dict[int, Extraction] = {}  # what was stored for the tasks with one
    reused: dict[str, list[str]] = {}
    for i in wanted:
        d = result.datasets[i]
        fmt = by_id[d.format]
        before = d.extraction or earlier.get(d.anchor)
        if before is None or (before.extractor, before.stamp) != (fmt.id, d.stamp):
            tasks.append(i)  # new or changed files
            continue
        if before.error is None and before.identity == identity:
            result.datasets[i] = replace(d, extraction=before)
            report.reused += 1
            reused.setdefault(fmt.id, []).append(d.anchor)
            continue
        befores[i] = before  # a failure (D9), or another identity (D3)
        tasks.append(i)
    spots: list[int] = []
    if seed is not None:
        report.spot = SpotCheck(seed)
        picked = sample(seed, reused, sample_size)
        index = {result.datasets[i].anchor: i for i in wanted}
        spots = [index[a] for fid in sorted(picked) for a in picked[fid]]
    outcomes = _run(
        [
            (by_id[result.datasets[i].format], result.datasets[i], root)
            for i in tasks + spots
        ],
        workers or default_workers(),
        time_limit,
        memory,
        check,
    )
    for i, (extracted, error, seconds) in zip(
        tasks, outcomes[: len(tasks)], strict=True
    ):
        d = result.datasets[i]
        fmt = by_id[d.format]
        new = Extraction(fmt.id, identity, d.stamp, extracted, error, seconds)
        result.datasets[i] = replace(d, extraction=new)
        report.run += 1
        report.seconds[fmt.id] = report.seconds.get(fmt.id, 0.0) + seconds
        report.slowest.append((d.anchor, fmt.id, seconds))
        before = befores.get(i)
        if before is None:
            continue
        if before.error is not None:
            counts = report.retried.setdefault(fmt.id, [0, 0])
            counts[0] += 1
            counts[1] += error is None
        else:
            counts = report.reextracted.setdefault((fmt.id, before.identity), [0, 0])
            counts[0] += 1
            counts[1] += _stored_form(before) != _stored_form(new)
    report.slowest = sorted(report.slowest, key=lambda x: x[2], reverse=True)[:SLOWEST]
    for i, (extracted, error, seconds) in zip(
        spots, outcomes[len(tasks) :], strict=True
    ):
        d = result.datasets[i]
        fmt = by_id[d.format]
        spot = report.spot
        spot.checked[fmt.id] = spot.checked.get(fmt.id, 0) + 1
        new = Extraction(fmt.id, identity, d.stamp, extracted, error, seconds)
        if error is not None:
            found = Difference(d.anchor, [], error)
        else:
            fields = _differences(d.extraction, new)
            if not fields:
                continue
            found = Difference(d.anchor, fields)
            result.datasets[i] = replace(
                d, extraction=new
            )  # what the installed code gives (192)
        spot.differ.setdefault(fmt.id, []).append(found)
        log.warning(
            "spot check: %s differs from the stored result: %s",
            d.anchor,
            f"now fails: {error}"
            if error is not None
            else "; ".join(
                f"{f}: stored {old!r}, now {now!r}" for f, old, now in fields
            ),
        )
    # Datasets of formats without an extractor (any more) carry none
    for i, d in enumerate(result.datasets):
        if d.format not in by_id and d.extraction is not None and not d.kept:
            result.datasets[i] = replace(d, extraction=None)
    for i, d in enumerate(result.datasets):
        if d.kept:
            continue
        result.datasets[i] = _slow(d)
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
    """The pool's worker initializer. Ctrl-C is the parent's to handle: it kills the workers."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if memory is not None:
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))


# extracted, error, seconds
Outcome = tuple[Extracted | None, str | None, float]

TIMED_OUT = "timed out after"  # the start of a task's error over the time limit
DIED = "process died"  # in the error of a task whose process died alone


class Pool:
    """The worker processes of `_run`: made when first needed, killed after a task over the limit.

    `_run` makes one per batch and shuts it down at the end; the walk's
    inspections keep one for the whole crawl (`keep=True`) and shut it down
    after the walk (change hdf5-links, design D5).
    """

    def __init__(self, workers: int, memory: int | None = MEMORY, keep: bool = False):
        self.workers = workers
        self.memory = memory
        self.keep = keep
        self._pool: ProcessPoolExecutor | None = None

    @property
    def alive(self) -> bool:
        return self._pool is not None

    def get(self) -> ProcessPoolExecutor:
        if self._pool is None:
            self._pool = ProcessPoolExecutor(
                self.workers,
                mp_context=multiprocessing.get_context("spawn"),
                initializer=_limit_memory,
                initargs=(self.memory,),
                max_tasks_per_child=TASKS_PER_WORKER,
            )
        return self._pool

    def discard(self, kill: bool) -> None:
        """Kill the workers (a task over the limit) or wait for them (a broken pool)."""
        if self._pool is not None:
            if kill:
                self._pool.kill_workers()
            else:
                self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None

    def done(self) -> None:
        """The end of a batch: shut down, unless kept."""
        if not self.keep:
            self.close()

    def close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None


def _run(
    tasks: list[tuple],
    workers: int,
    time_limit: float,
    memory: int | None = MEMORY,
    check: Callable[[], None] | None = None,
    work: Callable | None = None,
    pool: Pool | None = None,
) -> list[Outcome]:
    """Run the tasks in a pool of spawned processes; the time limit is enforced from outside.

    Each task is the arguments of `work` (a module-level function; the
    extractor's `_work` unless given). At most `workers` tasks are in flight,
    so each starts when submitted and its time counts from then. A task over
    the limit fails and the pool is killed and recreated; the other tasks in
    flight start again. When a process dies, the pool cannot tell whose task
    killed it: the tasks in flight are run again one at a time, and one that
    kills its process when alone fails. Without `pool`, the batch has a pool
    of its own.
    """
    out: list[Outcome | None] = [None] * len(tasks)
    if not tasks:
        return []
    work = work or _work
    pools = pool if pool is not None else Pool(workers, memory)
    queue = deque(range(len(tasks)))
    suspects: deque[int] = deque()  # run alone
    suspected: set[int] = set()
    running: dict = {}  # future -> (task index, start)
    pool_: ProcessPoolExecutor | None = None

    def submit(i: int) -> None:
        running[pool_.submit(work, *tasks[i])] = (i, time.monotonic())

    def requeue(indices: Iterable[int]) -> None:
        for i in sorted(indices, reverse=True):
            (suspects if i in suspected else queue).appendleft(i)

    try:
        while queue or suspects or running:
            pool_ = pools.get()
            if suspects:
                if not running:
                    submit(suspects.popleft())
            else:
                while queue and len(running) < workers:
                    submit(queue.popleft())
            deadline = min(start for _, start in running.values()) + time_limit
            done, _ = wait(
                running,
                timeout=min(CHECK_INTERVAL, max(0.0, deadline - time.monotonic())),
                return_when=FIRST_COMPLETED,
            )
            if check is not None:
                check()  # raising: the finally below kills the workers
            broken = False
            for future in done:
                i, start = running.pop(future)
                try:
                    out[i] = (future.result(), None, time.monotonic() - start)
                except BrokenProcessPool:
                    broken = True
                    running[future] = (i, start)  # handled with the others below
                except Exception as e:  # noqa: BLE001  a failing extractor must not stop the crawl
                    out[i] = (None, repr(e), time.monotonic() - start)
            if broken:
                lost = [i for i, _ in running.values()]
                if len(lost) == 1:
                    out[lost[0]] = (
                        None,
                        f"the extractor's {DIED}",
                        time.monotonic() - next(iter(running.values()))[1],
                    )
                else:
                    suspected.update(lost)
                    requeue(lost)
                running.clear()
                pools.discard(kill=False)
                continue
            now = time.monotonic()
            late = [i for i, start in running.values() if now - start >= time_limit]
            if late:
                for i in late:
                    out[i] = (None, f"{TIMED_OUT} {time_limit:g} s", time_limit)
                requeue(i for i, _ in running.values() if i not in late)
                running.clear()
                pools.discard(kill=True)
    finally:
        if running:
            pools.discard(kill=True)
        else:
            pools.done()
    return out  # type: ignore[return-value]
