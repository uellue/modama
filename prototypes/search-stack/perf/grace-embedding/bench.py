"""Embedding throughput of the warehouse's model (fastembed, BAAI/bge-small-en-v1.5, ONNX
Runtime) on CPU and GPU, each searched for its own optimum. Run by run.sh; the
subcommands, each with the Python of the venv it measures:

  bench.py cpu  MODE OUT LABEL  CPU sweep: processes x threads, pinned or not, sub-batch,
                                sorted or not; model files, session options, one
                                shared session, memory sharing
  bench.py gpu  MODE OUT LABEL [--force]
                                checks the GPU and its vectors, reruns the best CPU case
                                of each set with this venv's runtime, then the GPU sweep:
                                concurrent workers x batch size, token budgets, threads
                                on one session, float32 against float16
  bench.py gpu-check [--force]  only the GPU checks (nvidia-smi, CUDA provider, no other
                                process on the GPU, a session on the GPU)

The GPU part stops when another process uses the GPU (nvidia-smi's compute apps, checked
before every case), unless --force. Its workers' ONNX Runtime arenas together may take
GPU_MEM_FRACTION (environment, default 0.5) of the GPU's memory, and no batch has more
than MAX_BATCH_TOKENS tokens at the set's longest text.
  bench.py report OUT           the table, OUT/table.txt and OUT/summary.json (standard
                                library only)
  bench.py worker SPEC          one worker process (internal)
  bench.py tokenizer FILE       the tokenizer alone on FILE's texts (internal)

MODE is quick or full. OUT holds texts-{short,mixed,long}.jsonl (gen_texts.py) and
receives cases.jsonl, facts-LABEL.json, vectors-*.npy, checks.json and logs/. The model
variants come from prepare_model.py.

What production does (patch 0002 of the modama search stack, `_embed_locally`): the
texts of a transform batch (250 records) sorted by length, embedded in sub-batches of 32,
returned in the given order; one ONNX Runtime thread per process, 8 to 16 processes. A
worker here does the same with its share of the texts, a whole number of windows of 250
(SORT_WINDOW): sorts each window by length (or not), embeds it with `batch_size`, and
keeps the order; a GPU batch larger than a window takes consecutive sorted windows. The
timed part starts when all workers have loaded the model and warmed up.
"""

import json
import math
import os
import platform
import re
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from glob import glob
from pathlib import Path

MODEL = "BAAI/bge-small-en-v1.5"
HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("FASTEMBED_CACHE_DIR", HERE / "cache"))
VARIANTS = CACHE / "variants"  # prepare_model.py
SETS = ("short", "mixed", "long")
# the first texts of the mixed set: every variant's vectors compared on these
CHECK_TEXTS = 512
MIN_COSINE = 0.9999
PRODUCTION_SUB_BATCH = 32
# production's transform batch: texts are sorted by length within windows of this many,
# in every case (a worker's share is a whole number of windows)
SORT_WINDOW = 250
# GPU: no batch of more tokens than this (batch x the set's longest text)
MAX_BATCH_TOKENS = 2**20  # the long set: 2048 texts of 512
# GPU: the share of the GPU's memory all workers' ONNX Runtime arenas together may take
GPU_MEM_FRACTION = float(os.environ.get("GPU_MEM_FRACTION", "0.5"))
# a step counts as better only if it raises texts/s by more than 3 %
GAIN = 1.03
PERF_EVENTS = (
    "cycles,instructions,cache-references,cache-misses,LLC-loads,LLC-load-misses"
)
NO_PREPACK = {"session.disable_prepacking": "1"}
BF16 = {"mlas.enable_gemm_fastmath_arm64_bfloat16": "1"}  # aarch64 only

