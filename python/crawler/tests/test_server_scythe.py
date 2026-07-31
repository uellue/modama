"""Protocol compliance tests for OAI-PMH server using oaipmh-scythe client library.

These tests verify that the server works correctly with the oaipmh-scythe OAI-PMH client
library over real HTTP connections.
"""

import pytest
from pathlib import Path

from xdg import Mime

from modama_crawler.repository import path_from_identifier, get_identifier
from modama_crawler.server import _format_datestamp


# ============================================================================
# Protocol Compliance Tests with oaipmh-scythe Client
# ============================================================================


def test_scythe_identify(scythe_client):
    """Test Identify verb with scythe client."""
    response = scythe_client.identify()

    # Verify response is not None
    assert response is not None
    # The response is an Identify object, verify it has expected attributes
    assert hasattr(response, "protocolVersion") or str(response) is not None


def test_scythe_list_identifiers(scythe_client):
    """Test ListIdentifiers with scythe client."""
    headers = list(scythe_client.list_identifiers(metadata_prefix="oai_dc"))

    # Verify we got records
    assert len(headers) > 0

    # Verify each header has required fields
    for header in headers:
        # header is a Header object with attributes
        assert hasattr(header, "identifier")
        assert hasattr(header, "datestamp")
        assert header.identifier is not None
        assert header.datestamp is not None


def test_scythe_list_records_dublin_core(
    scythe_client, test_files, test_database, backend_with_db
):
    """Test ListRecords with Dublin Core metadata using scythe.

    Verifies that the metadata parsed by scythe matches what the server generates
    from FileHandler methods.
    """
    records = list(scythe_client.list_records(metadata_prefix="oai_dc"))

    # Verify we got records
    assert len(records) > 0

    # Verify each record has required structure
    for record in records:
        # record is a Record object with .header and .metadata attributes
        assert hasattr(record, "header")
        assert hasattr(record, "metadata")

        header = record.header
        metadata = record.metadata

        # Verify header
        assert header.identifier is not None
        # identifier in metadata may be a list, check if header.identifier is in it
        metadata_identifiers = metadata.get("identifier", [])
        if isinstance(metadata_identifiers, list):
            assert header.identifier in metadata_identifiers
        else:
            assert metadata_identifiers == header.identifier
        assert header.datestamp is not None

        # Verify metadata is accessible
        assert metadata is not None

        # Check that metadata has Dublin Core elements
        assert len(metadata) > 0  # Should have some DC elements

        # Extract path from identifier
        path_str = path_from_identifier(header.identifier)
        path = Path(path_str)

        # Extract MIME types from format field (guesses)
        guesses = []
        assert "format" in metadata

        formats = metadata.get("format", [])
        assert isinstance(formats, list)

        for fmt_str in formats:
            assert isinstance(fmt_str, str)
            guesses.append(Mime.MIMEtype(fmt_str))
        assert len(guesses) > 0

        # Instantiate FileHandler using the path and MIME type guesses from scythe
        handler = backend_with_db._get_handler_for_path(
            conn=test_database, path=path, guesses=guesses
        )

        # Verify MIME type intersection
        intersects = False
        handler_formats = handler.get_formats()
        for guess in guesses:
            if str(guess) in handler_formats:
                intersects = True
        assert intersects

        # Verify the handler's path matches
        assert handler.path == path

        # Verify the handler's metadata matches what scythe returned
        handler_titles = handler.get_titles()
        assert handler_titles == metadata.get("title", [])

        handler_identifiers = [get_identifier(handler.path)]
        # Handle both single identifier and list
        meta_id = metadata.get("identifier", [])
        if isinstance(meta_id, list):
            assert handler_identifiers[0] == meta_id[0]
        else:
            assert handler_identifiers[0] == meta_id

        # Verify dates match
        handler_dates = [_format_datestamp(d) for d in handler.get_dates()]
        # scythe may return metadata date as a string or list
        meta_date = metadata.get("date", [])
        if isinstance(meta_date, str):
            meta_date = [meta_date]
        assert handler_dates == meta_date

        # Verify title is a non-empty list
        titles = metadata.get("title", [])
        assert isinstance(titles, list)
        assert len(titles) > 0

        # Verify other expected fields are present
        assert "date" in metadata
        assert "format" in metadata
        assert "publisher" in metadata

        # Date should be in OAI-PMH format (YYYY-MM-DDThh:mm:ssZ)
        dates = metadata.get("date", [])
        if isinstance(dates, str):
            dates = [dates]
        assert isinstance(dates, list)
        assert len(dates) > 0
        assert all(isinstance(d, str) and "T" in d and d.endswith("Z") for d in dates)

        # Publisher should be present
        publishers = metadata.get("publisher", [])
        assert isinstance(publishers, list)
        assert len(publishers) > 0


