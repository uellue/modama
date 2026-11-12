"""The CPU budget of the search stack's transform worker and search API: processes and threads from what the
container may use, set before Celery or uvicorn starts (README, "CPU budget"; change cpu-budget of the crawler,
design D2, D5 to D8, D10).

  budget.py transform -- celery worker --queues transform     start the transform worker
  budget.py search-api -- uvicorn APP --host H --port P       start the search API
  budget.py explain transform|search-api                      print the budget and its reasons, start nothing

It counts the CPUs of the affinity (a cpuset included) and, for the transform worker, the physical cores among
them, capped by the own cgroup v2 group's CPU quota; the transform worker also by Airflow's task slots and, where
the container has a memory limit, by the memory of one batch process. It logs one line, sets the threads of
ONNX Runtime (EMBEDDING_THREADS, patch 0002), of the tokenizers (RAYON_NUM_THREADS) and of BLAS (1) in its own
environment, which every process the command starts inherits, and execs the command with --concurrency or
--workers. Overrides: TRANSFORM_PROCESSES, WORKERS and EMBEDDING_THREADS. A file it cannot parse or an override
that is not a positive integer stops it with a message, before anything starts. Standard library only.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Peak memory of one batch process with fastembed's sub-batch of 32 (patch 0002): 1.42 GB RSS for 2,000 texts
# of 512 tokens, plus 0.25 GB for the slot's Airflow supervisor (measured 2026-11-12, bge-small-en-v1.5; design D7)
PER_PROCESS = 1_700_000_000
BLAS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
ENTRYPOINT = "/entrypoint"  # the Airflow image's: waits for the broker before `celery`


class Malformed(Exception):
    """A file or an override that cannot be read: the start stops (D10)."""


@dataclass(frozen=True)
class Machine:
    affinity: int  # logical CPUs of the affinity
    cores: int  # physical cores among them (the affinity if the topology is missing), capped by the quota
    topology: bool  # whether the cores come from the topology
    quota: float | None  # CPUs per period; None: none, or not read
    cgroup_v2: bool
    memory: int | None  # the cgroup's memory.max in bytes; None: no limit

    @property
    def logical(self) -> int:
        """Logical CPUs usable: the affinity, capped by the quota."""
        return (
            self.affinity
            if self.quota is None
            else min(self.affinity, math.ceil(self.quota))
        )

    def quota_text(self) -> str:
        if not self.cgroup_v2:
            return "quota not read: no cgroup v2"
        return "no quota" if self.quota is None else f"quota {self.quota:g}"


@dataclass(frozen=True)
class Budget:
    processes: int
    threads: int
    line: str  # the log line
    overrides: dict[str, int]


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return None


def _cpu_list(path: Path, text: str) -> frozenset[int]:
    """A kernel CPU list such as `0-3,8`."""
    cpus: set[int] = set()
    try:
        for part in text.split(","):
            first, _, last = part.partition("-")
            cpus.update(range(int(first), int(last or first) + 1))
    except ValueError:
        raise Malformed(f"{path}: not a CPU list: {text!r}") from None
    return frozenset(cpus)


def machine(root: Path = Path("/")) -> Machine:
    """What this process may use; `root` is where `proc` and `sys` are (tests)."""
    affinity = sorted(os.sched_getaffinity(0))
    group = None
    for line in (root / "proc/self/cgroup").read_text().splitlines():
        # cgroup v2 only in unified mode: a hybrid host has a 0:: line too, with the controllers in v1
        if (
            line.startswith("0::")
            and (root / "sys/fs/cgroup/cgroup.controllers").exists()
        ):
            group = root / "sys/fs/cgroup" / line[3:].lstrip("/")
    quota = memory = None
    if group is not None:
        cpu_max = _read(group / "cpu.max")
        if cpu_max is not None:
            fields = cpu_max.split()
            if (
                len(fields) != 2
                or not fields[1].isdigit()
                or not (fields[0] == "max" or fields[0].isdigit())
            ):
                raise Malformed(
                    f"{group / 'cpu.max'}: cannot parse {cpu_max!r} (expected 'max PERIOD' or 'QUOTA PERIOD')"
                )
            quota = None if fields[0] == "max" else int(fields[0]) / int(fields[1])
        memory_max = _read(group / "memory.max")
        if memory_max is not None and memory_max != "max":
            if not memory_max.isdigit():
                raise Malformed(
                    f"{group / 'memory.max'}: cannot parse {memory_max!r} (expected 'max' or bytes)"
                )
            memory = int(memory_max)
    cores: set[frozenset[int]] = set()
    topology = True
    for cpu in affinity:
        base = root / f"sys/devices/system/cpu/cpu{cpu}/topology"
        for name in ("core_cpus_list", "thread_siblings_list"):
            text = _read(base / name)
            if text is not None:
                cores.add(_cpu_list(base / name, text))
                break
        else:
            topology = False
    count = len(cores) if topology else len(affinity)
    if quota is not None:
        count = min(count, math.ceil(quota))
    return Machine(len(affinity), count, topology, quota, group is not None, memory)


def override(environ, name: str) -> int | None:
    """A positive integer from the environment; empty or unset: None."""
    value = environ.get(name, "")
    if value == "":
        return None
    if not value.isdigit() or int(value) < 1:
        raise Malformed(f"{name} must be a positive integer: {value!r}")
    return int(value)


def _gb(n: int) -> str:
    return f"{n / 1e9:.1f} GB"


def _n(count: int, word: str) -> str:
    return (
        f"{count} {word}"
        if count == 1
        else f"{count} {word}{'es' if word.endswith('s') else 's'}"
    )


def _overrides(overrides: dict[str, int], threads: int, cpus: int, what: str) -> str:
    if not overrides:
        return "no override"
    text = " and ".join(f"{k}={v}" for k, v in overrides.items()) + " set"
    if threads > cpus:
        text += f"; {threads} threads exceed the {cpus} {what}"
    return text


def transform(
    m: Machine,
    *,
    slots: tuple[int, int],
    per_process: int = PER_PROCESS,
    processes: int | None = None,
    threads: int | None = None,
) -> Budget:
    """P batch processes and T threads each; `slots` are max_active_tasks_per_dag and parallelism (D6, D7).

    `processes` and `threads` are the overrides, obeyed as given."""
    overrides = {
        k: v
        for k, v in (("TRANSFORM_PROCESSES", processes), ("EMBEDDING_THREADS", threads))
        if v is not None
    }
    limit = min(slots)
    by_memory = None if m.memory is None else max(1, m.memory // per_process)
    if processes is None:
        wanted = m.cores if threads is None else max(1, m.cores // threads)
        processes = min(x for x in (wanted, limit, by_memory) if x is not None)
    if threads is None:
        threads = max(1, m.cores // processes)
    cores = f"{_n(m.cores, 'core')} usable ({m.affinity} logical CPUs, {m.quota_text()}"
    cores += ")" if m.topology else "; cores are logical CPUs: no topology)"
    memory = (
        "no memory limit"
        if by_memory is None
        else f"memory for {by_memory} (memory.max {_gb(m.memory)}, {_gb(per_process)} each)"
    )
    line = (
        f"CPU budget: {_n(processes, 'process')} × {_n(threads, 'thread')}; {cores}; {memory}; "
        f"{limit} task slots (max_active_tasks_per_dag {slots[0]}, parallelism {slots[1]}); "
        f"{_overrides(overrides, processes * threads, m.cores, 'cores')}"
    )
    return Budget(processes, threads, line, overrides)


def search_api(
    m: Machine, *, workers: int | None = None, threads: int | None = None
) -> Budget:
    """Workers on the logical CPUs usable, one thread each (D1, 158); `workers` and `threads` are the overrides."""
    overrides = {
        k: v
        for k, v in (("WORKERS", workers), ("EMBEDDING_THREADS", threads))
        if v is not None
    }
    workers = m.logical if workers is None else workers
    threads = 1 if threads is None else threads
    line = (
        f"CPU budget: {_n(workers, 'worker')} × {_n(threads, 'thread')}; "
        f"{_n(m.logical, 'CPU')} usable (affinity {m.affinity}, {m.quota_text()}); "
        f"{_overrides(overrides, workers * threads, m.logical, 'CPUs')}"
    )
    return Budget(workers, threads, line, overrides)


def _slots() -> tuple[int, int]:
    from airflow.configuration import conf  # 3 s; only in the Airflow image

    return tuple(
        _slot(conf.get("core", key), key)
        for key in ("max_active_tasks_per_dag", "parallelism")
    )


def _slot(value: str, key: str) -> int:
    """One of Airflow's task limits, a positive integer (AIRFLOW_TASK_LIMIT sets both)."""
    if not value.strip().isdigit() or int(value) < 1:
        raise Malformed(
            f"Airflow's core.{key} (AIRFLOW__CORE__{key.upper()}, from AIRFLOW_TASK_LIMIT) "
            f"must be a positive integer: {value!r}"
        )
    return int(value)


