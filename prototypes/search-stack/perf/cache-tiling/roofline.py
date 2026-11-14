"""Roofline of bge-small-en-v1.5 on one core: FLOPs per pass, the core's sgemm rate, ONNX Runtime per operator.

From the repository root, with the scratch venv (common.py says what TRIALS holds):

  V=/var/tmp/embed-research-trials/venv/bin/python
  export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
  taskset -c 2 $V prototypes/search-stack/perf/cache-tiling/roofline.py flops            # formula vs torch
  taskset -c 2 $V prototypes/search-stack/perf/cache-tiling/roofline.py gemm             # numpy sgemm GFLOP/s
  taskset -c 2 $V prototypes/search-stack/perf/cache-tiling/roofline.py ort SEQ [BATCH [MODEL]]  # per operator

`ort` runs the float32 model (or MODEL, an .onnx path) on one thread on BATCH (default 1) copies of a SEQ-token input, 3 warm-up runs,
then 10 profiled runs; per operator class the median per run, its share, its FLOPs (from the shapes in the
profile) and the GFLOP/s it reaches.
"""

import json
import statistics
import sys
import time
from collections import defaultdict

import common
import numpy as np

D, F, H, L = 384, 1536, 12, 12


def formula(T):
    """FLOPs of one pass of T tokens (batch 1), per part, all 12 layers. A multiply-add counts 2."""
    gemm = {
        "QKV projection": 2 * T * D * 3 * D,
        "scores Q.K^T": 2 * T * T * D,
        "A.V": 2 * T * T * D,
        "output projection": 2 * T * D * D,
        "FFN up": 2 * T * D * F,
        "FFN down": 2 * T * F * D,
    }
    # element-wise, rough operation counts: softmax max/sub/exp/sum/div; tanh-GELU ~8; LayerNorm ~8 + residual
    other = {
        "softmax": 5 * H * T * T,
        "GELU": 8 * T * F,
        "LayerNorm+residual": 2 * 9 * T * D,
    }
    return {k: v * L for k, v in gemm.items()}, {k: v * L for k, v in other.items()}


def cmd_flops():
    import torch
    from torch.utils.flop_counter import FlopCounterMode
    from transformers import AutoModel

    torch.set_num_threads(1)
    m = AutoModel.from_pretrained(
        str(common.TRIALS / "models/bge-small"), attn_implementation="eager"
    ).eval()
    for T in (512, 128):
        gemm, other = formula(T)
        ids = torch.randint(1000, 2000, (1, T))
        with torch.no_grad(), FlopCounterMode(display=False) as fc:
            m(input_ids=ids, attention_mask=torch.ones_like(ids))
        tf = fc.get_total_flops()
        g = sum(gemm.values())
        print(
            f"T={T}: formula GEMM {g / 1e9:.3f} GFLOP, element-wise {sum(other.values()) / 1e9:.3f} GFLOP; "
            f"torch flop_counter {tf / 1e9:.3f} GFLOP (matmuls only; includes the pooler {2 * D * D / 1e9:.4f})"
        )
        for k, v in {**gemm, **other}.items():
            print(
                f"  {k:20s} {v / 1e9:7.3f} GFLOP  {100 * v / (g + sum(other.values())):5.1f} %"
            )


def gemm_rate(m, k, n, min_time=0.5):
    a = np.random.rand(m, k).astype(np.float32)
    b = np.random.rand(k, n).astype(np.float32)
    c = np.empty((m, n), np.float32)
    np.matmul(a, b, out=c)
    reps = max(1, int(min_time / max(1e-7, _once(a, b, c))))
    rates = []
    for _ in range(5):
        t = time.perf_counter()
        for _ in range(reps):
            np.matmul(a, b, out=c)
        rates.append(2 * m * k * n * reps / (time.perf_counter() - t) / 1e9)
    return statistics.median(rates)


def _once(a, b, c):
    t = time.perf_counter()
    np.matmul(a, b, out=c)
    return time.perf_counter() - t


