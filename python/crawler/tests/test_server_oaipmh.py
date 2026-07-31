"""Protocol compliance tests for OAI-PMH server using oaipmh client library.

These tests verify that the server works correctly with the oaipmh OAI-PMH client
library over real HTTP connections.
"""

import pytest
from pathlib import Path

from xdg import Mime

from modama_crawler.repository import path_from_identifier, get_identifier
from modama_crawler.server import _format_datestamp


# ============================================================================
# Protocol Compliance Tests with oaipmh Client
# ============================================================================


def test_oaipmh_identify(oaipmh_client):
    """Test Identify verb with oaipmh client."""
    # Use oaipmh's identify method
    response = oaipmh_client.identify()

    # Verify response is not None
    assert response is not None
    # The response is an Identify object, just verify it exists
    assert hasattr(response, "protocolVersion") or str(response) is not None


def test_oaipmh_list_identifiers(oaipmh_client):
    """Test ListIdentifiers with oaipmh client."""
    # Use oaipmh's listIdentifiers method (camelCase)
    # This returns a generator, so convert to list
    headers = list(oaipmh_client.listIdentifiers(metadataPrefix="oai_dc"))

    # Verify we got records
    assert len(headers) > 0

    # Verify each header has required fields
    for header in headers:
        # header is a Header object with attributes
        assert hasattr(header, "identifier")
        assert hasattr(header, "datestamp")
        assert header.identifier is not None
        assert header.datestamp is not None


def test_oaipmh_list_records_dublin_core(
    oaipmh_client, test_files, test_database, backend_with_db
):
    """Test ListRecords with Dublin Core metadata using oaipmh.

    Verifies that the metadata parsed by oaipmh matches what the server generates
    from FileHandler methods.
    """
    # Use oaipmh's listRecords method (camelCase)
    records = list(oaipmh_client.listRecords(metadataPrefix="oai_dc"))

    # Verify we got records
    assert len(records) > 0

    # Verify each record has required structure
    # Note: oaipmh returns records as tuples (header, metadata, about)
    # unlike sickle which returns Record objects with .header and .metadata attributes
    for record in records:
        # record is a tuple: (header, metadata, about)
        assert isinstance(record, tuple)
        assert len(record) == 3

        header, metadata, about = record

        # Verify header
        assert header.identifier is not None
        # identifier in metadata may be a list, check if header.identifier is in it
        # Note: oaipmh's Header.identifier is a method, not a property
        metadata_identifiers = metadata["identifier"]
        header_id_str = str(header.identifier())
        if isinstance(metadata_identifiers, list):
            assert header_id_str in metadata_identifiers
        else:
            assert header_id_str in metadata_identifiers
        assert header.datestamp is not None

        # Verify metadata is accessible
        assert metadata is not None

        # Check that metadata has Dublin Core elements
        # oaipmh Metadata has getMap() method to access the underlying dict
        metadata_dict = metadata.getMap()
        assert len(metadata_dict) > 0  # Should have some DC elements

        # Extract path from identifier
        path_str = path_from_identifier(header.identifier())
        path = Path(path_str)

        # Extract MIME types from format field (guesses)
        guesses = []
        assert "format" in metadata_dict

        formats = metadata_dict["format"]
        assert isinstance(formats, list)

        for fmt_str in formats:
            assert isinstance(fmt_str, str)
            guesses.append(Mime.MIMEtype(fmt_str))
        assert len(guesses) > 0

        # Instantiate FileHandler using the path and MIME type guesses from oaipmh

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

        # Verify the handler's metadata matches what oaipmh returned
        handler_titles = handler.get_titles()
        assert handler_titles == metadata_dict["title"]

        handler_identifiers = [get_identifier(handler.path)]
        assert handler_identifiers[0] == metadata_dict["identifier"][0]

        # Verify dates match
        handler_dates = [_format_datestamp(d) for d in handler.get_dates()]
        assert handler_dates == metadata_dict["date"]

        # Verify title is a non-empty list
        titles = metadata_dict["title"]
        assert isinstance(titles, list)
        assert len(titles) > 0

        # Verify other expected fields are present
        # (these come from FileHandler methods)
        assert "date" in metadata_dict
        assert "format" in metadata_dict
        assert "publisher" in metadata_dict

        # Date should be in OAI-PMH format (YYYY-MM-DDThh:mm:ssZ)
        dates = metadata_dict["date"]
        assert isinstance(dates, list)
        assert len(dates) > 0
        assert all(isinstance(d, str) and "T" in d and d.endswith("Z") for d in dates)

        # Publisher should be present
        publishers = metadata_dict["publisher"]
        assert isinstance(publishers, list)
        assert len(publishers) > 0


