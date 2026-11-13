"""Storing a recognition result in PostgreSQL: datasets, their members, and the records the server serves."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from functools import cached_property

import psycopg
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

from .extraction import Report
from .formats import Dataset, Extracted, Extraction, Listing, Result
from .records import build, oai_identifier

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


def _store_lock(conn: psycopg.Connection, check: Callable[[], None]) -> None:
    """Take the store lock for the current transaction, calling check every second while it waits.

    In turns of a second (lock_timeout), each in a savepoint that the timeout
    rolls back; while a turn waits, PostgreSQL queues new requests behind it,
    so the store is not starved by a stream of short ones.
    """
    while True:
        try:
            with conn.transaction():
                conn.execute("SET LOCAL lock_timeout = '1s'")
                conn.execute("SELECT pg_advisory_xact_lock(%s, %s)", STORE_LOCK)
                conn.execute("SET LOCAL lock_timeout TO DEFAULT")
            return
        except psycopg.errors.LockNotAvailable:
            check()


def try_read_lock(conn: psycopg.Connection) -> bool:
    """Take the store lock shared, for the current transaction, without waiting; False while records are written."""
    ((taken,),) = conn.execute(
        "SELECT pg_try_advisory_xact_lock_shared(%s, %s)", STORE_LOCK
    ).fetchall()
    return taken


def start_run(
    conn: psycopg.Connection,
    root: str,
    *,
    scope: str | None = None,
    config: dict | None = None,
) -> int:
    """Record a new crawl run and commit it, so that it is visible while the walk runs. Returns its id.

    The start time is cut to the second, like record datestamps, so that it is
    never after a datestamp the crawl writes: every file whose ctime is before
    it was there when the walk began. `scope` is a subtree crawl's path
    ("/a/b"), None for a crawl of the whole tree; `config` the configuration
    it runs with (subtree-crawl D5).
    """
    now = datetime.now(UTC).replace(microsecond=0)
    ((run_id,),) = conn.execute(
        "INSERT INTO crawl_runs (root, started_at, updated_at, scope, config)"
        " VALUES (%s, %s, now(), %s, %s) RETURNING run_id",
        (root, now, scope, None if config is None else Jsonb(config)),
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
    extraction: Report | None = None,
    ingredients: dict | None = None,
    error: str | None = None,
    unanswered: dict | None = None,
    refused: dict | None = None,
) -> None:
    """Record the run's end; with `extraction`, its counts, its identity with `ingredients`, the re-extraction and the spot check.

    `unanswered` and `refused` are the folders the file system did not
    answer and the refused folders that had datasets (listing-errors D8).
    """
    now = datetime.now(UTC)
    counts = (
        (
            extraction.run,
            extraction.reused,
            extraction.failed,
            extraction.unchanged,
            extraction.identity or None,
            Jsonb(ingredients) if ingredients is not None else None,
            Jsonb(extraction.reextracted_json()),
            Jsonb(extraction.retried_json()),
            Jsonb(extraction.spot.to_json()) if extraction.spot else None,
        )
        if extraction
        else (None,) * 9
    )
    conn.execute(
        """
        UPDATE crawl_runs SET finished_at = %s, updated_at = %s, outcome = %s,
            directories = %s, files = %s, datasets = %s, warnings = %s,
            records_changed = %s, extractions_run = %s, extractions_reused = %s,
            extractions_failed = %s, directories_unchanged = %s, identity = %s,
            identity_ingredients = %s, reextracted = %s, retried = %s, spot_check = %s,
            error = %s, unanswered = %s, refused = %s
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
            *counts,
            error,
            None if unanswered is None else Jsonb(unanswered),
            None if refused is None else Jsonb(refused),
            run_id,
        ),
    )
    conn.commit()


def ingredients_of(conn: psycopg.Connection, identity: str) -> dict | None:
    """The ingredients of a stored identity, from the newest run that has it; None if no run has (D6)."""
    row = conn.execute(
        "SELECT identity_ingredients FROM crawl_runs WHERE identity = %s"
        " AND identity_ingredients IS NOT NULL ORDER BY run_id DESC LIMIT 1",
        (identity,),
    ).fetchone()
    return row[0] if row else None


