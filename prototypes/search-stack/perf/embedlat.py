"""Latency of one query embedding in the search API's image: fastembed's default threads against threads=1.

Run in the search-api container: python - < embedlat.py. Prints median and p90 of 100 queries per setting."""

import os
import statistics
import time

from fastembed import TextEmbedding

MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
for threads in (None, 1):
    model = TextEmbedding(MODEL, threads=threads)
    next(iter(model.embed(["warm up"])))
    times = []
    for i in range(100):
        t = time.perf_counter()
        next(iter(model.embed([f"ferritin sample {i} at liquid nitrogen temperature"])))
        times.append((time.perf_counter() - t) * 1000)
    times.sort()
    print(
        f"threads {threads}: median {statistics.median(times):.1f} ms, p90 {times[89]:.1f} ms, max {times[-1]:.1f} ms"
    )