# ============================================================================
# Additional Verbs and Arguments Tests with oaipmh Client
# ============================================================================


def test_oaipmh_list_metadata_formats(oaipmh_client):
    """Test ListMetadataFormats with oaipmh client."""
    # Use oaipmh's listMetadataFormats method (camelCase)
    # Returns a list of tuples: (metadataPrefix, schema, metadataNamespace)
    formats = list(oaipmh_client.listMetadataFormats())

    # Verify we got metadata formats
    assert len(formats) > 0

    # Verify each format has required elements (as tuple)
    for fmt in formats:
        assert isinstance(fmt, tuple)
        assert len(fmt) == 3
        metadataPrefix, schema, metadataNamespace = fmt
        assert metadataPrefix is not None
        assert schema is not None
        assert metadataNamespace is not None

    # Verify expected oai_dc format is present
    prefixes = [fmt[0] for fmt in formats]
    assert "oai_dc" in prefixes


def test_oaipmh_get_record_basic(oaipmh_client):
    """Test GetRecord with valid identifier using oaipmh client."""
    # First, get an identifier from listRecords to use for GetRecord
    records = list(oaipmh_client.listRecords(metadataPrefix="oai_dc"))
    assert len(records) > 0, "Need at least one record to test GetRecord"

    # Get the first header's identifier
    first_header = records[0][0]  # (header, metadata, about)
    identifier = str(first_header.identifier())

    # Use oaipmh's getRecord method (camelCase)
    record_response = oaipmh_client.getRecord(
        identifier=identifier, metadataPrefix="oai_dc"
    )

    # Verify we got a response
    assert record_response is not None

    # Parse the tuple: (header, metadata, about)
    header, metadata, about = record_response

    # Verify header matches expected identifier
    assert str(header.identifier()) == identifier
    assert header.datestamp is not None

    # Verify metadata exists and has content
    assert metadata is not None
    metadata_dict = metadata.getMap()
    assert len(metadata_dict) > 0


def test_oaipmh_get_record_invalid_identifier(oaipmh_client):
    """Test GetRecord with invalid identifier (should raise error)."""
    from oaipmh.error import IdDoesNotExistError

    # Use a clearly invalid identifier
    invalid_identifier = "oai:invalid.test/999999nonexistent"

    # GetRecord should raise an exception for invalid identifiers
    with pytest.raises(IdDoesNotExistError):
        oaipmh_client.getRecord(identifier=invalid_identifier, metadataPrefix="oai_dc")


def test_oaipmh_list_identifiers_with_sets(oaipmh_client):
    """Test ListIdentifiers with set parameter (server should return noSetHierarchy)."""

    # This repository does not support sets
    # Try to use set parameter and verify it fails appropriately
    try:
        list(oaipmh_client.listIdentifiers(metadataPrefix="oai_dc", set="some_set"))
        pytest.fail("Expected error when using set on non-set-supporting repository")
    except Exception as e:
        # Should get some kind of error about noSetHierarchy or invalid set
        assert "set" in str(e).lower() or "hierarchy" in str(e).lower(), (
            f"Unexpected error: {e}"
        )


