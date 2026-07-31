from pathlib import Path
import os
from contextlib import contextmanager
from typing import Optional, Mapping
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from .mime_sql import apply_mime_prefilter_with_resolution

# Load environment variables from .env file
load_dotenv()

# Data root path configuration
MODAMA_DATA_ROOT = Path(os.environ.get("MODAMA_DATA_ROOT", "/storage/er-c-data"))


@dataclass
class PostgresConfig:
    """PostgreSQL database configuration."""

    name: str
    admin: str
    password: str
    address: str
    port: str

    def connection_string(self) -> str:
        """Return PostgreSQL connection string."""
        return f"postgresql://{self.admin}:{self.password}@{self.address}:{self.port}/{self.name}"

    @classmethod
    def from_env(cls, env: Mapping = os.environ) -> "PostgresConfig":
        """Create a PostgresConfig instance from environment variables.

        Args:
            env: Mapping containing environment variables. Defaults to os.environ

        Returns:
            PostgresConfig with values from environment or defaults
        """
        return cls(
            name=env.get("MODAMA_CRAWLER_DB", "modama_crawler"),
            admin=env.get("POSTGRES_ADMIN", "postgres"),
            password=env.get("POSTGRES_PASSWORD", ""),
            address=env.get("POSTGRES_ADDRESS", "localhost"),
            port=env.get("POSTGRES_PORT", "5432"),
        )

    @classmethod
    def from_conninfo(cls, conninfo: psycopg.ConnectionInfo):
        return cls(
            name=conninfo.dbname,
            admin=conninfo.user,
            password=conninfo.password or "",
            address=conninfo.host,
            port=str(conninfo.port),
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


def crawl_repository(
    conn: psycopg.Connection,
    root_path: Path = MODAMA_DATA_ROOT,
) -> int:
    """Crawl the repository and populate a temporary crawl table.

    Walks the filesystem tree starting at root_path, collecting file and directory
    paths with their modification times. Creates a temporary table 'crawl' with the
    same schema as the 'files' table and populates it with all discovered entries.

    Args:
        conn: PostgreSQL database connection
        root_path: Root directory to crawl (defaults to MODAMA_DATA_ROOT)

    Returns:
        int: Number of entries crawled

    Note:
        This creates a temporary table that exists only for the duration of the
        connection. The caller should call populate_files_from_crawl() to transfer
        the data to the permanent files table.
    """
    cur = conn.cursor(row_factory=dict_row)
    total = 0

    for root, dirs, files in os.walk(root_path, followlinks=False):
        # Collect all entries
        entries: list[tuple[str, float, float]] = []
        # Process directories
        for d in dirs:
            dir_path = Path(root) / d
            try:
                stat_info = dir_path.stat(follow_symlinks=False)
                mtime = max(stat_info.st_mtime, stat_info.st_ctime)
                entries.append((str(dir_path), mtime, mtime))
            except (PermissionError, FileNotFoundError):
                continue

        # Process files
        for f in files:
            file_path = Path(root) / f
            try:
                stat_info = file_path.stat(follow_symlinks=False)
                mtime = max(stat_info.st_mtime, stat_info.st_ctime)
                entries.append((str(file_path), mtime, mtime))
            except (PermissionError, FileNotFoundError):
                continue

        # Batch insert into crawl table
        if entries:
            cur.executemany(
                "INSERT INTO crawl (path, mtime) VALUES (%s, %s) "
                "ON CONFLICT (path) DO UPDATE "
                "SET mtime = %s",
                entries,
            )

        conn.commit()
        total += len(entries)
    return total


def populate_files_from_crawl(conn: psycopg.Connection) -> tuple[int, int]:
    """Transfer data from temporary crawl table to permanent files table.

    This function performs the initial population of the files table from the
    temporary crawl table created by crawl_repository().

    Args:
        conn: PostgreSQL database connection

    Returns:
        number of files inserted

    Note:
        TODO: For incremental updates, add logic to:
        - Detect modified files (present in both crawl and files with different mtime)
        - Update mtimes for modified files
        - Handle deleted files and their references (TODO: update dataset mtimes)
        - Re-run MIME matching for modified files (TODO: call apply_mime_prefilter_with_resolution selectively)
    """
    cur = conn.cursor(row_factory=dict_row)

    # Remove deleted files from database
    # Foreign key constraints should take care of everything that references these files
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
        WHERE (crawl.path, crawl.mtime) IN (SELECT path, mtime FROM files)
        """
    )
    # Insert all files from crawl into files table
    cur.execute(
        """
        INSERT INTO files (path, mtime)
        SELECT path, mtime FROM crawl
        ON CONFLICT (path) DO UPDATE
        SET mtime = EXCLUDED.mtime WHERE files.mtime != EXCLUDED.mtime
        """
    )
    files_inserted = cur.rowcount

    conn.commit()
    return files_inserted


def crawl_and_populate(
    conn: psycopg.Connection,
    root_path: Optional[Path] = None,
    filters_map: Optional[dict] = None,
) -> dict:
    """Perform complete crawling and database population workflow.

    This function orchestrates the complete initial population workflow:
    1. Crawl the filesystem and populate temporary crawl table
    2. Transfer entries from crawl table to files table
    3. Run MIME prefilter with resolution to create datasets and mimes entries

    Args:
        conn: PostgreSQL database connection
        root_path: Root directory to crawl (defaults to MODAMA_DATA_ROOT)
        filters_map: Optional mapping of MIME types to filters for apply_mime_prefilter_with_resolution

    Returns:
        dict: Summary with counts:
            - 'crawled': number of entries crawled
            - 'files_inserted': number of files inserted into files table
            - 'datasets_created': number of datasets created by MIME prefilter

    Note:
        This is designed for initial population only. For incremental updates,
        see TODO comments in populate_files_from_crawl() for future enhancements.
    """
    # Create temporary crawl table with same schema as files
    with crawling(conn):
        # Step 1: Crawl the repository
        crawled_count = crawl_repository(conn, root_path=root_path)
        conn.commit()

        # Step 2: Transfer to permanent files table
        files_inserted = populate_files_from_crawl(conn)
        conn.commit()

        # Step 3: Apply MIME prefilter to create datasets and mimes
        mime_summary = apply_mime_prefilter_with_resolution(
            conn, filters_map=filters_map
        )
        conn.commit()
        datasets_created = mime_summary.get("datasets_created", 0)

        return {
            "crawled": crawled_count,
            "files_inserted": files_inserted,
            "datasets_created": datasets_created,
        }


def ensure_dataset_tables(conn: psycopg.Connection) -> None:
    """Create the 4-table MIME prefilter schema if it does not exist.

    Schema:
      files(path_id INTEGER PRIMARY KEY, path TEXT UNIQUE, mtime FLOAT)
      datasets(dataset_id INTEGER PRIMARY KEY, path_id INTEGER UNIQUE, FK→files)
      mimes(dataset_id INTEGER, mime TEXT, FK→datasets, UNIQUE(dataset_id, mime))
      files_in_datasets(dataset_id INTEGER, path_id INTEGER, FK→datasets, FK→files, UNIQUE(dataset_id, path_id))
    """
    cur = conn.cursor(row_factory=dict_row)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            path_id SERIAL PRIMARY KEY,
            path TEXT UNIQUE,
            mtime REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS datasets (
            dataset_id SERIAL PRIMARY KEY,
            path_id INTEGER UNIQUE,
            FOREIGN KEY (path_id) REFERENCES files(path_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS mimes (
            dataset_id INTEGER,
            mime TEXT,
            FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id),
            UNIQUE(dataset_id, mime)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS files_in_datasets (
            dataset_id INTEGER,
            path_id INTEGER,
            FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id),
            FOREIGN KEY (path_id) REFERENCES files(path_id),
            UNIQUE(dataset_id, path_id)
        )
        """
    )
    conn.commit()
