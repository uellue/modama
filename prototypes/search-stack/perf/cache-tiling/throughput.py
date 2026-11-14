"""Throughput with N processes at once, each pinned to its own CPUs, all embedding the same texts.

From the repository root (common.py says what TRIALS holds):

  V=/var/tmp/embed-research-trials/venv/bin/python
  $V prototypes/search-stack/perf/cache-tiling/throughput.py METHOD N TEXTS [--sub-batch 32] [--tokens T]
      [--threads 1] [--repeat 1] [--cpus 0,1,...] [--save OUT.npy] [--ref REF.npy]

METHOD: ort:PATH (an .onnx file, ONNX Runtime), torch-eager, torch-sdpa, torch-compile (the Hugging Face model
with the tanh GELU of the production file). --threads: threads per process (default 1); process r gets CPUs
cpus[r·threads … (r+1)·threads − 1]. --tokens T: sub-batches also bounded by T padded tokens (common.embed).
TEXTS: a file in TRIALS/texts. Each worker loads the model, embeds TEXTS once to warm up (torch.compile
compiles there), waits for the others, then embeds TEXTS REPEAT times as fastembed does (common.embed).
Prints the aggregate records/s, the wall time of the slowest worker and the CPU per record (process time of
all its threads, the median over workers); --save writes worker 0's vectors, --ref compares them (max abs
difference, min cosine).
"""

import argparse
import multiprocessing as mp
import os
import statistics
import time

for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[v] = "1"

import common
import numpy as np


def torch_embedder(kind, threads):
    import torch
    from transformers import AutoConfig, AutoModel

    torch.set_num_threads(threads)
    attn = "eager" if kind == "torch-eager" else "sdpa"
    path = str(common.TRIALS / "models/bge-small")
    # the production file computes GELU in the tanh form (FastGelu); the same here, for equal results
    config = AutoConfig.from_pretrained(path, hidden_act="gelu_pytorch_tanh")
    model = AutoModel.from_pretrained(
        path, config=config, attn_implementation=attn
    ).eval()
    if kind == "torch-compile":
        model = torch.compile(model, backend="inductor", dynamic=True)

    class Sess:
        def run(self, _, feed):
            with torch.inference_mode():
                out = model(**{k: torch.from_numpy(v) for k, v in feed.items()})
            return [out.last_hidden_state.numpy()]

    return Sess()


def make_session(method, threads):
    if method.startswith("ort:"):
        return common.session(method.split(":", 1)[1], threads=threads)
    return torch_embedder(method, threads)


def worker(
    rank, cpus, method, texts_name, sub_batch, tokens, threads, repeat, barrier, q
):
    os.sched_setaffinity(0, cpus)
    sess = make_session(method, threads)
    tok = common.tokenizer()
    texts = common.texts(texts_name)
    common.embed(
        sess, tok, texts, sub_batch, tokens
    )  # warm-up (and torch.compile's compiles)
    barrier.wait()
    c0, t0 = time.process_time(), time.perf_counter()
    for _ in range(repeat):
        vecs = common.embed(sess, tok, texts, sub_batch, tokens)
    q.put(
        (
            rank,
            time.perf_counter() - t0,
            time.process_time() - c0,
            vecs if rank == 0 else None,
        )
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("method")
    ap.add_argument("n", type=int)
    ap.add_argument("texts")
    ap.add_argument("--sub-batch", type=int, default=32)
    ap.add_argument("--tokens", type=int, default=None)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--cpus", default=None)
    ap.add_argument("--save")
    ap.add_argument("--ref")
    a = ap.parse_args()
    t = a.threads
    cpus = [int(c) for c in a.cpus.split(",")] if a.cpus else list(range(a.n * t))
    ctx = mp.get_context("spawn")
    barrier, q = ctx.Barrier(a.n), ctx.Queue()
    procs = [
        ctx.Process(
            target=worker,
            args=(
                r,
                set(cpus[r * t : (r + 1) * t]),
                a.method,
                a.texts,
                a.sub_batch,
                a.tokens,
                t,
                a.repeat,
                barrier,
                q,
            ),
        )
        for r in range(a.n)
    ]
    for p in procs:
        p.start()
    res = sorted(q.get(timeout=7200) for _ in procs)
    for p in procs:
        p.join()
    n_texts = len(common.texts(a.texts)) * a.repeat
    wall = max(r[1] for r in res)
    cpu = statistics.median(r[2] for r in res)
    sb = f"sub-batch {a.sub_batch}" + (f" or {a.tokens} tokens" if a.tokens else "")
    line = (
        f"{a.method} N={a.n}x{t} cpus={cpus} {a.texts} {sb}: {a.n * n_texts / wall:.2f} records/s,"
        f" slowest wall {wall:.1f} s, CPU per record {1e3 * cpu / n_texts:.0f} ms"
        f" (walls {[round(r[1], 1) for r in res]})"
    )
    vecs = res[0][3]
    if a.save:
        np.save(a.save, vecs)
    if a.ref:
        d, c = common.compare(vecs, np.load(a.ref))
        line += (
            f"; vs {os.path.basename(a.ref)}: max abs diff {d:.2e}, min cosine {c:.8f}"
        )
    print(line, flush=True)


if __name__ == "__main__":
    main()
