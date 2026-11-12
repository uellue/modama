"""Probe of the indexing batches in the transform worker: every batch process's life, CPU, threads and memory
(the largest VmRSS, VmHWM and VmSize seen, in kB), and a `py-spy record` of one of them.

Run inside airflow-worker-transform, reading this file from stdin (standard library only, writes only to OUT):
  docker compose exec -T airflow-worker-transform python3 - OUT [PROFILE_NTH] [PY_SPY_ARGS...] < perf/batch-probe.py
It watches for processes of the transform venv's Python (one per batch, `@task.external_python`), polls each
one's threads every POLL seconds, and attaches `py-spy record` to the PROFILE_NTH batch process (default 2:
the first may pay for cold caches). It stops when the file OUT/stop exists (the bench creates it when the
indexing run has ended) or after MAX_HOURS, and then writes OUT/batches.json (with each batch's thread variables
from its /proc/PID/environ, which a probe started with `docker compose exec` does not see otherwise), and
OUT/profile.raw and OUT/py-spy.log.
"""

import json
import os
import signal
import subprocess
import sys
import time

OUT = sys.argv[1]
PROFILE_NTH = int(sys.argv[2]) if len(sys.argv) > 2 else 2
# --nonblocking: py-spy's default pauses the process for every sample, which made a test embedding
# of 2,000 texts take 5.6 s instead of 3.2 s (ONNX Runtime's thread pool); --idle: waits count too
PY_SPY_ARGS = sys.argv[3:] or ["--idle", "--nonblocking", "--rate", "100"]
PYTHON = "/opt/airflow/transform-venv/bin/python"
PY_SPY = "/home/airflow/.local/bin/py-spy"
POLL = 0.05
MAX_HOURS = 4
TICK = os.sysconf("SC_CLK_TCK")
ME = os.getpid()


def read(path: str) -> str:
    with open(path) as f:
        return f.read()


def stat_fields(path: str) -> list[str]:
    s = read(path)
    return s[s.rindex(")") + 2 :].split()  # [0] is field 3 (state)


def uptime() -> float:
    return float(read("/proc/uptime").split()[0])


def batch_pids() -> list[int]:
    pids = []
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == ME:
            continue
        try:
            with open(f"/proc/{name}/cmdline", "rb") as f:
                cmd = f.read().split(b"\0")
        except OSError:
            continue
        # Airflow's ExternalPythonOperator first runs `python -c ...` for the version: not a batch
        if cmd and cmd[0].decode(errors="replace") == PYTHON and b"-c" not in cmd:
            pids.append(int(name))
    return pids


def memory(pid: int) -> dict[str, int]:
    """VmRSS, VmHWM (peak RSS) and VmSize of pid, in kB."""
    return {
        line.split(":")[0]: int(line.split()[1])
        for line in read(f"/proc/{pid}/status").splitlines()
        if line.startswith(("VmRSS", "VmHWM", "VmSize"))
    }


THREAD_VARIABLES = (
    "EMBEDDING_THREADS",
    "RAYON_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
)