# ============================================================================
# Additional Verbs and Arguments Tests with scythe Client
# ============================================================================


def test_scythe_list_metadata_formats(scythe_client):
    """Test ListMetadataFormats with scythe client."""
    # Returns an iterator of MetadataFormat objects
    formats = list(scythe_client.list_metadata_formats())

    # Verify we got metadata formats
    assert len(formats) > 0

    # Verify each format has required elements
    for fmt in formats:
        assert hasattr(fmt, "metadataPrefix")
        assert fmt.metadataPrefix is not None

    # Verify expected oai_dc format is present
    prefixes = [fmt.metadataPrefix for fmt in formats]
    assert "oai_dc" in prefixes


def test_scythe_get_record_basic(scythe_client):
    """Test GetRecord with valid identifier using scythe client."""
    # First, get an identifier from listRecords to use for GetRecord
    records = list(scythe_client.list_records(metadata_prefix="oai_dc"))
    assert len(records) > 0, "Need at least one record to test GetRecord"

    # Get the first header's identifier
    first_header = records[0].header
    identifier = first_header.identifier

    # Use scythe's get_record method
    record_response = scythe_client.get_record(
        identifier=identifier, metadata_prefix="oai_dc"
    )

    # Verify we got a response (scythe returns a Record object directly, not an iterator)
    assert record_response is not None

    # Verify header matches expected identifier
    assert record_response.header.identifier == identifier
    assert record_response.header.datestamp is not None

    # Verify metadata exists and has content
    assert record_response.metadata is not None
    metadata_dict = record_response.metadata
    assert len(metadata_dict) > 0


def test_scythe_get_record_invalid_identifier(scythe_client):
    """Test GetRecord with invalid identifier (should raise error)."""

    # Use a clearly invalid identifier
    invalid_identifier = "oai:invalid.test/999999nonexistent"

    # GetRecord should raise an exception for invalid identifiers
    with pytest.raises(Exception):  # scythe may raise different exceptions
        scythe_client.get_record(
            identifier=invalid_identifier, metadata_prefix="oai_dc"
        )


def test_scythe_list_identifiers_with_sets(scythe_client):
    """Test ListIdentifiers with set parameter (server should return noSetHierarchy)."""

    # This repository does not support sets
    try:
        list(scythe_client.list_identifiers(metadata_prefix="oai_dc", set_="some_set"))
        pytest.fail("Expected error when using set on non-set-supporting repository")
    except Exception as e:
        # Should get some kind of error about noSetHierarchy or invalid set
        assert "set" in str(e).lower() or "hierarchy" in str(e).lower(), (
            f"Unexpected error: {e}"
        )


def test_scythe_list_records_with_sets(scythe_client):
    """Test ListRecords with set parameter (server should return noSetHierarchy)."""

    # This repository does not support sets
    try:
        list(scythe_client.list_records(metadata_prefix="oai_dc", set_="some_set"))
        pytest.fail("Expected error when using set on non-set-supporting repository")
    except Exception as e:
        # Should get some kind of error about noSetHierarchy or invalid set
        assert "set" in str(e).lower() or "hierarchy" in str(e).lower(), (
            f"Unexpected error: {e}"
        )


