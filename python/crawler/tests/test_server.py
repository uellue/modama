"""Tests for the clean OAI-PMH server implementation.

This file contains unit tests, integration tests, and endpoint tests that don't
require external OAI-PMH client libraries.

For protocol compliance tests using external client libraries:
- test_server_sickle.py: Tests using the sickle OAI-PMH client library
- test_server_oaipmh.py: Tests using the oaipmh client library

Shared fixtures are defined in conftest.py and available to all test files.
"""

import pytest
from pathlib import Path
import sqlite3
from datetime import datetime

# Import the server components
from modama_crawler.server import (
    SimpleServer,
    _make_oai_response,
    _make_error,
    _encode_resumption_token,
    _decode_resumption_token,
    _parse_datestamp,
    _format_datestamp,
    _query_datasets_from_db,
    app,
)
from modama_crawler import server as server_module
from modama_crawler.mime_sql import ensure_dataset_tables
from modama_crawler.repository import (
    quote_path,
    unquote_path,
    get_identifier,
    path_from_identifier,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def server_with_db(test_database, test_files, monkeypatch) -> SimpleServer:
    """Create a SimpleServer configured to use the test database and files."""
    # Override ROOT_PATH and DB_ROOT_PATH for testing

    original_root = server_module.ROOT_PATH
    original_db_root = server_module.DB_ROOT_PATH

    # Set DB_ROOT_PATH to test_files (where files are stored)
    server_module.DB_ROOT_PATH = test_files
    # Set ROOT_PATH to empty (no additional prefix to strip)
    server_module.ROOT_PATH = Path("")
    monkeypatch.setenv("OAI_DB_PATH", ":memory:")  # Will use test_database directly

    try:
        # Create server instance
        server = SimpleServer(base_url="http://test.local/oai")

        # Store database connection for tests to use
        server._test_conn = test_database

        return server
    finally:
        server_module.ROOT_PATH = original_root
        server_module.DB_ROOT_PATH = original_db_root


@pytest.fixture
def flask_client(test_database, test_files, monkeypatch):
    """Create a Flask test client configured with test database and files."""
    original_root = server_module.ROOT_PATH
    original_db_root = server_module.DB_ROOT_PATH

    server_module.DB_ROOT_PATH = test_files
    server_module.ROOT_PATH = Path("")
    monkeypatch.setenv("OAI_DB_PATH", ":memory:")

    try:
        app.config["TESTING"] = True
        client = app.test_client()
        yield client
    finally:
        server_module.ROOT_PATH = original_root
        server_module.DB_ROOT_PATH = original_db_root


# ============================================================================


def test_resumption_token_encoding():
    """Test resumption token encoding and decoding."""
    # Test with continuation path and metadataPrefix
    token = _encode_resumption_token(Path("some/path"), metadataPrefix="oai_dc")
    assert token is not None
    continuation, params = _decode_resumption_token(token)
    assert str(continuation) == "some/path"
    assert params["metadataPrefix"] == "oai_dc"

    # Test with all parameters
    token = _encode_resumption_token(
        Path("another/path"),
        metadataPrefix="oai_dc",
        from_="2024-01-01T00:00:00Z",
        until="2024-12-31T23:59:59Z",
    )
    assert token is not None
    continuation, params = _decode_resumption_token(token)
    assert str(continuation) == "another/path"
    assert params["metadataPrefix"] == "oai_dc"
    assert params["from"] == "2024-01-01T00:00:00Z"
    assert params["until"] == "2024-12-31T23:59:59Z"

    # Test with None continuation
    token = _encode_resumption_token(None)
    assert token is None


def test_datestamp_conversion():
    """Test datestamp parsing and formatting."""
    # Test parsing
    dt = _parse_datestamp("2024-01-15T10:30:00Z")
    assert isinstance(dt, datetime)
    assert dt.year == 2024
    assert dt.month == 1
    assert dt.day == 15

    # Test formatting
    timestamp = dt.timestamp()
    formatted = _format_datestamp(timestamp)
    assert formatted == "2024-01-15T10:30:00Z"

    # Test None
    assert _parse_datestamp(None) is None


def test_server_identify():
    """Test Identify verb."""
    server = SimpleServer(base_url="http://example.org/oai")
    info = server.identify()

    assert info["repositoryName"] == "Modama OAI-PMH server"
    assert info["baseURL"] == "http://example.org/oai"
    assert info["protocolVersion"] == "2.0"
    assert info["deletedRecord"] == "no"
    assert info["granularity"] == "YYYY-MM-DDThh:mm:ssZ"
    assert "adminEmails" in info


def test_server_list_metadata_formats():
    """Test ListMetadataFormats verb."""
    server = SimpleServer()
    formats = server.listMetadataFormats()

    assert len(formats) == 1
    assert formats[0][0] == "oai_dc"
    assert "oai_dc.xsd" in formats[0][1]
    assert formats[0][2] == "http://purl.org/dc/elements/1.1/"


def test_server_list_sets():
    """Test ListSets verb."""
    server = SimpleServer()
    sets = server.listSets()

    assert sets == []


def test_error_response():
    """Test error response generation."""
    error_xml = _make_error("badVerb", "Missing verb parameter")

    assert b"<error" in error_xml
    assert b'code="badVerb"' in error_xml
    assert b"Missing verb parameter" in error_xml
    assert b"OAI-PMH" in error_xml


def test_oai_response_structure():
    """Test OAI-PMH response structure."""
    children = [{"repositoryName": "Test Repository"}, {"baseURL": "http://test.org"}]
    args = {"verb": "Identify", "base_url": "http://test.org"}

    xml = _make_oai_response("Identify", children, args)

    # Check XML structure
    assert b"<?xml version" in xml
    assert b"<OAI-PMH" in xml
    assert b"<responseDate>" in xml
    assert b"<request" in xml
    assert b"<Identify>" in xml
    assert b"<repositoryName>Test Repository</repositoryName>" in xml
    assert b"<baseURL>http://test.org</baseURL>" in xml


# ============================================================================
# Database Query Tests
# ============================================================================


def test_query_datasets_from_db_basic(test_database):
    """Test basic database query without filters."""
    paths, next_path = _query_datasets_from_db(
        test_database, continuation=None, from_=None, until=None, batch_size=10
    )

    # Should get all 6 paths
    assert len(paths) == 6
    assert next_path is None  # All records returned, no continuation


def test_query_datasets_from_db_pagination(test_database, tmp_path):
    """Test pagination with batch_size."""
    # Set DB_ROOT_PATH to tmp_path so paths can be stripped correctly
    from modama_crawler import server as server_module

    original_db_root = server_module.DB_ROOT_PATH
    server_module.DB_ROOT_PATH = tmp_path

    try:
        # First batch
        paths1, next_path1 = _query_datasets_from_db(
            test_database, continuation=None, from_=None, until=None, batch_size=2
        )
        assert len(paths1) == 2
        assert str(paths1[0]) == "dataset-alpha/file1.txt"
        assert str(paths1[1]) == "dataset-beta/file2.txt"
        assert next_path1 is not None  # More records available

        # Second batch
        paths2, next_path2 = _query_datasets_from_db(
            test_database, continuation=next_path1, from_=None, until=None, batch_size=2
        )
        assert len(paths2) == 2
        assert str(paths2[0]) == "dataset-delta/file4.txt"
        assert str(paths2[1]) == "dataset-epsilon/file5.txt"
        assert next_path2 is not None

        # Third batch (last) - still returns next_path because len == batch_size
        # The actual end is detected when the next query returns empty results
        paths3, next_path3 = _query_datasets_from_db(
            test_database, continuation=next_path2, from_=None, until=None, batch_size=2
        )
        assert len(paths3) == 2
        assert str(paths3[0]) == "dataset-gamma/file3.txt"
        assert str(paths3[1]) == "dataset-zeta/file6.txt"
        assert next_path3 is not None  # Last path returned, but we need to try again

        # Fourth query - should return empty
        paths4, next_path4 = _query_datasets_from_db(
            test_database, continuation=next_path3, from_=None, until=None, batch_size=2
        )
        assert len(paths4) == 0
        assert next_path4 is None
    finally:
        server_module.DB_ROOT_PATH = original_db_root  # No more records


def test_query_datasets_from_db_date_filtering(test_database, tmp_path):
    """Test date filtering with from_ and until."""
    # Set DB_ROOT_PATH to tmp_path
    from modama_crawler import server as server_module

    original_db_root = server_module.DB_ROOT_PATH
    server_module.DB_ROOT_PATH = tmp_path

    try:
        # Filter to date range: 2024-06-01 to 2024-12-31
        from_dt = datetime(2024, 6, 1)
        until_dt = datetime(2024, 12, 31)

        paths, next_path = _query_datasets_from_db(
            test_database,
            continuation=None,
            from_=from_dt,
            until=until_dt,
            batch_size=10,
        )

        # Should get 4 records (ordered by path): beta, delta, epsilon, gamma
        assert len(paths) == 4
        assert str(paths[0]) == "dataset-beta/file2.txt"
        assert str(paths[1]) == "dataset-delta/file4.txt"
        assert str(paths[2]) == "dataset-epsilon/file5.txt"
        assert str(paths[3]) == "dataset-gamma/file3.txt"
        assert next_path is None
    finally:
        server_module.DB_ROOT_PATH = original_db_root


def test_query_datasets_from_db_from_boundary(test_database, tmp_path):
    """Test that from_ is inclusive (boundary condition)."""
    # Set DB_ROOT_PATH to tmp_path
    from modama_crawler import server as server_module

    original_db_root = server_module.DB_ROOT_PATH
    server_module.DB_ROOT_PATH = tmp_path

    try:
        # from_ at exact boundary: 2024-06-01 (dataset-beta)
        from_dt = datetime(2024, 6, 1)

        paths, _ = _query_datasets_from_db(
            test_database, continuation=None, from_=from_dt, until=None, batch_size=10
        )

        # Should include dataset-beta (at boundary) and all after
        assert len(paths) == 5
        assert str(paths[0]) == "dataset-beta/file2.txt"
    finally:
        server_module.DB_ROOT_PATH = original_db_root


def test_query_datasets_from_db_until_boundary(test_database, tmp_path):
    """Test that until is inclusive in OAI-PMH (boundary condition)."""
    # Set DB_ROOT_PATH to tmp_path
    from modama_crawler import server as server_module

    original_db_root = server_module.DB_ROOT_PATH
    server_module.DB_ROOT_PATH = tmp_path

    try:
        # until at exact boundary: 2024-12-31 23:59:59 (dataset-epsilon)
        until_dt = datetime(2024, 12, 31, 23, 59, 59)

        paths, _ = _query_datasets_from_db(
            test_database, continuation=None, from_=None, until=until_dt, batch_size=10
        )

        # Should include dataset-epsilon (at boundary) and all before it in time
        # Results are ordered by path, so we check count and that epsilon is included
        assert len(paths) == 5
        path_strings = [str(p) for p in paths]
        assert "dataset-epsilon/file5.txt" in path_strings
        assert "dataset-zeta/file6.txt" not in path_strings  # Excluded (after until)
    finally:
        server_module.DB_ROOT_PATH = original_db_root


def test_query_datasets_from_db_empty_result(test_database, tmp_path):
    """Test query with no matching results."""
    # Set DB_ROOT_PATH to tmp_path
    from modama_crawler import server as server_module

    original_db_root = server_module.DB_ROOT_PATH
    server_module.DB_ROOT_PATH = tmp_path

    try:
        # Date range with no data
        from_dt = datetime(2023, 1, 1)
        until_dt = datetime(2023, 12, 31)

        paths, next_path = _query_datasets_from_db(
            test_database,
            continuation=None,
            from_=from_dt,
            until=until_dt,
            batch_size=10,
        )

        assert len(paths) == 0
        assert next_path is None
    finally:
        server_module.DB_ROOT_PATH = original_db_root


# ============================================================================
# Integration Tests with SimpleServer
# ============================================================================


def test_list_identifiers_basic(server_with_db):
    """Test basic listIdentifiers with database."""
    # Mock the _get_conn method to use test database
    original_get_conn = server_with_db._get_conn
    server_with_db._get_conn = lambda: server_with_db._test_conn

    try:
        headers, token = server_with_db.listIdentifiers(
            from_=None,
            until=None,
            continuation=None,
            batch_size=2,
            metadataPrefix="oai_dc",
        )

        assert len(headers) == 2
        assert "identifier" in headers[0]
        assert "datestamp" in headers[0]
        assert token is not None  # More records available
    finally:
        server_with_db._get_conn = original_get_conn


def test_list_identifiers_pagination(server_with_db):
    """Test listIdentifiers pagination."""
    server_with_db._get_conn = lambda: server_with_db._test_conn

    try:
        # First batch
        headers1, token1 = server_with_db.listIdentifiers(
            from_=None,
            until=None,
            continuation=None,
            batch_size=2,
            metadataPrefix="oai_dc",
        )
        assert len(headers1) == 2
        assert token1 is not None

        # Second batch
        headers2, token2 = server_with_db.listIdentifiers(
            from_=None,
            until=None,
            continuation=token1,
            batch_size=2,
            metadataPrefix="oai_dc",
        )
        assert len(headers2) == 2
        assert token2 is not None

        # Third batch
        headers3, token3 = server_with_db.listIdentifiers(
            from_=None,
            until=None,
            continuation=token2,
            batch_size=2,
            metadataPrefix="oai_dc",
        )
        assert len(headers3) == 2
        # Last batch may or may not have token depending on implementation
        # (token is set when len == batch_size, even if it's the last batch)
    finally:
        server_with_db._get_conn = lambda: server_with_db._test_conn


def test_list_identifiers_date_filtering(server_with_db):
    """Test listIdentifiers with date filtering."""
    server_with_db._get_conn = lambda: server_with_db._test_conn

    try:
        from_dt = datetime(2024, 6, 1)
        until_dt = datetime(2024, 12, 31)

        headers, token = server_with_db.listIdentifiers(
            from_=from_dt,
            until=until_dt,
            continuation=None,
            batch_size=10,
            metadataPrefix="oai_dc",
        )

        # Should get 4 records
        assert len(headers) == 4
        assert token is None  # All records returned
    finally:
        server_with_db._get_conn = lambda: server_with_db._test_conn


def test_list_records_basic(server_with_db):
    """Test basic listRecords with database."""
    server_with_db._get_conn = lambda: server_with_db._test_conn

    try:
        records, token = server_with_db.listRecords(
            metadataPrefix="oai_dc",
            from_=None,
            until=None,
            continuation=None,
            batch_size=2,
        )

        assert len(records) == 2
        assert "header" in records[0]
        assert "metadata" in records[0]
        assert token is not None
    finally:
        server_with_db._get_conn = lambda: server_with_db._test_conn


def test_resumption_token_preserves_parameters(server_with_db):
    """Test that resumption token preserves metadataPrefix, from, and until."""
    server_with_db._get_conn = lambda: server_with_db._test_conn

    try:
        from_dt = datetime(2024, 6, 1)
        until_dt = datetime(2024, 12, 31)

        # First request
        headers1, token1 = server_with_db.listIdentifiers(
            from_=from_dt,
            until=until_dt,
            continuation=None,
            batch_size=2,
            metadataPrefix="oai_dc",
        )

        assert token1 is not None

        # Decode token and verify parameters
        continuation, params = _decode_resumption_token(token1)
        assert continuation is not None
        assert params["metadataPrefix"] == "oai_dc"
        assert "from" in params
        assert "until" in params

        # Verify date format is OAI-PMH compliant
        from_str = params["from"]
        until_str = params["until"]
        assert from_str.endswith("Z")  # UTC indicator
        assert until_str.endswith("Z")  # UTC indicator
    finally:
        server_with_db._get_conn = lambda: server_with_db._test_conn


# ============================================================================
# Tests for Path Separation (DB_ROOT_PATH vs ROOT_PATH)
# ============================================================================


def test_path_separation_with_root_prefix(tmp_path, monkeypatch):
    """Test that paths are correctly stripped when ROOT_PATH is configured."""
    from modama_crawler import server as server_module

    # Create test database with absolute paths
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_dataset_tables(conn)

    # Create test files
    db_root = tmp_path / "storage" / "er-c-data"
    db_root.mkdir(parents=True)

    # Create a file at: db_root / "adhoc" / "absorption" / "file.txt"
    test_file = db_root / "adhoc" / "absorption" / "file.txt"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("test content")

    # Insert into database with absolute path
    cur = conn.cursor()
    abs_path = str(test_file)
    cur.execute(
        "INSERT INTO files (path_id, path, mtime) VALUES (?, ?, ?)",
        (1, abs_path, datetime(2024, 6, 1).timestamp()),
    )
    cur.execute("INSERT INTO datasets (dataset_id, path_id) VALUES (?, ?)", (1, 1))
    cur.execute("INSERT INTO mimes (dataset_id, mime) VALUES (?, ?)", (1, "text/plain"))
    cur.execute(
        "INSERT INTO files_in_datasets (dataset_id, path_id) VALUES (?, ?)", (1, 1)
    )
    conn.commit()

    # Configure server with ROOT_PATH = "adhoc"
    original_db_root = server_module.DB_ROOT_PATH
    original_root = server_module.ROOT_PATH

    server_module.DB_ROOT_PATH = db_root
    server_module.ROOT_PATH = Path("adhoc")

    try:
        # Query should return path relative to ROOT_PATH
        paths, next_path = server_module._query_datasets_from_db(
            conn, continuation=None, from_=None, until=None, batch_size=10
        )

        # Should return path relative to ROOT_PATH, not DB_ROOT_PATH
        assert len(paths) == 1
        assert (
            str(paths[0]) == "absorption/file.txt"
        )  # Stripped DB_ROOT_PATH and ROOT_PATH
    finally:
        server_module.DB_ROOT_PATH = original_db_root
        server_module.ROOT_PATH = original_root
        conn.close()


# ============================================================================
# Flask Endpoint Tests
# ============================================================================


def test_flask_identify_endpoint(flask_client):
    """Test Flask endpoint for Identify verb."""
    response = flask_client.get("/oai?verb=Identify")

    assert response.status_code == 200
    assert b"OAI-PMH" in response.data
    assert b"Identify" in response.data
    assert b"Modama OAI-PMH server" in response.data


def test_flask_bad_verb_endpoint(flask_client):
    """Test Flask endpoint with invalid verb."""
    response = flask_client.get("/oai?verb=InvalidVerb")

    assert response.status_code == 200
    assert b"error" in response.data
    assert b"badVerb" in response.data


# ============================================================================
# Path Encoding/Decoding Tests
# ============================================================================


def test_quote_path_basic():
    """Test basic path quoting."""
    path = "simple/path/file.txt"
    quoted = quote_path(path)
    # Forward slashes are in the safe parameter, so they're not encoded
    assert quoted == "simple/path/file.txt"


def test_quote_path_special_chars():
    """Test path quoting with special characters."""
    path = "path with spaces/file.txt"
    quoted = quote_path(path)
    assert " " not in quoted  # Spaces should be encoded


def test_unquote_path_basic():
    """Test basic path unquoting."""
    quoted = "simple%2Fpath%2Ffile.txt"
    unquoted = unquote_path(quoted)
    assert unquoted == "simple/path/file.txt"


def test_quote_unquote_roundtrip():
    """Test that quoting and unquoting preserves the original path."""
    test_paths = [
        "simple/path/file.txt",
        "path with spaces/file.txt",
        "path/with/special!chars.txt",
        "path/with( parentheses ).txt",
        "path/with'quotes'.txt",
    ]

    for original in test_paths:
        quoted = quote_path(original)
        unquoted = unquote_path(quoted)
        assert unquoted == original, f"Failed for path: {original}"


# ============================================================================
# Identifier Generation Tests
# ============================================================================


def test_get_identifier_basic():
    """Test basic identifier generation."""
    path = Path("some/path/file.txt")
    identifier = get_identifier(path)

    assert identifier is not None
    assert "https://er-c-data-mgmt.fz-juelich.de/browse?path=" in identifier
    assert "some/path/file.txt" in identifier


def test_get_identifier_with_spaces():
    """Test identifier generation with spaces in path."""
    path = Path("path with spaces/file.txt")
    identifier = get_identifier(path)

    assert identifier is not None
    # Spaces should be encoded
    assert " " not in identifier


def test_get_identifier_none():
    """Test identifier generation with None path."""
    identifier = get_identifier(None)
    assert identifier is None


def test_path_from_identifier_basic():
    """Test extracting path from basic identifier."""
    identifier = "https://er-c-data-mgmt.fz-juelich.de/browse?path=some/path/file.txt"
    path = path_from_identifier(identifier)

    assert path == "some/path/file.txt"


def test_path_from_identifier_with_encoding():
    """Test extracting path with encoded characters."""
    identifier = (
        "https://er-c-data-mgmt.fz-juelich.de/browse?path=path%20with%20spaces/file.txt"
    )
    path = path_from_identifier(identifier)

    assert path == "path with spaces/file.txt"


def test_path_from_identifier_with_leading_slash():
    """Test that leading slash is removed from path."""
    # Note: get_identifier adds a leading slash, so we test the roundtrip
    original_path = "some/path/file.txt"
    identifier = get_identifier(Path(original_path))
    extracted_path = path_from_identifier(identifier)

    assert extracted_path == original_path


def test_path_from_identifier_invalid():
    """Test that invalid identifier raises ValueError."""
    invalid_identifier = "https://example.com/invalid"

    with pytest.raises(ValueError):
        path_from_identifier(invalid_identifier)
