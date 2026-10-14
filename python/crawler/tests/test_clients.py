"""The main verbs with real-world OAI-PMH client libraries over HTTP.

The EOSC harvester uses oaipmh-scythe, a fork of sickle. Each adapter maps
one library onto the same small interface; ranges are seconds-granularity
datestamps like the EOSC harvester sends.
"""

from datetime import datetime

import oaipmh_scythe
import pytest
import sickle
from conftest import RECORDS
from oaipmh.client import Client
from oaipmh.metadata import MetadataRegistry, oai_dc_reader

SECONDS = "%Y-%m-%dT%H:%M:%SZ"


class Sickle:
    def __init__(self, url):
        self.client = sickle.Sickle(url)

    def earliest_datestamp(self):
        return self.client.Identify().earliestDatestamp

    def metadata_prefixes(self):
        return [f.metadataPrefix for f in self.client.ListMetadataFormats()]

    def get_record(self, identifier):
        record = self.client.GetRecord(identifier=identifier, metadataPrefix="oai_dc")
        return record.header.identifier, record.metadata["title"]

    def list_records(self, **range_):
        records = self.client.ListRecords(metadataPrefix="oai_dc", **_sickle(range_))
        return [(r.header.identifier, r.metadata["title"]) for r in records]

    def list_identifiers(self, **range_):
        headers = self.client.ListIdentifiers(
            metadataPrefix="oai_dc", **_sickle(range_)
        )
        return [h.identifier for h in headers]


def _sickle(range_):
    return {k.rstrip("_"): v for k, v in range_.items()}


class Scythe:
    def __init__(self, url):
        self.client = oaipmh_scythe.Scythe(url)

    def earliest_datestamp(self):
        return self.client.identify().earliestDatestamp

    def metadata_prefixes(self):
        return [f.metadataPrefix for f in self.client.list_metadata_formats()]

    def get_record(self, identifier):
        record = self.client.get_record(identifier=identifier)
        return record.header.identifier, record.metadata["title"]

    def list_records(self, **range_):
        records = self.client.list_records(**range_)
        return [(r.header.identifier, r.metadata["title"]) for r in records]

    def list_identifiers(self, **range_):
        return [h.identifier for h in self.client.list_identifiers(**range_)]


class PyOAI:
    def __init__(self, url):
        registry = MetadataRegistry()
        registry.registerReader("oai_dc", oai_dc_reader)
        self.client = Client(url, registry)

    def earliest_datestamp(self):
        return self.client.identify().earliestDatestamp().strftime(SECONDS)

    def metadata_prefixes(self):
        return [
            prefix for prefix, schema, namespace in self.client.listMetadataFormats()
        ]

    def get_record(self, identifier):
        header, metadata, _ = self.client.getRecord(
            identifier=identifier, metadataPrefix="oai_dc"
        )
        return header.identifier(), metadata.getField("title")

    def list_records(self, **range_):
        records = self.client.listRecords(metadataPrefix="oai_dc", **_pyoai(range_))
        return [(h.identifier(), m.getField("title")) for h, m, _ in records]

    def list_identifiers(self, **range_):
        headers = self.client.listIdentifiers(metadataPrefix="oai_dc", **_pyoai(range_))
        return [h.identifier() for h in headers]


def _pyoai(range_):
    return {k: datetime.strptime(v, SECONDS) for k, v in range_.items()}


@pytest.fixture(params=[Sickle, Scythe, PyOAI], ids=["sickle", "scythe", "oaipmh"])
def client(request, base_url):
    return request.param(base_url)


def test_identify(client, records):
    assert client.earliest_datestamp() == "2024-01-01T00:00:00Z"


def test_list_metadata_formats(client, records):
    assert client.metadata_prefixes() == ["oai_dc"]


def test_get_record(client, records):
    assert client.get_record(records[3]) == (records[3], ["/e:f.txt"])


def test_list_records(client, records):
    """A full harvest over three pages."""
    assert client.list_records() == [(i, [p]) for i, p in zip(records, RECORDS)]


def test_list_identifiers(client, records):
    assert client.list_identifiers() == records


def test_incremental_harvest(client, records):
    found = client.list_records(
        from_="2024-06-01T12:00:00Z", until="2024-06-01T23:59:59Z"
    )
    assert [identifier for identifier, title in found] == records[2:4]
