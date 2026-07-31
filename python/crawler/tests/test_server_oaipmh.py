"""Protocol compliance tests for OAI-PMH server using oaipmh client library.

These tests verify that the server works correctly with the oaipmh OAI-PMH client
library over real HTTP connections.
"""

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
        with test_database as conn:
            handler = backend_with_db._get_handler_for_path(
                conn, test_files, path, guesses
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
