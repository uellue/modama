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
import re
import requests
import xml.etree.ElementTree as ET

from psycopg_pool import ConnectionPool
from lxml import etree

# Import the server components
from modama_crawler.server import (
    OAIFileDBBackend,
    OAIServer,
    PostgresConfig,
    create_app,
    _parse_datestamp,
    _format_datestamp,
)
from modama_crawler.recognition import FileHandler

# Import schemas module for XSD validation (absolute import from tests)
import sys

sys.path.insert(0, str(Path(__file__).parent))
from schemas import get_schema_path


class LocalSchemaResolver(etree.Resolver):
    """Custom resolver that maps external schema references to local files.

    This resolver handles:
    - oai_dc.xsd imports (simpledc20021212.xsd)
    - simpledc20021212.xsd imports (xml.xsd from W3C)
    """

    def resolve(self, system_url, public_id, context):
        url_str = str(system_url) if system_url else ""
        schemas_path = get_schema_path("")

        # Map Dublin Core schema to local file
        if "simpledc20021212.xsd" in url_str:
            return self.resolve_filename(
                str(schemas_path / "simpledc20021212.xsd"), context
            )

        # Map W3C XML namespace schema to local file
        if "xml.xsd" in url_str:
            return self.resolve_filename(str(schemas_path / "xml.xsd"), context)

        return None


def pretty_print_xml_response(response):
    """Pretty-print an XML response if content-type indicates XML."""
    if "xml" in response.headers.get("content-type", "").lower():
        try:
            import xml.dom.minidom

            dom = xml.dom.minidom.parseString(response.text)
            pretty_xml = dom.toprettyxml()
            print(f"Response (XML):\n{pretty_xml}")
        except Exception:
            # If parsing fails, just print the raw text
            print(f"Response body:\n{response.text}")
    else:
        print(f"Response body:\n{response.text}")


def validate_dc_date(date_value: str):
    """Validate that a Dublin Core date follows ISO 8601 / W3C Date-Time Format.

    According to Dublin Core and OAI-PMH specifications, dates should follow
    ISO 8601 format with UTC timezone indicator (Z suffix).

    For consistency in this test suite, only the full datetime format is accepted:
    - YYYY-MM-DDThh:mm:ssZ (full datetime with seconds granularity)

    This matches the W3C Date-Time Format (W3CDTF) profile of ISO 8601.
    """
    pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"

    if re.match(pattern, date_value):
        return True

    # If none matched, it's invalid
    return False


def validate_dc_date_in_response(root: ET.Element, ns: dict) -> list[str]:
    """Find and validate all dc:date elements in the response.

    Args:
        root: The parsed XML document root element
        ns: Namespace dictionary for XPath queries

    Returns:
        List of valid date values

    Raises:
        AssertionError if any date is invalid or contains a Unix timestamp
    """
    # Extract all dc:date elements from metadata
    date_elements = root.findall(".//oai_dc:dc/dc:date", ns)

    assert len(date_elements) > 0, "No dc:date elements found in response"

    valid_dates = []
    for date_elem in date_elements:
        date_value = date_elem.text

        # Check that it's not a raw timestamp (which would indicate the bug)
        # Timestamps are numeric strings like "1785494744.596561"
        assert not re.match(r"^\d+\.?\d*$", date_value), (
            f"dc:date contains a Unix timestamp instead of ISO 8601 format: {date_value}"
        )

        # Validate the format
        is_valid = validate_dc_date(date_value)
        assert is_valid, (
            f"dc:date '{date_value}' does not match Dublin Core/ISO 8601 format"
        )
        valid_dates.append(date_value)

    return valid_dates


def validate_dc_format(date_value: str):
    """Validate that a Dublin Core format value is a valid MIME type.

    According to IETF RFC 2046, MIME types follow the pattern:
    type/subtype where type and subtype are alphanumeric strings
    possibly containing + or - characters.

    Examples of valid MIME types:
    - text/plain
    - image/jpeg
    - application/json
    - application/octet-stream
    """
    # Valid MIME type pattern (simplified)
    # Type: starts with alphanumeric, can contain +, -, .
    # Subtype: same rules as type
    mime_pattern = r"^[a-zA-Z0-9][a-zA-Z0-9+\-\.]*/[a-zA-Z0-9][a-zA-Z0-9+\-\.]*$"

    if re.match(mime_pattern, date_value):
        return True

    # If it doesn't match, it's invalid
    return False