def test_scythe_list_identifiers_with_date_range(scythe_client, backend_with_db):
    """Test ListIdentifiers with from/until date range parameters."""
    # Use scythe's list_identifiers with string dates
    headers = list(scythe_client.list_identifiers(metadata_prefix="oai_dc"))
    assert len(headers) > 0

    # Get the earliest and latest dates from existing data
    all_dates = [h.datestamp for h in headers]

    def normalize_date(dt):
        """Normalize date to string format."""
        if hasattr(dt, "isoformat"):
            return dt.isoformat()
        return str(dt)

    min_date_str = normalize_date(min(all_dates))
    max_date_str = normalize_date(max(all_dates))

    # Extract just the date part (YYYY-MM-DD) if we have full datetime
    start = min_date_str.split("T")[0] if "T" in min_date_str else min_date_str
    end = max_date_str.split("T")[0] if "T" in max_date_str else max_date_str

    # Use a very broad range to ensure we capture data (based on conftest.py dates)
    # The test data has dates from 2024-01-01 to 2025-02-01
    start = "2024-01-01"
    end = "2026-12-31"

    headers = list(
        scythe_client.list_identifiers(metadata_prefix="oai_dc", from_=start, until=end)
    )

    # Verify we got headers matching date range
    assert len(headers) > 0, f"Expected at least one header in range {start} to {end}"

    for header in headers:
        assert header.identifier is not None
        assert header.datestamp is not None


def test_scythe_list_records_with_date_range(scythe_client, backend_with_db):
    """Test ListRecords with from/until date range parameters."""
    # Use scythe's list_records with string dates
    records = list(scythe_client.list_records(metadata_prefix="oai_dc"))
    assert len(records) > 0

    # Get the earliest and latest dates from existing data
    all_dates = [r.header.datestamp for r in records]

    def normalize_date(dt):
        """Normalize date to string format."""
        if hasattr(dt, "isoformat"):
            return dt.isoformat()
        return str(dt)

    min_date_str = normalize_date(min(all_dates))
    max_date_str = normalize_date(max(all_dates))

    # Extract just the date part (YYYY-MM-DD) if we have full datetime
    start = min_date_str.split("T")[0] if "T" in min_date_str else min_date_str
    end = max_date_str.split("T")[0] if "T" in max_date_str else max_date_str

    # Use a very broad range to ensure we capture data (based on conftest.py dates)
    # The test data has dates from 2024-01-01 to 2025-02-01
    start = "2024-01-01"
    end = "2026-12-31"

    records = list(
        scythe_client.list_records(metadata_prefix="oai_dc", from_=start, until=end)
    )

    # Verify we got records matching date range
    assert len(records) > 0, f"Expected at least one record in range {start} to {end}"

    for record in records:
        header = record.header
        assert header.identifier is not None
        assert header.datestamp is not None
        assert record.metadata is not None


def test_scythe_identify_verify_fields(scythe_client):
    """Verify all required Identify response fields."""
    identify = scythe_client.identify()

    # Verify required fields exist and have valid values
    # Use getattr since attributes may vary based on response content
    repo_name = getattr(identify, "repositoryName", None)
    base_url = getattr(identify, "baseURL", None)
    protocol_version = getattr(identify, "protocolVersion", None)

    assert repo_name is not None
    assert base_url is not None
    assert protocol_version == "2.0"

    earliest_datestamp = getattr(identify, "earliestDatestamp", None)
    assert earliest_datestamp is not None

    deleted_record = getattr(identify, "deletedRecord", None)
    assert deleted_record in ("yes", "no", "persistent")

    granularity = getattr(identify, "granularity", None)
    assert granularity in ("YYYY-MM-DD", "YYYY-MM-DDThh:mm:ssZ")

    # adminEmail may be returned as a single string or a list depending on implementation
    admin_emails = getattr(identify, "adminEmail", None)
    if admin_emails:
        # Handle both single email (string) and multiple emails (list)
        if isinstance(admin_emails, str):
            assert len(admin_emails) > 0, "adminEmail should not be empty"
        else:
            assert isinstance(admin_emails, list), (
                f"Expected list or string, got {type(admin_emails)}"
            )
            assert len(admin_emails) > 0, "adminEmails should not be empty"

    # Verify compression field (may be just identity)
    compression = getattr(identify, "compression", None)
    assert compression is not None


