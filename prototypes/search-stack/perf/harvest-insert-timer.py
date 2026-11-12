"""What a harvest event costs the warehouse database, per request as today and batched or pooled as an option.

Run inside `transform` after a harvest (it reuses that run's events), in one transaction that is rolled back:
  docker compose exec -T -w /code -e PYTHONPATH=/code/src transform /code/.venv/bin/python - < perf/harvest-insert-timer.py
The INSERT is upstream's create_harvest_events_bulk_in_db (src/app/db_methods.py, v1.10.0), copied verbatim.
"""

import time

import psycopg
from config.postgres_config import PostgresConfig

SQL = """
            INSERT INTO harvest_events
                (record_identifier,
                datestamp,
                raw_metadata,
                additional_metadata,
                repository_id,
                endpoint_id,
                metadata_protocol,
                metadata_format,
                harvest_run_id,
                is_deleted
                )
            VALUES (
                %s,
                %s,
                XMLPARSE(DOCUMENT %s),
                %s,
                (SELECT id from repositories WHERE code=%s),
                (SELECT id from endpoints WHERE harvest_url=%s),
                %s,
                %s,
                (SELECT id FROM harvest_runs WHERE id = %s and status = 'open'),
                %s
                )
            RETURNING id
            """
N = 1000
params = PostgresConfig().connection_params
with psycopg.connect(**params) as conn:
    rows = conn.execute(
        """SELECT he.record_identifier, he.datestamp, he.raw_metadata::text, r.code, e.harvest_url, he.endpoint_id
           FROM harvest_events he JOIN endpoints e ON e.id = he.endpoint_id JOIN repositories r ON r.id = e.repository_id
           WHERE he.harvest_run_id = (SELECT id FROM harvest_runs WHERE status = 'closed' ORDER BY started_at DESC LIMIT 1)
           ORDER BY he.id LIMIT %s""",
        (N,),
    ).fetchall()
    endpoint = rows[0][5]


def events(run: str, tag: str) -> list[tuple]:
    return [
        (f"{ident}-{tag}", ds, xml, None, code, url, "OAI-PMH", "XML", run, False)
        for ident, ds, xml, code, url, _ in rows
    ]


def timed(label: str, fn) -> None:
    w = time.monotonic()
    fn()
    print(f"{label:62} {(time.monotonic() - w) / N * 1000:6.2f} ms per event")


conn = psycopg.connect(**params)
run = str(
    conn.execute(
        "INSERT INTO harvest_runs (endpoint_id, status) VALUES (%s, 'open') RETURNING id",
        (endpoint,),
    ).fetchone()[0]
)


def one_by_one(
    tag: str,
) -> None:  # one statement per event on an open connection (a pool, no new connection)
    with conn.cursor() as cur:
        for e in events(run, tag):
            cur.executemany(SQL, [e], returning=True)


def batched(
    tag: str, size: int
) -> None:  # upstream's bulk route: one executemany per request
    evs = events(run, tag)
    with conn.cursor() as cur:
        for i in range(0, N, size):
            cur.executemany(SQL, evs[i : i + size], returning=True)


def connect_each(
    tag: str,
) -> (
    None
):  # as today's /harvest_event: a new connection per event (the INSERT not repeated)
    for _ in range(N):
        psycopg.connect(**params).close()


print(
    f"{N} events of the last harvest, inserted again into a new open run, rolled back at the end"
)
timed(
    "a new connection (connect + close), as every request today",
    lambda: connect_each("c"),
)
timed("INSERT one event per statement, open connection", lambda: one_by_one("a"))
timed("INSERT 100 events per executemany (the bulk route)", lambda: batched("b", 100))
timed("INSERT 1000 events per executemany", lambda: batched("d", 1000))
conn.rollback()
conn.close()