def validate_dc_format_in_response(root: ET.Element, ns: dict) -> list[str]:
    """Find and validate all dc:format elements contain valid MIME types.

    Args:
        root: The parsed XML document root element
        ns: Namespace dictionary for XPath queries

    Returns:
        List of valid format values

    Raises:
        AssertionError if any metadata block lacks a valid MIME type in format elements
    """
    # Extract all oai_dc:dc elements (each represents a metadata block)
    dc_elements = root.findall(".//oai_dc:dc", ns)

    assert len(dc_elements) > 0, "No oai_dc:dc metadata blocks found in response"

    valid_formats = []

    for i, dc_elem in enumerate(dc_elements):
        # Find all format elements within this specific dc element
        format_elements = dc_elem.findall("dc:format", ns)

        # Check if this metadata block has any format elements
        has_format_element = len(format_elements) > 0

        # Track if at least one format in this block is valid
        block_has_valid_format = False

        for format_elem in format_elements:
            format_value = format_elem.text

            if format_value is None:
                continue

            # Validate that it's a proper MIME type (not just "mime/" or incomplete)
            is_valid = validate_dc_format(format_value)
            if is_valid:
                valid_formats.append(format_value)
                block_has_valid_format = True

        # Each metadata block must have at least one valid MIME type
        if has_format_element and not block_has_valid_format:
            assert False, (
                f"Metadata block {i + 1} has format elements but none are valid MIME types. "
                f"Found {[e.text for e in format_elements if e.text is not None]}"
            )

        if has_format_element and not block_has_valid_format:
            assert False, (
                f"Metadata block {i + 1} has no format elements. "
                f"All metadata blocks must have at least one dc:format element with a valid MIME type."
            )

    assert len(valid_formats) > 0, (
        f"No valid MIME type found in any dc:format elements across {len(dc_elements)} metadata block(s)"
    )

    return valid_formats


def validate_dublin_core_metadata(root: ET.Element, ns: dict) -> None:
    """Validate all metadata elements against oai_dc.xsd schema.

    Args:
        root: The parsed XML document root element
        ns: Namespace dictionary for XPath queries

    Raises:
        AssertionError if metadata does not validate against oai_dc.xsd
    """
    # Get schema path for metadata validation
    oai_dc_schema_path = get_schema_path("oai_dc.xsd")

    # Extract the metadata element and validate it against oai_dc.xsd
    metadata_elements = root.findall(".//oai:metadata", ns)

    parser = etree.XMLParser()
    parser.resolvers.add(LocalSchemaResolver())

    for metadata_elem in metadata_elements:
        # The child of metadata should be oai_dc:dc
        if len(metadata_elem) > 0:
            dc_elem = metadata_elem[0]

            # Create a wrapper element in the oai_dc namespace with name 'dc'
            wrapped = etree.Element("{http://www.openarchives.org/OAI/2.0/oai_dc/}dc")

            # Copy attributes and children from dc_elem to wrapped
            wrapped.attrib.update(dc_elem.attrib)
            for child in dc_elem:
                wrapped.append(child)

            # Convert to string and validate
            dc_xml_str = etree.tostring(wrapped, encoding="unicode")

            try:
                oai_dc_doc = etree.parse(str(oai_dc_schema_path), parser)
                oai_dc_schema = etree.XMLSchema(oai_dc_doc)
                doc = etree.fromstring(dc_xml_str)
                oai_dc_schema.assertValid(doc)
            except etree.DocumentInvalid as e:
                assert False, (
                    f"Dublin Core metadata does not validate against oai_dc.xsd: {e}"
                )


def validate_oai_pmh_response(response_content: bytes) -> None:
    """Validate the entire OAI-PMH response document against combined schema.

    Args:
        response_content: The raw XML response content as bytes

    Raises:
        AssertionError if response does not validate against OAI-PMH.xsd
    """
    # Validate the entire OAI-PMH response document against OAI-PMH.xsd
    oai_pmh_schema_path = get_schema_path("oai-pmh-oai-dc.xsd")

    parser = etree.XMLParser()
    parser.resolvers.add(LocalSchemaResolver())

    try:
        oai_pmh_doc = etree.parse(str(oai_pmh_schema_path), parser)
        oai_pmh_schema = etree.XMLSchema(oai_pmh_doc)

        # Parse the entire response and validate
        doc = etree.fromstring(response_content)
        oai_pmh_schema.assertValid(doc)
    except etree.DocumentInvalid as e:
        assert False, f"OAI-PMH response does not validate against OAI-PMH.xsd: {e}"


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def flask_client(test_database):
    """Create a Flask test client configured with test database and files."""

    # Use connection pool from test(Database)
    pool = ConnectionPool(
        conninfo=PostgresConfig.from_conninfo(test_database.info).connection_string(),
        min_size=1,
        max_size=2,
    )

    app = create_app(pool=pool)
    client = app.test_client()
    yield client