MODES = {
    "quick": {
        # the timed part of a case takes at least about this long
        "seconds": 3,
        # short texts, larger sub-batches: at the best composition
        "short_sub_batches": (128,),
        # every set, other sub-batches: at the best case
        "cpu_sub_batches": (),
        # model files, session options, one shared session: on these sets
        "variant_sets": ("short",),
        # memory of the shared model file: at these numbers of processes (C: all cores)
        "memory_processes": (1, "C"),
        "memory_variants": ({"model": "fp32"},),
        "gpu_workers": (1, 2, 4),
        "gpu_batches": (32, 256, 2048),
        "refine": False,
        "gpu_budgets": (16384,),
        "gpu_callers": (2,),
        "gpu_fp32_factors": (1,),
    },
    "full": {
        "seconds": 20,
        # at every composition that fills the machine
        "short_sub_batches": (128, 512),
        "cpu_sub_batches": (16, 64, 128, 256),
        "variant_sets": SETS,
        "memory_processes": (1, 8, "C"),
        "memory_variants": (
            {"model": "fp32"},
            {"model": "fp32", "options": NO_PREPACK},
        ),
        "gpu_workers": (1, 2, 4, 8, 16),
        "gpu_batches": (32, 128, 512, 2048, 8192, 32768),
        "refine": True,
        # tokens per batch (TEI's default is 16384)
        "gpu_budgets": (4096, 16384, 65536, 262144),
        "gpu_callers": (2, 4),
        "gpu_fp32_factors": (0.25, 1, 4),
    },
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- topology


def parse_cpulist(s: str) -> list[int]:
    out = []
    for part in s.strip().split(","):
        if part:
            a, _, b = part.partition("-")
            out.extend(range(int(a), int(b or a) + 1))
    return out


def topology() -> dict:
    """The usable CPUs, ordered by NUMA node and L3 domain (from sysfs), the domains,
    and the NUMA nodes that have memory but no CPUs (on a GH200: the GPU's)."""
    cpus = sorted(os.sched_getaffinity(0))
    node, l3, memory_only = {}, {}, []
    for d in sorted(glob("/sys/devices/system/node/node[0-9]*")):
        n = int(d.rsplit("node", 1)[1])
        listed = parse_cpulist(Path(d, "cpulist").read_text())
        node.update(dict.fromkeys(listed, n))
        if not listed and re.search(r"MemTotal:\s+[1-9]", read(f"{d}/meminfo")):
            memory_only.append(n)
    for c in cpus:
        shared = Path(f"/sys/devices/system/cpu/cpu{c}/cache/index3/shared_cpu_list")
        try:
            l3[c] = min(parse_cpulist(shared.read_text()))
        except (OSError, ValueError):
            l3[c] = -1  # not reported
    order = sorted(cpus, key=lambda c: (node.get(c, 0), l3[c], c))
    return {
        "cpus": order,
        "numa_nodes": sorted({node.get(c, 0) for c in cpus}),
        "numa_nodes_memory_only": memory_only,
        "l3_domains": sorted(set(l3.values())) if -1 not in l3.values() else [],
    }


def cores() -> int:
    return len(os.sched_getaffinity(0))


def read(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return "(unreadable)"


# ---------------------------------------------------------------- worker


def vm_hwm_kb() -> int:
    """Peak RSS of this process (ru_maxrss would include the parent's: it survives exec)."""
    with open("/proc/self/status") as f:
        return next(int(x.split()[1]) for x in f if x.startswith("VmHWM"))


def smaps() -> dict:
    """RSS, PSS (shared pages divided among their users) and USS (private pages) in MB."""
    kb = {}
    for line in read("/proc/self/smaps_rollup").splitlines()[1:]:
        k, _, v = line.partition(":")
        if v.strip().endswith("kB"):
            kb[k] = int(v.split()[0])
    uss = kb.get("Private_Clean", 0) + kb.get("Private_Dirty", 0)
    return {
        "rss": kb.get("Rss", 0) / 1024,
        "pss": kb.get("Pss", 0) / 1024,
        "pss_file": kb.get("Pss_File", 0) / 1024,
        "uss": uss / 1024,
    }


def load_model(ort, case: dict, gpu: bool):
    """fastembed's TextEmbedding, as production loads it; for a model variant or extra
    session options, with a session of our own in place of fastembed's (same tokenizer,
    same pre- and post-processing)."""
    from fastembed import TextEmbedding
    from fastembed.common.preprocessor_utils import load_tokenizer

    threads, name = case["threads"], case.get("model", "prod")
    providers = ["CPUExecutionProvider"]
    if gpu:
        # the arena's limit: what a CUDA out-of-memory error stops at, not the whole GPU
        cuda = {"gpu_mem_limit": case["gpu_mem_limit"]}
        providers = [("CUDAExecutionProvider", cuda)]
    if name == "prod" and not case.get("options"):
        return TextEmbedding(
            MODEL, cache_dir=str(CACHE), threads=threads, providers=providers
        )
    model = TextEmbedding(MODEL, cache_dir=str(CACHE), threads=threads, lazy_load=True)
    inner = model.model
    path = VARIANTS / f"model-{name}.onnx"
    if name == "prod":
        path = Path(inner._model_dir) / "model_optimized.onnx"
    so = ort.SessionOptions()  # as fastembed sets it up
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.intra_op_num_threads = so.inter_op_num_threads = threads
    for k, v in (case.get("options") or {}).items():
        so.add_session_config_entry(k, v)
    inner.tokenizer, inner.special_token_to_id = load_tokenizer(Path(inner._model_dir))
    inner.model = ort.InferenceSession(str(path), sess_options=so, providers=providers)
    return model


def batches_of(order: list[int], lengths: list[int], batch: int, budget: int | None):
    """Batches of `batch` texts, or (budget) as many texts as fit in `budget` tokens,
    each text counted at the batch's longest (the padding)."""
    if not budget:
        return [order[i : i + batch] for i in range(0, len(order), batch)]
    out, cur, longest = [], [], 0
    for i in order:
        if cur and (len(cur) + 1) * max(longest, lengths[i]) > budget:
            out.append(cur)
            cur, longest = [], 0
        cur.append(i)
        longest = max(longest, lengths[i])
    return [*out, cur] if cur else out


def windows_of(texts: list[str], sort: bool) -> list[list[int]]:
    """The indices in windows of SORT_WINDOW, each sorted by length if `sort`."""
    n = len(texts)
    out = [list(range(w, min(w + SORT_WINDOW, n))) for w in range(0, n, SORT_WINDOW)]
    if sort:
        for w in out:
            w.sort(key=lambda i: len(texts[i]))
    return out


def worker(spec: dict) -> None:
    """Load the model, warm up, wait for "go" on stdin, embed, print one JSON line; on
    "mem", print the memory."""
    if spec.get("cpus"):
        # before ONNX Runtime and the tokenizers start their threads, which inherit it
        os.sched_setaffinity(0, spec["cpus"])
    # as the CPU budget sets them (budget.py): the tokenizers' Rayon pool explicit,
    # BLAS and OpenMP at 1
    os.environ["RAYON_NUM_THREADS"] = str(spec["rayon"])
    for v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[v] = "1"
    import numpy as np
    import onnxruntime as ort

    gpu = spec["device"] == "gpu"
    if gpu and hasattr(ort, "preload_dlls"):
        # CUDA and cuDNN from the nvidia-* wheels in the venv, else the system's
        ort.preload_dlls()
    t0 = time.monotonic()
    model = load_model(ort, spec, gpu)
    load = time.monotonic() - t0
    providers = model.model.model.get_providers()
    if gpu and providers[0] != "CUDAExecutionProvider":
        msg = f"no session on the GPU: ONNX Runtime fell back to {providers}"
        raise RuntimeError(msg)

    with open(spec["texts"]) as f:
        pool = [json.loads(line)["text"] for line in f]
    k, p, n = spec["index"], spec["processes"], spec["n"]
    texts = [pool[(k + j * p) % len(pool)] for j in range(n)]
    windows = windows_of(texts, spec["sorted"])
    order = [i for w in windows for i in w]
    b, budget, callers = spec["batch"], spec.get("budget"), spec.get("callers", 1)
    lengths = []
    for i in range(0, n if budget else 0, 1024):
        # token counts for the budget, before the timed part (in chunks: the tokenizer
        # pads each call's texts to its longest)
        enc = model.model.tokenizer.encode_batch(texts[i : i + 1024])
        lengths += [sum(e.attention_mask) for e in enc]
    if budget or b > SORT_WINDOW:
        # by tokens, or a GPU batch of several windows: across windows
        batches = batches_of(order, lengths, b, budget)
    else:  # production's sub-batches, within a window
        batches = [w[i : i + b] for w in windows for i in range(0, len(w), b)]

    # warm-up: the batch with the most tokens (the longest texts), the largest shapes
    t0 = time.monotonic()
    widest = max(batches, key=lambda x: len(x) * max(len(texts[i]) for i in x))
    list(model.embed([texts[i] for i in widest], batch_size=len(widest)))
    warmup = time.monotonic() - t0

    print(json.dumps({"ready": True}), flush=True)
    sys.stdin.readline()
    # the vectors are kept only for a check, not in a timed case (they would take memory)
    vectors = [None] * n if spec.get("save") else None

    def keep(indices: list[int], got) -> None:
        for i, v in zip(indices, got, strict=True):
            if vectors is not None:
                vectors[i] = v

    def embed(mine: list[list[int]]) -> None:
        for batch in mine:
            keep(batch, model.embed([texts[i] for i in batch], batch_size=len(batch)))

    c0, w0 = time.process_time(), time.time()
    if not budget and callers == 1 and b <= SORT_WINDOW:
        # production's call: one embed per window (transform batch)
        for w in windows:
            keep(w, model.embed([texts[i] for i in w], batch_size=b))
    elif callers == 1:
        embed(batches)
    else:  # threads calling one session (Run() is thread-safe in ONNX Runtime)
        with ThreadPoolExecutor(callers) as ex:
            list(ex.map(embed, [batches[c::callers] for c in range(callers)]))
    w1, c1 = time.time(), time.process_time()
    if vectors is not None:
        np.save(spec["save"], np.stack(vectors))
    done = {
        "start": w0,
        "end": w1,
        "cpu_s": c1 - c0,
        "load_s": load,
        "warmup_s": warmup,
        "rss_kb": vm_hwm_kb(),
        "providers": providers,
    }
    print(json.dumps(done), flush=True)
    sys.stdin.readline()  # "mem": while all workers are still there
    print(json.dumps(smaps()), flush=True)


def tokenizer_rate(path: str) -> None:
    """Texts/s of the model's tokenizer alone, in batches of 32 and 1024 (RAYON_NUM_THREADS
    set by the caller)."""
    from fastembed import TextEmbedding
    from fastembed.common.preprocessor_utils import load_tokenizer

    model = TextEmbedding(MODEL, cache_dir=str(CACHE), lazy_load=True)
    tok, _ = load_tokenizer(Path(model.model._model_dir))
    with open(path) as f:
        texts = [json.loads(line)["text"] for line in f][:2000]
    out = {}
    for b in (32, 1024):
        tok.encode_batch(texts[:b])
        t0 = time.perf_counter()
        for i in range(0, len(texts), b):
            tok.encode_batch(texts[i : i + b])
        out[str(b)] = round(len(texts) / (time.perf_counter() - t0), 1)
    print(json.dumps(out))


# ---------------------------------------------------------------- sampling


def hwmon_sensors() -> dict[str, str]:
    """Grace's power telemetry (ACPI power meter in hwmon, NVIDIA's Grace performance
    tuning guide): label -> file of the mean power in microwatts."""
    found = {}
    for info in sorted(glob("/sys/class/hwmon/hwmon*/device/power1_oem_info")):
        avg = info.replace("power1_oem_info", "power1_average")
        try:
            label = Path(info).read_text().strip()
            int(Path(avg).read_text())
        except (OSError, ValueError):
            continue
        found[label] = avg
    return found


class Sampler:
    """Samples, while a case runs, nvidia-smi (GPU utilisation, memory, power) and the
    hwmon power sensors."""

    def __init__(self, gpu: bool):
        self.gpu, self.sensors = gpu, hwmon_sensors()
        self.smi: list[tuple[float, list[float | None]]] = []
        self.power: list[tuple[float, dict[str, float]]] = []
        self.stopped = threading.Event()
        self.threads: list[threading.Thread] = []
        self.proc = None

    def start(self) -> None:
        if self.gpu:
            query = "utilization.gpu,memory.used,power.draw"
            self.proc = subprocess.Popen(
                ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"]
                + ["-i", "0", "-lms", "200"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self.threads.append(threading.Thread(target=self._read_smi, daemon=True))
        if self.sensors:
            self.threads.append(threading.Thread(target=self._read_hwmon, daemon=True))
        for t in self.threads:
            t.start()

    def _read_smi(self) -> None:
        for line in self.proc.stdout:
            vals = []
            for x in line.split(","):
                try:
                    vals.append(float(x))
                except ValueError:  # [N/A]
                    vals.append(None)
            self.smi.append((time.time(), vals))

    def _read_hwmon(self) -> None:
        while not self.stopped.wait(0.2):
            d = {}
            for label, path in self.sensors.items():
                try:
                    d[label] = int(Path(path).read_text()) / 1e6
                except (OSError, ValueError):
                    pass
            self.power.append((time.time(), d))

    def stop(self) -> None:
        self.stopped.set()
        if self.proc:
            self.proc.terminate()
            self.proc.wait()
        for t in self.threads:
            t.join(timeout=2)

    def summary(self, start: float, end: float) -> dict:
        out: dict = {}
        smi = [v for t, v in self.smi if start <= t <= end and len(v) == 3]
        if smi:
            util, mem, pw = ([x for x in col if x is not None] for col in zip(*smi))
            out["gpu"] = {
                "samples": len(smi),
                "util_mean": round(statistics.mean(util), 1) if util else None,
                "util_max": max(util) if util else None,
                "mem_max_mib": max(mem) if mem else None,
                "power_mean_w": round(statistics.mean(pw), 1) if pw else None,
            }
        pw = [d for t, d in self.power if start <= t <= end]
        if pw:
            out["hwmon_w"] = {
                label: round(statistics.mean(d[label] for d in pw if label in d), 1)
                for label in self.sensors
                if any(label in d for d in pw)
            }
        return out


def perf_problem() -> str | None:
    """Whether `perf stat` can count this user's processes: None if it can, else why
    not."""
    if not shutil.which("perf"):
        return "perf is not installed"
    p = subprocess.run(
        ["perf", "stat", "-x,", "-e", "cycles,instructions", "--", "true"],
        check=False,
        capture_output=True,
        text=True,
    )
    counted = [x for x in p.stderr.splitlines() if x.split(",")[0].strip().isdigit()]
    if p.returncode != 0 or not counted:
        paranoid = read("/proc/sys/kernel/perf_event_paranoid")
        return f"perf stat may not count here (perf_event_paranoid {paranoid})"
    return None


def parse_perf(text: str) -> dict:
    """perf stat -x, output: value,unit,event,...; '<not supported>' and '<not counted>'
    become None."""
    out = {}
    for line in text.splitlines():
        f = line.split(",")
        if len(f) >= 3 and not line.startswith("#") and f[2]:
            try:
                out[f[2].split(":")[0]] = int(float(f[0]))
            except ValueError:
                out[f[2].split(":")[0]] = None
    return out


# ---------------------------------------------------------------- one case


class GpuBusy(Exception):
    """Another process uses the GPU: the GPU part stops (unless --force)."""


class Context:
    def __init__(self, mode: str, out: Path, label: str, force: bool = False):
        self.mode, self.cfg, self.out, self.label = mode, MODES[mode], out, label
        self.force = force
        self.gpu_mem_mib = 0  # the GPU's total memory (GPU part)
        self.tokens: dict = {}  # the sets' token lengths (cpu_reference)
        self.cases = out / "cases.jsonl"
        (out / "logs").mkdir(exist_ok=True)
        self.count = 0
        self.runtime = runtime()
        self.topo = topology()
        self.perf_problem = perf_problem()
        # CPU workers' memory on the CPUs' nodes, where a node has memory but no CPUs
        # (on a GH200 the GPU's memory; NVIDIA's Grace tuning guide)
        self.membind = None
        if self.topo["numa_nodes_memory_only"] and shutil.which("numactl"):
            self.membind = ",".join(str(n) for n in self.topo["numa_nodes"])


def dist(name: str) -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(name)
    except PackageNotFoundError:
        return None


def runtime() -> str:
    import onnxruntime as ort

    name = "onnxruntime-gpu" if dist("onnxruntime-gpu") else "onnxruntime"
    return f"{name} {ort.__version__}"


def run_once(ctx: Context, case: dict, n: int, save: str | None = None) -> dict:
    """Start the case's workers, time the embedding of n texts over all of them, return
    the measurement."""
    p, t, gpu = case["processes"], case["threads"], case["device"] == "gpu"
    ctx.count += 1
    name = f"{ctx.label}-{ctx.count:03d}-{case['device']}-{case['set']}"
    logf = ctx.out / "logs" / f"{name}.log"
    perf_file = logf.with_suffix(".perf")
    per = math.ceil(n / p)
    result = dict(case, runtime=ctx.runtime, venv=ctx.label, texts=per * p)
    result["sort_window"] = SORT_WINDOW
    if gpu:
        # all workers' arenas together: GPU_MEM_FRACTION of the GPU's memory
        limit = int(GPU_MEM_FRACTION * ctx.gpu_mem_mib * 2**20 / p)
        case = dict(case, gpu_mem_limit=limit)
        result["gpu_mem_limit"] = limit
    result["log"] = str(logf.relative_to(ctx.out))
    result["loadavg_before"] = os.getloadavg()[0]
    bind = not gpu and ctx.membind and case.get("membind", True)
    if bind:
        result["membind"] = ctx.membind
    prefix = ["numactl", f"--membind={ctx.membind}"] if bind else []
    procs = []
    with open(logf, "w") as err:
        for k in range(p):
            spec = dict(
                case,
                index=k,
                n=per,
                # the tokenizers: the case's threads; a GPU worker's: its share of the cores
                rayon=t * case.get("callers", 1) if not gpu else max(1, cores() // p),
                texts=str(ctx.out / f"texts-{case['set']}.jsonl"),
                save=save,
                cpus=ctx.topo["cpus"][k * t : (k + 1) * t]
                if case.get("pinned")
                else None,
            )
            procs.append(
                subprocess.Popen(
                    [*prefix, sys.executable, __file__, "worker", json.dumps(spec)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=err,
                    text=True,
                )
            )
        sampler = Sampler(gpu)
        perf = None

        def ask(proc, line: str, expect: str) -> dict:
            if line:
                proc.stdin.write(line)
                proc.stdin.flush()
            got = proc.stdout.readline()
            if not got.startswith(expect):
                raise RuntimeError(got)
            return json.loads(got)

        try:
            for proc in procs:
                ask(proc, "", '{"ready"')
            if not gpu and not ctx.perf_problem:
                pids = ",".join(str(x.pid) for x in procs)
                perf = subprocess.Popen(
                    ["perf", "stat", "-x,", "-o", str(perf_file), "-e", PERF_EVENTS]
                    + ["-p", pids],
                    stderr=err,
                )
                time.sleep(0.5)  # attached before the timed part
            sampler.start()
            for proc in procs:
                proc.stdin.write("go\n")
                proc.stdin.flush()
            res = [ask(proc, "", '{"start"') for proc in procs]
            sampler.stop()
            if perf:
                perf.send_signal(signal.SIGINT)
                perf.wait()
            mem = [ask(proc, "mem\n", '{"rss"') for proc in procs]
        except RuntimeError:
            time.sleep(0.5)  # let the worker that failed finish its message
            # SIGKILL before ours: on Linux usually the kernel's out-of-memory killer
            killed = any(proc.poll() == -signal.SIGKILL for proc in procs)
            for proc in procs:
                proc.kill()
            for proc in procs:
                proc.wait()
            sampler.stop()
            if perf:
                perf.kill()
            err.flush()
            text = logf.read_text()
            lines = [x for x in text.strip().splitlines() if x.strip()]
            mine = [x for x in lines if x.startswith("worker error:")]
            if killed:
                mine = ["a worker was killed (SIGKILL), probably for lack of memory"]
            last = (mine or lines or ["a worker ended without a message"])[-1]
            result["error"] = last[:600]
            oom = r"out of memory|Failed to allocate|bad_alloc|SIGKILL"
            result["oom"] = bool(
                re.search(oom, "\n".join([text, *mine]), re.IGNORECASE)
            )
            return result
        for proc in procs:
            proc.wait()
    start, end = min(r["start"] for r in res), max(r["end"] for r in res)
    wall = end - start
    cpu = sum(r["cpu_s"] for r in res)
    result.update(
        wall_s=round(wall, 3),
        texts_per_s=round(result["texts"] / wall, 2),
        wall_ms_per_text=round(1000 * wall / result["texts"], 3),
        cpu_s=round(cpu, 2),
        cpu_ms_per_text=round(1000 * cpu / result["texts"], 2),
        load_s=round(max(r["load_s"] for r in res), 2),
        warmup_s=round(max(r["warmup_s"] for r in res), 2),
        rss_max_mb=round(max(r["rss_kb"] for r in res) / 1024),
        # at the end of the timed part, all workers alive: mean per process
        mem_mb={k: round(statistics.mean(m[k] for m in mem)) for k in mem[0]},
        providers=res[0]["providers"],
        **sampler.summary(start, end),
    )
    if perf and perf_file.exists():
        # attached half a second before "go", until all are done
        result["perf"] = parse_perf(perf_file.read_text())
    lines = logf.read_text().splitlines()
    warnings = sorted(
        {x.strip() for x in lines if re.search(r"\bW:|warn", x, re.IGNORECASE)}
    )
    if warnings:
        result["warnings"] = warnings[:5]
    return result


def variant(case: dict) -> str:
    """The model file and session options, e.g. 'prod', 'fp32 noprepack'."""
    opts = case.get("options") or {}
    flags = ["noprepack" if k == "session.disable_prepacking" else "bf16" for k in opts]
    return " ".join([case.get("model", "prod"), *flags])


def describe(case: dict) -> str:
    """One line for the log and the table: shape, batch, order, variant."""
    if case["device"] == "cpu":
        shape = f"{case['processes']}x{case['threads']}"
        if case.get("pinned"):
            shape += " pinned"
    else:
        shape = f"{case['processes']} workers"
    if case.get("callers", 1) > 1:
        shape += f", {case['callers']} threads on 1 session"
    batch = (
        f"budget {case['budget']}" if case.get("budget") else f"batch {case['batch']}"
    )
    order = "sorted" if case["sorted"] else "given order"
    extra = "" if case.get("membind", True) else ", memory not bound"
    return f"{case['device']} {case['set']:5} {variant(case):14} {shape:>13} {batch:>12} {order}{extra}"


def measure(ctx: Context, case: dict, rate_estimate: float | None) -> dict:
    """One case, with enough texts for about ctx's seconds; again with more texts while
    it was too short."""
    seconds = ctx.cfg["seconds"]
    p = case["processes"]
    each = 2 * case["batch"] if not case.get("budget") else case["budget"] // 8

    def texts(want: float) -> int:
        # a whole number of sort windows per worker, at least one
        return p * SORT_WINDOW * max(1, math.ceil(want / (p * SORT_WINDOW)))

    n_min = texts(p * each)
    n = max(n_min, texts(rate_estimate * seconds)) if rate_estimate else n_min
    for attempt in range(1, 4):
        if case["device"] == "gpu" and not ctx.force and (others := gpu_others()):
            raise GpuBusy("; ".join(others))
        r = run_once(ctx, case, n)
        r["attempt"] = attempt
        if "error" in r or r["wall_s"] >= seconds / 2 or attempt == 3:
            break
        n = max(n_min, texts(r["texts_per_s"] * seconds * 1.1))
    with open(ctx.cases, "a") as f:
        f.write(json.dumps(r) + "\n")
    if "error" in r:
        what = "OUT OF MEMORY" if r["oom"] else "FAILED"
        log(f"  {describe(case)}: {what}: {r['error'][:300]}")
    else:
        g = r.get("gpu")
        extra = ""
        if g:
            extra = (
                f", GPU {g['util_mean']} % busy, {g['mem_max_mib']} MiB, "
                f"{g['power_mean_w']} W"
            )
        m = r["mem_mb"]
        log(
            f"  {describe(case)}: {r['texts_per_s']:9.1f} texts/s ({r['texts']} texts, "
            f"{r['wall_s']:.1f} s), CPU {r['cpu_ms_per_text']:.1f} ms/text, per process "
            f"peak {r['rss_max_mb']} MB, PSS {m['pss']} MB, USS {m['uss']} MB{extra}"
        )
    return r


def ok(results: list[dict]) -> list[dict]:
    return [r for r in results if "error" not in r]


def fastest(results: list[dict]) -> dict:
    return max(ok(results), key=lambda r: r["texts_per_s"])


KEYS = ("device", "set", "processes", "threads", "batch", "sorted", "pinned")
KEYS += ("model", "options", "callers", "budget", "membind")


def case_of(r: dict) -> dict:
    return {k: r[k] for k in KEYS if k in r and k != "membind" or r.get(k) is False}


def plain(results: list[dict]) -> list[dict]:
    """The cases of production's model and call: no variant, no callers, no budget."""
    keys = ("model", "options", "callers", "budget")
    return [r for r in ok(results) if not any(k in r for k in keys) and r["sorted"]]


# ---------------------------------------------------------------- CPU


def compositions(topo: dict, quick: bool) -> list[tuple[int, int]]:
    """Processes x threads: 1 x 1 first (one text on one core; the rate estimate for
    the rest), production's 8 and 16 processes of one thread, then the machine filled in
    different splits, including one process per L3 domain and per NUMA node."""
    c = len(topo["cpus"])
    pts = {(c, 1), (1, c)} | {(p, 1) for p in ((8,) if quick else (8, 16)) if p < c}
    if not quick:
        pts |= {(c // t, t) for t in (2, 4, 8) if c % t == 0 and c // t > 1}
        for domains in (topo["l3_domains"], topo["numa_nodes"]):
            if domains and c % len(domains) == 0:
                pts.add((len(domains), c // len(domains)))
    return [(1, 1), *sorted(pts - {(1, 1)})]


def mem_available_mb() -> float:
    with open("/proc/meminfo") as f:
        return next(int(x.split()[1]) for x in f if x.startswith("MemAvailable")) / 1024


def cpu_variants() -> list[dict]:
    """Model files and session options tried at the best layout: the float32 file
    (shared by mapping), without pre-packing, with bf16 fast math (aarch64), int8."""
    out = [{"model": "fp32"}, {"model": "fp32", "options": NO_PREPACK}]
    if platform.machine() == "aarch64":
        out.append({"model": "fp32", "options": BF16})
    return [*out, {"model": "int8"}]


def cpu_sweep(ctx: Context, set_name: str) -> list[dict]:
    log(f"CPU, {set_name} texts ({ctx.runtime})")
    c = len(ctx.topo["cpus"])
    results = []
    per_core = None

    def run(case: dict, estimate: float | None) -> dict:
        r = measure(ctx, case, estimate)
        results.append(r)
        return r

    def composition(p: int, t: int, **more) -> dict:
        case = {
            "device": "cpu",
            "set": set_name,
            "processes": p,
            "threads": t,
            "batch": PRODUCTION_SUB_BATCH,
            "sorted": True,
        }
        return run(case | more, per_core * p * t if per_core else None)

    # A: processes x threads, production's sub-batch, sorted, not pinned
    comps = compositions(ctx.topo, ctx.mode == "quick")
    for p, t in comps:
        r = composition(p, t)
        if (p, t) == (1, 1) and "error" not in r:
            per_core = r["texts_per_s"]
    if not ok(results):
        return results
    # B: the same, each process pinned to its own cores (in order of NUMA node and L3
    # domain); quick: only c x 1
    full = [(p, t) for p, t in comps if p * t == c and p > 1]
    for p, t in full[-1:] if ctx.mode == "quick" else full:
        composition(p, t, pinned=True)
    # C: short texts, larger sub-batches (more rows per pass over the weights): at every
    # composition that fills the machine, or (quick) at the best
    if set_name == "short":
        best = fastest(results)
        targets = [case_of(best)]
        if ctx.mode != "quick":
            targets = [
                case_of(r) for r in ok(results) if r["processes"] * r["threads"] == c
            ]
        for b in ctx.cfg["short_sub_batches"]:
            for case in targets:
                run(dict(case, batch=b), best["texts_per_s"])
    # D: other sub-batches at the best case, where they fit in memory
    best = fastest(results)
    same = case_of(best) | {"batch": 0}
    tried = {r["batch"] for r in results if case_of(r) | {"batch": 0} == same}
    for b in ctx.cfg["cpu_sub_batches"]:
        if b in tried:
            continue
        # the peak grows with the sub-batch, about linearly or less
        need = best["processes"] * best["rss_max_mb"] * b / best["batch"]
        free = mem_available_mb()
        if need > 0.7 * free:
            log(
                f"  sub-batch {b} skipped: about {need / 1024:.0f} GB, {free / 1024:.0f} GB free"
            )
            continue
        run(dict(case_of(best), batch=b), best["texts_per_s"])
    # E: the best in the given order (what sorting gains); without the memory binding
    best = fastest(results)
    run(dict(case_of(best), sorted=False), best["texts_per_s"])
    if ctx.membind:
        run(dict(case_of(best), membind=False), best["texts_per_s"])
    # F: model files and session options at the best case; one process, one session,
    # c threads calling it (one copy of the weights)
    if set_name in ctx.cfg["variant_sets"]:
        for v in cpu_variants():
            run(case_of(best) | v, best["texts_per_s"])
        one = case_of(best) | {
            "processes": 1,
            "threads": 1,
            "callers": c,
            "pinned": False,
        }
        run(one, best["texts_per_s"])
    # G: short texts, the memory of the float32 file mapped by 1, 8 and c processes
    if set_name == "short":
        for v in ctx.cfg["memory_variants"]:
            for p in sorted(
                {c if x == "C" else x for x in ctx.cfg["memory_processes"]}
            ):
                if p <= c:
                    composition(p, 1, **v)
    return results


def tokenizer_rates(ctx: Context) -> dict:
    """The tokenizer alone, per set: texts/s with 1 thread and with all cores."""
    out = {}
    for s in SETS:
        for threads in (1, cores()):
            env = dict(os.environ, RAYON_NUM_THREADS=str(threads))
            cmd = [
                sys.executable,
                __file__,
                "tokenizer",
                str(ctx.out / f"texts-{s}.jsonl"),
            ]
            p = subprocess.run(
                cmd, check=False, capture_output=True, text=True, env=env
            )
            got = p.stdout.strip().splitlines()[-1:] or ["{}"]
            out[f"{s}, {threads} threads"] = (
                json.loads(got[0]) if p.returncode == 0 else p.stderr[-300:]
            )
    return out


# ---------------------------------------------------------------- GPU


def gpu_case(set_name: str, workers: int, batch: int, **more) -> dict:
    # threads: ONNX Runtime's CPU threads in a GPU worker (for nodes left on the CPU)
    case = {
        "device": "gpu",
        "set": set_name,
        "processes": workers,
        "threads": 1,
        "batch": batch,
        "sorted": True,
    }
    return case | more


def gpu_sweep(ctx: Context, set_name: str) -> list[dict]:
    """Workers x batch size. For each number of workers the batch grows (x4) until
    texts/s rises by no more than 3 % or the GPU runs out of memory, then its neighbours
    (x2) around the best; more workers only while they raise the best by more than 3 %.
    Then at the best: token budgets, threads on one session, the float32 file, the
    given order."""
    log(f"GPU, {set_name} texts ({ctx.runtime})")
    results: list[dict] = []
    best_rate = None
    prev_best = 0.0
    longest = ctx.tokens[set_name]["max"]

    def fits(b: int) -> bool:
        return b * longest <= MAX_BATCH_TOKENS

    if not all(fits(b) for b in ctx.cfg["gpu_batches"]):
        log(
            f"  batches above {MAX_BATCH_TOKENS // longest} texts not tried: more than "
            f"{MAX_BATCH_TOKENS} tokens at the longest text, {longest} tokens"
        )
    for w in ctx.cfg["gpu_workers"]:
        tried: dict[int, dict] = {}
        limit = None  # the smallest batch that failed
        last = 0.0
        for b in filter(fits, ctx.cfg["gpu_batches"]):
            r = measure(ctx, gpu_case(set_name, w, b), best_rate)
            results.append(r)
            if "error" in r:
                limit = b
                break
            tried[b] = r
            best_rate = max(best_rate or 0, r["texts_per_s"])
            if r["texts_per_s"] <= last * GAIN:
                break
            last = r["texts_per_s"]
        if not tried:
            if w == ctx.cfg["gpu_workers"][0]:
                log("  the first GPU case failed: no sweep")
                return results
            break
        if ctx.cfg["refine"]:
            top = max(tried.values(), key=lambda r: r["texts_per_s"])["batch"]
            for b in (top // 2, top * 2):
                fresh = b >= 32 and b not in tried and fits(b)
                if fresh and (limit is None or b < limit):
                    r = measure(ctx, gpu_case(set_name, w, b), best_rate)
                    results.append(r)
                    if "error" not in r:
                        tried[b] = r
                        best_rate = max(best_rate, r["texts_per_s"])
        w_best = max(r["texts_per_s"] for r in tried.values())
        if w_best <= prev_best * GAIN:
            break
        prev_best = w_best
    if not ok(results):
        return results
    best = fastest(results)
    w, b, rate = best["processes"], best["batch"], best["texts_per_s"]
    for budget in ctx.cfg["gpu_budgets"]:
        results.append(measure(ctx, gpu_case(set_name, w, b, budget=budget), rate))
    for callers in ctx.cfg["gpu_callers"]:
        results.append(measure(ctx, gpu_case(set_name, 1, b, callers=callers), rate))
    for f in ctx.cfg["gpu_fp32_factors"]:
        if fits(int(b * f)):
            case = gpu_case(set_name, w, max(32, int(b * f)), model="fp32")
            results.append(measure(ctx, case, rate))
    results.append(measure(ctx, dict(case_of(best), sorted=False), rate))
    return results


def gpu_others() -> list[str]:
    """The processes on the GPU (nvidia-smi's compute apps), except an MPS server."""
    apps = "--query-compute-apps=pid,process_name,used_memory"
    got = run(["nvidia-smi", apps, "--format=csv,noheader"])
    return [x for x in got.splitlines() if x.strip() and "mps-server" not in x]


def gpu_check(force: bool = False) -> str | None:
    """The cheap checks before any GPU work; returns what is wrong, or None."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return (
            "no NVIDIA GPU visible: nvidia-smi is not on PATH. On grace, run `nvidia-smi` "
            "in this shell; in a container or a batch job the GPU has to be passed in "
            "(e.g. --gpus all, or the job's GPU request)."
        )
    p = subprocess.run([smi, "-L"], check=False, capture_output=True, text=True)
    if p.returncode != 0 or "GPU 0" not in p.stdout:
        said = (p.stdout + p.stderr).strip()[:300]
        return f"no NVIDIA GPU visible: `nvidia-smi -L` says: {said}"
    import onnxruntime as ort

    if dist("onnxruntime") and dist("onnxruntime-gpu"):
        return (
            "both onnxruntime and onnxruntime-gpu are installed in this venv; they share "
            "the module and the CPU package may win. Make a fresh venv-gpu with "
            "requirements-gpu.txt only."
        )
    available = ort.get_available_providers()
    if "CUDAExecutionProvider" not in available:
        return (
            f"this venv's ONNX Runtime has no CUDA provider ({runtime()}: {available}); "
            "it is the CPU build. Make venv-gpu with requirements-gpu.txt."
        )
    others = [] if force else gpu_others()
    if others:
        return (
            f"other processes use the GPU ({'; '.join(others)}). It is shared: run "
            "when it is free, or with --force."
        )
    return None


def gpu_mem_mib() -> int:
    """The GPU's total memory, MiB."""
    got = run(
        ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"]
    )
    return int(got.splitlines()[0])


def gpu_session_hint(error: str) -> str:
    return (
        f"the model did not start on the GPU: {error[:400]}\n"
        "Usual causes: the NVIDIA driver is older than 580 (onnxruntime-gpu 1.31.1 is "
        "built for CUDA 13; `nvidia-smi` shows the driver and its CUDA version at the "
        "top), or CUDA/cuDNN libraries are missing or of another major version (pip list "
        "| grep nvidia: nvidia-cuda-runtime 13.*, nvidia-cudnn-cu13 9.*). ONNX Runtime's "
        'own messages ("Failed to load ...") are above, or in the worker log.'
    )


def mps_state() -> str:
    """Whether NVIDIA's MPS daemon runs (started by the user; this script does not)."""
    p = subprocess.run(
        ["pgrep", "-l", "nvidia-cuda-mps"], check=False, capture_output=True, text=True
    )
    return p.stdout.strip() or "not running"


# ---------------------------------------------------------------- reference, checks, facts


def load_jsonl(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f]


def cpu_reference(ctx: Context) -> dict:
    """Model load time in one process, the sets' token lengths, and the CPU vectors of
    the check texts (as production embeds them: sorted in windows, sub-batch 32), with
    this venv's runtime."""
    import numpy as np
    from fastembed import TextEmbedding

    # the first load also downloads the model, before workers start in parallel
    t0 = time.monotonic()
    TextEmbedding(MODEL, cache_dir=str(CACHE), threads=cores(), cuda=False)
    load_first = time.monotonic() - t0
    t0 = time.monotonic()
    model = TextEmbedding(MODEL, cache_dir=str(CACHE), threads=cores(), cuda=False)
    load = time.monotonic() - t0
    texts = [r["text"] for r in load_jsonl(ctx.out / "texts-mixed.jsonl")[:CHECK_TEXTS]]
    vecs = [None] * len(texts)
    for w in windows_of(texts, sort=True):
        embedded = model.embed([texts[i] for i in w], batch_size=PRODUCTION_SUB_BATCH)
        for i, v in zip(w, embedded, strict=True):
            vecs[i] = v
    np.save(ctx.out / f"vectors-{ctx.label}-cpu.npy", np.stack(vecs))
    tokens = {}
    tok = model.model.tokenizer
    for s in SETS:
        enc = tok.encode_batch(
            [r["text"] for r in load_jsonl(ctx.out / f"texts-{s}.jsonl")]
        )
        # the attention mask: without the padding to the longest
        lengths = sorted(sum(e.attention_mask) for e in enc)
        tokens[s] = {
            "texts": len(lengths),
            "min": lengths[0],
            "median": lengths[len(lengths) // 2],
            "p90": lengths[int(len(lengths) * 0.9)],
            "max": lengths[-1],
            "at_512": round(sum(x >= 512 for x in lengths) / len(lengths), 3),
        }
    return {
        "model_load_s_first": round(load_first, 2),
        "model_load_s": round(load, 2),
        "tokens": tokens,
    }


def cosines(a, b) -> list[float]:
    import numpy as np

    return list(
        (a * b).sum(axis=1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
    )


def check_vectors(ctx: Context, case: dict) -> dict:
    """The case's model and options on the check texts, compared with production's CPU
    vectors (venv-cpu's, else this venv's): the minimum cosine; recorded in checks.json."""
    import numpy as np

    gpu = case["device"] == "gpu"
    name = f"{case['device']} {variant(case)} ({ctx.runtime})"
    save = str(
        ctx.out
        / f"vectors-{ctx.label}-{case['device']}-{variant(case).replace(' ', '-')}.npy"
    )
    probe = case_of(case) | {
        "set": "mixed",
        "processes": 1,
        "threads": 1 if gpu else cores(),
        "sorted": True,
        "pinned": False,
    }
    probe.pop("callers", None)
    probe.pop("budget", None)
    r = run_once(ctx, probe, CHECK_TEXTS, save=save)
    if "error" in r:
        got = {"error": r["error"], "log": r["log"]}
    else:
        ref = ctx.out / "vectors-cpu-cpu.npy"
        if not ref.exists():
            ref = ctx.out / f"vectors-{ctx.label}-cpu.npy"
        low = float(min(cosines(np.load(save), np.load(ref))))
        got = {"min": low, "passed": low >= MIN_COSINE, "reference": ref.name}
    record_check(ctx.out, name, got)
    return got


def record_check(out: Path, name: str, got: dict) -> None:
    path = out / "checks.json"
    checks = json.loads(path.read_text()) if path.exists() else {}
    checks.setdefault("min_cosine_required", MIN_COSINE)
    checks.setdefault("texts", f"the first {CHECK_TEXTS} of the mixed set")
    checks.setdefault("vectors", {})[name] = got
    write_json(path, checks)
    if "min" in got:
        verdict = "passed" if got["passed"] else f"BELOW {MIN_COSINE}"
        log(
            f"  vectors of {name}: min cosine {got['min']:.6f} to production's, {verdict}"
        )
    else:
        log(f"  vectors of {name}: not made: {got['error'][:200]}")


def run(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=30)
        return (p.stdout + p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"({cmd[0]}: {e})"


def facts(ctx: Context) -> dict:
    from importlib.metadata import distributions

    import onnxruntime as ort

    pkgs = {d.metadata["Name"].lower(): d.version for d in distributions()}
    keep = (
        "fastembed",
        "fastembed-gpu",
        "onnxruntime",
        "onnxruntime-gpu",
        "onnx",
        "tokenizers",
        "numpy",
        "huggingface-hub",
    )
    with open("/proc/meminfo") as f:
        mem_total = next(int(x.split()[1]) for x in f if x.startswith("MemTotal"))
    f = {
        "venv": ctx.label,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "glibc": " ".join(platform.libc_ver()),
        "cores_usable": cores(),
        "mem_total_gb": round(mem_total / 1024**2, 1),
        "loadavg": os.getloadavg(),
        "packages": {
            k: v
            for k, v in sorted(pkgs.items())
            if k in keep or k.startswith("nvidia-")
        },
        "ort_providers_available": ort.get_available_providers(),
        "lscpu": run(["lscpu"]),
        "lscpu_caches": run(["lscpu", "-C"]),
        "lscpu_cpus": run(["lscpu", "-e"]),
        "numactl_hardware": (
            run(["numactl", "--hardware"])
            if shutil.which("numactl")
            else "(numactl not installed)"
        ),
        "numa_balancing": read("/proc/sys/kernel/numa_balancing"),
        "topology": {
            "numa_nodes": ctx.topo["numa_nodes"],
            "numa_nodes_memory_only": ctx.topo["numa_nodes_memory_only"],
            "l3_domains": ctx.topo["l3_domains"],
            "cpu_order_for_pinning": ctx.topo["cpus"],
        },
        "membind": ctx.membind
        or (
            "not needed (no NUMA node with memory only)"
            if not ctx.topo["numa_nodes_memory_only"]
            else "not done: numactl is not installed"
        ),
        "perf": ctx.perf_problem or f"perf stat -e {PERF_EVENTS}, per CPU case",
        "hwmon_power_sensors": list(hwmon_sensors()),
        "model_files": {
            p.name: p.stat().st_size for p in sorted(VARIANTS.glob("model-*"))
        },
    }
    if shutil.which("nvidia-smi"):
        query = (
            "name,driver_version,memory.total,power.limit,clocks.max.sm,compute_mode"
        )
        f["nvidia_smi_L"] = run(["nvidia-smi", "-L"])
        f["nvidia_smi_gpu"] = run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv"]
        )
        m = re.search(r"CUDA Version:\s*(\S+)", run(["nvidia-smi"]))
        f["cuda_driver_version"] = m.group(1) if m else None
        apps = "--query-compute-apps=pid,process_name,used_memory"
        f["nvidia_smi_apps"] = run(["nvidia-smi", apps, "--format=csv"])
        f["mps"] = mps_state()
    return f


# ---------------------------------------------------------------- the parts


def part_cpu(mode: str, out: Path, label: str) -> None:
    ctx = Context(mode, out, label)
    write_json(
        out / f"facts-{label}.json",
        facts(ctx)
        | cpu_reference(ctx)
        | {"tokenizer_texts_per_s": tokenizer_rates(ctx)},
    )
    if ctx.perf_problem:
        log(f"No cache counters: {ctx.perf_problem}")
    results = []
    for s in SETS:
        results += cpu_sweep(ctx, s)
    log("CPU, the variants' vectors")
    done = set()
    for r in results:
        if ("model" in r or "options" in r) and variant(r) not in done:
            done.add(variant(r))
            check_vectors(ctx, r)


def part_gpu(mode: str, out: Path, label: str, force: bool) -> int:
    problem = gpu_check(force)
    if problem:
        log(f"GPU part not run: {problem}")
        record_check(out, "gpu", {"error": problem})
        return 3
    ctx = Context(mode, out, label, force)
    ctx.perf_problem = "not used in the GPU part"
    ctx.gpu_mem_mib = gpu_mem_mib()
    ref = cpu_reference(ctx)
    ctx.tokens = ref["tokens"]
    limits = {
        "gpu_mem_fraction": GPU_MEM_FRACTION,
        "max_batch_tokens": MAX_BATCH_TOKENS,
        "forced": force,
    }
    write_json(out / f"facts-{label}.json", facts(ctx) | ref | limits)
    try:
        return gpu_cases(ctx)
    except GpuBusy as e:
        log(f"GPU part stopped: other processes use the GPU ({e}); --force runs anyway")
        record_check(out, "gpu", {"error": f"stopped: other processes on the GPU: {e}"})
        return 5


def gpu_cases(ctx: Context) -> int:
    out, label = ctx.out, ctx.label

    # the check vectors on the GPU first: also the test that a session starts there
    log("GPU, the vectors")
    got = check_vectors(ctx, gpu_case("mixed", 1, PRODUCTION_SUB_BATCH))
    if "error" in got:
        log(
            f"GPU part not run: {gpu_session_hint(got['error'])} (log: {out / got['log']})"
        )
        return 4
    check_vectors(ctx, gpu_case("mixed", 1, PRODUCTION_SUB_BATCH, model="fp32"))
    ref = out / f"vectors-{label}-cpu.npy"
    if (out / "vectors-cpu-cpu.npy").exists():
        import numpy as np

        low = float(min(cosines(np.load(ref), np.load(out / "vectors-cpu-cpu.npy"))))
        name = f"cpu prod ({ctx.runtime})"
        record_check(out, name, {"min": low, "passed": low >= MIN_COSINE})

    # the best CPU case of each set again, with this venv's runtime (the CPU provider of
    # the GPU build)
    cases = load_jsonl(out / "cases.jsonl") if (out / "cases.jsonl").exists() else []
    for s in SETS:
        cpu = [c for c in plain(cases) if c["device"] == "cpu" and c["set"] == s]
        if cpu:
            log(f"CPU, {s} texts, the best case again ({ctx.runtime})")
            best = fastest(cpu)
            measure(ctx, case_of(best), best["texts_per_s"])
    for s in SETS:
        gpu_sweep(ctx, s)
    return 0


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=1, default=str) + "\n")


# ---------------------------------------------------------------- report (stdlib only)


def energy(r: dict) -> str:
    """J per text from the mean power while the case ran: the GPU's (nvidia-smi),
    Grace's sensors (hwmon)."""
    parts = []
    w = r.get("gpu", {}).get("power_mean_w")
    if w:
        parts.append(f"GPU {w * r['wall_s'] / r['texts']:.3f} J/text")
    for label, w in r.get("hwmon_w", {}).items():
        if label.startswith(("Module Power", "Grace Power")):
            parts.append(f"{label} {w * r['wall_s'] / r['texts']:.3f} J/text")
    return "; ".join(parts)


def perf_cols(r: dict) -> tuple[str, str]:
    """IPC and last-level cache misses per text (LLC-load-misses, else cache-misses)."""
    p = r.get("perf") or {}
    ipc = ""
    if p.get("instructions") and p.get("cycles"):
        ipc = f"{p['instructions'] / p['cycles']:.2f}"
    miss = p.get("LLC-load-misses") or p.get("cache-misses")
    return ipc, (f"{miss / r['texts'] / 1e3:.0f}k" if miss else "")


def vectors_of(checks: dict, r: dict) -> dict | None:
    return checks.get("vectors", {}).get(f"{r['device']} {variant(r)} ({r['runtime']})")


def vectors_ok(checks: dict, r: dict) -> bool:
    """Whether the case's vectors passed the check; production's file on the CPU without
    a check is the reference itself."""
    got = vectors_of(checks, r)
    if got is None:
        return r["device"] == "cpu" and variant(r) == "prod"
    return bool(got.get("passed"))


def check_of(checks: dict, r: dict) -> str:
    got = vectors_of(checks, r)
    if not got or "min" not in got:
        return ""
    return (
        f"; vectors: min cosine {got['min']:.6f}{'' if got['passed'] else ' (BELOW)'}"
    )


def headline_lines(
    cases: list[dict], tokens: dict, checks: dict
) -> tuple[list[str], dict]:
    lines = [
        "Best CPU against best GPU, each at its own optimum (texts/s; higher is better):",
        "the best case, the best with production's model file if another; apart, and not",
        "in the ratio: int8 (it changes every vector) and every variant whose vectors did",
        "not pass the check",
    ]
    counted = ("", " production's file")
    kinds = {
        "": lambda c: c.get("model") != "int8" and vectors_ok(checks, c),
        " production's file": lambda c: variant(c) == "prod" and vectors_ok(checks, c),
        " int8": lambda c: c.get("model") == "int8",
        " vectors not passed": lambda c: (
            c.get("model") != "int8" and not vectors_ok(checks, c)
        ),
    }
    headline = {}
    for s in SETS:
        tok = tokens.get(s, {})
        lines.append(
            f"{s} texts (tokens median {tok.get('median')}, max {tok.get('max')}, "
            f"{100 * tok.get('at_512', 0):.0f} % at 512):"
        )
        row = {}
        best_of: dict[str, list[dict]] = {"cpu": [], "gpu": []}  # in the ratio
        groups = sorted({(c["device"], c["venv"]) for c in cases})
        for device, venv in groups:
            for kind, wanted in kinds.items():
                mine = [
                    c
                    for c in ok(cases)
                    if (c["set"], c["device"], c["venv"]) == (s, device, venv)
                    and wanted(c)
                ]
                if not mine or fastest(mine) in row.values():
                    continue
                b = fastest(mine)
                key = f"{device} ({b['runtime']}){kind}"
                row[key] = b
                if kind in counted:
                    best_of[device].append(b)
                e = energy(b)
                lines.append(
                    f"  {device.upper()} {b['runtime']:24} {b['texts_per_s']:9.1f} texts/s  "
                    f"{describe(b).split(' ', 2)[2]}; CPU {b['cpu_ms_per_text']} ms/text"
                    + (f"; {e}" if e else "")
                    + check_of(checks, b)
                    + ("" if kind in counted else f"; apart:{kind}")
                )
        cpu, gpu = best_of["cpu"], best_of["gpu"]
        # (the ratio of the best cases; production's file is among them)
        if cpu and gpu:
            ratio = fastest(gpu)["texts_per_s"] / fastest(cpu)["texts_per_s"]
            lines.append(f"  best GPU / best CPU: {ratio:.1f}x")
        headline[s] = {
            "tokens": tok,
            "best": {
                k: case_of(b) | {"texts_per_s": b["texts_per_s"]}
                for k, b in row.items()
            },
        }
    return lines, headline


def case_line(c: dict) -> str:
    head = f"{c['runtime'][:25]:25} {describe(c):78} {c['texts']:>7}"
    if "error" in c:
        return f"{head} {'OUT OF MEMORY' if c.get('oom') else 'FAILED: ' + c['error'][:80]}"
    g = c.get("gpu", {})
    m = c.get("mem_mb", {})
    ipc, miss = perf_cols(c)
    note = "warnings in log" if c.get("warnings") else ""
    return (
        f"{head} {c['wall_s']:>6.1f} {c['texts_per_s']:>9.1f} {c['wall_ms_per_text']:>8.2f} "
        f"{c['cpu_ms_per_text']:>8.1f} {c['rss_max_mb']:>6} {m.get('pss', ''):>6} "
        f"{m.get('uss', ''):>6} {ipc:>5} {miss:>8} {g.get('util_mean', ''):>5} "
        f"{g.get('mem_max_mib', ''):>7} {g.get('power_mean_w', ''):>5}  {note}"
    )


def report(out: Path) -> None:
    cases = load_jsonl(out / "cases.jsonl") if (out / "cases.jsonl").exists() else []
    facts_ = {
        p.stem.removeprefix("facts-"): json.loads(p.read_text())
        for p in sorted(out.glob("facts-*.json"))
    }
    checks = {}
    if (out / "checks.json").exists():
        checks = json.loads((out / "checks.json").read_text())
    first = next(iter(facts_.values()), {})
    title = (
        f"Embedding benchmark, {MODEL}, {out.name}; {first.get('machine')}, "
        f"{first.get('cores_usable')} cores"
    )
    lines = [title]
    for label, f in facts_.items():
        pk = ", ".join(
            f"{k} {v}" for k, v in f["packages"].items() if not k.startswith("nvidia-")
        )
        lines.append(
            f"  {label}: Python {f['python']}, {pk}; model load {f['model_load_s']} s "
            "(one process)"
        )
    if first.get("nvidia_smi_gpu"):
        gpu = first["nvidia_smi_gpu"].splitlines()[-1]
        lines.append(f"  GPU: {gpu}; CUDA (driver) {first.get('cuda_driver_version')}")
    if first.get("tokenizer_texts_per_s"):
        rates = "; ".join(
            f"{k}: {v.get('1024', v) if isinstance(v, dict) else v}"
            for k, v in first["tokenizer_texts_per_s"].items()
        )
        lines.append(f"  tokenizer alone, texts/s in batches of 1024: {rates}")
    best, headline = headline_lines(cases, first.get("tokens", {}), checks)
    lines += ["", *best, ""]
    if not any(c["device"] == "gpu" and "error" not in c for c in cases):
        lines.append("GPU: not measured (the reason is in run.log and below)")
    for name, got in checks.get("vectors", {}).items():
        if "min" in got:
            verdict = "passed" if got["passed"] else f"BELOW {MIN_COSINE}"
            lines.append(
                f"Vectors, {name}: min cosine {got['min']:.6f} to production's, {verdict}"
            )
        else:
            lines.append(f"Vectors, {name}: not made: {got['error'][:300]}")
    header = (
        f"{'runtime':25} {'case':78} {'texts':>7} {'s':>6} {'texts/s':>9} {'ms/text':>8} "
        f"{'CPU ms':>8} {'peak':>6} {'PSS':>6} {'USS':>6} {'IPC':>5} {'LLC/text':>8} "
        f"{'GPU %':>5} {'GPU MiB':>7} {'GPU W':>5}  note"
    )
    lines += [
        "",
        "All cases (in the order run)",
        header,
        *(case_line(c) for c in cases),
        "",
        (
            "ms/text: wall time per text over all workers (1000 / texts/s); CPU ms: CPU "
            "time of all workers per text; peak: peak RSS per process, MB; PSS, USS: per "
            "process at the end of the timed part, MB (PSS divides shared pages among "
            "their users, USS counts private ones); IPC and LLC/text: perf stat "
            "(instructions per cycle, last-level cache misses per text; "
            f"{first.get('perf', '')}); GPU %, MiB, W: nvidia-smi's utilization.gpu "
            "(mean), memory.used (max, whole GPU), power.draw (mean) while the case ran."
        ),
    ]
    text = "\n".join(lines)
    print(text)
    (out / "table.txt").write_text(text + "\n")
    summary = {"headline": headline, "checks": checks, "facts": facts_, "cases": cases}
    write_json(out / "summary.json", summary)
    print(f"\nWritten: {out / 'summary.json'} (send this one) and {out / 'table.txt'}")


def gpu_check_command(force: bool) -> int:
    problem = gpu_check(force)
    if problem:
        print(f"GPU check failed: {problem}")
        return 3
    import onnxruntime as ort
    from fastembed import TextEmbedding

    ort.preload_dlls()
    model = TextEmbedding(MODEL, cache_dir=str(CACHE), threads=1, cuda=True)
    providers = model.model.model.get_providers()
    if providers[0] != "CUDAExecutionProvider":
        print(
            f"GPU check failed: {gpu_session_hint(f'the session runs on {providers}')}"
        )
        return 4
    v = next(iter(model.embed(["a test sentence"])))
    print(
        f"GPU check passed: {runtime()}, session providers {providers}, a vector of {len(v)}"
    )
    return 0


def main() -> int:
    force = "--force" in sys.argv  # the GPU part even while others use the GPU
    sys.argv = [a for a in sys.argv if a != "--force"]
    cmd = sys.argv[1:2]
    if cmd == ["worker"]:
        try:
            worker(json.loads(sys.argv[2]))
        # any failure goes to the parent as the case's error, the traceback to the log
        except Exception as e:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            print(f"worker error: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            return 1
        return 0
    if cmd == ["tokenizer"] and len(sys.argv) == 3:
        tokenizer_rate(sys.argv[2])
        return 0
    if cmd in (["cpu"], ["gpu"]) and len(sys.argv) == 5 and sys.argv[2] in MODES:
        mode, out, label = sys.argv[2], Path(sys.argv[3]), sys.argv[4]
        if cmd == ["cpu"]:
            part_cpu(mode, out, label)
            return 0
        return part_gpu(mode, out, label, force)
    if cmd == ["gpu-check"]:
        return gpu_check_command(force)
    if cmd == ["report"] and len(sys.argv) == 3:
        report(Path(sys.argv[2]))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