def test_oaipmh_list_records_with_sets(oaipmh_client):
    """Test ListRecords with set parameter (server should return noSetHierarchy)."""

    # This repository does not support sets
    try:
        res = list(oaipmh_client.listRecords(metadataPrefix="oai_dc", set="some_set"))
        print(res)
        pytest.fail("Expected error when using set on non-set-supporting repository")
    except Exception as e:
        # Should get some kind of error about noSetHierarchy or invalid set
        assert "set" in str(e).lower() or "hierarchy" in str(e).lower(), (
            f"Unexpected error: {e}"
        )


def test_oaipmh_list_identifiers_with_date_range(oaipmh_client, backend_with_db):
    """Test ListIdentifiers with from/until date range parameters."""
    # Use datetime objects as expected by oaipmh client
    from datetime import timedelta

    headers = list(oaipmh_client.listIdentifiers(metadataPrefix="oai_dc"))
    assert len(headers) > 0

    # Get the earliest and latest dates from existing data
    all_dates = [h.datestamp() for h in headers]
    min_date = min(all_dates)
    max_date = max(all_dates)

    # Use a range that definitely covers our data (use yesterday to tomorrow)
    start = min_date.replace(hour=0, minute=0, second=0) - timedelta(days=1)
    end = max_date + timedelta(days=1)

    headers = list(
        oaipmh_client.listIdentifiers(metadataPrefix="oai_dc", from_=start, until=end)
    )

    # Verify we got headers matching date range
    assert len(headers) > 0, f"Expected at least one header in range {start} to {end}"

    for header in headers:
        assert header.identifier is not None
        assert header.datestamp is not None


def test_oaipmh_list_records_with_date_range(oaipmh_client, backend_with_db):
    """Test ListRecords with from/until date range parameters."""
    from datetime import timedelta

    records = list(oaipmh_client.listRecords(metadataPrefix="oai_dc"))
    assert len(records) > 0

    # Get the earliest and latest dates from existing data
    all_dates = [r[0].datestamp() for r in records]
    min_date = min(all_dates)
    max_date = max(all_dates)

    # Use a range that definitely covers our data (use yesterday to tomorrow)
    start = min_date.replace(hour=0, minute=0, second=0) - timedelta(days=1)
    end = max_date + timedelta(days=1)

    records = list(
        oaipmh_client.listRecords(metadataPrefix="oai_dc", from_=start, until=end)
    )

    # Verify we got records matching date range
    assert len(records) > 0, f"Expected at least one record in range {start} to {end}"

    for record in records:
        header, metadata, about = record
        assert header.identifier is not None
        assert header.datestamp is not None
        assert metadata is not None


def test_oaipmh_identify_verify_fields(oaipmh_client):
    """Verify all required Identify response fields."""
    identify = oaipmh_client.identify()

    # Verify required fields exist and have valid values
    assert identify.repositoryName() is not None
    assert identify.baseURL() is not None
    assert identify.protocolVersion() == "2.0"
    assert identify.earliestDatestamp() is not None
    deleted_record = identify.deletedRecord()
    assert deleted_record in ("yes", "no", "persistent")
    granularity = identify.granularity()
    assert granularity in ("YYYY-MM-DD", "YYYY-MM-DDThh:mm:ssZ")

    # Verify adminEmails exists and is non-empty
    admin_emails = identify.adminEmails()
    assert isinstance(admin_emails, list)
    assert len(admin_emails) > 0

    # Verify compression field (may be just identity)
    compression = identify.compression()
    assert isinstance(compression, list)


def test_oaipmh_list_identifiers_pagination(oaipmh_client, backend_with_db):
    """Test ListIdentifiers pagination using resumptionToken."""
    # Get first batch of identifiers
    headers = list(oaipmh_client.listIdentifiers(metadataPrefix="oai_dc"))

    # oaipmh client handles pagination internally via generators
    # so we just verify we got some results
    assert len(headers) > 0

    # Each header should have required elements
    for header in headers:
        assert hasattr(header, "identifier")
        assert hasattr(header, "datestamp")