# ============================================================================


def test_resumption_token_encoding():
    """Test resumption token encoding and decoding."""
    # Test with continuation path and metadataPrefix
    token = OAIServer._encode_resumption_token(
        Path("some/path"), metadataPrefix="oai_dc"
    )
    assert token is not None
    continuation, params = OAIServer._decode_resumption_token(token)
    assert str(continuation) == "some/path"
    assert params["metadataPrefix"] == "oai_dc"

    # Test with all parameters
    token = OAIServer._encode_resumption_token(
        Path("another/path"),
        metadataPrefix="oai_dc",
        from_="2024-01-01T00:00:00Z",
        until="2024-12-31T23:59:59Z",
    )
    assert token is not None
    continuation, params = OAIServer._decode_resumption_token(token)
    assert str(continuation) == "another/path"
    assert params["metadataPrefix"] == "oai_dc"
    assert params["from"] == "2024-01-01T00:00:00Z"
    assert params["until"] == "2024-12-31T23:59:59Z"

    # Test with None continuation
    token = OAIServer._encode_resumption_token(None)
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

    # Check for noSetHierarchy error (repository does not support sets)
    assert b'<error code="noSetHierarchy">' in xml_content
    assert b"This repository does not support sets" in xml_content


def test_http_endpoint_bad_verb(flask_client):
    """Test bad verb error handling via HTTP endpoint."""
    response = flask_client.get("/oai?verb=BadVerb")

    assert response.status_code == 200

    xml_content = response.data

    # Check for error response
    assert b"<error" in xml_content
    assert b'code="badVerb"' in xml_content


@pytest.fixture(autouse=True)
def fixed_filehandler_mtime(monkeypatch):
    """Fix FileHandler mtime methods to avoid source code modification time interference."""

    def mock_youngest():
        return 0.0

    def mock_oldest():
        return 0.0

    monkeypatch.setattr(FileHandler, "youngest_source_mtime", mock_youngest)
    monkeypatch.setattr(FileHandler, "oldest_source_mtime", mock_oldest)


# ============================================================================
# Database Query Tests
# ============================================================================


def test_query_datasets_from_db_basic(backend_with_db):
    """Test basic database query without filters."""
    paths, next_path = backend_with_db._query_datasets_from_db(
        continuation=None, from_=None, until=None, batch_size=10
    )

    # Should get all 6 paths
    assert len(paths) == 6
    assert next_path is None  # All records returned, no continuation


def test_query_datasets_from_db_pagination(backend_with_db):
    """Test pagination with batch_size."""
    # backend_with_db._root is already set to test_files from fixture

    # First batch
    paths1, next_path1 = backend_with_db._query_datasets_from_db(
        continuation=None, from_=None, until=None, batch_size=2
    )
    assert len(paths1) == 2
    assert str(paths1[0]) == "dataset-alpha/file1.txt"
    assert str(paths1[1]) == "dataset-beta/file2.txt"
    assert next_path1 is not None  # More records available

    # Second batch
    paths2, next_path2 = backend_with_db._query_datasets_from_db(
        continuation=next_path1, from_=None, until=None, batch_size=2
    )
    assert len(paths2) == 2
    assert str(paths2[0]) == "dataset-delta/file4.txt"
    assert str(paths2[1]) == "dataset-epsilon/file5.txt"
    assert next_path2 is not None

    # Third batch (last) - still returns next_path because len == batch_size
    # The actual end is detected when the next query returns empty results
    paths3, next_path3 = backend_with_db._query_datasets_from_db(
        continuation=next_path2, from_=None, until=None, batch_size=2
    )
    assert len(paths3) == 2
    assert str(paths3[0]) == "dataset-gamma/file3.txt"
    assert str(paths3[1]) == "dataset-zeta/file6.txt"
    assert next_path3 is not None  # Last path returned, but we need to try again

    # Fourth query - should return empty
    paths4, next_path4 = backend_with_db._query_datasets_from_db(
        continuation=next_path3, from_=None, until=None, batch_size=2
    )
    assert len(paths4) == 0
    assert next_path4 is None