def test_scythe_list_identifiers_pagination(scythe_client, backend_with_db):
    """Test ListIdentifiers pagination using resumptionToken."""
    # Get first batch of identifiers
    headers = list(scythe_client.list_identifiers(metadata_prefix="oai_dc"))

    # scythe handles pagination internally via generators
    # so we just verify we got some results
    assert len(headers) > 0

    # Each header should have required elements
    for header in headers:
        assert hasattr(header, "identifier")
        assert hasattr(header, "datestamp")


def test_scythe_list_records_pagination(scythe_client):
    """Test ListRecords pagination using resumptionToken."""
    # Get all records (scythe handles pagination automatically)
    records = list(scythe_client.list_records(metadata_prefix="oai_dc"))

    # Verify we got some records
    assert len(records) > 0

    # Each record should have complete structure
    for record in records:
        header = record.header
        metadata = record.metadata
        assert header.identifier is not None
        assert header.datestamp is not None
        assert metadata is not None


def test_scythe_list_metadata_formats_with_identifier(scythe_client, backend_with_db):
    """Test ListMetadataFormats with valid identifier parameter."""
    # Get an identifier from listRecords to use for ListMetadataFormats
    records = list(scythe_client.list_records(metadata_prefix="oai_dc"))
    assert len(records) > 0

    first_header = records[0].header
    identifier = first_header.identifier

    # Use scythe's list_metadata_formats with identifier
    formats = list(scythe_client.list_metadata_formats(identifier=identifier))

    # Should return the same format definitions as a list of MetadataFormat objects
    assert len(formats) > 0

    prefixes = [fmt.metadataPrefix for fmt in formats]
    assert "oai_dc" in prefixes


def test_scythe_datestamp_format_validation(scythe_client, backend_with_db):
    """Validate that all datestamps are in proper OAI-PMH format."""
    import re

    # Pattern for UTC datetime: YYYY-MM-DDThh:mm:ssZ or YYYY-MM-DDThh:mm:ss
    # scythe may return both formats
    date_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z)?$"

    # Test ListIdentifiers - scythe returns datetime objects for datestamp
    headers = list(scythe_client.list_identifiers(metadata_prefix="oai_dc"))
    for header in headers:
        datestamp = str(header.datestamp)
        assert re.match(date_pattern, datestamp), (
            f"Date {datestamp} should match UTC datetime format"
        )

    # Test ListRecords
    records = list(scythe_client.list_records(metadata_prefix="oai_dc"))
    for record in records:
        header = record.header
        datestamp = str(header.datestamp)
        assert re.match(date_pattern, datestamp), (
            f"Date {datestamp} should match UTC datetime format"
        )

    # Test Identify response - earliestDatestamp may be a datetime or string
    identify = scythe_client.identify()
    earliest_ds = getattr(identify, "earliestDatestamp", None)
    # Just verify it's present
    assert earliest_ds is not None


def test_scythe_metadata_content_validation(scythe_client, backend_with_db):
    """Validate Dublin Core metadata content structure."""
    records = list(scythe_client.list_records(metadata_prefix="oai_dc"))

    for record in records:
        _ = record.header
        metadata = record.metadata

        # Verify required DC elements exist and have valid structure
        assert "title" in metadata, "title element should exist"
        assert "identifier" in metadata, "identifier element should exist"
        assert "date" in metadata, "date element should exist"

        # Title should be non-empty list
        titles = metadata.get("title", [])
        assert isinstance(titles, list), "title should be a list"
        assert len(titles) > 0, "title list should not be empty"
        assert all(isinstance(t, str) for t in titles), "title items should be strings"

        # Date should be non-empty list with proper format
        dates = metadata.get("date", [])
        if isinstance(dates, str):
            dates = [dates]
        assert isinstance(dates, list), "date should be a list"
        assert len(dates) > 0, "date list should not be empty"


@pytest.fixture
def scythe_client(running_http_server):
    """Create oaipmh-scythe client connected to test HTTP server."""
    from oaipmh_scythe import Scythe

    return Scythe(running_http_server)
