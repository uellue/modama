import logging
import os
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from .mime_sql import apply_mime_prefilter_with_resolution
from .records import publish_records

log = logging.getLogger(__name__)


def conninfo_from_env(env: Mapping = os.environ) -> str:
    return make_conninfo(
        dbname=env.get("MODAMA_CRAWLER_DB", "modama_crawler"),
        user=env.get("POSTGRES_ADMIN", "postgres"),
        password=env.get("POSTGRES_PASSWORD", ""),
        host=env.get("POSTGRES_ADDRESS", "localhost"),
        port=env.get("POSTGRES_PORT", "5432"),
    )


@contextmanager
def crawling(conn):
    cur = conn.cursor(row_factory=dict_row)
    # Create temporary crawl table with same schema as files
    cur.execute(
        """
        CREATE TEMP TABLE crawl ( LIKE files INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES )
        ON COMMIT PRESERVE ROWS
        """
    )
    try:
        yield
    finally:
        cur.execute("DROP TABLE IF EXISTS crawl")


def _is_utf8(name: str) -> bool:
    # os.walk() returns names that aren't valid UTF-8 with surrogate escapes,
    # which PostgreSQL text can't store.
    try:
        name.encode()
        return True
    except UnicodeEncodeError:
        return False


def crawl_repository(conn: psycopg.Connection, root_path: Path) -> int:
    """Walk the tree below root_path into the temporary crawl table.

    Returns the number of entries crawled.
    """
    total = 0
    for root, dirs, files in os.walk(root_path, followlinks=False):
        entries = []
        for name in dirs + files:
            if not _is_utf8(name):
                log.warning("Skipping non-UTF-8 name %r in %s", name, root)
                continue
            path = Path(root) / name
            try:
                stat = path.stat(follow_symlinks=False)
            except (PermissionError, FileNotFoundError):
                continue
            entries.append((str(path), max(stat.st_mtime, stat.st_ctime), stat.st_uid))
        # Don't descend into directories we skipped
        dirs[:] = [d for d in dirs if _is_utf8(d)]
        with conn.cursor().copy("COPY crawl (path, mtime, uid) FROM STDIN") as copy:
            for entry in entries:
                copy.write_row(entry)
        conn.commit()
        total += len(entries)
    return total


def populate_files_from_crawl(conn: psycopg.Connection) -> int:
    """Transfer data from temporary crawl table to permanent files table.

    Returns the number of new or changed files.

    Note:
        TODO: For incremental updates, re-run MIME matching for modified files
    """
    cur = conn.cursor(row_factory=dict_row)

    # Remove deleted files, cascading to their datasets and records
    cur.execute(
        """
        DELETE FROM files
        WHERE files.path NOT IN (SELECT path FROM crawl)
        """
    )
    # Ignore everything that is unchanged
    cur.execute(
        """
        DELETE FROM crawl
        WHERE (crawl.path, crawl.mtime, crawl.uid) IN (SELECT path, mtime, uid FROM files)
        """
    )
    cur.execute(
        """
        INSERT INTO files (path, mtime, uid)
        SELECT path, mtime, uid FROM crawl
        ON CONFLICT (path) DO UPDATE
        SET mtime = EXCLUDED.mtime, uid = EXCLUDED.uid
        """
    )
    files_inserted = cur.rowcount

    conn.commit()
    return files_inserted


def crawl_and_populate(
    conn: psycopg.Connection,
    root_path: Path,
    filters_map: dict | None = None,
) -> dict:
    """Crawl root_path and bring files, datasets and OAI-PMH records up to date.

    1. Crawl the filesystem into the temporary crawl table
    2. Transfer entries from the crawl table to the files table
    3. Run the MIME prefilter to create datasets and mimes entries
    4. Publish a record for every dataset

    Returns a summary with counts.
    """
    with crawling(conn):
        crawled_count = crawl_repository(conn, root_path=root_path)
        files_inserted = populate_files_from_crawl(conn)
        mime_summary = apply_mime_prefilter_with_resolution(
            conn, filters_map=filters_map
        )
        conn.commit()

    records_changed = publish_records(conn, root_path)
    return {
        "crawled": crawled_count,
        "files_inserted": files_inserted,
        "datasets_created": mime_summary.get("datasets_created", 0),
        "records_changed": records_changed,
    }


def ensure_dataset_tables(conn: psycopg.Connection) -> None:
    """Create the schema if it does not exist.

    files, datasets, mimes and files_in_datasets are the crawler's view of the
    file system. records holds what the OAI-PMH server publishes.
    """
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            path_id SERIAL PRIMARY KEY,
            path TEXT UNIQUE,
            mtime DOUBLE PRECISION,
            uid INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS datasets (
            dataset_id SERIAL PRIMARY KEY,
            path_id INTEGER UNIQUE REFERENCES files(path_id) ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS mimes (
            dataset_id INTEGER REFERENCES datasets(dataset_id) ON DELETE CASCADE,
            mime TEXT,
            UNIQUE(dataset_id, mime)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS files_in_datasets (
            dataset_id INTEGER REFERENCES datasets(dataset_id) ON DELETE CASCADE,
            path_id INTEGER REFERENCES files(path_id) ON DELETE CASCADE,
            UNIQUE(dataset_id, path_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            dataset_id INTEGER PRIMARY KEY REFERENCES datasets(dataset_id) ON DELETE CASCADE,
            identifier TEXT NOT NULL UNIQUE,
            datestamp TIMESTAMPTZ NOT NULL,
            metadata JSONB NOT NULL
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS records_datestamp ON records (datestamp, dataset_id)"
    )
    conn.commit()