def environ(pid: int) -> dict[str, str]:
    """The thread variables of the CPU budget in pid's environment (README, "CPU budget")."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            pairs = (
                item.decode(errors="replace").partition("=")
                for item in f.read().split(b"\0")
            )
            return {k: v for k, _, v in pairs if k in THREAD_VARIABLES}
    except OSError:
        return {}


def threads(pid: int) -> dict[int, tuple[float, str, str]]:
    """tid -> (cpu seconds, comm, allowed CPUs) of every thread of pid."""
    out = {}
    for tid in os.listdir(f"/proc/{pid}/task"):
        try:
            f = stat_fields(f"/proc/{pid}/task/{tid}/stat")
            comm = read(f"/proc/{pid}/task/{tid}/comm").strip()
            allowed = next(
                line.split()[1]
                for line in read(f"/proc/{pid}/task/{tid}/status").splitlines()
                if line.startswith("Cpus_allowed_list")
            )
        except (OSError, StopIteration):
            continue
        out[int(tid)] = ((int(f[11]) + int(f[12])) / TICK, comm, allowed)
    return out


os.makedirs(OUT, exist_ok=True)
seen: dict[int, dict] = {}  # pid -> record
order: list[int] = []
spy = None
deadline = time.monotonic() + MAX_HOURS * 3600
max_parallel = 0
while not os.path.exists(f"{OUT}/stop") and time.monotonic() < deadline:
    live = batch_pids()
    max_parallel = max(max_parallel, len(live))
    now_up, now = uptime(), time.time()
    for pid in live:
        rec = seen.get(pid)
        if rec is None:
            try:
                start_ticks = int(stat_fields(f"/proc/{pid}/stat")[19])
            except OSError:
                continue
            age = now_up - start_ticks / TICK
            rec = seen[pid] = {
                "pid": pid,
                "n": len(order) + 1,
                "start": now - age,
                "seen_after_s": round(age, 3),
                "environ": environ(pid),
            }
            order.append(pid)
            if rec["n"] == PROFILE_NTH and spy is None:
                raw = f"{OUT}/profile.raw"
                cmd = [
                    PY_SPY,
                    "record",
                    *PY_SPY_ARGS,
                    "--format",
                    "raw",
                    "-o",
                    raw,
                    "--pid",
                    str(pid),
                ]
                spy = subprocess.Popen(
                    cmd,
                    # open for py-spy's whole life, which outlasts this block; closed when the probe exits
                    stdout=open(f"{OUT}/py-spy.log", "w"),  # noqa: SIM115
                    stderr=subprocess.STDOUT,
                )
                rec["profiled"] = {
                    "attached_after_s": round(time.time() - rec["start"], 3),
                    "cmd": cmd,
                }
        try:
            th = threads(pid)
        except OSError:
            continue  # ended between listing and reading
        try:
            f = stat_fields(
                f"/proc/{pid}/stat"
            )  # the whole process, threads that have ended included
            rec["process_cpu_s"] = (int(f[11]) + int(f[12])) / TICK
            vm = memory(pid)
        except OSError:
            continue
        # the largest seen; VmHWM is the kernel's own peak, so the last poll is the closest to the end
        for key, value in vm.items():
            rec[f"{key}_kb"] = max(rec.get(f"{key}_kb", 0), value)
        if th:
            rec["end"] = time.time()
            # per thread, the last poll before the end is the closest to the total
            rec.setdefault("threads", {}).update(th)
            rec["max_threads"] = max(rec.get("max_threads", 0), len(th))
    time.sleep(POLL)

if spy is not None:
    try:
        spy.wait(timeout=30)
    except subprocess.TimeoutExpired:
        spy.send_signal(
            signal.SIGINT
        )  # py-spy writes its output on SIGINT, not on SIGTERM
        spy.wait()

batches = []
for pid in order:
    rec = seen[pid]
    th = rec.pop("threads", {})
    main = th.get(pid, (0.0, "", ""))[0]
    others = sorted(
        (
            (cpu, comm, allowed)
            for tid, (cpu, comm, allowed) in th.items()
            if tid != pid
        ),
        reverse=True,
    )
    rec.update(
        life_s=round(rec.get("end", rec["start"]) - rec["start"], 2),
        cpu_s=round(rec.pop("process_cpu_s", 0.0), 2),
        main_thread_cpu_s=round(main, 2),
        other_threads_cpu_s=round(sum(c for c, _, _ in others), 2),
        # the busiest other threads: cpu, name, allowed CPUs (ONNX Runtime pins its pool threads to cores)
        other_threads=[
            [round(c, 2), comm, allowed] for c, comm, allowed in others if c > 0.05
        ],
    )
    batches.append(rec)
with open(f"{OUT}/batches.json", "w") as f:
    json.dump({"max_parallel": max_parallel, "batches": batches}, f, indent=1)
print(
    f"{len(batches)} batch processes, at most {max_parallel} at once; profiled: #{PROFILE_NTH}"
)
