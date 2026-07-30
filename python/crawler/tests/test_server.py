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
from datetime import datetime
from psycopg_pool import ConnectionPool

# Import the server components
from modama_crawler.server import (
    OAIFileDBBackend,
    OAIServer,
    PostgresConfig,
    create_app,
    _encode_resumption_token,
    _decode_resumption_token,
    _parse_datestamp,
    _format_datestamp,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def server_with_db(test_database, test_files) -> OAIFileDBBackend:
    """Create a SimpleServer configured to use the test database and files."""
    from psycopg_pool import ConnectionPool

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

    # Create server instance with explicit root = test_files
    backend = OAIFileDBBackend(pool=pool, root=test_files)

    return backend


@pytest.fixture
def oai_server_with_db(test_database, test_files) -> OAIServer:
    """Create an OAIServer configured to use the test database and files."""
    from psycopg_pool import ConnectionPool

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

    backend = OAIFileDBBackend(pool=pool, root=test_files)
    server = OAIServer(backend=backend, base_url="http://test.local/oai")
    return server


@pytest.fixture
def flask_client(test_database, test_files, monkeypatch):
    """Create a Flask test client configured with test database and files."""

    # Use connection pool from test(Database)
    pool = ConnectionPool(
        conninfo=PostgresConfig.from_env().connection_string(),
        min_size=1,
        max_size=2,
    )

    config_dict = {
        "TESTING": True,
        "DB_ROOT_PATH": test_files,
        "MODAMA_DATA_ROOT": test_files,
        "OAI_BASE_URL": "http://test.local/oai",
    }

    app = create_app(pool=pool, config=config_dict)
    client = app.test_client()
    yield client


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
    from psycopg_pool import ConnectionPool
    from modama_crawler.repository import RepositoryConfig
    from modama_crawler.server import OAIServer

    pool = ConnectionPool(conninfo="dbname=test", open=True)
    config = RepositoryConfig.from_env()
    backend = OAIFileDBBackend(pool=pool, root=config.data_root)
    server = OAIServer(backend, config)
    info = server.identify()

    assert info["repositoryName"] == "Modama OAI-PMH server"
    assert info["protocolVersion"] == "2.0"
    assert info["deletedRecord"] == "no"
    assert info["granularity"] == "YYYY-MM-DDThh:mm:ssZ"
    assert "adminEmails" in info


def test_server_list_metadata_formats():
    """Test ListMetadataFormats verb."""
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(conninfo="dbname=test", open=True)
    backend = OAIFileDBBackend(pool=pool, root=Path("/tmp"))
    formats = backend.listMetadataFormats()

    assert len(formats) == 1
    assert formats[0][0] == "oai_dc"
    assert "oai_dc.xsd" in formats[0][1]
    assert formats[0][2] == "http://purl.org/dc/elements/1.1/"


def test_server_list_sets():
    """Test ListSets verb."""
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(conninfo="dbname=test", open=True)
    backend = OAIFileDBBackend(pool=pool, root=Path("/tmp"))
    sets = backend.listSets()

    assert sets == []


def test_error_response():
    """Test error response generation."""
    from psycopg_pool import ConnectionPool
    from modama_crawler.repository import RepositoryConfig

    # Test using the backend instance
    pool = ConnectionPool(conninfo="dbname=test", open=True)
    config = RepositoryConfig.from_env()
    backend = OAIFileDBBackend(pool=pool, root=config.data_root)
    server = OAIServer(backend=backend, config=config)
    error_xml = server._make_error("badVerb", "Missing verb parameter")

    assert b"<error" in error_xml
    assert b'code="badVerb"' in error_xml
    assert b"Missing verb parameter" in error_xml
    assert b"OAI-PMH" in error_xml


def test_oai_response_structure():
    """Test OAI-PMH response structure."""
    from psycopg_pool import ConnectionPool
    from modama_crawler.repository import RepositoryConfig

    # Create a server instance to access the method
    pool = ConnectionPool(conninfo="dbname=test", open=True)
    config = RepositoryConfig.from_env()
    backend = OAIFileDBBackend(pool=pool, root=config.data_root)
    server = OAIServer(backend=backend, config=config)
    children = [{"repositoryName": "Test Repository"}, {"baseURL": "http://test.org"}]
    args = {"verb": "Identify", "base_url": "http://test.org"}

    xml = server._make_oai_response("Identify", children, args)

    # Check XML structure
    assert b"<?xml version" in xml
    assert b"<OAI-PMH" in xml
    assert b"<responseDate>" in xml
    assert b"<request" in xml
    assert b"<Identify>" in xml
    assert b"<repositoryName>Test Repository</repositoryName>" in xml
    assert b"<baseURL>http://test.org</baseURL>" in xml


def test_http_endpoint_namespaces(flask_client):
    """Test that actual HTTP endpoint returns correct namespace declarations.

    This integration test verifies that the Flask endpoint properly includes
    all required namespaces in the XML response.
    """
    response = flask_client.get("/oai?verb=Identify")

    assert response.status_code == 200
    assert (
        b"text/xml" in response.content_type.encode()
        or b"xml" in response.content_type.lower()
    )

    xml_content = response.data

    # Check that the root element has the correct namespace declarations
    assert b'xmlns="http://www.openarchives.org/OAI/2.0/"' in xml_content
    assert b'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"' in xml_content
    assert (
        b'xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/ http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd"'
        in xml_content
    )

    # Also verify the response has expected content
    assert b"<Identify>" in xml_content
    assert b"<repositoryName>" in xml_content


def test_http_endpoint_identify(flask_client):
    """Test Identify verb via HTTP endpoint."""
    response = flask_client.get("/oai?verb=Identify")

    assert response.status_code == 200

    xml_content = response.data

    # Check for expected XML elements
    assert b"<repositoryName>Modama OAI-PMH server</repositoryName>" in xml_content
    assert b"<baseURL" in xml_content
    assert b"<protocolVersion>2.0</protocolVersion>" in xml_content


def test_http_endpoint_list_metadata_formats(flask_client):
    """Test ListMetadataFormats verb via HTTP endpoint."""
    response = flask_client.get("/oai?verb=ListMetadataFormats")

    assert response.status_code == 200

    xml_content = response.data

    # Check for expected XML elements
    assert b"<metadataFormat>" in xml_content
    assert b"<metadataPrefix>oai_dc</metadataPrefix>" in xml_content
    assert (
        b"<schema>http://www.openarchives.org/OAI/2.0/oai_dc.xsd</schema>"
        in xml_content
    )


def test_http_endpoint_list_sets(flask_client):
    """Test ListSets verb via HTTP endpoint."""
    response = flask_client.get("/oai?verb=ListSets")

    assert response.status_code == 200

    xml_content = response.data

    # Check for expected XML elements
    assert b"<sets>" in xml_content or b"</ListSets>" in xml_content


def test_http_endpoint_bad_verb(flask_client):
    """Test bad verb error handling via HTTP endpoint."""
    response = flask_client.get("/oai?verb=BadVerb")

    assert response.status_code == 200

    xml_content = response.data

    # Check for error response
    assert b"<error" in xml_content
    assert b'code="badVerb"' in xml_content


# ============================================================================
# Database Query Tests
# ============================================================================


def test_query_datasets_from_db_basic(server_with_db):
    """Test basic database query without filters."""
    paths, next_path = server_with_db._query_datasets_from_db(
        continuation=None, from_=None, until=None, batch_size=10
    )

    # Should get all 6 paths
    assert len(paths) == 6
    assert next_path is None  # All records returned, no continuation


def test_query_datasets_from_db_pagination(server_with_db):
    """Test pagination with batch_size."""
    # server_with_db._root is already set to test_files from fixture

    # First batch
    paths1, next_path1 = server_with_db._query_datasets_from_db(
        continuation=None, from_=None, until=None, batch_size=2
    )
    assert len(paths1) == 2
    assert str(paths1[0]) == "dataset-alpha/file1.txt"
    assert str(paths1[1]) == "dataset-beta/file2.txt"
    assert next_path1 is not None  # More records available

    # Second batch
    paths2, next_path2 = server_with_db._query_datasets_from_db(
        continuation=next_path1, from_=None, until=None, batch_size=2
    )
    assert len(paths2) == 2
    assert str(paths2[0]) == "dataset-delta/file4.txt"
    assert str(paths2[1]) == "dataset-epsilon/file5.txt"
    assert next_path2 is not None

    # Third batch (last) - still returns next_path because len == batch_size
    # The actual end is detected when the next query returns empty results
    paths3, next_path3 = server_with_db._query_datasets_from_db(
        continuation=next_path2, from_=None, until=None, batch_size=2
    )
    assert len(paths3) == 2
    assert str(paths3[0]) == "dataset-gamma/file3.txt"
    assert str(paths3[1]) == "dataset-zeta/file6.txt"
    assert next_path3 is not None  # Last path returned, but we need to try again

    # Fourth query - should return empty
    paths4, next_path4 = server_with_db._query_datasets_from_db(
        continuation=next_path3, from_=None, until=None, batch_size=2
    )
    assert len(paths4) == 0
    assert next_path4 is None


def test_query_datasets_from_db_date_filtering(server_with_db):
    """Test date filtering with from_ and until."""
    # Filter to date range: 2024-06-01 to 2024-12-31
    # Using the exact timestamps from the database fixture for accurate testing
    # epsilon has timestamp: datetime(2024, 12, 31, 23, 59, 59)
    from_dt = datetime(2024, 6, 1)  # dataset-beta is at 2024-06-01 (inclusive)
    until_dt = datetime(2024, 12, 31, 23, 59, 59)  # epsilon at exactly this time

    paths, next_path = server_with_db._query_datasets_from_db(
        continuation=None,
        from_=from_dt,
        until=until_dt,
        batch_size=10,
    )

    # Should get 4 records (ordered by path alphabetically): beta, delta, epsilon, gamma
    assert len(paths) == 4
    assert str(paths[0]) == "dataset-beta/file2.txt"
    assert str(paths[1]) == "dataset-delta/file4.txt"
    assert str(paths[2]) == "dataset-epsilon/file5.txt"
    assert str(paths[3]) == "dataset-gamma/file3.txt"
    assert next_path is None


def test_query_datasets_from_db_from_boundary(server_with_db):
    """Test that from_ is inclusive (boundary condition)."""
    # from_ at exact boundary: 2024-06-01 (dataset-beta)
    from_dt = datetime(2024, 6, 1)

    paths, _ = server_with_db._query_datasets_from_db(
        continuation=None, from_=from_dt, until=None, batch_size=10
    )

    # Should include dataset-beta (at boundary) and all after
    assert len(paths) == 5
    assert str(paths[0]) == "dataset-beta/file2.txt"


def test_query_datasets_from_db_until_boundary(server_with_db):
    """Test that until is inclusive in OAI-PMH (boundary condition)."""
    # until at exact boundary: 2024-12-31 23:59:59 (dataset-epsilon)
    until_dt = datetime(2024, 12, 31, 23, 59, 59)

    paths, _ = server_with_db._query_datasets_from_db(
        continuation=None, from_=None, until=until_dt, batch_size=10
    )

    # Should include dataset-epsilon (at boundary) and all before it in time
    # Results are ordered by path, so we check count and that epsilon is included
    assert len(paths) == 5
    path_strings = [str(p) for p in paths]
    assert "dataset-epsilon/file5.txt" in path_strings
    assert "dataset-zeta/file6.txt" not in path_strings  # Excluded (after until)


def test_query_datasets_from_db_empty_result(server_with_db):
    """Test query with no matching results."""
    # Date range with no data
    from_dt = datetime(2023, 1, 1)
    until_dt = datetime(2023, 12, 31)

    paths, next_path = server_with_db._query_datasets_from_db(
        continuation=None,
        from_=from_dt,
        until=until_dt,
        batch_size=10,
    )

    assert len(paths) == 0
    assert next_path is None


# ============================================================================
# Integration Tests with SimpleServer
# ============================================================================


def test_list_identifiers_basic(server_with_db):
    """Test basic listIdentifiers with database."""
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


def test_list_identifiers_pagination(server_with_db):
    """Test listIdentifiers pagination."""
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


def test_list_identifiers_date_filtering(server_with_db):
    """Test listIdentifiers with date filtering."""
    from_dt = datetime(2024, 6, 1)
    until_dt = datetime(2024, 12, 31, 23, 59, 59)

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


def test_list_records_basic(server_with_db):
    """Test basic listRecords with database."""
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


def test_resumption_token_preserves_parameters(server_with_db):
    """Test that resumption token preserves metadataPrefix, from, and until."""
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