def test_query_datasets_from_db_date_filtering(backend_with_db):
    """Test date filtering with from_ and until."""
    # Use a relaxed date range to ensure we get records even with timestamp precision issues
    # Database has: alpha(2024-01), beta(2024-06), gamma(2024-06), delta(2024-07), epsilon(2024-12), zeta(2025-02)
    from_dt = datetime(2024, 5, 1)  # After alpha, before beta
    until_dt = datetime(2025, 1, 15)  # After epsilon, before zeta

    paths, next_path = backend_with_db._query_datasets_from_db(
        continuation=None,
        from_=from_dt,
        until=until_dt,
        batch_size=10,
    )

    # Should get all records except alpha (before from_) and zeta (after until)
    assert len(paths) == 4
    assert str(paths[0]) == "dataset-beta/file2.txt"
    assert str(paths[1]) == "dataset-delta/file4.txt"
    assert str(paths[2]) == "dataset-epsilon/file5.txt"
    assert str(paths[3]) == "dataset-gamma/file3.txt"
    assert next_path is None


def test_query_datasets_from_db_from_boundary(backend_with_db):
    """Test that from_ is inclusive (boundary condition)."""
    # from_ at exact boundary: 2024-06-01 (dataset-beta)
    from_dt = datetime(2024, 6, 1)

    paths, _ = backend_with_db._query_datasets_from_db(
        continuation=None, from_=from_dt, until=None, batch_size=10
    )

    # Should include dataset-beta (at boundary) and all after
    assert len(paths) == 5
    assert str(paths[0]) == "dataset-beta/file2.txt"


def test_query_datasets_from_db_until_boundary(backend_with_db):
    """Test that until is inclusive in OAI-PMH (boundary condition)."""
    # until at exact boundary: 2024-12-31 23:59:59 (dataset-epsilon)
    until_dt = datetime(2025, 1, 15)

    paths, _ = backend_with_db._query_datasets_from_db(
        continuation=None, from_=None, until=until_dt, batch_size=10
    )

    # Should include dataset-epsilon (at boundary) and all before it in time
    # Results are ordered by path alphabetically; zeta is excluded
    assert len(paths) == 5
    path_strings = [str(p) for p in paths]
    assert "dataset-epsilon/file5.txt" in path_strings
    assert "dataset-zeta/file6.txt" not in path_strings  # Excluded (after until)


