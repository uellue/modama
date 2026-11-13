"""How far the float32 file's vectors and rankings are from the upstream file's (change embedding-fp32-model,
design D4 and E6; task 1.3). A measurement, run by hand, not part of the build.

  python agreement.py UPSTREAM OUT WORK [--records 832] [--queries 192]

UPSTREAM and OUT as for fp32.py. Makes the benchmark's sets with perf/grace-embedding/gen_texts.py in WORK
(512 short, 512 mixed, 64 long; a corpus of RECORDS mixed texts and QUERIES short ones, other seeds) and
prints:
- per set, fp32.py check's numbers (bitwise identical, largest difference, minimum cosine in float64);
- the largest difference against a rough 7-bit scalar quantisation step, a stand-in for the index's
  `encoder: sq` (metadata-warehouse/config/opensearch_mapping.json): (max - min) / 127 over the corpus;
- rankings: each query embedded alone, the top 10 of the corpus by cosine; the mean overlap of the top-10
  sets and the share of queries with the same order, (a) float32 against upstream, (b) the stand-in
  against upstream's own float vectors, (c) both quantised.

Needs fastembed and numpy (the test venv of test_fp32.py, or the image's transform venv).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fp32  # noqa: E402

GEN = HERE.parent / "perf" / "grace-embedding" / "gen_texts.py"


def texts(work: Path, name: str, n: int, share: str, seed: int) -> list[str]:
    path = work / f"{name}.jsonl"
    subprocess.run(
        [
            sys.executable,
            "-I",
            str(GEN),
            str(path),
            "--n",
            str(n),
            "--long-share",
            share,
            "--seed",
            str(seed),
        ],
        check=True,
        capture_output=True,
    )
    return [json.loads(line)["text"] for line in path.read_text().splitlines()]


def model(folder: Path):
    from fastembed import TextEmbedding

    return TextEmbedding(fp32.MODEL, specific_model_path=str(folder), threads=1)


def embed(m, items: list[str]) -> np.ndarray:
    order = sorted(range(len(items)), key=lambda i: len(items[i]))
    got = list(m.embed([items[i] for i in order], batch_size=fp32.SUB_BATCH))
    out = np.empty((len(items), len(got[0])), dtype=np.float32)
    for i, v in zip(order, got, strict=True):
        out[i] = v
    return out


def alone(m, items: list[str]) -> np.ndarray:
    return np.stack([next(iter(m.embed([t]))) for t in items]).astype(np.float32)


def top10(queries: np.ndarray, corpus: np.ndarray) -> np.ndarray:
    q = queries.astype(np.float64)
    c = corpus.astype(np.float64)
    sims = (q @ c.T) / np.outer(np.linalg.norm(q, axis=1), np.linalg.norm(c, axis=1))
    return np.argsort(-sims, axis=1, kind="stable")[:, :10]


def compare(a: np.ndarray, b: np.ndarray) -> str:
    overlap = np.mean([len(set(x) & set(y)) / 10 for x, y in zip(a, b, strict=True)])
    same = np.mean([list(x) == list(y) for x, y in zip(a, b, strict=True)])
    return f"top-10 overlap {overlap:.3f}, same order {same:.0%}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("upstream", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("work", type=Path)
    ap.add_argument("--records", type=int, default=832)
    ap.add_argument("--queries", type=int, default=192)
    args = ap.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    up, f32 = model(args.upstream), model(args.out)

    for name, n, share, seed in (
        ("short", 512, "0", 1),
        ("mixed", 512, "0.12", 2),
        ("long", 64, "1", 3),
    ):
        items = texts(args.work, name, n, share, seed)
        a, b = embed(up, items), embed(f32, items)
        a64, b64 = a.astype(np.float64), b.astype(np.float64)
        cos = (a64 * b64).sum(1) / np.sqrt((a64 * a64).sum(1) * (b64 * b64).sum(1))
        print(
            f"{name}: {n} texts, {int(np.all(a == b, axis=1).sum())} bitwise identical, "
            f"largest difference {np.abs(a64 - b64).max():.3g}, minimum cosine {cos.min():.8f}",
            flush=True,
        )

    corpus_texts = texts(args.work, "corpus", args.records, "0.12", 4)
    query_texts = texts(args.work, "queries", args.queries, "0", 5)
    ca, cb = embed(up, corpus_texts), embed(f32, corpus_texts)
    qa, qb = alone(up, query_texts), alone(f32, query_texts)
    lo, hi = float(ca.min()), float(ca.max())
    step = (hi - lo) / 127

    def sq(v: np.ndarray) -> np.ndarray:
        return np.round((np.clip(v, lo, hi) - lo) / step) * step + lo

    print(
        f"corpus {args.records}, queries {args.queries} (each alone); 7-bit stand-in step {step:.3g}, "
        f"largest corpus difference {np.abs(ca.astype(np.float64) - cb).max():.3g}"
    )
    ta, tb = top10(qa, ca), top10(qb, cb)
    print("(a) float32 against upstream, float vectors:", compare(ta, tb))
    print("(b) upstream quantised against upstream:", compare(ta, top10(qa, sq(ca))))
    print(
        "(c) both quantised, float32 against upstream:",
        compare(top10(qa, sq(ca)), top10(qb, sq(cb))),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
