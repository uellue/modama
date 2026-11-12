"""Everything this tool knows about upstream internals, in one place (D4).

EOSC metadata-warehouse v1.10.0 and data-commons-search 0.10.2: the tables
endpoints, harvest_runs, harvest_events and records of datasetdb; the
harvester keeping an OAI identifier after its last ":"; the record URL as
OpenSearch _id; the DAG warehouse_transform_index with harvest_run_id in its
conf; Airflow's REST API /api/v2. The e2e test traces real items through the
real stack, so an upgrade that changes one of these fails there.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

import psycopg

INDEX_DAG = "warehouse_transform_index"
TIMEOUT = 60


class Unreachable(Exception):
    """A store cannot be reached; the message names it."""


def local_id(identifier: str) -> str:
    """The identifier as the harvester keeps it: the part after the last ':'."""
    return identifier.rsplit(":", 1)[-1]


@dataclass(frozen=True)
class HarvestRun:
    id: str
    status: str  # open, closed, failed
    started_at: datetime
    from_date: datetime | None
    until_date: datetime | None


@dataclass(frozen=True)
class Event:
    run: HarvestRun
    datestamp: datetime | None
    is_deleted: bool
    error: str | None


@dataclass(frozen=True)
class WarehouseRecord:
    id: str
    url: str
    datestamp: datetime | None
    synced: bool
    synced_at: datetime | None


@dataclass(frozen=True)
class IndexRun:
    state: str
    start: datetime | None
    end: datetime | None
    harvest_run_id: str | None


_RUN = "r.id::text, r.status::text, r.started_at, r.from_date, r.until_date"


def endpoint(conn: psycopg.Connection, harvest_url: str) -> str | None:
    row = conn.execute(
        "SELECT id::text FROM endpoints WHERE harvest_url = %s", (harvest_url,)
    ).fetchone()
    return row[0] if row else None


def harvest_runs(conn: psycopg.Connection, endpoint_id: str) -> list[HarvestRun]:
    """The endpoint's harvest runs, oldest first."""
    rows = conn.execute(
        f"SELECT {_RUN} FROM harvest_runs r WHERE r.endpoint_id = %s ORDER BY r.started_at, r.until_date",
        (endpoint_id,),
    ).fetchall()
    return [HarvestRun(*row) for row in rows]


def latest_event(
    conn: psycopg.Connection, endpoint_id: str, local: str
) -> Event | None:
    row = conn.execute(
        f"""
        SELECT {_RUN}, e.datestamp, e.is_deleted, e.error_message
        FROM harvest_events e JOIN harvest_runs r ON r.id = e.harvest_run_id
        WHERE e.endpoint_id = %s AND e.record_identifier = %s
            -- events of failed or open runs are not transformed; the next run harvests their window again
            AND r.status = 'closed'
        ORDER BY r.started_at DESC, e.datestamp DESC LIMIT 1
        """,
        (endpoint_id, local),
    ).fetchone()
    return Event(HarvestRun(*row[:5]), *row[5:]) if row else None


def record(
    conn: psycopg.Connection, endpoint_id: str, local: str
) -> WarehouseRecord | None:
    row = conn.execute(
        """
        SELECT id, url, datestamp, opensearch_synced, opensearch_synced_at
        FROM records WHERE endpoint_id = %s AND record_identifier = %s
        """,
        (endpoint_id, local),
    ).fetchone()
    return WarehouseRecord(*row) if row else None


def get_json(url: str, store: str, data=None, headers=None, missing_ok=False):
    """GET (or POST with data) a JSON document; None for a 404 if missing_ok. Raises Unreachable naming the store."""
    request = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        if missing_ok and e.code == 404:
            return None
        raise Unreachable(f"{store} at {url}: HTTP {e.code} {e.reason}") from e
    except (urllib.error.URLError, OSError) as e:
        raise Unreachable(f"{store} at {url}: {getattr(e, 'reason', e)}") from e


def document(opensearch: str, index: str, url: str) -> dict | None:
    """The index's document (`_source`) for the record URL, which upstream uses as _id; None if there is none."""
    doc = get_json(
        f"{opensearch}/{index}/_doc/{urllib.parse.quote(url, safe='')}",
        "OpenSearch",
        missing_ok=True,
    )
    return doc["_source"] if doc and doc.get("found") else None


def has_document(opensearch: str, index: str, url: str) -> bool:
    """Whether the index holds a document for the record URL."""
    return document(opensearch, index, url) is not None


def search_hits(search_api: str, query: str) -> list[dict]:
    """The search API's hits for query, in rank order, as `/search` returns them."""
    result = get_json(
        f"{search_api}/search?"
        + urllib.parse.urlencode({"q": query, "resource": "datasets"}),
        "search API",
    )
    return result["hits"]


def search(search_api: str, query: str) -> list[str]:
    """The URLs of the search API's hits for query, in rank order."""
    return [hit["_source"]["url"] for hit in search_hits(search_api, query)]


def repository_code(conn: psycopg.Connection, harvest_url: str) -> str | None:
    """The code of the repository of the endpoint with this harvest URL: the index documents' `_repo`."""
    row = conn.execute(
        """
        SELECT r.code FROM endpoints e JOIN repositories r ON r.id = e.repository_id
        WHERE e.harvest_url = %s
        """,
        (harvest_url,),
    ).fetchone()
    return row[0] if row else None


def index_runs(airflow: str, user: str, password: str) -> list[IndexRun]:
    """All runs of the indexing DAG, newest first, each with the harvest run it indexed.

    All, page by page: T needs every closed harvest's indexing run, and the
    API cannot filter by conf.
    """
    token = get_json(
        f"{airflow}/auth/token", "Airflow", {"username": user, "password": password}
    )["access_token"]
    runs, page = [], 100
    while True:
        batch = get_json(
            f"{airflow}/api/v2/dags/{INDEX_DAG}/dagRuns?order_by=-start_date&limit={page}&offset={len(runs)}",
            "Airflow",
            headers={"Authorization": f"Bearer {token}"},
        )["dag_runs"]
        runs += batch
        if len(batch) < page:
            break
    return [
        IndexRun(
            r["state"],
            _time(r.get("start_date")),
            _time(r.get("end_date")),
            (r.get("conf") or {}).get("harvest_run_id"),
        )
        for r in runs
    ]


def _time(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None
