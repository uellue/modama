"""Phase timings of upstream's transform steps on one real batch, without writing anything: a cross-check of the
py-spy profile (which loses samples in deep stacks) and a measure of code-level options without applying them.

Run inside airflow-worker-transform after a bench run (it reads the last closed harvest run of the warehouse):
  docker compose exec -T airflow-worker-transform sh -c 'cat > /tmp/phase-timer.py' < perf/phase-timer.py
  docker compose exec -T -w /opt/airflow/project airflow-worker-transform \
      /opt/airflow/transform-venv/bin/python /tmp/phase-timer.py [BATCH]
`docker compose exec` does not get the variables budget.py sets before it starts Celery: for a batch process's
threads, add -e EMBEDDING_THREADS=T -e RAYON_NUM_THREADS=T -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1
-e MKL_NUM_THREADS=1 (README, "CPU budget").
It calls the same functions as transform.transform_core.transform_batch_impl, in the same order, per step for the
whole batch, and prints wall and CPU seconds per step.
"""

import sys
import time

t_imports = time.monotonic()
import jsonschema  # noqa: E402
import psycopg  # noqa: E402
import xmltodict  # noqa: E402
from lxml import etree as ET  # noqa: E402

from planning.transform_planning import load_batch  # noqa: E402
from transform.transform_core import (
    OAI_METADATA,
    OAI_RECORD,
    TransformResources,
    EMBEDDING_MODEL,
)  # noqa: E402
from utils import handle_xml, normalize_datacite_json  # noqa: E402
from utils.embedding_utils import _embed_locally, get_embedding_text_from_fields  # noqa: E402
from utils.queue_utils import HarvestEventQueue  # noqa: E402
from config.postgres_config import PostgresConfig  # noqa: E402

imports_s = time.monotonic() - t_imports
size = int(sys.argv[1]) if len(sys.argv) > 1 else 250


class Timer:
    def __init__(self) -> None:
        self.rows: list[tuple[str, float, float]] = []

    def __call__(self, name: str, fn):
        w, c = time.monotonic(), time.process_time()
        result = fn()
        self.rows.append((name, time.monotonic() - w, time.process_time() - c))
        return result


timer = Timer()
with psycopg.connect(**PostgresConfig().connection_params) as conn:
    (run_id,) = conn.execute(
        "SELECT id FROM harvest_runs WHERE status = 'closed' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    ids = [
        str(r[0])
        for r in conn.execute(
            "SELECT id FROM harvest_events WHERE harvest_run_id = %s ORDER BY id LIMIT %s",
            (run_id, size),
        )
    ]
events = timer("load_batch (DB read)", lambda: load_batch(str(run_id), ids[0], ids[-1]))
resources = timer("TransformResources (model load)", TransformResources)


def normalize_all():
    out = []
    for ele in events:
        ev = HarvestEventQueue(*ele)
        root = ET.fromstring(ev.xml.encode("utf-8"))
        metadata_ns = handle_xml.detect_metadata_namespace(root)
        payload_ns = handle_xml.detect_payload_namespace(root)
        converted = xmltodict.parse(
            handle_xml.preprocess_xml(root), process_namespaces=True
        )
        resource, ns = handle_xml.get_resource(
            converted[OAI_RECORD][OAI_METADATA], metadata_ns, payload_ns
        )
        out.append(normalize_datacite_json.normalize_datacite_json(resource, ns))
    return out


records = timer("XML parse + normalize", normalize_all)
timer(
    "validate: jsonschema.validate per record (upstream)",
    lambda: [jsonschema.validate(instance=r, schema=resources.schema) for r in records],
)
validator = timer(
    "validate: build one validator (option)",
    lambda: jsonschema.validators.validator_for(resources.schema)(resources.schema),
)
timer(
    "validate: validator.validate per record (option)",
    lambda: [validator.validate(r) for r in records],
)
texts = timer(
    "embedding text", lambda: [get_embedding_text_from_fields(r) for r in records]
)
timer(
    "embedding (fastembed, ONNX), first call",
    lambda: _embed_locally(texts, resources.embedding_transformer),
)
timer(
    "embedding again, same texts (warm session)",
    lambda: _embed_locally(texts, resources.embedding_transformer),
)

print(
    f"{len(events)} events, model {EMBEDDING_MODEL}; imports of the transform modules: {imports_s:.2f} s"
)
print(f"{'step':52} {'wall s':>7} {'CPU s':>7} {'ms/record':>10}")
for name, wall, cpu in timer.rows:
    print(f"{name:52} {wall:7.2f} {cpu:7.2f} {wall / len(events) * 1000:10.2f}")
print(
    f"mean embedding text: {sum(map(len, texts)) / len(texts):.0f} characters; example: {texts[0]!r}"
)
