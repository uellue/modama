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

    # Check for expected XML elements
    assert b"</ListSets>" in xml_content


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
    # Filter to date range: 2024-06-01 to 2024-12-31
    # Using the exact timestamps from the database fixture for accurate testing
    # epsilon has timestamp: datetime(2024, 12, 31, 23, 59, 59)
    from_dt = datetime(2024, 6, 1)  # dataset-beta is at 2024-06-01 (inclusive)
    until_dt = datetime(2024, 12, 31, 23, 59, 59)  # epsilon at exactly this time

    paths, next_path = backend_with_db._query_datasets_from_db(
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
    until_dt = datetime(2024, 12, 31, 23, 59, 59)

    paths, _ = backend_with_db._query_datasets_from_db(
        continuation=None, from_=None, until=until_dt, batch_size=10
    )

    # Should include dataset-epsilon (at boundary) and all before it in time
    # Results are ordered by path, so we check count and that epsilon is included
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
    from_dt = datetime(2024, 6, 1)
    until_dt = datetime(2024, 12, 31, 23, 59, 59)

    headers, token = backend_with_db.listIdentifiers(
        from_=from_dt,
        until=until_dt,
        continuation=None,
        batch_size=10,
    )

    # Should get 4 records
    assert len(headers) == 4
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
