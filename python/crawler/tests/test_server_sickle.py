"""Protocol compliance tests for OAI-PMH server using sickle client library.

These tests verify that the server works correctly with the sickle OAI-PMH client
library over real HTTP connections.
"""

from pathlib import Path

from xdg import Mime

from modama_crawler.repository import path_from_identifier, get_identifier
from modama_crawler.server import _format_datestamp


# ============================================================================
# Protocol Compliance Tests with Sickle Client
# ============================================================================


def test_sickle_identify_real_http(sickle_client):
    """Test OAI-PMH Identify verb with real sickle client over HTTP."""
    # Use sickle's Identify method (capitalized)
    identify = sickle_client.Identify()

    # Verify response object and attributes
    assert identify is not None
    assert str(identify.repositoryName) == "Modama OAI-PMH server"
    # baseURL may be None depending on sickle version, just check protocol version
    assert str(identify.protocolVersion) == "2.0"
    assert str(identify.granularity) == "YYYY-MM-DDThh:mm:ssZ"


def test_sickle_list_identifiers_pagination(sickle_client):
    """Test ListIdentifiers with pagination using sickle iterator."""
    # Use sickle's ListIdentifiers method
    identifiers = list(sickle_client.ListIdentifiers(metadataPrefix="oai_dc"))

    # Verify we got records
    assert len(identifiers) > 0

    # Verify each identifier has required attributes
    for header in identifiers:
        assert hasattr(header, "identifier")
        assert hasattr(header, "datestamp")
        assert header.identifier is not None
        assert header.datestamp is not None

        # datestamp may be string or datetime depending on sickle version
        # Just verify it's a valid datestamp format
        datestamp_str = str(header.datestamp)
        assert "T" in datestamp_str  # ISO format
        assert datestamp_str.endswith("Z")  # UTC indicator


def test_sickle_list_records_dublin_core(
    sickle_client, test_files, test_database, backend_with_db
):
    """Test ListRecords with Dublin Core metadata using sickle.

    Verifies that the metadata parsed by sickle matches what the server generates
    from FileHandler methods.
    """
    # Use sickle's ListRecords method
    records = list(sickle_client.ListRecords(metadataPrefix="oai_dc"))

    # Verify we got records
    assert len(records) > 0

    # Verify each record has required structure
    for record in records:
        assert hasattr(record, "header")
        assert hasattr(record, "metadata")

        # Verify header
        assert record.header.identifier is not None
        # May have other identifiers, but I guess at east the one in header and
        # metadata should be consistent!
        assert record.header.identifier in record.metadata["identifier"]
        assert record.header.datestamp is not None

        # Verify metadata is accessible
        # sickle parses Dublin Core into a dict-like object
        assert record.metadata is not None

        # Check that metadata has Dublin Core elements
        metadata_dict = dict(record.metadata)
        assert len(metadata_dict) > 0  # Should have some DC elements

        # Extract path from identifier
        path_str = path_from_identifier(record.header.identifier)
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

        handler = backend_with_db._get_handler_for_path(
            conn=test_database, path=path, guesses=guesses
        )
        intersects = False
        handler_formats = handler.get_formats()
        for guess in guesses:
            if str(guess) in handler_formats:
                intersects = True
        assert intersects
        # Verify the handler's path matches
        assert handler.path == path
        # Verify the handler's metadata matches what sickle returned
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


def test_sickle_date_filtering(sickle_client):
    """Test ListIdentifiers with date filtering using sickle."""
    # Use sickle's ListIdentifiers with from_ and until parameters
    identifiers = list(
        sickle_client.ListIdentifiers(
            metadataPrefix="oai_dc", from_="2024-06-01", until="2024-12-31"
        )
    )

    # Verify we got some filtered records
    # Note: Date filtering is tested more thoroughly in unit tests
    assert len(identifiers) > 0
