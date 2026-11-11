"""Storing a recognition result in PostgreSQL: datasets, their members, and the records the server serves."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

from .formats import Dataset, Extracted, Extraction, Listing, Result
from .records import build

# Advisory lock keys (two 32-bit integers; the database is the crawler's own).
# CRAWL_LOCK: one crawl at a time, held by the crawl's session and released by
# PostgreSQL when that session ends, also when the crawler crashes. STORE_LOCK:
# held exclusively by the transaction that writes records, shared by every
# OAI-PMH request, so that a harvester never reads while a crawl's records are
# half written (crawl spec, "A harvest does not miss a crawl's records").
CRAWL_LOCK = (0x6D6F, 1)
STORE_LOCK = (0x6D6F, 2)


def try_crawl_lock(conn: psycopg.Connection) -> bool:
    """Take the crawl lock for this session without waiting; False if another crawl holds it."""
    ((taken,),) = conn.execute(
        "SELECT pg_try_advisory_lock(%s, %s)", CRAWL_LOCK
    ).fetchall()
    conn.commit()
    return taken


def try_read_lock(conn: psycopg.Connection) -> bool:
    """Take the store lock shared, for the current transaction, without waiting; False while records are written."""
    ((taken,),) = conn.execute(
        "SELECT pg_try_advisory_xact_lock_shared(%s, %s)", STORE_LOCK
    ).fetchall()
    return taken


def ensure_tables(conn: psycopg.Connection) -> None:
    """Create the schema if it does not exist. There are no migrations: recreate the database after a change.

    The datasets, members and directories tables carry the state of the last
    stored crawl over to the next one (D3), and are read by the chain tool
    (python/search-chain); their shape is provisional.
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
            uid INTEGER NOT NULL,
            parts JSONB NOT NULL,
            size BIGINT NOT NULL,
            stamp TEXT NOT NULL,
            directory TEXT NOT NULL,
            extractor TEXT,
            extractor_version TEXT,
            extracted JSONB,
            extract_error TEXT,
            extract_seconds DOUBLE PRECISION,
            extract_retry BOOLEAN
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS datasets_directory ON datasets (directory)")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS members (
            dataset_id INTEGER REFERENCES datasets(dataset_id) ON DELETE CASCADE,
            path TEXT NOT NULL
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS members_dataset ON members (dataset_id)")
    # One row per directory listed by the last stored crawl (D3)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS directories (
            path TEXT PRIMARY KEY,
            digest TEXT NOT NULL,
            pre_warnings JSONB NOT NULL,
            post_warnings JSONB NOT NULL,
            retry BOOLEAN NOT NULL
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
            error TEXT,
            rules TEXT
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


def last_finished(conn: psycopg.Connection) -> datetime | None:
    """When the newest finished crawl ended."""
    return conn.execute(
        "SELECT max(finished_at) FROM crawl_runs WHERE outcome = 'finished'"
    ).fetchone()[0]


# The columns of a dataset row besides its id, in the order of _row()
_COLUMNS = (
    "anchor", "type", "format", "version", "basis", "warnings", "parent",
    "collapsed", "mtime", "uid", "parts", "size", "stamp", "directory",
    "extractor", "extractor_version", "extracted", "extract_error", "extract_seconds",
    "extract_retry",
)  # fmt: skip
_COLUMN_LIST = ", ".join(_COLUMNS)
_VALUES = ", ".join(f"EXCLUDED.{c}" for c in _COLUMNS[1:])
_CURRENT = ", ".join(f"datasets.{c}" for c in _COLUMNS[1:])
_UPSERT_DATASET = f"""
    INSERT INTO datasets ({_COLUMN_LIST}) VALUES ({", ".join(["%s"] * len(_COLUMNS))})
    ON CONFLICT (anchor) DO UPDATE SET ({", ".join(_COLUMNS[1:])}) = ({_VALUES})
    WHERE ({_CURRENT}) IS DISTINCT FROM ({_VALUES})
    RETURNING dataset_id
"""


def _row(d: Dataset) -> tuple:
    x = d.extraction
    return (
        d.anchor, d.type, d.format, d.version, d.basis, Jsonb(list(d.warnings)),
        d.parent, d.collapsed, d.mtime, d.uid, Jsonb(list(d.parts)), d.size,
        d.stamp, d.directory,
        x and x.extractor, x and x.version,
        Jsonb(asdict(x.extracted)) if x and x.extracted else None,
        x and x.error, x and x.seconds, x and x.retry,
    )  # fmt: skip


