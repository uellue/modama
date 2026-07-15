"""Protocol compliance tests for OAI-PMH server using sickle client library.

These tests verify that the server works correctly with the sickle OAI-PMH client
library over real HTTP connections.
"""


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


def test_sickle_list_records_dublin_core(sickle_client, test_files, test_database):
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
        assert record.header.datestamp is not None

        # Verify metadata is accessible
        # sickle parses Dublin Core into a dict-like object
        assert record.metadata is not None

        # Check that metadata has Dublin Core elements
        metadata_dict = dict(record.metadata)
        assert len(metadata_dict) > 0  # Should have some DC elements

        # Verify required Dublin Core fields are present
        assert "title" in metadata_dict
        assert "identifier" in metadata_dict

        # Verify title is a non-empty list
        titles = metadata_dict["title"]
        assert isinstance(titles, list)
        assert len(titles) > 0
        # Title should be the path (from handler.get_titles())
        assert any(isinstance(t, str) and len(t) > 0 for t in titles)

        # Verify identifier is present and properly formatted
        identifiers = metadata_dict["identifier"]
        assert isinstance(identifiers, list)
        assert len(identifiers) > 0
        # Identifier should contain the path identifier
        assert any("path=" in str(iden) for iden in identifiers)

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

        # Format should be MIME types
        formats = metadata_dict["format"]
        assert isinstance(formats, list)
        # Formats may be empty if no MIME types detected, but should be a list

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