def _budget(service: str, environ, root: Path) -> tuple[Machine, Budget]:
    m = machine(root)
    threads = override(environ, "EMBEDDING_THREADS")
    if service == "transform":
        processes = override(environ, "TRANSFORM_PROCESSES")
        return m, transform(m, slots=_slots(), processes=processes, threads=threads)
    return m, search_api(m, workers=override(environ, "WORKERS"), threads=threads)


def explain(service: str, m: Machine, b: Budget) -> str:
    """The budget line, its inputs and how to change it, for cpu-budget.sh (D11)."""
    lines = [b.line, f"  logical CPUs of the affinity: {m.affinity}"]
    if service == "transform":
        source = "topology" if m.topology else "no topology: logical CPUs"
        if m.quota is not None and math.ceil(m.quota) == m.cores:
            source += ", capped by the CPU quota"
        lines.append(f"  physical cores usable: {m.cores} ({source})")
    quota = (
        "not read"
        if not m.cgroup_v2
        else "none"
        if m.quota is None
        else f"{m.quota:g} CPUs"
    )
    memory = "none" if m.memory is None else _gb(m.memory)
    lines.append(
        f"  cgroup v2: {'yes' if m.cgroup_v2 else 'no'}; CPU quota: {quota}; memory limit: {memory}"
    )
    if service == "transform":
        lines.append(
            f"  expected memory: up to {b.processes} × {_gb(PER_PROCESS)} = {_gb(b.processes * PER_PROCESS)}"
            " (texts of 512 tokens; less for shorter ones)"
        )
        lines.append(
            "  AIRFLOW_TASK_LIMIT in the deployment's env file sets both task limits"
        )
    lines.append(
        "  overrides: "
        + (", ".join(f"{k}={v}" for k, v in b.overrides.items()) or "none")
    )
    if service == "transform":
        lines.append(
            "  TRANSFORM_PROCESSES=N sets the batch processes, EMBEDDING_THREADS=T the threads of each,"
            " in airflow-worker-transform's environment"
        )
    else:
        lines.append(
            "  WORKERS=N sets the workers, EMBEDDING_THREADS=T the threads of each, in search-api's environment"
        )
    return "\n".join(lines)


