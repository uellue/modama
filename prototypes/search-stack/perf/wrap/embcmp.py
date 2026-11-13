"""Compare the embeddings of two bulk bodies (BULK_OUT) of the same batch: cosine similarity per document."""

import json
import math
import sys
from pathlib import Path


def embeddings(path):
    lines = Path(path).read_text().splitlines()
    # by position: the batch's documents in the batch's order (the _id repeats, the records are repeated)
    return {
        i: (next(iter(json.loads(action).values()))["_id"], json.loads(doc)["emb"])
        for i, (action, doc) in enumerate(zip(lines[0::2], lines[1::2]))
    }


a, b = embeddings(sys.argv[1]), embeddings(sys.argv[2])
sims = []
assert all(a[k][0] == b[k][0] for k in a), "different order"
a = {k: v[1] for k, v in a.items()}
b = {k: v[1] for k, v in b.items()}
for k, x in a.items():
    y = b[k]
    dot = sum(p * q for p, q in zip(x, y))
    sims.append(dot / math.sqrt(sum(p * p for p in x) * sum(q * q for q in y)))
sims.sort()
same = sum(a[k] == b[k] for k in a)
print(
    f"{len(sims)} documents, {same} identical; cosine min {sims[0]:.6f}, median {sims[len(sims) // 2]:.6f}"
)
