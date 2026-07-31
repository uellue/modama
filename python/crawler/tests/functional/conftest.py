"""Functional test fixtures for end-to-end OAI-PMH testing.

This module provides isolated fixtures for functional tests that:
1. Create realistic test directory structures with actual files
2. Crawl and populate the database
3. Test the OAI-PMH server with an oaipmh-scythe client

All fixtures are self-contained and don't depend on other conftest.py files.
"""

import pytest
from pathlib import Path
from typing import Generator
import datetime

import psycopg
from psycopg.rows import dict_row


# ============================================================================
# File Directory Fixture - Creates realistic test data
# ============================================================================


@pytest.fixture
def test_data_dir(tmp_path: Path) -> Path:
    """Create a realistic test directory structure with various file types.

    Creates:
    - Text files (.txt)
    - XML metadata files (.xml)
    - Subdirectories

    The directory structure is designed to be easily extensible as tests grow.

    Returns:
        Path to the test data directory root.
    """
    # Create directory structure
    (tmp_path / "dataset_alpha").mkdir()
    (tmp_path / "dataset_beta").mkdir()
    (tmp_path / "subfolder").mkdir()

    # Create text file with readable content
    (tmp_path / "dataset_alpha" / "README.txt").write_text(
        "# Dataset Alpha\n\nThis is the readme file for dataset alpha.\n"
        "It contains basic information about the data.\n",
        encoding="utf-8",
    )

    # Create metadata XML file
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
    <title>Dataset Alpha Metadata</title>
    <creator>Research Team</creator>
    <date>2024-06-15</date>
    <description>Experimental dataset with various file types.</description>
</metadata>
"""
    (tmp_path / "dataset_alpha" / "metadata.xml").write_text(
        xml_content, encoding="utf-8"
    )

    # Create CSV data file
    csv_content = """id,name,value,timestamp
1,alpha,100,2024-06-15T10:30:00Z
2,beta,200,2024-06-15T11:45:00Z
3,gamma,150,2024-06-15T12:00:00Z
"""
    (tmp_path / "dataset_beta" / "data.csv").write_text(csv_content, encoding="utf-8")

    # Create another text file in subfolder
    (tmp_path / "subfolder" / "notes.txt").write_text(
        "Notes and observations from the experiment.\n\n"
        "Observation 1: Initial results are promising.\n"
        "Observation 2: Need to verify with additional runs.\n",
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture
def test_data_dir_with_png(tmp_path: Path) -> Path:
    """Create test directory including valid PNG images.

    Uses Pillow to generate real PNG files (not just magic bytes).

    Args:
        tmp_path: Pytest temporary directory fixture

    Returns:
        Path to test data directory with PNG files
    """
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow library not available for PNG generation")

    # Create directory structure
    (tmp_path / "images").mkdir()

    # Create valid PNG image 1 - small RGB image
    img1 = Image.new("RGB", (64, 64), color=(255, 0, 0))
    img1.save(tmp_path / "images" / "red_square.png", "PNG")

    # Create valid PNG image 2 - gradient
    img2 = Image.new("RGB", (100, 100))
    pixels = img2.load()
    for x in range(100):
        for y in range(100):
            pixels[x, y] = (x * 2 % 256, y * 2 % 256, (x + y) % 256)
    img2.save(tmp_path / "images" / "gradient.png", "PNG")

    # Create text file alongside images
    (tmp_path / "images" / "README.txt").write_text(
        "Image dataset with various PNG files for testing.\n", encoding="utf-8"
    )

    return tmp_path


# ============================================================================
# Database Fixtures
# ============================================================================


@pytest.fixture
def populated_database(
    postgresql, test_data_dir: Path
) -> Generator[psycopg.Connection, None, None]:
    """Create a PostgreSQL database with full crawl and MIME resolution.

    This fixture combines:
    1. The postgresql fixture for database access
    2. The test_data_dir fixture for file content
    3. Complete crawling workflow from modama_crawler.database

    Args:
        postgresql: Pytest-postgresql database fixture
        test_data_dir: Directory with test files

    Yields:
        Database connection ready for querying
    """
    conn = postgresql
    conn.row_factory = dict_row

    # Import crawler modules
    from modama_crawler import database
    from modama_crawler import mime_sql

    # Ensure schema exists
    database.ensure_dataset_tables(conn)

    # Build comprehensive MIME filters
    filters_map = mime_sql.build_mime_filter_map()

    # Run complete crawl workflow
    summary = database.crawl_and_populate(
        conn, root_path=test_data_dir, filters_map=filters_map
    )

    # Verify the crawl worked
    assert summary["crawled"] > 0, "No files were crawled"
    assert summary["files_inserted"] > 0, "No files were inserted"
    assert summary["datasets_created"] > 0, "No datasets were created"

    yield conn

    # Cleanup happens automatically with postgresql fixture


@pytest.fixture
def populated_database_with_png(
    postgresql, test_data_dir_with_png: Path
) -> Generator[psycopg.Connection, None, None]:
    """Database with PNG images included.

    Similar to populated_database but includes valid PNG files for testing
    image MIME type handling.

    Args:
        postgresql: Database fixture
        test_data_dir_with_png: Directory with PNG files

    Yields:
        Database connection with PNG data
    """
    conn = postgresql
    conn.row_factory = dict_row

    from modama_crawler import database
    from modama_crawler import mime_sql

    database.ensure_dataset_tables(conn)

    filters_map = mime_sql.build_mime_filter_map()

    summary = database.crawl_and_populate(
        conn, root_path=test_data_dir_with_png, filters_map=filters_map
    )

    assert summary["crawled"] > 0, "No files were crawled"

    yield conn


# ============================================================================
# OAI-PMH Backend Fixtures
# ============================================================================


@pytest.fixture
def backend_with_populated_db(
    populated_database: psycopg.Connection, test_data_dir: Path
):
    """Create an OAIFileDBBackend instance with a populated database.

    Args:
        populated_database: Database fixture with crawled data
        test_data_dir: Test directory path

    Yields:
        OAIFileDBBackend instance ready for testing
    """
    from modama_crawler.server import OAIFileDBBackend
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        conninfo=populated_database.info,
        open=True,
    )

    backend = OAIFileDBBackend(pool=pool, root=test_data_dir)

    yield backend

    pool.close()


# ============================================================================
# HTTP Server Fixtures
# ============================================================================


class ThreadedServer:
    """Simple threaded HTTP server for testing."""

    def __init__(self, app, port: int = 18765):
        from werkzeug.serving import make_server

        self.server = make_server("localhost", port, app, threaded=True)
        self.port = port
        self.thread = None

    def start(self):
        """Start the server in a background thread."""
        import threading

        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the server."""
        self.server.shutdown()


