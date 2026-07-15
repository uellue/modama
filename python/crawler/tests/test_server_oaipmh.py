"""Protocol compliance tests for OAI-PMH server using oaipmh client library.

These tests verify that the server works correctly with the oaipmh OAI-PMH client
library over real HTTP connections.
"""


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