def test_query_datasets_from_db_empty_result(backend_with_db):
    """Test query with no matching results."""
    # Date range with no data
    from_dt = datetime(2023, 1, 1)
    until_dt = datetime(2023, 12, 31)

    paths, next_path = backend_with_db._query_datasets_from_db(
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


def test_list_identifiers_basic(backend_with_db):
    """Test basic listIdentifiers with database."""
    headers, token = backend_with_db.listIdentifiers(
        from_=None,
        until=None,
        continuation=None,
        batch_size=2,
    )

    assert len(headers) == 2
    assert "identifier" in headers[0]
    assert "datestamp" in headers[0]
    assert token is not None  # More records available


def test_list_identifiers_pagination(backend_with_db):
    """Test listIdentifiers pagination."""
    # First batch
    headers1, token1 = backend_with_db.listIdentifiers(
        from_=None,
        until=None,
        continuation=None,
        batch_size=2,
    )
    assert len(headers1) == 2
    assert token1 is not None

    # Second batch
    headers2, token2 = backend_with_db.listIdentifiers(
        from_=None,
        until=None,
        continuation=token1,
        batch_size=2,
    )
    assert len(headers2) == 2
    assert token2 is not None

    # Third batch
    headers3, token3 = backend_with_db.listIdentifiers(
        from_=None,
        until=None,
        continuation=token2,
        batch_size=2,
    )
    assert len(headers3) == 2
    # Last batch may or may not have token depending on implementation
    # (token is set when len == batch_size, even if it's the last batch)


def test_list_identifiers_date_filtering(backend_with_db):
    """Test listIdentifiers with date filtering."""
    from_dt = datetime(2024, 5, 1)
    until_dt = datetime(2026, 6, 1)  # Well after all records

    headers, token = backend_with_db.listIdentifiers(
        from_=from_dt,
        until=until_dt,
        continuation=None,
        batch_size=10,
    )

    # Should get 5 records: beta, gamma, delta, epsilon, zeta (all except alpha)
    assert len(headers) == 5
    assert token is None  # All records returned


def test_list_records_basic(backend_with_db):
    """Test basic listRecords with database."""
    records, token = backend_with_db.listRecords(
        from_=None,
        until=None,
        continuation=None,
        batch_size=2,
    )

    assert len(records) == 2
    assert "header" in records[0]
    assert "metadata" in records[0]
    assert token is not None


def test_resumption_token_preserves_parameters(backend_with_db):
    """Test that resumption token preserves metadataPrefix, from, and until."""
    from_dt = datetime(2024, 6, 1)
    until_dt = datetime(2024, 12, 31)

    # First request
    headers1, next_path = backend_with_db.listIdentifiers(
        from_=from_dt,
        until=until_dt,
        continuation=None,
        batch_size=2,
    )

    assert next_path is not None

    # Encode token the way the server does
    from_str_token = _format_datestamp(from_dt.timestamp()) if from_dt else None
    until_str_token = _format_datestamp(until_dt.timestamp()) if until_dt else None
    encoded_token = OAIServer._encode_resumption_token(
        next_path, "oai_dc", from_str_token, until_str_token
    )

    # Decode token and verify parameters
    continuation, params = OAIServer._decode_resumption_token(encoded_token)
    assert continuation is not None
    assert params["metadataPrefix"] == "oai_dc"
    assert "from" in params
    assert "until" in params

    # Verify date format is OAI-PMH compliant
    from_str = params["from"]
    until_str = params["until"]
    assert from_str.endswith("Z")  # UTC indicator
    assert until_str.endswith("Z")  # UTC indicator


def test_request_list_records(running_http_server):
    """Test ListRecords verb via HTTP endpoint."""
    response = requests.get(
        f"{running_http_server}?verb=ListRecords&metadataPrefix=oai_dc"
    )
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200
    assert b"<ListRecords>" in response.content
    assert b"<record>" in response.content

    # Parse XML and validate using lxml.etree for schema validation

    root = etree.fromstring(response.content)

    # Define namespaces
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Register namespaces
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    # Validate dc:date elements in the response
    validate_dc_date_in_response(root, ns)

    # Validate we have at least some MIME types
    # as format specifiers
    validate_dc_format_in_response(root, ns)

    # Validate Dublin Core metadata content against oai_dc.xsd
    validate_dublin_core_metadata(root, ns)

    # Validate the entire OAI-PMH response document
    validate_oai_pmh_response(response.content)


# ============================================================================
# Additional OAI-PMH Protocol Compliance Tests
# ============================================================================


def test_request_bad_verb(running_http_server):
    """Test bad verb error response."""
    response = requests.get(f"{running_http_server}?verb=BadVerb")
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200
    assert b"<error" in response.content
    assert b'code="badVerb"' in response.content

    # Validate the OAI-PMH response structure even for errors
    etree.fromstring(response.content)

    # Check required error elements exist
    assert b"<responseDate>" in response.content
    assert b"<request>" in response.content

    # Validate against OAI-PMH schema (even for errors)
    validate_oai_pmh_response(response.content)


def test_request_identify(running_http_server):
    """Test Identify verb with full validation."""
    response = requests.get(f"{running_http_server}?verb=Identify")
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200

    # Parse XML and validate using lxml.etree for schema validation
    etree.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Register namespaces
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    # Check all required Identify elements exist
    assert b"<repositoryName>" in response.content
    assert b"<baseURL>" in response.content
    assert b"<protocolVersion>2.0</protocolVersion>" in response.content
    assert b"<earliestDatestamp>" in response.content
    assert b"<deletedRecord>" in response.content
    assert b"<granularity>" in response.content

    # Validate the entire OAI-PMH response document
    validate_oai_pmh_response(response.content)


def test_request_list_metadata_formats(running_http_server):
    """Test ListMetadataFormats verb with full validation."""
    response = requests.get(f"{running_http_server}?verb=ListMetadataFormats")
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200

    # Parse XML and validate using lxml.etree for schema validation
    root = etree.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Register namespaces
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    # Check required metadataFormat elements exist
    assert b"<metadataFormat>" in response.content
    assert b"<metadataPrefix>oai_dc</metadataPrefix>" in response.content

    schema_elem = root.find(
        ".//oai:ListMetadataFormats//oai:metadataFormat/oai:schema", ns
    )
    assert schema_elem is not None, "schema element should exist"
    assert b"http://www.openarchives.org/OAI/2.0/oai_dc.xsd" in response.content

    namespace_elem = root.find(".//oai:metadataFormat/oai:metadataNamespace", ns)
    assert namespace_elem is not None, "metadataNamespace element should exist"
    assert b"http://purl.org/dc/elements/1.1/" in response.content

    # Validate the entire OAI-PMH response document
    validate_oai_pmh_response(response.content)


def test_request_list_identifiers_basic(running_http_server):
    """Test ListIdentifiers verb basic functionality."""
    response = requests.get(
        f"{running_http_server}?verb=ListIdentifiers&metadataPrefix=oai_dc"
    )
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200

    # Parse XML and validate using lxml.etree for schema validation
    root = etree.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Register namespaces
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    # Check required ListIdentifiers elements exist
    assert b"<ListIdentifiers>" in response.content
    assert b"<header>" in response.content
    assert b"<identifier>" in response.content
    assert b"<datestamp>" in response.content

    # Validate header structure - each header should have identifier and datestamp
    headers = root.findall(".//oai:ListIdentifiers/oai:header", ns)
    assert len(headers) > 0, "Should return at least one header"

    for i, header in enumerate(headers):
        identifier = header.find("oai:identifier", ns)
        datestamp = header.find("oai:datestamp", ns)
        assert identifier is not None, f"Header {i} should have identifier"
        assert datestamp is not None, f"Header {i} should have datestamp"

    # Validate the entire OAI-PMH response document
    validate_oai_pmh_response(response.content)


def test_request_list_identifiers_with_from_until(running_http_server):
    """Test ListIdentifiers with selective harvesting (date range)."""

    # Use date range that should match some records based on test_database fixture
    from_date = "2024-06-01"
    until_date = "2024-12-31T23:59:59Z"

    response = requests.get(
        f"{running_http_server}?verb=ListIdentifiers&metadataPrefix=oai_dc&from={from_date}&until={until_date}"
    )
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200

    root = etree.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Register namespaces
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    # Should return headers with datestamps within the range
    headers = root.findall(".//oai:ListIdentifiers/oai:header", ns)
    assert len(headers) > 0, "Should return headers matching date range"

    for header in headers:
        datestamp_elem = header.find("oai:datestamp", ns)
        if datestamp_elem is not None and datestamp_elem.text:
            # Verify date is in ISO 8601 format
            date_value = datestamp_elem.text
            assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", date_value), (
                f"Datestamp {date_value} should be in ISO 8601 format"
            )

    # Validate the entire OAI-PMH response document
    validate_oai_pmh_response(response.content)