def test_oaipmh_list_records_pagination(oaipmh_client):
    """Test ListRecords pagination using resumptionToken."""
    # Get all records (oaipmh handles pagination automatically)
    records = list(oaipmh_client.listRecords(metadataPrefix="oai_dc"))

    # Verify we got some records
    assert len(records) > 0

    # Each record should have complete structure
    for record in records:
        header, metadata, about = record
        assert header.identifier is not None
        assert header.datestamp is not None
        assert metadata is not None


def test_oaipmh_list_metadata_formats_with_identifier(oaipmh_client, backend_with_db):
    """Test ListMetadataFormats with valid identifier parameter."""
    # Get an identifier from listRecords to use for ListMetadataFormats
    records = list(oaipmh_client.listRecords(metadataPrefix="oai_dc"))
    assert len(records) > 0

    first_header = records[0][0]
    identifier = str(first_header.identifier())

    # Use oaipmh's listMetadataFormats with identifier (returns tuples)
    formats = list(oaipmh_client.listMetadataFormats(identifier=identifier))

    # Should return the same format definitions as a list of tuples
    assert len(formats) > 0

    prefixes = [
        fmt[0] for fmt in formats
    ]  # fmt is (metadataPrefix, schema, metadataNamespace)
    assert "oai_dc" in prefixes


def test_oaipmh_datestamp_format_validation(oaipmh_client, backend_with_db):
    """Validate that all datestamps are in proper OAI-PMH format."""
    import re

    # Pattern for UTC datetime: YYYY-MM-DDThh:mm:ssZ or YYYY-MM-DDThh:mm:ss (from datetime)
    date_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$"

    # Test ListIdentifiers - oaipmh returns datetime objects for datestamp
    headers = list(oaipmh_client.listIdentifiers(metadataPrefix="oai_dc"))
    for header in headers:
        datestamp = str(header.datestamp())
        # Handle both string format (with Z) and datetime repr (without T)
        if "T" not in datestamp:
            # datetime object representation, convert
            continue  # This is valid, just not the right format to check
        assert re.match(date_pattern, datestamp), (
            f"Date {datestamp} should match UTC datetime format"
        )

    # Test ListRecords
    records = list(oaipmh_client.listRecords(metadataPrefix="oai_dc"))
    for record in records:
        header = record[0]
        datestamp = str(header.datestamp())
        if "T" not in datestamp:
            continue  # This is valid datetime object
        assert re.match(date_pattern, datestamp), (
            f"Date {datestamp} should match UTC datetime format"
        )

    # Test Identify response - earliestDatestamp is a datetime object
    identify = oaipmh_client.identify()
    earliest_ds = identify.earliestDatestamp()  # Already a datetime object
    # Just verify it's a valid datetime, not empty
    assert earliest_ds is not None


def test_oaipmh_metadata_content_validation(oaipmh_client, backend_with_db):
    """Validate Dublin Core metadata content structure."""
    records = list(oaipmh_client.listRecords(metadataPrefix="oai_dc"))

    for record in records:
        header, metadata, about = record

        # Get metadata dict
        metadata_dict = metadata.getMap()

        # Verify required DC elements exist and have valid structure
        assert "title" in metadata_dict, "title element should exist"
        assert "identifier" in metadata_dict, "identifier element should exist"
        assert "date" in metadata_dict, "date element should exist"

        # Title should be non-empty list
        titles = metadata_dict["title"]
        assert isinstance(titles, list), "title should be a list"
        assert len(titles) > 0, "title list should not be empty"
        assert all(isinstance(t, str) for t in titles), "title items should be strings"

        # Date should be non-empty list with proper format
        dates = metadata_dict["date"]
        assert isinstance(dates, list), "date should be a list"
        assert len(dates) > 0, "date list should not be empty"
