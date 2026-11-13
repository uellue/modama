"""The check instrument of the embedding service (change embedding-service-grace, design D4,
D8, D9; README.md next to this file has the commands for staging):

  check.py sets [--n 512] [--sets short,mixed,long,over]
      the benchmark's fixed texts (perf/grace-embedding/gen_texts.py, seed 1) and texts over
      the model's window, sent to the service and embedded here by the warehouse's own
      local path; per set the minimum cosine, the largest component difference and the
      top-10 overlap of the ranking check. Exit 0 only if every set passes design D4.
  check.py rate [--texts 2000] [--callers 1,4,16]
      texts/s and MB/s through the service with requests of TEXTS mixed texts, CALLERS at
      once (each sends 2 requests).
  check.py snapshot [--n 1000] > FILE
      the stored vectors and datestamps of N records of the warehouse, chosen by a hash of
      their identifiers, as JSON lines on stdout; read with MODAMA_CHAIN_WAREHOUSE_DB (the
      read-only role). Standard library and psycopg only.
  check.py compare BEFORE AFTER
      two snapshots: the records whose datestamp did not change, compared as `sets` does.

The service: EMBED_API_URL and EMBED_API_KEY from the environment (the transform worker's),
never from the command line. The local path: the warehouse's `_embed_locally` from
--warehouse-src (default the worker's /opt/airflow/project/src), with TextEmbedding as
TransformResources makes it (EMBEDDING_MODEL, FASTEMBED_CACHE_DIR, EMBEDDING_THREADS).
"""

import argparse
import json
import os
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN_TEXTS = HERE.parent / "perf" / "grace-embedding" / "gen_texts.py"
MODEL = "BAAI/bge-small-en-v1.5"
# design D4: the bound, and the criterion for a set below it
BOUND = 0.99999
MAX_DIFF = 1e-3
MIN_OVERLAP = 0.997
TOP = 10
# the ranking check's queries: short texts of another seed, each embedded alone, as the
# search API embeds a query
QUERIES, QUERY_SEED = 64, 2
# set: (share of long texts, words of a long description); "over" goes past 512 tokens
SETS = {
    "short": (0, 480),
    "mixed": (0.12, 480),
    "long": (1, 480),
    "over": (1, 2000),
}