def test_request_list_identifiers_pagination(running_http_server):
    """Test ListIdentifiers with resumptionToken pagination."""
    # First request with small batch size (if supported) or just get first page
    response = requests.get(
        f"{running_http_server}?verb=ListIdentifiers&metadataPrefix=oai_dc"
    )
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200

    root = etree.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Register namespaces
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    # Check for resumptionToken (indicates pagination is available)
    resumption_tokens = root.findall(".//oai:ListIdentifiers/oai:resumptionToken", ns)

    if len(resumption_tokens) > 0:
        token_elem = resumption_tokens[0]
        token_value = token_elem.text
        print(f"Resumption token: {token_value}")

        # Optional: Verify token attributes exist (completeListSize, cursor)
        if token_elem.attrib.get("completeListSize"):
            print(f"Complete list size: {token_elem.attrib['completeListSize']}")
        if token_elem.attrib.get("cursor"):
            print(f"Cursor: {token_elem.attrib['cursor']}")

    # Validate the entire OAI-PMH response document
    validate_oai_pmh_response(response.content)


def test_request_list_records_basic(running_http_server):
    """Test ListRecords verb basic functionality."""
    response = requests.get(
        f"{running_http_server}?verb=ListRecords&metadataPrefix=oai_dc"
    )
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200

    # Parse XML and validate using lxml.etree for schema validation
    root = etree.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Register namespaces
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    # Check required ListRecords elements exist
    assert b"<ListRecords>" in response.content
    assert b"<record>" in response.content

    # Validate record structure - each record should have header and metadata
    records = root.findall(".//oai:ListRecords/oai:record", ns)
    assert len(records) > 0, "Should return at least one record"

    for i, record in enumerate(records):
        header = record.find("oai:header", ns)
        metadata = record.find("oai:metadata", ns)
        assert header is not None, f"Record {i} should have a header"
        assert metadata is not None, f"Record {i} should have metadata"

    # Validate Dublin Core metadata
    validate_dublin_core_metadata(root, ns)

    # Validate the entire OAI-PMH response document
    validate_oai_pmh_response(response.content)


def test_request_list_records_with_from_until(running_http_server):
    """Test ListRecords with selective harvesting (date range)."""

    # Use date range that should match some records based on test_database fixture
    from_date = "2024-06-01"
    until_date = "2024-12-31T23:59:59Z"

    response = requests.get(
        f"{running_http_server}?verb=ListRecords&metadataPrefix=oai_dc&from={from_date}&until={until_date}"
    )
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200

    root = etree.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Register namespaces
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    # Should return records with headers and metadata
    records = root.findall(".//oai:ListRecords/oai:record", ns)
    assert len(records) > 0, "Should return records matching date range"

    for record in records:
        header = record.find("oai:header", ns)
        metadata = record.find("oai:metadata", ns)

        assert header is not None, "Each record should have a header"
        assert metadata is not None, "Each record should have metadata"

        # Validate the date in dc:date elements
        if metadata is not None and len(metadata) > 0:
            dc_elem = metadata[0]
            for date_elem in dc_elem.findall("dc:date", ns):
                if date_elem.text:
                    assert re.match(
                        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", date_elem.text
                    ), f"dc:date {date_elem.text} should be in ISO 8601 format"

    # Validate Dublin Core metadata
    validate_dublin_core_metadata(root, ns)

    # Validate the entire OAI-PMH response document
    validate_oai_pmh_response(response.content)


