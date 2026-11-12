"""Peak memory of one whole transform batch, run as the DAG's run_transform_batch runs it, in a throwaway
container of the airflow image (transform venv), without writing anywhere.

  python batch-memory.py N FILL THREADS [SUB_BATCH]
    N          events in the batch (the VM's real events from the warehouse, repeated with distinct identifiers)
    FILL       0: the records' own embedding text; K: K filler words appended (long texts, up to the model's 512
               tokens; 190 tokens at about K=150, 512 at K=500)
    THREADS    0: fastembed's default; T: threads=T (what patch 0002's EMBEDDING_THREADS does)
    SUB_BATCH  0: the image's own `embed` sub-batch; S: batch_size=S (fastembed's default is 256; patch 0002: 32)

One throwaway container per case, on the running test deployment's network (the design's "Measurement of one
batch", change cpu-budget; the test deployment's throwaway password of the read-only role):

  docker run --rm --network search-stack_search -v "$PWD/perf":/probe:ro \
    -v search-stack_fastembed-airflow:/opt/airflow/cache/fastembed:ro \
    -e PYTHONPATH=/opt/airflow/project/src:/opt/airflow/project \
    -e EMBEDDING_MODEL=BAAI/bge-small-en-v1.5 -e FASTEMBED_CACHE_DIR=/opt/airflow/cache/fastembed \
    -e POSTGRES_USER=chain_reader -e POSTGRES_PASSWORD=test-chain-reader -e POSTGRES_DB=datasetdb \
    -e POSTGRES_ADDRESS_DOCKER=postgres -e OPENSEARCH_ADDRESS_DOCKER=opensearch -e OPENSEARCH_PORT_DOCKER=9200 \
    --entrypoint /opt/airflow/transform-venv/bin/python search-stack-airflow:3.3.2 /probe/batch-memory.py 250 0 0

With the budget's variables add `-e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1
-e RAYON_NUM_THREADS=T`. In an image with patch 0002 the image's own sub-batch is already 32.

Reads the warehouse with the read-only role (POSTGRES_* in the environment). The writes are replaced:
psycopg's connection inside transform_batch_impl is a fake that records statements, and the OpenSearch bulk
serializes every action as opensearch-py does, then returns success. Prints VmHWM (peak RSS) per stage.
"""

import os
import sys
import time


def st():
    with open("/proc/self/status") as f:
        d = {
            l.split(":")[0]: l.split(":")[1].strip()
            for l in f
            if l.startswith(("VmSize", "VmRSS", "VmHWM", "Threads"))
        }
    return f"RSS {d['VmRSS']:>11}  peak {d['VmHWM']:>11}  size {d['VmSize']:>11}  threads {d['Threads']}"


n, fill, threads, embed_batch = (int(a) for a in (sys.argv[1:5] + ["0"])[:4])
print("start      ", st(), flush=True)

import psycopg  # noqa: E402

from planning.transform_planning import load_batch  # noqa: E402
import transform.transform_core as core  # noqa: E402

print("imported   ", st(), flush=True)

# the VM's real events: every closed run, loaded as the DAG loads a batch
with psycopg.connect(**core.PostgresConfig().connection_params) as c:
    runs = c.execute(
        "SELECT hr.id, min(he.id::text), max(he.id::text) FROM harvest_runs hr JOIN harvest_events he ON he.harvest_run_id = hr.id "
        "WHERE hr.status = 'closed' GROUP BY hr.id"
    ).fetchall()
real = [
    e
    for r in runs
    for e in load_batch(str(r[0]), str(r[1]), str(r[2]))
    if not e.is_deleted
]
events = [
    e._replace(
        id=f"{e.id}-{i}",
        record_identifier=f"{e.record_identifier}-{i}",
        xml=(e.xml + " ")[:-1],
    )
    for i, e in ((i, real[i % len(real)]) for i in range(n))
]
del real
print(
    f"loaded {len(events):>4}",
    st(),
    f"(xml {sum(len(e.xml) for e in events) / len(events):.0f} chars/event)",
    flush=True,
)

words = (
    "beam dose sample tilt focus aberration detector camera frame series drift lattice defect interface grain "
    "vacuum specimen holder voltage current spectrum map region particle thickness calibration alignment".split()
)
filler = " ".join(words[i * 7 % len(words)] for i in range(fill))
text_of = core.get_embedding_text_from_fields
texts = []


def text_with_fill(src):
    texts.append((text_of(src) + " " + filler) if fill else text_of(src))
    return texts[-1]


core.get_embedding_text_from_fields = text_with_fill

if threads:
    _init = core.TextEmbedding.__init__
    core.TextEmbedding.__init__ = lambda self, *a, **k: _init(
        self, *a, threads=threads, **k
    )


if embed_batch:
    _embed = core.TextEmbedding.embed
    core.TextEmbedding.embed = lambda self, docs, *a, **k: _embed(
        self, docs, batch_size=embed_batch
    )


class Cursor:
    def execute(self, query, params=None):
        Conn.statements += 1

    def fetchone(self):
        return None


class Conn:
    statements = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return Cursor()


core.psycopg = type("fake_psycopg", (), {"connect": staticmethod(lambda **k: Conn())})


def bulk(client, actions):
    from opensearchpy.helpers.actions import expand_action

    body = []
    for a in actions:
        op, data = expand_action(a)
        body.append(client.transport.serializer.dumps(op))
        if data is not None:
            body.append(client.transport.serializer.dumps(data))
    bulk.bytes = sum(len(b) for b in body) + len(body)
    return len(actions), []


core.bulk = bulk

t = time.monotonic()
resources = core.TransformResources()
resources.client.indices.exists = lambda **k: True
print("resources  ", st(), f"{time.monotonic() - t:.1f} s", flush=True)
t = time.monotonic()
indexed = core.transform_batch_impl(resources, events, "test_datacite", False)
print(
    f"transformed {indexed}",
    st(),
    f"{time.monotonic() - t:.1f} s, {Conn.statements} statements, "
    f"bulk body {bulk.bytes / 1e6:.1f} MB",
    flush=True,
)
tok = resources.embedding_transformer.model.tokenizer
lengths = sorted(len(tok.encode(x).ids) for x in texts)
print(
    f"tokens per text (truncated at 512): min {lengths[0]}, median {lengths[len(lengths) // 2]}, max {lengths[-1]}",
    flush=True,
)
allowed = {}
for tid in os.listdir("/proc/self/task"):
    with open(f"/proc/self/task/{tid}/status") as f:
        cpus = next(l.split()[1] for l in f if l.startswith("Cpus_allowed_list"))
    with open(f"/proc/self/task/{tid}/comm") as f:
        allowed.setdefault(cpus, []).append(f.read().strip())
print(
    "threads by allowed CPUs:",
    {k: len(v) for k, v in allowed.items()},
    sorted({n for v in allowed.values() for n in v}),
)
