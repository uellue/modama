"""Storing a recognition result in PostgreSQL: datasets, their members, and the records the server serves."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

from .formats import Result
from .records import build


def ensure_tables(conn: psycopg.Connection) -> None:
    """Create the schema if it does not exist. There are no migrations: recreate the database after a change.

    The datasets and members tables are written on every crawl and read by
    the chain tool (python/search-chain) only; their shape is provisional.
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
    # One row per crawl (crawl-runs spec, D1). Read as an interface by the
    # chain tool (python/search-chain); change it only together with that.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS crawl_runs (
            run_id SERIAL PRIMARY KEY,
            root TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ,
            outcome TEXT CHECK (outcome IN ('finished', 'failed')),
            directories INTEGER NOT NULL DEFAULT 0,
            files INTEGER NOT NULL DEFAULT 0,
            datasets INTEGER,
            warnings INTEGER,
            records_changed INTEGER,
            error TEXT
        )
        """
    )
    conn.commit()


def start_run(conn: psycopg.Connection, root: str) -> int:
    """Record a new crawl run and commit it, so that it is visible while the walk runs. Returns its id.

    The start time is cut to the second, like record datestamps, so that it is
    never after a datestamp the crawl writes: every file whose ctime is before
    it was there when the walk began.
    """
    now = datetime.now(UTC).replace(microsecond=0)
    ((run_id,),) = conn.execute(
        "INSERT INTO crawl_runs (root, started_at, updated_at) VALUES (%s, %s, now()) RETURNING run_id",
        (root, now),
    ).fetchall()
    conn.commit()
    return run_id


def progress_run(
    conn: psycopg.Connection, run_id: int, directories: int, files: int
) -> None:
    conn.execute(
        "UPDATE crawl_runs SET directories = %s, files = %s, updated_at = now() WHERE run_id = %s",
        (directories, files, run_id),
    )
    conn.commit()


def end_run(
    conn: psycopg.Connection,
    run_id: int,
    outcome: str,
    *,
    directories: int,
    files: int,
    datasets: int | None = None,
    warnings: int | None = None,
    records_changed: int | None = None,
    error: str | None = None,
) -> None:
    now = datetime.now(UTC)
    conn.execute(
        """
        UPDATE crawl_runs SET finished_at = %s, updated_at = %s, outcome = %s,
            directories = %s, files = %s, datasets = %s, warnings = %s,
            records_changed = %s, error = %s
        WHERE run_id = %s
        """,
        (
            now,
            now,
            outcome,
            directories,
            files,
            datasets,
            warnings,
            records_changed,
            error,
            run_id,
        ),
    )
    conn.commit()


@dataclass(frozen=True)
class Run:
    run_id: int
    root: str
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    outcome: str | None
    directories: int
    files: int
    datasets: int | None
    warnings: int | None
    records_changed: int | None
    error: str | None
    age: timedelta  # since the last update, by the database's clock, so that readers on other hosts agree


_RUN_SELECT = """SELECT run_id, root, started_at, updated_at, finished_at, outcome,
    directories, files, datasets, warnings, records_changed, error, now() - updated_at AS age
    FROM crawl_runs"""


def recent_runs(conn: psycopg.Connection, limit: int) -> list[Run]:
    """The newest runs first."""
    with conn.cursor(row_factory=class_row(Run)) as cur:
        return cur.execute(
            f"{_RUN_SELECT} ORDER BY started_at DESC, run_id DESC LIMIT %s", (limit,)
        ).fetchall()


def get_run(conn: psycopg.Connection, run_id: int) -> Run:
    with conn.cursor(row_factory=class_row(Run)) as cur:
        return cur.execute(f"{_RUN_SELECT} WHERE run_id = %s", (run_id,)).fetchone()


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
