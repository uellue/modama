"""Storing a recognition result in PostgreSQL: datasets, their members, and the records the server serves."""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
from psycopg.types.json import Jsonb

from .formats import Result
from .records import build


def ensure_tables(conn: psycopg.Connection) -> None:
    """Create the schema if it does not exist. There are no migrations: recreate the database after a change.

    The datasets and members tables are written on every crawl and read by
    nothing yet (the survey command will); their shape is provisional.
    """
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS datasets (
            dataset_id SERIAL PRIMARY KEY,
            anchor TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL,
            format TEXT NOT NULL,
            version TEXT NOT NULL,
            basis TEXT NOT NULL,
            warnings JSONB NOT NULL,
            parent TEXT,
            collapsed BOOLEAN NOT NULL,
            mtime DOUBLE PRECISION NOT NULL,
            uid INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS members (
            dataset_id INTEGER REFERENCES datasets(dataset_id) ON DELETE CASCADE,
            path TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            record_id SERIAL PRIMARY KEY,
            identifier TEXT NOT NULL UNIQUE,
            datestamp TIMESTAMPTZ NOT NULL,
            metadata JSONB NOT NULL
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS records_datestamp ON records (datestamp, record_id)"
    )
    conn.commit()


def store(conn: psycopg.Connection, result: Result) -> int:
    """Replace the stored datasets with the result and bring the records up to date.

    Returns the number of records that changed. A record's datestamp moves only
    when its content changes, so an unchanged crawl leaves datestamps alone;
    records of datasets that disappeared are deleted. All records changed by
    one call get the same datestamp, taken just before they are written, so
    that a harvester's window is the upsert and commit, not the whole call.
    """
    with conn.cursor() as cur:
        # The whole content is replaced, and nothing reads these tables while
        # the crawl runs (the server reads records only), so TRUNCATE instead
        # of a cascading DELETE, which is quadratic without an index on members.
        cur.execute("TRUNCATE datasets, members")
        for d in result.datasets:
            cur.execute(
                """
                INSERT INTO datasets (anchor, type, format, version, basis, warnings, parent, collapsed, mtime, uid)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING dataset_id
                """,
                (
                    d.anchor,
                    d.type,
                    d.format,
                    d.version,
                    d.basis,
                    Jsonb(list(d.warnings)),
                    d.parent,
                    d.collapsed,
                    d.mtime,
                    d.uid,
                ),
            )
            ((dataset_id,),) = cur.fetchall()
            cur.executemany(
                "INSERT INTO members (dataset_id, path) VALUES (%s, %s)",
                [(dataset_id, m) for m in d.members],
            )
        records = [build(d) for d in result.datasets]
        cur.execute(
            "DELETE FROM records WHERE identifier <> ALL(%s)",
            ([identifier for identifier, _ in records],),
        )
        changed = cur.rowcount
        now = datetime.now(UTC).replace(microsecond=0)
        cur.executemany(
            """
            INSERT INTO records (identifier, metadata, datestamp)
            VALUES (%s, %s, %s)
            ON CONFLICT (identifier) DO UPDATE
            SET metadata = EXCLUDED.metadata, datestamp = EXCLUDED.datestamp
            WHERE records.metadata IS DISTINCT FROM EXCLUDED.metadata
            """,
            [(identifier, Jsonb(metadata), now) for identifier, metadata in records],
        )
        changed += cur.rowcount
    conn.commit()
    return changed
