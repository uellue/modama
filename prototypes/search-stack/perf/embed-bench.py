"""Embedding throughput of the warehouse's model outside the stack: P processes at once, each with T ONNX Runtime
threads, embedding the same kind of texts as the bench's records. An upper bound for the indexing's records/s.

Run inside airflow-worker-transform with the transform venv (an option's code change is not needed for this, the
script passes `threads` to fastembed itself):
  docker compose exec -T airflow-worker-transform sh -c 'cat > /tmp/embed-bench.py' < perf/embed-bench.py
  docker compose exec -T airflow-worker-transform /opt/airflow/transform-venv/bin/python /tmp/embed-bench.py P:T[:B] ...
T 0 is ONNX Runtime's default (fastembed's threads=None); B is fastembed's embed batch size (default 256).
"""

import json
import os
import random
import subprocess
import sys
import time

TEXTS = 2000


def texts(seed: int) -> list[str]:
    """Like the records of perf/seed.py: the path as title, the crawler's description."""
    rng = random.Random(seed)
    words = "beam dose sample tilt focus detector camera frame series drift lattice defect grain".split()
    out = []
    for i in range(TEXTS):
        folder = f"perf-seed/{rng.choice(['ferritin', 'graphene', 'zeolite', 'SrTiO3'])}-{rng.randrange(50):02d}"
        name = f"{rng.choice(['haadf', 'eels', 'edx', 'tomography'])}_{rng.choice(words)}_{i:06d}.txt"
        out.append(
            f"{folder}/{name} plain text document, 1 file, {rng.randint(30, 300)} B, in {folder}/"
        )
    return out


def worker(threads: int, batch: int, start_at: float) -> None:
    from fastembed import TextEmbedding

    model = TextEmbedding(
        model_name=os.environ["EMBEDDING_MODEL"],
        cache_dir=os.environ["FASTEMBED_CACHE_DIR"],
        threads=threads or None,
    )
    docs = texts(os.getpid())
    list(model.embed(docs[:16]))  # warm-up
    time.sleep(max(0.0, start_at - time.time()))
    c0, w0 = time.process_time(), time.time()
    list(model.embed(docs, batch_size=batch))
    print(
        json.dumps({"start": w0, "end": time.time(), "cpu": time.process_time() - c0}),
        flush=True,
    )


def main() -> None:
    for spec in sys.argv[1:]:
        p, t, *b = (int(x) for x in spec.split(":"))
        batch = b[0] if b else 256
        start_at = time.time() + 8  # all loaded by then
        procs = [
            subprocess.Popen(
                [
                    sys.executable,
                    __file__,
                    "--worker",
                    str(t),
                    str(batch),
                    str(start_at),
                ],
                stdout=subprocess.PIPE,
                text=True,
            )
            for _ in range(p)
        ]
        res = [
            json.loads(proc.communicate()[0].strip().splitlines()[-1]) for proc in procs
        ]
        wall = max(r["end"] for r in res) - min(r["start"] for r in res)
        cpu = sum(r["cpu"] for r in res)
        print(
            f"P={p} T={t or 'default'} batch={batch}: {p * TEXTS} texts in {wall:.2f} s = {p * TEXTS / wall:.0f} "
            f"texts/s, CPU {cpu:.1f} s = {cpu / (p * TEXTS) * 1000:.2f} ms per text, {cpu / wall:.1f} cores busy",
            flush=True,
        )


if __name__ == "__main__":
    if sys.argv[1:2] == ["--worker"]:
        worker(int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]))
    else:
        main()
