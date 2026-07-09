"""Tests for the clean OAI-PMH server implementation."""

import pytest
from pathlib import Path
import tempfile
from datetime import datetime

# Import the server components
from modama_crawler.server import (
    SimpleServer,
    _make_oai_response,
    _make_error,
    _encode_resumption_token,
    _decode_resumption_token,
    _parse_datestamp,
    _format_datestamp,
    _get_crawl_results,
)


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
    server = SimpleServer(base_url="http://example.org/oai")
    info = server.identify()

    assert info["repositoryName"] == "Modama OAI-PMH server"
    assert info["baseURL"] == "http://example.org/oai"
    assert info["protocolVersion"] == "2.0"
    assert info["deletedRecord"] == "no"
    assert info["granularity"] == "YYYY-MM-DDThh:mm:ssZ"
    assert "adminEmails" in info


def test_server_list_metadata_formats():
    """Test ListMetadataFormats verb."""
    server = SimpleServer()
    formats = server.listMetadataFormats()

    assert len(formats) == 1
    assert formats[0][0] == "oai_dc"
    assert "oai_dc.xsd" in formats[0][1]
    assert formats[0][2] == "http://purl.org/dc/elements/1.1/"


def test_server_list_sets():
    """Test ListSets verb."""
    server = SimpleServer()
    sets = server.listSets()

    assert sets == []


def test_error_response():
    """Test error response generation."""
    error_xml = _make_error("badVerb", "Missing verb parameter")

    assert b"<error" in error_xml
    assert b'code="badVerb"' in error_xml
    assert b"Missing verb parameter" in error_xml
    assert b"OAI-PMH" in error_xml


def test_oai_response_structure():
    """Test OAI-PMH response structure."""
    children = [{"repositoryName": "Test Repository"}, {"baseURL": "http://test.org"}]
    args = {"verb": "Identify", "base_url": "http://test.org"}

    xml = _make_oai_response("Identify", children, args)

    # Check XML structure
    assert b"<?xml version" in xml
    assert b"<OAI-PMH" in xml
    assert b"<responseDate>" in xml
    assert b"<request" in xml
    assert b"<Identify>" in xml
    assert b"<repositoryName>Test Repository</repositoryName>" in xml
    assert b"<baseURL>http://test.org</baseURL>" in xml


def test_crawl_integration():
    """Test crawl integration with server."""
    # Create a temporary directory with test files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create some test files
        (tmppath / "file1.txt").write_text("content1")
        (tmppath / "file2.txt").write_text("content2")
        (tmppath / "file3.txt").write_text("content3")

        # Import and configure server to use temp directory
        from modama_crawler import server

        original_root = server.ROOT_PATH
        server.ROOT_PATH = tmppath

        try:
            # Test crawl results
            records, continuation = _get_crawl_results(
                continuation=None, from_=None, until=None, n=2
            )

            # Should get 2 records
            assert len(records) == 2

            # Continuation should be a Path
            assert continuation is not None
            assert isinstance(continuation, Path)

            # Get remaining records
            records2, continuation2 = _get_crawl_results(
                continuation=continuation, from_=None, until=None, n=2
            )

            # Should get 1 more record
            assert len(records2) == 1

            # Continuation should be None (finished)
            assert continuation2 is None

        finally:
            server.ROOT_PATH = original_root


def test_list_identifiers_integration():
    """Test ListIdentifiers with crawl integration."""
    # Create a temporary directory with test files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create some test files
        (tmppath / "a.txt").write_text("content")
        (tmppath / "b.txt").write_text("content")

        # Import and configure server to use temp directory
        from modama_crawler import server

        original_root = server.ROOT_PATH
        server.ROOT_PATH = tmppath

        try:
            server_instance = SimpleServer()

            # List first batch
            headers, token = server_instance.listIdentifiers(
                from_=None, until=None, continuation=None, batch_size=1
            )

            # Should get 1 header
            assert len(headers) == 1
            assert "identifier" in headers[0]

            # Token should be present
            assert token is not None

            # List second batch
            headers2, token2 = server_instance.listIdentifiers(
                from_=None, until=None, continuation=token, batch_size=1
            )

            # Should get 1 more header
            assert len(headers2) == 1

            # When count == remaining, continuation can be either None or the last file
            # (undefined behavior - see test_dirwalk.py::test_walk_skip)
            # Just verify it's a valid token (either None or encoded path)
            assert token2 is None or token2.startswith("continuation=")

        finally:
            server.ROOT_PATH = original_root


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