def cmd_gemm():
    np.show_config() if "-v" in sys.argv else None
    shapes = [
        ("large", 2048, 2048, 2048),
        ("large", 4096, 4096, 4096),
        ("QKV  T=512", 512, 384, 1152),
        ("out  T=512", 512, 384, 384),
        ("up   T=512", 512, 384, 1536),
        ("down T=512", 512, 1536, 384),
        ("QK^T one head", 512, 32, 512),
        ("AV   one head", 512, 512, 32),
        ("QKV  T=128", 128, 384, 1152),
        ("up   T=128", 128, 384, 1536),
        ("down T=128", 128, 1536, 384),
        ("up   T=32 (token tile)", 32, 384, 1536),
        ("down T=32 (token tile)", 32, 1536, 384),
    ]
    for name, m, k, n in shapes:
        print(
            f"{name:24s} {m:5d}x{k:5d}x{n:5d}  {gemm_rate(m, k, n):6.1f} GFLOP/s (median of 5)"
        )


def node_flops(op, a, out):
    """GEMM FLOPs of one profiled node from its first input's and its output's shapes (the profile leaves
    out prepacked weights); 0 for element-wise nodes."""
    if op in ("MatMul", "FusedMatMul", "Gemm"):
        return 2 * int(np.prod(a[:-1])) * a[-1] * out[-1]
    if op == "Attention":
        bsz, t, d = a
        return 2 * bsz * t * d * 3 * d + 4 * bsz * t * t * d
    return 0


def cmd_ort(T, batch, path):
    tmp = common.TRIALS / "tmp"
    sess = common.session(path, profile_prefix=tmp / f"ort-T{T}-B{batch}")
    feed = {
        "input_ids": np.random.default_rng(0)
        .integers(1000, 20000, (batch, T))
        .astype(np.int64),
        "attention_mask": np.ones((batch, T), np.int64),
        "token_type_ids": np.zeros((batch, T), np.int64),
    }
    feed = {
        i.name: feed[i.name] for i in sess.get_inputs()
    }  # mha-nomask has no mask input
    for _ in range(3):
        sess.run(None, feed)
    walls = []
    for _ in range(10):
        t = time.perf_counter()
        sess.run(None, feed)
        walls.append(time.perf_counter() - t)
    path = sess.end_profiling()
    with open(path) as f:
        ev = json.load(f)
    runs = [e for e in ev if e.get("cat") == "Session" and e["name"] == "model_run"][
        -10:
    ]
    t0 = runs[0]["ts"]
    per = defaultdict(lambda: [0.0] * 10)
    flops = defaultdict(int)
    for e in ev:
        if (
            e.get("cat") != "Node"
            or not e["name"].endswith("_kernel_time")
            or e["ts"] < t0
        ):
            continue
        r = next(
            i for i, x in enumerate(runs) if x["ts"] <= e["ts"] <= x["ts"] + x["dur"]
        )
        op = e["args"]["op_name"]
        per[op][r] += e["dur"] / 1e6
        if r == 0:
            a = next(iter(e["args"]["input_type_shape"][0].values()))
            out = next(iter(e["args"]["output_type_shape"][0].values()))
            flops[op] += node_flops(op, a, out)
    wall = statistics.median(walls)
    tot = sum(statistics.median(v) for v in per.values())
    print(
        f"T={T} batch={batch}: wall per run median {wall * 1e3:.1f} ms (runs {[round(w * 1e3) for w in walls]}),"
        f" kernels {tot * 1e3:.1f} ms; profile {path}"
    )
    for op, v in sorted(per.items(), key=lambda kv: -statistics.median(kv[1])):
        m = statistics.median(v)
        rate = f"{flops[op] / m / 1e9:6.1f} GFLOP/s" if flops[op] else ""
        print(
            f"  {op:24s} {m * 1e3:8.2f} ms {100 * m / tot:5.1f} %  {flops[op] / 1e9:7.3f} GFLOP {rate}"
        )
    gf = sum(flops.values())
    print(
        f"  GEMM-class FLOPs {gf / 1e9:.3f} GFLOP over the wall time: {gf / wall / 1e9:.1f} GFLOP/s"
    )


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "flops":
        cmd_flops()
    elif c == "gemm":
        cmd_gemm()
    elif c == "ort":
        cmd_ort(
            int(sys.argv[2]),
            int(sys.argv[3]) if len(sys.argv) > 3 else 1,
            sys.argv[4] if len(sys.argv) > 4 else common.FP32,
        )
