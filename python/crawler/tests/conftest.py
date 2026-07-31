import pytest

import os
from importlib import reload
from pathlib import Path
import psycopg
from datetime import datetime
from typing import Generator
import threading
import time
import requests

import xdg

# Import crawler classes
import modama_crawler.recognition
from modama_crawler.database import ensure_dataset_tables


# MIME for self test
CANARY_MIME = xdg.Mime.MIMEtype("application", "x.modamatestfile")


# File handler for self test
class Canary(modama_crawler.recognition.FileHandler):
    file_types = (CANARY_MIME,)

    @staticmethod
    def xdg_mimeinfo():
        return """
<mime-type type="application/x.modamatestfile">
  <comment>Canary file type to test database installation effect</comment>
  <glob pattern="*.modamatestfile"/>
</mime-type>
"""


@pytest.fixture(scope="session", autouse=True)
def install_handlers(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("localshare")
    os.environ["XDG_DATA_HOME"] = str(workdir)
    # Make the new base directory active
    reload(xdg.BaseDirectory)
    modama_crawler.recognition.FileHandler.install_mime_info()
    # Self-test: Make sure the MIME definition installation worked
    assert xdg.Mime.get_type_by_name("/home/whatever.modamatestfile") == CANARY_MIME


# ============================================================================
# Fixtures for Unit Tests (no full test data needed)
# ============================================================================


@pytest.fixture
def pg_unit_test(postgresql):
    """Simple PostgreSQL connection for unit tests that don't need test data.

    Returns a fresh connection with row factory set.
    """
    conn = postgresql
    conn.row_factory = psycopg.rows.dict_row
    return conn


# ============================================================================
# Shared Fixtures for OAI-PMH Server Tests
# ============================================================================


@pytest.fixture
def test_database(postgresql, tmp_path) -> Generator[psycopg.Connection, None, None]:
    """Create a PostgreSQL test database with schema and test data.

    Sets up:
    - 6 dataset paths with varying mtimes for pagination and date filtering tests
    - MIME types for each dataset
    - Paths are stored as absolute paths (tmp_path / relative_path)
    """

    # Use the postgresql fixture connection
    conn = postgresql
    conn.row_factory = psycopg.rows.dict_row

    # Create schema using the official function
    ensure_dataset_tables(conn)

    # Test data: 6 datasets with different mtimes
    # Date range for testing: 2024-06-01 to 2024-12-31
    # Paths are relative, will be converted to absolute for database storage
    relative_paths = [
        "dataset-alpha/file1.txt",
        "dataset-beta/file2.txt",
        "dataset-gamma/file3.txt",
        "dataset-delta/file4.txt",
        "dataset-epsilon/file5.txt",
        "dataset-zeta/file6.txt",
    ]

    cur = conn.cursor()

    # Insert files with absolute paths
    # Use specific dates to match test expectations:
    # dataset-alpha: 2024-01-01 (before date filter range)
    # dataset-beta: 2024-06-01 (at from_ boundary)
    # dataset-gamma: 2024-06-15 (within range)
    # dataset-delta: 2024-07-01 (within range)
    # dataset-epsilon: 2024-12-31 23:59:59 (at until boundary)
    # dataset-zeta: 2025-02-01 (after until boundary)
    test_dates = [
        datetime(2024, 1, 1),
        datetime(2024, 6, 1),
        datetime(2024, 6, 15),
        datetime(2024, 7, 1),
        datetime(2024, 12, 31, 23, 59, 59),
        datetime(2025, 2, 1),
    ]
    mimes = [
        "application/pdf",
        "text/plain",
        "image/jpeg",
        "application/pdf",
        "text/csv",
        "application/zip",
    ]

    for i, rel_path in enumerate(relative_paths):
        # Store as absolute path (will be stripped by server)
        abs_path = str(tmp_path / rel_path)
        mtime = test_dates[i].timestamp()
        mime = mimes[i]
        cur.execute(
            "INSERT INTO files (path_id, path, mtime) VALUES (%s, %s, %s)",
            (i + 1, abs_path, mtime),
        )
        # Insert dataset
        cur.execute(
            "INSERT INTO datasets (dataset_id, path_id) VALUES (%s, %s)", (i + 1, i + 1)
        )
        # Insert MIME type
        cur.execute(
            "INSERT INTO mimes (dataset_id, mime) VALUES (%s, %s)", (i + 1, mime)
        )
        # Link file to dataset
        cur.execute(
            "INSERT INTO files_in_datasets (dataset_id, path_id) VALUES (%s, %s)",
            (i + 1, i + 1),
        )

    conn.commit()
    yield conn


@pytest.fixture
def test_files(tmp_path) -> Path:
    """Create temporary test files that match the database paths."""
    # Create files for each dataset
    test_paths = [
        "dataset-alpha/file1.txt",
        "dataset-beta/file2.txt",
        "dataset-gamma/file3.txt",
        "dataset-delta/file4.txt",
        "dataset-epsilon/file5.txt",
        "dataset-zeta/file6.txt",
    ]

    for path in test_paths:
        file_path = tmp_path / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(f"Content of {path}")

    return tmp_path


@pytest.fixture(scope="session")
def running_http_server(test_database, test_files):
    """Start OAI-PMH server as HTTP server in background thread.

    Yields the base URL of the running server (e.g., "http://127.0.0.1:12345/oai").
    Server is automatically stopped when test completes.
    """
    from modama_crawler.server import create_app, PostgresConfig
    from psycopg_pool import ConnectionPool
    from werkzeug.serving import make_server

    # Create PostgreSQL config from test_database fixture
    db_config = PostgresConfig(
        name=test_database.info.dbname,
        admin=test_database.info.user,
        password=test_database.info.password or "",
        address=test_database.info.host,
        port=str(test_database.info.port),
    )

    pool = ConnectionPool(
        conninfo=db_config.connection_string(),
        min_size=1,
        max_size=2,
    )

    # Configure backend for testing
    config_dict = {"TESTING": True, "DB_ROOT_PATH": test_files, "ROOT_PATH": Path("")}

    # Create app with direct configuration (no environment monkeypatching needed)
    app = create_app(pool=pool, config=config_dict)

    # Create server instance
    server = make_server("127.0.0.1", 0, app, threaded=True)
    port = server.server_address[1]

    # Start server in background thread
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Wait for server to be ready
    base_url = f"http://127.0.0.1:{port}/oai"

    # Retry connection a few times
    for i in range(10):
        try:
            response = requests.get(f"{base_url}?verb=Identify", timeout=1)
            if response.status_code == 200:
                break
        except requests.ConnectionError:
            time.sleep(0.1)

    try:
        yield base_url
    finally:
        # Shutdown server
        server.shutdown()


@pytest.fixture
def sickle_client(running_http_server):
    """Create sickle client connected to test HTTP server."""
    from sickle import Sickle

    return Sickle(running_http_server)


@pytest.fixture
def oaipmh_client(running_http_server):
    """Create oaipmh client connected to test HTTP server."""
    from oaipmh.client import Client
    from oaipmh.metadata import global_metadata_registry, oai_dc_reader

    # Register the oai_dc reader with the global metadata registry
    # This is needed because oaipmh doesn't register it by default
    if not global_metadata_registry.hasReader("oai_dc"):
        global_metadata_registry.registerReader("oai_dc", oai_dc_reader)

    return Client(running_http_server)


@pytest.fixture
def backend_with_db(test_database, test_files):
    """Create an OAIFileDBBackend instance configured with test database and files.

    Provides the backend instance needed to access FileHandler creation logic.
    """
    from psycopg_pool import ConnectionPool
    from modama_crawler.server import OAIFileDBBackend, PostgresConfig

    # Use connection pool with test database
    db_config = PostgresConfig(
        name=test_database.info.dbname,
        admin=test_database.info.user,
        password=test_database.info.password or "",
        address=test_database.info.host,
        port=str(test_database.info.port),
    )

    pool = ConnectionPool(
        conninfo=db_config.connection_string(),
        min_size=1,
        max_size=2,
    )

    # Create backend instance with explicit root = test_files
    backend = OAIFileDBBackend(pool=pool, root=test_files)

    return backend