def say(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def texts_of(n: int, long_share: float, long_words: int, seed: int) -> list[str]:
    """gen_texts.py's texts, as the benchmark made them (deterministic by seed)."""
    import importlib.util
    import random

    spec = importlib.util.spec_from_file_location("gen_texts", GEN_TEXTS)
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    rng = random.Random(seed)
    return [gen.record(rng, i, rng.random() < long_share, long_words) for i in range(n)]


def local_model(warehouse_src: str):
    """The warehouse's local path: TextEmbedding as TransformResources makes it, and
    `_embed_locally` (sorted, sub-batches of 32, patch 0002)."""
    sys.path.insert(0, warehouse_src)
    from fastembed import TextEmbedding
    from utils.embedding_utils import _embed_locally

    threads = os.environ.get("EMBEDDING_THREADS")
    model = TextEmbedding(
        model_name=os.environ.get("EMBEDDING_MODEL") or MODEL,
        cache_dir=os.environ.get(
            "FASTEMBED_CACHE_DIR", str(Path.home() / ".cache" / "fastembed")
        ),
        threads=int(threads) if threads else None,
    )
    say(f"local: {model.model._model_dir}")
    return model, _embed_locally


class Service:
    def __init__(self):
        import requests

        self.url = os.environ.get("EMBED_API_URL", "")
        key = os.environ.get("EMBED_API_KEY", "")
        if not self.url or not key:
            raise SystemExit(
                "check.py: EMBED_API_URL and EMBED_API_KEY must be set (the transform worker's environment)"
            )
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {key}"
        health = self.url.rsplit("/v1", 1)[0] + "/health"
        say(f"service: {self.session.get(health, timeout=30).text.strip()}")

    def embed(self, texts: list[str]) -> tuple[list[list[float]], int, int]:
        """The vectors, the request's and the answer's bytes."""
        body = json.dumps({"model": MODEL.split("/")[-1], "input": texts})
        r = self.session.post(
            self.url + "/embeddings",
            data=body,
            headers={"Content-Type": "application/json"},
            timeout=300,
        )
        r.raise_for_status()
        data = sorted(r.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data], len(body), len(r.content)


def quantised(vectors, lo: float, hi: float):
    """A rough 7-bit stand-in for the index's `sq` encoder (embedding-fp32-model, E6, whose
    code is not in the repository): every component on one of 128 levels between the
    corpus's smallest and largest component."""
    import numpy as np

    step = (hi - lo) / 127
    return lo + np.round((np.clip(vectors, lo, hi) - lo) / step) * step


def compare(name: str, got, ref, queries) -> dict:
    """Minimum cosine, largest component difference and the ranking check's top-10
    overlap of two sets of vectors of the same texts (float64); passed by design D4."""
    import numpy as np

    got, ref = np.asarray(got, np.float64), np.asarray(ref, np.float64)
    cos = (got * ref).sum(1) / (
        np.linalg.norm(got, axis=1) * np.linalg.norm(ref, axis=1)
    )
    diff = float(np.abs(got - ref).max())
    lo, hi = float(ref.min()), float(ref.max())
    a, b = quantised(got, lo, hi) @ queries.T, quantised(ref, lo, hi) @ queries.T
    top = min(TOP, len(ref))
    ta = np.argsort(-a, axis=0)[:top].T
    tb = np.argsort(-b, axis=0)[:top].T
    overlap = float(np.mean([len(set(x) & set(y)) / top for x, y in zip(ta, tb)]))
    low = float(cos.min())
    passed = low >= BOUND or (diff < MAX_DIFF and overlap >= MIN_OVERLAP)
    return {
        "set": name,
        "texts": len(ref),
        "min_cosine": low,
        "max_diff": diff,
        "overlap": overlap,
        "passed": passed,
    }


def table(rows: list[dict]) -> None:
    print(
        f"{'set':<8} {'texts':>6} {'min cosine':>12} {'max diff':>10} {'top-10':>7}  "
    )
    for r in rows:
        verdict = "pass" if r["passed"] else "FAIL"
        print(
            f"{r['set']:<8} {r['texts']:>6} {r['min_cosine']:>12.9f} {r['max_diff']:>10.2e}"
            f" {r['overlap']:>7.4f}  {verdict}"
        )
    print(
        f"(pass: min cosine >= {BOUND}, or max diff < {MAX_DIFF:g} and top-10 overlap >= {MIN_OVERLAP})"
    )


def query_vectors(model):
    import numpy as np

    queries = texts_of(QUERIES, 0, 480, QUERY_SEED)
    return np.array([next(iter(model.embed([q]))) for q in queries], np.float64)


def cmd_sets(a) -> int:
    service = Service()
    model, embed_locally = local_model(a.warehouse_src)
    queries = query_vectors(model)
    rows = []
    for name in a.sets.split(","):
        share, words = SETS[name]
        texts = texts_of(a.n, share, words, 1)
        got, _, _ = service.embed(texts)
        rows.append(compare(name, got, embed_locally(texts, model), queries))
    table(rows)
    failed = [r["set"] for r in rows if not r["passed"]]
    if failed:
        say(f"check.py: outside design D4: {', '.join(failed)}")
        return 1
    return 0


def cmd_rate(a) -> int:
    service = Service()
    mixed = texts_of(a.texts, *SETS["mixed"], 1)
    print(
        f"{'callers':>7} {'requests':>8} {'texts/s':>9} {'MB/s answers':>12} {'MB/s requests':>13}"
    )
    for callers in (int(c) for c in a.callers.split(",")):
        start = time.monotonic()
        with ThreadPoolExecutor(callers) as pool:
            done = list(pool.map(lambda _: service.embed(mixed), range(2 * callers)))
        took = time.monotonic() - start
        sent = sum(d[1] for d in done) / took / 1e6
        got = sum(d[2] for d in done) / took / 1e6
        rate = len(done) * len(mixed) / took
        print(f"{callers:>7} {len(done):>8} {rate:>9.0f} {got:>12.1f} {sent:>13.2f}")
    return 0


def cmd_snapshot(a) -> int:
    import psycopg

    dsn = os.environ.get("MODAMA_CHAIN_WAREHOUSE_DB")
    if not dsn:
        raise SystemExit(
            "check.py: MODAMA_CHAIN_WAREHOUSE_DB is not set (the read-only role; run it in the crawler's container)"
        )
    sql = (
        # id: the primary key, endpoint and identifier (review R6)
        "SELECT id, datestamp, embeddings FROM records "
        "WHERE embeddings IS NOT NULL ORDER BY md5(id), id LIMIT %s"
    )
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(sql, (a.n,)).fetchall()
    for identifier, datestamp, vector in rows:
        print(
            json.dumps(
                {"id": identifier, "datestamp": datestamp.isoformat(), "vector": vector}
            )
        )
    say(f"check.py: {len(rows)} records")
    return 0


def read_snapshot(path: str) -> dict[str, dict]:
    with open(path) as f:
        return {r["id"]: r for r in map(json.loads, f)}


def cmd_compare(a) -> int:
    before, after = read_snapshot(a.before), read_snapshot(a.after)
    same = [
        i
        for i in before
        if i in after and after[i]["datestamp"] == before[i]["datestamp"]
    ]
    say(
        f"check.py: {len(before)} records before, {len(after)} after, {len(same)} with the same datestamp"
    )
    if not same:
        say("check.py: no record to compare")
        return 1
    model, _ = local_model(a.warehouse_src)
    row = compare(
        "records",
        [after[i]["vector"] for i in same],
        [before[i]["vector"] for i in same],
        query_vectors(model),
    )
    table([row])
    return 0 if row["passed"] else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("\n\n", 1)[1],
    )
    ap.add_argument(
        "--warehouse-src",
        default="/opt/airflow/project/src",
        help="the warehouse's src folder (default: the transform worker's)",
    )
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sets", help="agreement on the fixed sets")
    p.add_argument("--n", type=int, default=512, help="texts per set (default 512)")
    p.add_argument("--sets", default="short,mixed,long,over")
    p = sub.add_parser("rate", help="texts/s and MB/s through the service")
    p.add_argument("--texts", type=int, default=2000, help="texts per request")
    p.add_argument("--callers", default="1,4,16", help="requests at once")
    p = sub.add_parser("snapshot", help="stored vectors as JSON lines on stdout")
    p.add_argument("--n", type=int, default=1000, help="records (default 1000)")
    p = sub.add_parser("compare", help="two snapshots")
    p.add_argument("before")
    p.add_argument("after")
    a = ap.parse_args()
    if a.command == "sets" and not set(a.sets.split(",")) <= set(SETS):
        ap.error(f"--sets: one or more of {', '.join(SETS)}")
    return {
        "sets": cmd_sets,
        "rate": cmd_rate,
        "snapshot": cmd_snapshot,
        "compare": cmd_compare,
    }[a.command](a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        # a closed output pipe ends quietly
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