def test_request_list_records_pagination(running_http_server):
    """Test ListRecords with resumptionToken pagination."""
    response = requests.get(
        f"{running_http_server}?verb=ListRecords&metadataPrefix=oai_dc"
    )
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200

    root = etree.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Register namespaces
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    # Check records structure
    records = root.findall(".//oai:ListRecords/oai:record", ns)
    assert len(records) > 0, "Should return at least one record"

    for i, record in enumerate(records):
        header = record.find("oai:header", ns)
        metadata = record.find("oai:metadata", ns)

        assert header is not None, f"Record {i} should have a header"
        assert metadata is not None, f"Record {i} should have metadata"

        # Validate Dublin Core structure
        if len(metadata) > 0:
            dc_elem = metadata[0]
            assert dc_elem.tag == "{http://www.openarchives.org/OAI/2.0/oai_dc/}dc", (
                f"Record {i} metadata should be oai_dc:dc"
            )

    # Validate Dublin Core metadata against schema
    validate_dublin_core_metadata(root, ns)

    # Validate the entire OAI-PMH response document
    validate_oai_pmh_response(response.content)


def test_request_list_sets(running_http_server):
    """Test ListSets verb (may return noSetHierarchy error if sets not supported)."""
    response = requests.get(f"{running_http_server}?verb=ListSets")
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200

    root = etree.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Register namespaces
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    # Check if repository supports sets
    error_no_set_hierarchy = root.find(".//oai:error[@code='noSetHierarchy']", ns)

    if error_no_set_hierarchy is not None:
        print("Repository does not support sets (noSetHierarchy error)")
    else:
        # If no error, check for ListSets response elements
        assert b"<ListSets>" in response.content
        assert b"<set>" in response.content or b"</ListSets>" in response.content

        sets = root.findall(".//oai:ListSets/oai:set", ns)
        if len(sets) > 0:
            for i, set_elem in enumerate(sets):
                set_spec = set_elem.find("oai:setSpec", ns)
                set_name = set_elem.find("oai:setName", ns)
                assert set_spec is not None, f"Set {i} should have setSpec"
                assert set_name is not None, f"Set {i} should have setName"

    # Validate the entire OAI-PMH response document
    validate_oai_pmh_response(response.content)


