from pathlib import Path
import os

import psycopg
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Data root path configuration
MODAMA_DATA_ROOT = Path(os.environ.get("MODAMA_DATA_ROOT", "/storage/er-c-data"))

# PostgreSQL configuration
DB_NAME = os.environ.get("MODAMA_CRAWLER_DB", "modama_crawler")
POSTGRES_ADMIN = os.environ.get("POSTGRES_ADMIN", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_ADDRESS = os.environ.get("POSTGRES_ADDRESS", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")


def get_connection_string() -> str:
    """Build PostgreSQL connection string from environment variables.

    Returns:
        str: PostgreSQL connection string
    """
    return f"postgresql://{POSTGRES_ADMIN}:{POSTGRES_PASSWORD}@{POSTGRES_ADDRESS}:{POSTGRES_PORT}/{DB_NAME}"


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
    cur = conn.cursor()

    # Create temporary crawl table with same schema as files
    cur.execute(
        """
        CREATE TEMP TABLE crawl (
            path TEXT UNIQUE,
            mtime REAL
        ) ON COMMIT PRESERVE ROWS
        """
    )

    # Collect all entries
    entries: list[tuple[str, float]] = []

    for root, dirs, files in os.walk(root_path, followlinks=False):
        # Process directories
        for d in dirs:
            dir_path = Path(root) / d
            try:
                stat_info = dir_path.stat(follow_symlinks=False)
                mtime = max(stat_info.st_mtime, stat_info.st_ctime)
                entries.append((str(dir_path), mtime))
            except (PermissionError, FileNotFoundError):
                continue

        # Process files
        for f in files:
            file_path = Path(root) / f
            try:
                stat_info = file_path.stat(follow_symlinks=False)
                mtime = max(stat_info.st_mtime, stat_info.st_ctime)
                entries.append((str(file_path), mtime))
            except (PermissionError, FileNotFoundError):
                continue

    # Batch insert into crawl table
    if entries:
        cur.executemany(
            "INSERT INTO crawl (path, mtime) VALUES (%s, %s)",
            entries,
        )

    conn.commit()
    return len(entries)


def populate_files_from_crawl(conn: psycopg.Connection) -> tuple[int, int]:
    """Transfer data from temporary crawl table to permanent files table.

    This function performs the initial population of the files table from the
    temporary crawl table created by crawl_repository().

    Args:
        conn: PostgreSQL database connection

    Returns:
        tuple: (number of files inserted, number of directories inserted)

    Note:
        TODO: For incremental updates, add logic to:
        - Detect modified files (present in both crawl and files with different mtime)
        - Detect deleted files (present in files but not in crawl)
        - Update mtimes for modified files
        - Handle deleted files and their references (TODO: update dataset mtimes)
        - Re-run MIME matching for modified files (TODO: call apply_mime_prefilter_with_resolution selectively)
    """
    cur = conn.cursor()

    # Insert all files from crawl into files table
    cur.execute(
        """
        INSERT INTO files (path, mtime)
        SELECT path, mtime FROM crawl
        ON CONFLICT (path) DO NOTHING
        """
    )
    files_inserted = cur.rowcount

    conn.commit()

    # Drop the temporary crawl table
    cur.execute("DROP TABLE IF EXISTS crawl")
    conn.commit()

    return files_inserted, 0  # Directories are also inserted into files table


def ensure_dataset_tables(conn: psycopg.Connection) -> None:
    """Create the 4-table MIME prefilter schema if it does not exist.

    Schema:
      files(path_id INTEGER PRIMARY KEY, path TEXT UNIQUE, mtime FLOAT)
      datasets(dataset_id INTEGER PRIMARY KEY, path_id INTEGER UNIQUE, FK→files)
      mimes(dataset_id INTEGER, mime TEXT, FK→datasets, UNIQUE(dataset_id, mime))
      files_in_datasets(dataset_id INTEGER, path_id INTEGER, FK→datasets, FK→files, UNIQUE(dataset_id, path_id))
    """
    cur = conn.cursor()
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