def _set_pool(processes: int) -> None:
    """The pool `transform` with P slots, so that batches beyond P wait in the scheduler (D6 (i))."""
    subprocess.run(
        [
            "airflow",
            "pools",
            "set",
            "transform",
            str(processes),
            "transform batches: the transform worker's processes",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def main(argv: list[str], environ=os.environ, root: Path = Path("/")) -> int:
    usage = "usage: budget.py transform|search-api -- COMMAND... | budget.py explain transform|search-api"
    if (
        len(argv) >= 2
        and argv[0] == "explain"
        and argv[1] in ("transform", "search-api")
    ):
        try:
            m, b = _budget(argv[1], environ, root)
        except Malformed as e:
            print(f"budget.py: {e}", file=sys.stderr)
            return 2
        print(explain(argv[1], m, b))
        return 0
    if len(argv) < 3 or argv[0] not in ("transform", "search-api") or argv[1] != "--":
        print(usage, file=sys.stderr)
        return 2
    service, command = argv[0], argv[2:]
    try:
        _, b = _budget(service, environ, root)
    except Malformed as e:
        print(f"budget.py: {e}; nothing started", file=sys.stderr)
        return 2
    print(b.line, file=sys.stderr, flush=True)
    environ.update(
        {"EMBEDDING_THREADS": str(b.threads), "RAYON_NUM_THREADS": str(b.threads)}
    )
    environ.update(dict.fromkeys(BLAS, "1"))
    if service == "transform":
        try:
            _set_pool(b.processes)
        except subprocess.CalledProcessError as e:
            # Airflow's database not reachable yet (a host restart starts containers without depends_on):
            # the container restarts and tries again (D10)
            print(
                f"budget.py: setting the pool transform failed ({e}); Celery not started",
                file=sys.stderr,
            )
            return 2
        command = [ENTRYPOINT, *command, "--concurrency", str(b.processes)]
    else:
        command = [*command, "--workers", str(b.processes)]
    os.execvpe(command[0], command, environ)
    return 1  # not reached


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
