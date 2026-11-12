"""Patch 0001 changes no result: jsonschema.validate() per record against one validator per process, on the
warehouse's real records and on invalid copies of them (change cpu-budget, decision 177).

Every closed harvest run's events are normalized as transform_batch_impl does (the XML to the DataCite JSON),
then each record is validated as it is, without its first required property, and with the type of its
first property broken, both ways. Prints the counts and every difference (raised or not, message, path);
exits 1 on a difference. Read-only. Run like perf/batch-memory.py (its header has the docker command), with
/probe/validator-check.py instead.
"""

import json
import sys

import psycopg
import transform.transform_core as core
import xmltodict
from jsonschema.exceptions import best_match
from jsonschema.validators import validate, validator_for
from lxml import etree as ET
from planning.transform_planning import load_batch
from utils import handle_xml, normalize_datacite_json


def normalized(xml: str) -> dict | None:
    """The record as transform_batch_impl validates it (transform_core.py, the steps before validate)."""
    root = ET.fromstring(xml.encode("utf-8"))
    metadata_ns = handle_xml.detect_metadata_namespace(root)
    payload_ns = handle_xml.detect_payload_namespace(root)
    converted = xmltodict.parse(
        handle_xml.preprocess_xml(root), process_namespaces=True
    )
    if (
        core.OAI_RECORD not in converted
        or core.OAI_METADATA not in converted[core.OAI_RECORD]
    ):
        return None
    result = handle_xml.get_resource(
        converted[core.OAI_RECORD][core.OAI_METADATA], metadata_ns, payload_ns
    )
    if result is None:
        return None
    resource, namespace = result
    return normalize_datacite_json.normalize_datacite_json(resource, namespace)


def outcome(check, record):
    try:
        check(record)
    except Exception as e:  # noqa: BLE001  # the outcome is the comparison
        return (
            type(e).__name__,
            getattr(e, "message", str(e)),
            list(getattr(e, "absolute_path", [])),
        )
    return None


with open(core.SCHEMA_PATH) as f:
    schema = json.load(f)
cls = validator_for(schema)
cls.check_schema(schema)
validator = cls(schema)


def old(record):
    validate(instance=record, schema=schema)


def new(record):  # patch 0001
    error = best_match(validator.iter_errors(record))
    if error is not None:
        raise error


with psycopg.connect(**core.PostgresConfig().connection_params) as c:
    runs = c.execute(
        "SELECT hr.id, min(he.id::text), max(he.id::text) FROM harvest_runs hr JOIN harvest_events he"
        " ON he.harvest_run_id = hr.id WHERE hr.status = 'closed' GROUP BY hr.id"
    ).fetchall()
records = [
    r
    for run in runs
    for e in load_batch(str(run[0]), str(run[1]), str(run[2]))
    if not e.is_deleted and (r := normalized(e.xml)) is not None
]
required = schema.get("required", [])
cases = []
for r in records:
    cases.append(("as is", r))
    if required and required[0] in r:
        cases.append(
            (f"without {required[0]}", {k: v for k, v in r.items() if k != required[0]})
        )
    first = next(iter(r), None)
    if first is not None:
        cases.append((f"{first} as 12345", {**r, first: 12345}))
differences = 0
rejected = 0
for label, record in cases:
    a, b = outcome(old, record), outcome(new, record)
    rejected += a is not None
    if a != b:
        differences += 1
        print(f"DIFFERENT ({label}): validate {a} / one validator {b}")
print(
    f"{len(records)} records, {len(cases)} cases, {rejected} rejected by validate(), {differences} differences"
)
sys.exit(1 if differences else 0)
