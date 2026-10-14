import logging
import os
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.conninfo import make_conninfo

from .mime import detect
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
    cur = conn.cursor()
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


def populate_files_from_crawl(conn: psycopg.Connection, batch_size: int = 1000) -> int:
    """Bring files up to date with the crawl table and create a dataset per regular file.

    Only new and changed files are classified, since that may read their contents.
    Returns the number of new or changed files.
    """
    cur = conn.cursor()
    # Deleted files cascade to their datasets and records
    cur.execute("DELETE FROM files WHERE path NOT IN (SELECT path FROM crawl)")
    cur.execute(
        """
        DELETE FROM crawl
        WHERE (path, mtime, uid) IN (SELECT path, mtime, uid FROM files)
        """
    )
    conn.commit()

    changed = 0
    with conn.cursor(name="changed_files", withhold=True) as crawled:
        crawled.execute("SELECT path, mtime, uid FROM crawl")
        while rows := crawled.fetchmany(batch_size):
            params = []
            for path, mtime, uid in rows:
                try:
                    params.append((path, mtime, uid, detect(path)))
                except OSError as e:
                    log.warning("Skipping %s: %s", path, e)
            cur.executemany(
                """
                INSERT INTO files (path, mtime, uid, mime) VALUES (%s, %s, %s, %s)
                ON CONFLICT (path) DO UPDATE
                SET mtime = EXCLUDED.mtime, uid = EXCLUDED.uid, mime = EXCLUDED.mime
                """,
                params,
            )
            changed += len(params)
            conn.commit()

    # One dataset per regular file, for now
    cur.execute(
        """
        INSERT INTO datasets (path_id)
        SELECT path_id FROM files WHERE mime NOT LIKE 'inode/%'
        ON CONFLICT (path_id) DO NOTHING
        """
    )
    conn.commit()
    return changed


def crawl_and_populate(conn: psycopg.Connection, root_path: Path) -> dict:
    """Crawl root_path and bring files, datasets and OAI-PMH records up to date.

    Returns a summary with counts.
    """
    with crawling(conn):
        crawled = crawl_repository(conn, root_path=root_path)
        changed = populate_files_from_crawl(conn)
    return {
        "crawled": crawled,
        "files_changed": changed,
        "records_changed": publish_records(conn, root_path),
    }


def ensure_dataset_tables(conn: psycopg.Connection) -> None:
    """Create the schema if it does not exist.

    files, datasets and files_in_datasets are the crawler's view of the
    file system. records holds what the OAI-PMH server publishes.
    """
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            path_id SERIAL PRIMARY KEY,
            path TEXT UNIQUE,
            mtime DOUBLE PRECISION,
            uid INTEGER,
            mime TEXT
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
