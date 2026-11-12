"""Summary of one indexing-bench.sh run, from the files it collected in OUT (standard library only).

python3 report.py OUT
"""

import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

out = Path(sys.argv[1])
meta = dict(line.split("=", 1) for line in (out / "meta.env").read_text().split())
t0 = float(meta["t0"])
# the worker's real concurrency, from its command line (the bench's PROCESSES may be empty: the budget)
command = (
    (out / "worker-command.txt").read_text()
    if (out / "worker-command.txt").exists()
    else ""
)
found = re.search(r"--concurrency (\d+)", command)
concurrency = int(found.group(1)) if found else None


def rows(name: str) -> list[list[str]]:
    return [line.split("|") for line in (out / name).read_text().splitlines() if line]


def stats(xs: list[float]) -> str:
    if not xs:
        return "none"
    return f"n={len(xs)} min={min(xs):.1f} median={statistics.median(xs):.1f} max={max(xs):.1f} sum={sum(xs):.1f}"


# ------------------------------------------------------------------ runs and wall time
runs = {
    dag: (float(s), float(e) if e else None, state)
    for dag, s, e, state in rows("dagruns.txt")
}
h_start, h_end, h_state = runs["warehouse_harvest_and_index"]
t_start, t_end, t_state = runs.get("warehouse_transform_index", (None, None, "missing"))
count = json.loads((out / "count.json").read_text()).get("count")
print(
    f"run: N={meta['n']} CELERY_BATCH_SIZE={meta['batch']} concurrency={concurrency} "
    f"(PROCESSES={meta['conc'] or 'budget'} PERF_THREADS={meta.get('threads') or 'budget'} "
    f"PERF_TODAY={meta.get('today') or 0})  load at start: {meta['load']}"
)
if (out / "budget.txt").exists():
    print((out / "budget.txt").read_text().strip())
print(f"model pre-warm (download into the empty cache): {meta['prewarm_s']} s")
print(f"crawl: {float(meta['crawl_end']) - t0:.1f} s ({meta['crawl_summary']})")
print(f"harvest DAG: {h_state}; transform DAG: {t_state}")
print(f"records indexed (OpenSearch _count): {count}")
if t_end:
    wall = t_end - h_start
    print(
        f"harvest start -> indexing end: {wall:.1f} s = harvest {t_start - h_start:.1f} s + indexing {t_end - t_start:.1f} s"
    )
    print(
        f"records/s: {count / wall:.1f} overall, {count / (t_end - t_start):.1f} in the indexing"
    )

# ------------------------------------------------------------------ batches (Airflow's task instances)
tasks = defaultdict(list)
for dag, task, _map, state, queued, start, end in rows("tasks.txt"):
    if dag == "warehouse_transform_index" and start and end:
        tasks[task].append((float(queued or start), float(start), float(end), state))
for task in ("run_transform_batch", "run_filemeta_batch"):
    ts = sorted(tasks.get(task, []), key=lambda t: t[1])
    print(f"{task}: task durations (s) {stats([e - s for _, s, e, _ in ts])}")
    print(f"  queued -> started (s) {stats([s - q for q, s, _, _ in ts])}")
    if ts and task == "run_transform_batch" and t_end and concurrency:
        busy = sum(e - s for _, s, e, _ in ts)
        span = max(e for *_, e, _ in ts) - min(s for _, s, _, _ in ts)
        print(
            f"  first start -> last end {span:.1f} s; task-seconds / (span x concurrency) = "
            f"{busy / (span * concurrency):.0%} of the worker's slots busy"
        )
log = (out / "batch-log.txt").read_text()
ready = [
    float(x) for x in re.findall(r"Transform resources ready after ([\d.]+)s", log)
]
inside = [
    float(x)
    for x in re.findall(r"Transformed batch in ([\d.]+)s, (?!0 documents)", log)
]
print("in the batch process (task log lines):")
print(f"  model load (s) {stats(ready)}")
print(f"  transform_batch_impl, batches with documents (s) {stats(inside)}")

# ------------------------------------------------------------------ CPU per container
samples = defaultdict(list)  # service -> [(t, usage s)]
for line in (out / "cpu.tsv").read_text().splitlines():
    t, service, usec = line.split("\t")
    samples[service].append((float(t), int(usec) / 1e6))


def usage_at(xs: list[tuple[float, float]], t: float) -> float:
    """The last sample of xs at or before t (the first one if none)."""
    best = xs[0][1]
    for ts, u in xs:
        if ts > t:
            break
        best = u
    return best


windows = [("crawl", t0, float(meta["crawl_end"]))]
if t_end:
    windows += [("harvest", h_start, t_start), ("indexing", t_start, t_end)]
print("CPU seconds per container (cgroup cpu.stat usage_usec, sampled every 2 s):")
print(f"  {'container':26}" + "".join(f"{w:>11}" for w, _, _ in windows))
totals = defaultdict(float)
for service in sorted(samples):
    cells = []
    for w, a, b in windows:
        d = usage_at(samples[service], b) - usage_at(samples[service], a)
        totals[w] += d
        cells.append(d)
    if max(cells) >= 1:
        print(f"  {service:26}" + "".join(f"{c:11.1f}" for c in cells))