class Stored:
    """The datasets and directory listings of the last stored crawl, read as the walk asks for them (D3)."""

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn
        self._listings = {
            path: Listing(digest, _pairs(pre), _pairs(post), retry)
            for path, digest, pre, post, retry in conn.execute(
                "SELECT path, digest, pre_warnings, post_warnings, retry FROM directories"
            )
        }

    def listing(self, rel: str) -> Listing | None:
        return self._listings.get(rel)

    def datasets(self, rel: str) -> list[Dataset]:
        rows = self.conn.execute(
            f"""
            SELECT {_COLUMN_LIST},
                coalesce(array_agg(m.path ORDER BY m.path) FILTER (WHERE m.path IS NOT NULL), '{{}}')
            FROM datasets d LEFT JOIN members m USING (dataset_id)
            WHERE d.directory = %s GROUP BY d.dataset_id
            """,
            (rel,),
        ).fetchall()
        return [_dataset(row) for row in rows]

    def extractions(self, anchors: list[str]) -> dict[str, Extraction]:
        """The stored extractions of the datasets at these anchors."""
        rows = self.conn.execute(
            """
            SELECT anchor, extractor, extractor_version, stamp, extracted, extract_error,
                extract_seconds, extract_retry
            FROM datasets WHERE anchor = ANY(%s) AND extractor IS NOT NULL
            """,
            (anchors,),
        ).fetchall()
        return {row[0]: _extraction(*row[1:]) for row in rows}


def _pairs(warnings: list) -> tuple[tuple[str, str], ...]:
    return tuple((path, text) for path, text in warnings)


def _extraction(
    extractor, version, stamp, extracted, error, seconds, retry
) -> Extraction:
    return Extraction(
        extractor,
        version,
        stamp,
        Extracted(**extracted) if extracted is not None else None,
        error,
        seconds,
        retry,
    )


def _dataset(row: tuple) -> Dataset:
    v = dict(zip(_COLUMNS, row, strict=False))
    return Dataset(
        anchor=v["anchor"],
        members=tuple(row[len(_COLUMNS)]),
        parts=tuple(v["parts"]),
        basis=v["basis"],
        warnings=tuple(v["warnings"]),
        collapsed=v["collapsed"],
        type=v["type"],
        format=v["format"],
        version=v["version"],
        parent=v["parent"],
        mtime=v["mtime"],
        uid=v["uid"],
        size=v["size"],
        stamp=v["stamp"],
        directory=v["directory"],
        extraction=_extraction(
            v["extractor"], v["extractor_version"], v["stamp"], v["extracted"],
            v["extract_error"], v["extract_seconds"], v["extract_retry"],
        ) if v["extractor"] is not None else None,
    )  # fmt: skip


def previous(conn: psycopg.Connection, rules: str) -> Stored | None:
    """The last stored crawl, if it ran under the same rule set; else None: everything is recognised again (D3)."""
    row = conn.execute(
        "SELECT rules FROM crawl_runs WHERE rules IS NOT NULL ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    return Stored(conn) if row is not None and row[0] == rules else None


def store(
    conn: psycopg.Connection,
    result: Result,
    run_id: int | None = None,
    rules: str | None = None,
) -> int:
    """Bring the stored datasets, directory listings and records up to date with the result.

    Returns the number of records that changed. A record's datestamp moves only
    when its content changes, so an unchanged crawl leaves datestamps alone;
    records of datasets that disappeared are deleted. All records changed by
    one call get the same datestamp, taken after the store lock is held: no
    OAI-PMH request reads until the commit, so a harvest whose window ends
    after the datestamp reads the records, and one whose window ended before
    gets them in its next window. With a run, its rule set is stored in the
    same transaction, so that the next crawl knows what the stored datasets
    were recognised under.
    """
    with conn.cursor() as cur:
        # Rows stay from crawl to crawl (D3): only what changed is written
        cur.execute(
            "DELETE FROM datasets WHERE anchor <> ALL(%s)",
            ([d.anchor for d in result.datasets],),
        )
        for d in result.datasets:
            row = cur.execute(_UPSERT_DATASET, _row(d)).fetchone()
            if row is not None:  # inserted or changed
                cur.execute("DELETE FROM members WHERE dataset_id = %s", row)
                cur.executemany(
                    "INSERT INTO members (dataset_id, path) VALUES (%s, %s)",
                    [(row[0], m) for m in d.members],
                )
        cur.execute(
            "DELETE FROM directories WHERE path <> ALL(%s)", (list(result.listings),)
        )
        cur.executemany(
            """
            INSERT INTO directories (path, digest, pre_warnings, post_warnings, retry)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (path) DO UPDATE
            SET digest = EXCLUDED.digest, pre_warnings = EXCLUDED.pre_warnings,
                post_warnings = EXCLUDED.post_warnings, retry = EXCLUDED.retry
            WHERE (directories.digest, directories.pre_warnings, directories.post_warnings, directories.retry)
                IS DISTINCT FROM (EXCLUDED.digest, EXCLUDED.pre_warnings, EXCLUDED.post_warnings, EXCLUDED.retry)
            """,
            [
                (path, x.digest, Jsonb([list(w) for w in x.pre]), Jsonb([list(w) for w in x.post]), x.retry)
                for path, x in result.listings.items()
            ],
        )  # fmt: skip
        records = [build(d) for d in result.datasets]
        # waits for the requests in flight, which are single short queries
        cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", STORE_LOCK)
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
        # Not before the store lock: a crawl stopped while it waits for the
        # lock would hold the run's row, and could not record its failure
        if run_id is not None:
            cur.execute(
                "UPDATE crawl_runs SET rules = %s WHERE run_id = %s", (rules, run_id)
            )
    conn.commit()
    return changed
