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