print(f"  {'all':26}" + "".join(f"{totals[w]:11.1f}" for w, _, _ in windows))
print(
    "  cores busy on average:   "
    + "".join(f"{totals[w] / max(b - a, 1e-9):11.2f}" for w, a, b in windows)
)
if (out / "pressure.tsv").exists():
    stalls = defaultdict(list)  # service -> [(t, stall s)]: cpu.pressure "some" total
    for line in (out / "pressure.tsv").read_text().splitlines():
        t, service, usec = line.split("\t")
        stalls[service].append((float(t), int(usec) / 1e6))
    print(
        "CPU pressure per container (seconds some task waited for a CPU, cpu.pressure):"
    )
    for service, xs in sorted(stalls.items()):
        cells = [usage_at(xs, b) - usage_at(xs, a) for _, a, b in windows]
        if max(cells) >= 0.5:
            print(f"  {service:26}" + "".join(f"{c:11.1f}" for c in cells))
if (out / "load.tsv").exists():
    loads = [
        tuple(map(float, line.split("\t")))
        for line in (out / "load.tsv").read_text().splitlines()
    ]
    print(
        "  1-min load average, max:  "
        + "".join(
            f"{max((v for t, v in loads if a <= t <= b), default=float('nan')):11.2f}"
            for w, a, b in windows
        )
    )

# ------------------------------------------------------------------ batch processes (probe)
probe = out / "probe"
if (probe / "batches.json").exists():
    data = json.loads((probe / "batches.json").read_text())
    bs = [b for b in data["batches"] if b.get("life_s", 0) > 0]
    print(
        f"batch processes in the transform worker: {len(bs)}, at most {data['max_parallel']} at once"
    )
    print(f"  life (s) {stats([b['life_s'] for b in bs])}")
    print(f"  CPU (s) {stats([b['cpu_s'] for b in bs])}")
    print(f"  main thread CPU (s) {stats([b['main_thread_cpu_s'] for b in bs])}")
    print(f"  other threads CPU (s) {stats([b['other_threads_cpu_s'] for b in bs])}")
    print(f"  threads at most: {sorted({b['max_threads'] for b in bs})}")
    envs = sorted({json.dumps(b.get("environ", {}), sort_keys=True) for b in bs})
    print(f"  thread variables (from /proc/PID/environ): {', '.join(envs)}")
    mib = [b["VmHWM_kb"] / 1024 for b in bs if "VmHWM_kb" in b]
    print(f"  peak RSS, VmHWM (MiB) {stats(mib)}")
    task_s = sum(e - s for _, s, e, _ in tasks.get("run_transform_batch", []))
    life_s = sum(b["life_s"] for b in bs)
    print(
        f"  Airflow's share of the tasks: task durations {task_s:.1f} s - batch process lives {life_s:.1f} s "
        f"= {task_s - life_s:.1f} s ({(task_s - life_s) / max(task_s, 1e-9):.0%}; task runner, version check, "
        f"script setup; the probe polls every 0.05 s)"
    )
    prof = next((b for b in bs if "profiled" in b), None)
    if prof:
        print(
            f"  profiled batch #{prof['n']}: life {prof['life_s']} s, CPU {prof['cpu_s']} s "
            f"(main thread {prof['main_thread_cpu_s']}, others {prof['other_threads_cpu_s']}), "
            f"py-spy attached {prof['profiled']['attached_after_s']} s after the process start"
        )
        print(
            f"  its busiest other threads [CPU s, name, allowed CPUs]: {prof['other_threads'][:12]}"
        )

# ------------------------------------------------------------------ profile by phase
PHASES = [  # first match wins; on the whole stack (frames joined by ";")
    (
        "embedding inference (ONNX session.run)",
        lambda s: "onnx_embed (fastembed" in s and "onnxruntime" in s,
    ),
    ("tokenization", lambda s: "tokenize (fastembed" in s),
    ("embedding, rest (fastembed post-processing)", lambda s: "embed (fastembed" in s),
    ("model load (TransformResources)", lambda s: "__init__ (transform_core.py" in s),
    ("DB read (load_batch)", lambda s: "load_batch" in s),
    (
        "OpenSearch writes (bulk, index check)",
        lambda s: "transform_batch_impl" in s and "opensearchpy" in s,
    ),
    (
        "DB writes (records, harvest_events)",
        lambda s: "transform_batch_impl" in s and "psycopg" in s,
    ),
    # deep jsonschema stacks come without their root frames (py-spy's depth limit)
    ("validation (jsonschema)", lambda s: "jsonschema" in s or "referencing" in s),
    ("text preparation (XML, normalize)", lambda s: "transform_batch_impl" in s),
    ("imports", lambda s: "_find_and_load" in s),
    ("no Python frame (start, exit, idle)", lambda s: not s.strip()),
    ("other (task wrapper, interpreter)", lambda s: True),
]
raw = probe / "profile.raw"
if raw.exists() and raw.stat().st_size:
    phase = defaultdict(int)
    for line in raw.read_text().splitlines():
        stack, _, n = line.rpartition(" ")
        if not n.isdigit():
            continue
        name = next(p for p, match in PHASES if match(stack))
        phase[name] += int(n)
    total = sum(phase.values())
    spy_log = (
        (probe / "py-spy.log").read_text() if (probe / "py-spy.log").exists() else ""
    )
    m = re.search(r"Samples: (\d+) Errors: (\d+)", spy_log)
    lost = f", {m[2]} samples lost to read errors" if m else ""
    print(
        f"profile of one batch process by phase (py-spy --idle --nonblocking, main thread, "
        f"{total} samples at 100 Hz{lost}):"
    )
    for name, _ in PHASES:
        if phase[name]:
            print(f"  {name:45} {phase[name] / 100:7.2f} s  {phase[name] / total:6.1%}")