@pytest.fixture
def running_server(
    populated_database, test_data_dir: Path
) -> Generator[str, None, None]:
    """Start the OAI-PMH server in a background thread.

    Args:
        postgresql: Database fixture
        test_data_dir: Test directory path

    Yields:
        Base URL of the running server (e.g., "http://localhost:18765")
    """
    import time
    import requests

    from modama_crawler.server import create_app, PostgresConfig
    from psycopg_pool import ConnectionPool

    # Create database config
    db_config = PostgresConfig.from_conninfo(populated_database.info)

    from modama_crawler.repository import RepositoryConfig

    pool = ConnectionPool(
        conninfo=db_config.connection_string(),
        open=True,
    )

    # Create app with test configuration
    repo_config = RepositoryConfig(
        admin_email="test@example.com",
        repository_name="Test Repository",
        earliest_datestamp=datetime.datetime.fromtimestamp(
            test_data_dir.stat().st_mtime
        ),  # Use mtime of test dir
        data_root=test_data_dir,
    )
    app = create_app(pool=pool, repo_config=repo_config)

    # Start server
    server = ThreadedServer(app, port=18765)
    server.start()

    # Wait for server to be ready
    max_attempts = 10
    base_url = f"http://localhost:{server.port}/oai"

    for attempt in range(max_attempts):
        try:
            resp = requests.get(f"{base_url}?verb=Identify", timeout=2)
            if resp.status_code == 200:
                break
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            pass

        time.sleep(0.5)
    else:
        raise RuntimeError(f"Server failed to start after {max_attempts} attempts")

    yield base_url

    server.stop()
    pool.close()


# ============================================================================
# OAI-PMH Client Fixture
# ============================================================================


@pytest.fixture
def scythe_client(running_server: str):
    """Create an oaipmh-scythe client connected to the test server.

    Args:
        running_server: Base URL of the running OAI-PMH server

    Yields:
        Scythe client instance ready for querying
    """
    from oaipmh_scythe import Scythe

    client = Scythe(running_server)
    yield client