def test_request_get_record_basic(running_http_server):
    """Test GetRecord verb with valid identifier and metadataPrefix."""
    # First, get an identifier from ListIdentifiers to use for GetRecord
    list_response = requests.get(
        f"{running_http_server}?verb=ListIdentifiers&metadataPrefix=oai_dc"
    )

    assert list_response.status_code == 200

    root = etree.fromstring(list_response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Get the first identifier
    headers = root.findall(".//oai:ListIdentifiers/oai:header", ns)
    assert len(headers) > 0, "Need at least one header to test GetRecord"

    identifier_elem = headers[0].find("oai:identifier", ns)
    assert identifier_elem is not None and identifier_elem.text, (
        "First header should have identifier"
    )

    identifier = identifier_elem.text

    # Now test GetRecord with this identifier
    response = requests.get(
        f"{running_http_server}?verb=GetRecord&identifier={identifier}&metadataPrefix=oai_dc"
    )
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200

    # Validate the entire OAI-PMH response document
    validate_oai_pmh_response(response.content)

    # Check for GetRecord with record structure
    root_get = etree.fromstring(response.content)
    get_record = root_get.find(".//oai:GetRecord", ns)
    assert get_record is not None, "Response should have GetRecord element"

    record = root_get.find(".//oai:record", ns)
    assert record is not None, "GetRecord response should contain a record"

    # Validate record structure
    header = record.find("oai:header", ns)
    metadata = record.find("oai:metadata", ns)

    assert header is not None, "Record should have header"
    assert metadata is not None, "Record should have metadata"


def test_request_get_record_invalid_identifier(running_http_server):
    """Test GetRecord with invalid identifier (idDoesNotExist error)."""
    # Use a clearly invalid identifier
    invalid_identifier = "oai:invalid.test/999999nonexistent"

    response = requests.get(
        f"{running_http_server}?verb=GetRecord&identifier={invalid_identifier}&metadataPrefix=oai_dc"
    )
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200

    root = etree.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Register namespaces
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    # Should return an error with code idDoesNotExist
    error_elem = root.find(".//oai:error[@code='idDoesNotExist']", ns)
    assert error_elem is not None, (
        "GetRecord with invalid identifier should return idDoesNotExist error"
    )

    # Validate the OAI-PMH response structure even for errors
    validate_oai_pmh_response(response.content)


def test_request_get_record_bad_argument(running_http_server):
    """Test GetRecord with missing required parameters (badArgument error)."""
    # Test missing identifier
    response = requests.get(
        f"{running_http_server}?verb=GetRecord&metadataPrefix=oai_dc"
    )
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200

    root = etree.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Should return badArgument error for missing identifier
    error_elem = root.find(".//oai:error[@code='badArgument']", ns)
    assert error_elem is not None, (
        "GetRecord with missing identifier should return badArgument error"
    )

    # Validate the OAI-PMH response structure even for errors
    validate_oai_pmh_response(response.content)


def test_request_list_identifiers_with_resumption_token(running_http_server):
    """Test pagination using resumptionToken from ListIdentifiers."""
    # First request to get a resumption token
    response = requests.get(
        f"{running_http_server}?verb=ListIdentifiers&metadataPrefix=oai_dc"
    )

    assert response.status_code == 200

    root = etree.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Check for resumptionToken
    resumption_tokens = root.findall(".//oai:ListIdentifiers/oai:resumptionToken", ns)

    if len(resumption_tokens) > 0:
        token_elem = resumption_tokens[0]

        if token_elem.text and token_elem.text.strip():
            # We have a valid token, use it to get next page
            response2 = requests.get(
                f"{running_http_server}?verb=ListIdentifiers&resumptionToken={token_elem.text}"
            )

            assert response2.status_code == 200

            root2 = etree.fromstring(response2.content)
            headers2 = root2.findall(".//oai:ListIdentifiers/oai:header", ns)

            # Should get some more results or a terminator token
            if len(headers2) > 0:
                print(f"Got {len(headers2)} more identifiers from pagination")

            # Check for terminator (empty resumptionToken means complete list)
            resumption_tokens_2 = root2.findall(
                ".//oai:ListIdentifiers/oai:resumptionToken", ns
            )
            if len(resumption_tokens_2) > 0:
                token_elem_2 = resumption_tokens_2[0]
                if not token_elem_2.text or not token_elem_2.text.strip():
                    print("Pagination complete (empty terminator token)")

    # Validate the first response
    validate_oai_pmh_response(response.content)


def test_error_list_metadata_formats_invalid_identifier(running_http_server):
    """Test ListMetadataFormats with invalid identifier."""
    invalid_identifier = "oai:invalid.test/999999nonexistent"

    response = requests.get(
        f"{running_http_server}?verb=ListMetadataFormats&identifier={invalid_identifier}"
    )
    print(f"Status code: {response.status_code}")

    pretty_print_xml_response(response)

    assert response.status_code == 200

    root = etree.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Register namespaces
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    # Should return an error with code idDoesNotExist
    error_elem = root.find(".//oai:error[@code='idDoesNotExist']", ns)
    assert error_elem is not None, (
        "ListMetadataFormats with invalid identifier should return idDoesNotExist error"
    )

    # Validate the OAI-PMH response structure even for errors
    validate_oai_pmh_response(response.content)


def test_http_content_type(flask_client):
    """Test that responses have correct Content-Type header."""
    response = flask_client.get("/oai?verb=Identify")

    assert response.status_code == 200
    content_type = response.headers.get("Content-Type", "")
    assert "text/xml" in content_type.lower(), (
        f"Content-Type should be text/xml, got {content_type}"
    )


def test_response_date_utc_timezone(running_http_server):
    """Test that responseDate elements use UTC timezone with Z suffix."""
    response = requests.get(f"{running_http_server}?verb=Identify")

    assert response.status_code == 200

    root = etree.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    # Find responseDate element
    response_date_elem = root.find(".//oai:responseDate", ns)
    assert response_date_elem is not None and response_date_elem.text, (
        "Response should have responseDate element"
    )

    date_value = response_date_elem.text

    # Verify it ends with Z (UTC indicator) and matches ISO 8601 format
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", date_value), (
        f"responseDate {date_value} should be in UTC with Z suffix"
    )