def other_identities(
    conn: psycopg.Connection, identity: str
) -> list[tuple[str, str, int, float]]:
    """(stored identity, format, datasets, their summed extraction seconds) of the stored extractions under another identity (D7)."""
    return conn.execute(
        """
        SELECT extractor_identity, format, count(*), coalesce(sum(extract_seconds), 0)
        FROM datasets WHERE extractor IS NOT NULL AND extractor_identity IS DISTINCT FROM %s
        GROUP BY 1, 2 ORDER BY 1, 2
        """,
        (identity,),
    ).fetchall()


def first_extractions(
    conn: psycopg.Connection, formats: list[str]
) -> tuple[list[tuple[str, int]], float | None]:
    """(format, datasets) of the stored datasets of these formats without an extraction, and the stored extractions' mean seconds (280)."""
    groups = conn.execute(
        "SELECT format, count(*) FROM datasets WHERE extractor IS NULL AND format = ANY(%s)"
        " GROUP BY 1 ORDER BY 1",
        (formats,),
    ).fetchall()
    if not groups:
        return [], None
    (mean,) = conn.execute("SELECT avg(extract_seconds) FROM datasets").fetchone()
    return groups, mean


def single_files_of(conn: psycopg.Connection, types: list[str]) -> int:
    """The stored single files without a format whose stored type is one of these (290)."""
    (n,) = conn.execute(
        "SELECT count(*) FROM datasets WHERE format = '' AND type = ANY(%s)", (types,)
    ).fetchone()
    return n


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
    extractions_run: int | None
    extractions_reused: int | None
    extractions_failed: int | None
    directories_unchanged: int | None
    identity: str | None
    reextracted: list | None  # Report.reextracted_json()
    spot_check: dict | None  # SpotCheck.to_json()
    error: str | None
    age: timedelta  # since the last update, by the database's clock, so that readers on other hosts agree
    # a subtree crawl's path, "/a/b"; None for a crawl of the whole tree
    scope: str | None = None
    # the folders the file system did not answer, the refused ones (listing-errors D8)
    unanswered: dict | None = None
    refused: dict | None = None


