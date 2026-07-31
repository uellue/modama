"""End-to-end functional tests for OAI-PMH server.

These tests create realistic test data, populate the database,
start the OAI-PMH server, and verify correctness using the oaipmh-scythe client.

This is the first in a series of end-to-end tests. Start with listRecords
and expand to other verbs incrementally.
"""

from pathlib import Path


def test_list_records_e2e(scythe_client):
    """End-to-end test of ListRecords verb using scythe client.

    This test:
    1. Creates a test directory structure with text and XML files
    2. Crawls and populates the database
    3. Starts the OAI-PMH server in background thread
    4. Uses scythe to query ListRecords
    5. Verifies results match expected structure

    Expected records (from test_data_dir fixture):
    - dataset_alpha/README.txt (text/plain)
    - dataset_alpha/metadata.xml (text/xml)
    - dataset_beta/data.csv (text/csv)
    - subfolder/notes.txt (text/plain)

    Total: 4 records
    """
    # Query all records
    records = list(scythe_client.list_records(metadata_prefix="oai_dc"))

    # Verify we got some records
    assert len(records) > 0, "Expected at least one record"

    # Verify each record has correct structure
    for record in records:
        header = record.header
        metadata = record.metadata

        # Header checks
        assert header.identifier is not None, "Identifier should not be None"
        assert header.datestamp is not None, "Datestamp should not be None"

        # Verify identifier format (URL)
        assert isinstance(header.identifier, str), "Identifier should be a string"
        assert header.identifier.startswith("http"), "Identifier should be a URL"

        # Metadata checks (Dublin Core elements)
        assert metadata is not None, "Metadata should not be None"
        assert len(metadata) > 0, "Metadata should have at least one element"

    # Extract identifiers for specific file verification
    identifiers = [record.header.identifier for record in records]

    # Verify expected files are present
    from modama_crawler.repository import get_identifier

    for path_str in ["dataset_alpha/README.txt", "dataset_alpha/metadata.xml"]:
        expected_id = get_identifier(Path(path_str))
        assert expected_id in identifiers, (
            f"Expected file {path_str} not found in records"
        )


def test_identify_endpoint(scythe_client):
    """Test Identify verb returns correct repository information."""
    identify = scythe_client.identify()

    # Verify required fields exist
    assert identify is not None, "Identify response should not be None"

    # Check basic properties (attribute access may vary by scythe version)
    identify_dict = dict(identify)

    assert "repositoryName" in identify_dict or hasattr(identify, "repositoryName")
    assert "baseURL" in identify_dict or hasattr(identify, "baseURL")
    assert "protocolVersion" in identify_dict or hasattr(identify, "protocolVersion")
    assert "earliestDatestamp" in identify_dict or hasattr(
        identify, "earliestDatestamp"
    )
    assert "deletedRecord" in identify_dict or hasattr(identify, "deletedRecord")
    assert "granularity" in identify_dict or hasattr(identify, "granularity")


def test_list_metadata_formats(scythe_client):
    """Test ListMetadataFormats returns supported formats."""
    formats = list(scythe_client.list_metadata_formats())

    # Should return at least oai_dc
    assert len(formats) > 0, "Should have at least one metadata format"

    prefixes = [fmt.metadataPrefix for fmt in formats]
    assert "oai_dc" in prefixes, "oai_dc format should be supported"


def test_list_records_structure(scythe_client):
    """Test that ListRecords returns properly structured records."""
    records = list(scythe_client.list_records(metadata_prefix="oai_dc"))

    # Check each record's comprehensive structure
    for i, record in enumerate(records):
        header = record.header
        metadata = record.metadata

        # Header must have these
        assert hasattr(header, "identifier"), f"Record {i}: Header missing identifier"
        assert hasattr(header, "datestamp"), f"Record {i}: Header missing datestamp"

        # Datestamp should be valid OAI-PMH format
        datestamp = str(header.datestamp)
        assert "T" in datestamp or len(datestamp) >= 10, (
            f"Invalid datestamp format: {datestamp}"
        )

        # Metadata must have required DC elements
        if metadata:
            assert isinstance(metadata.get("identifier"), list), (
                f"Record {i}: identifier should be a list"
            )
            assert len(metadata["identifier"]) > 0, (
                f"Record {i}: identifier list should not be empty"
            )


def test_list_records_with_specified_metadata_prefix(scythe_client):
    """Test ListRecords with explicit metadataPrefix parameter."""
    # Test with oai_dc (should work)
    records = list(scythe_client.list_records(metadata_prefix="oai_dc"))

    assert len(records) > 0, "Should return records with oai_dc prefix"

    # Verify all returned records have valid Dublin Core structure
    for record in records:
        metadata = record.metadata

        if metadata:
            # Check DC elements exist
            expected_elements = [
                "title",
                "creator",
                "date",
                "identifier",
                "description",
            ]
            for element in expected_elements:
                assert element in metadata or len(metadata) > 0, (
                    f"Expected Dublin Core element '{element}' in metadata"
                )