_RUN_SELECT = """SELECT run_id, root, started_at, updated_at, finished_at, outcome,
    directories, files, datasets, warnings, records_changed, extractions_run,
    extractions_reused, extractions_failed, directories_unchanged, identity,
    reextracted, spot_check, error, now() - updated_at AS age, scope, unanswered,
    refused
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
    """When the newest finished crawl of the whole tree ended; subtree crawls do not count."""
    return conn.execute(
        "SELECT max(finished_at) FROM crawl_runs WHERE outcome = 'finished' AND scope IS NULL"
    ).fetchone()[0]


def unanswered_before(
    conn: psycopg.Connection, run_id: int, folder: str
) -> dict | None:
    """The folders the file system did not answer of the newest finished run before this one that covered `folder`.

    Covered: a crawl of the whole tree, or a subtree crawl whose path holds
    the folder; subtree crawls elsewhere do not count (listing-errors D8).
    """
    row = conn.execute(
        "SELECT unanswered FROM crawl_runs WHERE outcome = 'finished' AND run_id < %s"
        " AND (scope IS NULL OR scope = %s OR starts_with(%s, scope || '/'))"
        " ORDER BY run_id DESC LIMIT 1",
        (run_id, folder, folder),
    ).fetchone()
    return row[0] if row else None


def collapsed_above(conn: psycopg.Connection, path: str) -> str | None:
    """The anchor of a stored collapsed dataset whose folder is above `path` ("/a/b"), or None (subtree-crawl D2)."""
    row = conn.execute(
        "SELECT anchor FROM datasets WHERE collapsed AND starts_with(%s, directory || '/')"
        " ORDER BY length(directory) LIMIT 1",
        (path,),
    ).fetchone()
    return row[0] if row else None


def last_full_crawl(conn: psycopg.Connection) -> tuple[str, dict | None] | None:
    """The data root and configuration of the newest finished crawl of the whole tree, or None (subtree-crawl D2)."""
    return conn.execute(
        "SELECT root, config FROM crawl_runs WHERE outcome = 'finished' AND scope IS NULL"
        " ORDER BY finished_at DESC, run_id DESC LIMIT 1"
    ).fetchone()


# The columns of a dataset row besides its id, in the order of _row()
_COLUMNS = (
    "anchor", "type", "format", "version", "basis", "warnings", "parent",
    "collapsed", "mtime", "uid", "parts", "size", "stamp", "directory",
    "extractor", "extractor_identity", "extracted", "extract_error", "extract_seconds",
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
        x and x.extractor, x and x.identity,
        Jsonb(asdict(x.extracted)) if x and x.extracted else None,
        x and x.error, x and x.seconds,
    )  # fmt: skip


class Stored:
    """The datasets and directory listings of the last stored crawl, read as the walk asks for them (D3).

    Also what the walk keeps where the file system did not answer (walk.Kept,
    change listing-errors D4). The listings are read on first use.
    """

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    @cached_property
    def _listings(self) -> dict[str, Listing]:
        return {
            path: Listing(digest, _pairs(pre), _pairs(post), retry)
            for path, digest, pre, post, retry in self.conn.execute(
                "SELECT path, digest, pre_warnings, post_warnings, retry FROM directories"
            )
        }

    def listing(self, rel: str) -> Listing | None:
        return self._listings.get(rel)

    def datasets(self, rel: str) -> list[Dataset]:
        return self._datasets_in([rel])

    def _datasets_in(self, directories: list[str]) -> list[Dataset]:
        rows = self.conn.execute(
            f"""
            SELECT {_COLUMN_LIST},
                coalesce(array_agg(m.path ORDER BY m.path) FILTER (WHERE m.path IS NOT NULL), '{{}}')
            FROM datasets d LEFT JOIN members m USING (dataset_id)
            WHERE d.directory = ANY(%s) GROUP BY d.dataset_id
            """,
            (directories,),
        ).fetchall()
        return [_dataset(row) for row in rows]

    def _directories_under(self, folders: list[str]) -> dict[str, str]:
        """Each stored dataset directory at or below one of the folders, with that folder.

        One scan of the distinct directories, each matched by its ancestors,
        rather than a prefix scan per folder: an outage gives thousands of
        folders (listing-errors D4, review 11).
        """
        wanted = set(folders)
        found = {}
        for (directory,) in self.conn.execute(
            "SELECT DISTINCT directory FROM datasets"
        ):
            path = directory
            while path not in wanted and path != "/":
                path = path.rsplit("/", 1)[0] or "/"
            if path in wanted:
                found[directory] = path
        return found

    def stored(self, subtrees: list[str], folders: list[str]) -> list[Dataset]:
        directories = set(self._directories_under(subtrees)) if subtrees else set()
        return self._datasets_in(sorted(directories | set(folders)))

    def counts(self, subtrees: list[str]) -> dict[str, int]:
        under = self._directories_under(subtrees)
        counts: dict[str, int] = {}
        for directory, n in self.conn.execute(
            "SELECT directory, count(*) FROM datasets WHERE directory = ANY(%s) GROUP BY 1",
            (list(under),),
        ):
            counts[under[directory]] = counts.get(under[directory], 0) + n
        return counts

    def extractions(self, anchors: list[str]) -> dict[str, Extraction]:
        """The stored extractions of the datasets at these anchors."""
        rows = self.conn.execute(
            """
            SELECT anchor, extractor, extractor_identity, stamp, extracted, extract_error,
                extract_seconds
            FROM datasets WHERE anchor = ANY(%s) AND extractor IS NOT NULL
            """,
            (anchors,),
        ).fetchall()
        return {row[0]: _extraction(*row[1:]) for row in rows}


def _pairs(warnings: list) -> tuple[tuple[str, str], ...]:
    return tuple((path, text) for path, text in warnings)


def _extraction(extractor, identity, stamp, extracted, error, seconds) -> Extraction:
    return Extraction(
        extractor,
        identity,
        stamp,
        Extracted(**extracted) if extracted is not None else None,
        error,
        seconds,
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
            v["extractor"], v["extractor_identity"], v["stamp"], v["extracted"],
            v["extract_error"], v["extract_seconds"],
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
    names: Mapping[str, str],
    run_id: int | None = None,
    rules: str | None = None,
    check: Callable[[], None] = lambda: None,
    scope: str | None = None,
) -> int:
    """Bring the stored datasets, directory listings and records up to date with the result.

    `names` are the formats' display names for the records (records.format_names).
    `check` is called while the store lock is waited for and before the
    commit; what it raises ends the store without a change (SIGTERM).

    Returns the number of records that changed. A record's datestamp moves only
    when its content changes, so an unchanged crawl leaves datestamps alone;
    records of datasets that disappeared are deleted. All records changed by
    one call get the same datestamp, taken after the store lock is held: no
    OAI-PMH request reads until the commit, so a harvest whose window ends
    after the datestamp reads the records, and one whose window ended before
    gets them in its next window. With a run, its rule set is stored in the
    same transaction, so that the next crawl knows what the stored datasets
    were recognised under.

    With `scope`, a subtree crawl's path ("/a/b"), the result is that of the
    subtree alone: only datasets and records under it are deleted, its
    stored listings are deleted and none are stored, and no rule set is
    recorded, so that the next crawl of the whole tree recognises it again
    (subtree-crawl D4). "Under" is the path itself or a path that continues
    it after a "/", so that a sibling "/a/bc" is not under "/a/b".
    """
    anchors = [d.anchor for d in result.datasets]
    with conn.cursor() as cur:
        # Rows stay from crawl to crawl (D3): only what changed is written
        if scope is None:
            cur.execute("DELETE FROM datasets WHERE anchor <> ALL(%s)", (anchors,))
        else:
            gone = cur.execute(
                "DELETE FROM datasets WHERE (directory = %s OR starts_with(directory, %s || '/'))"
                " AND anchor <> ALL(%s) RETURNING anchor",
                (scope, scope, anchors),
            ).fetchall()
        for d in result.datasets:
            row = cur.execute(_UPSERT_DATASET, _row(d)).fetchone()
            if row is not None:  # inserted or changed
                cur.execute("DELETE FROM members WHERE dataset_id = %s", row)
                cur.executemany(
                    "INSERT INTO members (dataset_id, path) VALUES (%s, %s)",
                    [(row[0], m) for m in d.members],
                )
        if scope is not None:
            cur.execute(
                "DELETE FROM directories WHERE path = %s OR starts_with(path, %s || '/')",
                (scope, scope),
            )
        else:
            cur.execute(
                "DELETE FROM directories WHERE path <> ALL(%s)",
                (list(result.listings),),
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
                for path, x in (result.listings.items() if scope is None else ())
            ],
        )  # fmt: skip
        records = [build(d, names) for d in result.datasets]
        # waits for the requests in flight, which are single short queries
        _store_lock(conn, check)
        if scope is None:
            cur.execute(
                "DELETE FROM records WHERE identifier <> ALL(%s)",
                ([identifier for identifier, _ in records],),
            )
        else:  # records have no anchor: by the identifiers of the deleted datasets
            cur.execute(
                "DELETE FROM records WHERE identifier = ANY(%s)",
                ([oai_identifier(anchor) for (anchor,) in gone],),
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
        if run_id is not None and scope is None:
            cur.execute(
                "UPDATE crawl_runs SET rules = %s WHERE run_id = %s", (rules, run_id)
            )
    check()  # the caller closes the connection: the transaction is rolled back
    conn.commit()
    return changed
