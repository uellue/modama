#!/usr/bin/env python3
"""Simple OAI-PMH server (Flask) example.

This provides a minimal, self-contained OAI-PMH endpoint implementing
Identify, GetRecord, ListIdentifiers and ListRecords (oai_dc only).

Run:

    python python/oaipmh_flask_server.py

Then access: http://localhost:8000/oai?verb=Identify

Adapt the `RECORDS` mapping or replace the backend with your
modama_crawler integration.
"""
from flask import Flask, request, Response
import os
from datetime import datetime

from oaipmh.server import Server as OAIServer
from oaipmh.server import oai_dc_writer
from oaipmh import error as oaipmh_error
from oaipmh import metadata as oaipmh_metadata

app = Flask(__name__)

# Example in-memory records. Replace with modama_crawler datasource.
RECORDS = {
    "oai:example.org:1": {
        "datestamp": "2020-01-01T00:00:00Z",
        "metadata": {
            "title": "Example Record 1",
            "creator": "Alice",
            "subject": "Test",
            "description": "An example record",
        },
    },
    "oai:example.org:2": {
        "datestamp": "2021-06-15T12:34:56Z",
        "metadata": {
            "title": "Example Record 2",
            "creator": "Bob",
            "subject": "Demo",
            "description": "Another example record",
        },
    },
}

OAI_NS = "http://www.openarchives.org/OAI/2.0/"
OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DC_NS = "http://purl.org/dc/elements/1.1/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

NSMAP = {
    None: OAI_NS,
    'oai_dc': OAI_DC_NS,
    'dc': DC_NS,
    'xsi': XSI_NS,
}


# --- oaipmh integration ---
def _parse_datestamp(s):
    # accepts YYYY-MM-DD or full timestamp ending with Z
    if s is None:
        return None
    if s.endswith('Z'):
        return datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ')
    return datetime.strptime(s, '%Y-%m-%d')


class SimpleIdentify:
    def __init__(self, baseURL):
        self._base = baseURL

    def repositoryName(self):
        return 'Example OAI-PMH server'

    def baseURL(self):
        return self._base

    def protocolVersion(self):
        return '2.0'

    def adminEmails(self):
        return [os.environ.get('OAI_ADMIN_EMAIL', 'admin@example.org')]

    def earliestDatestamp(self):
        dates = [_parse_datestamp(r['datestamp']) for r in RECORDS.values()]
        return min(dates)

    def deletedRecord(self):
        return 'no'

    def granularity(self):
        return 'YYYY-MM-DDThh:mm:ssZ'

    def compression(self):
        return ['identity']

    def descriptions(self):
        return []


class SimpleHeader:
    def __init__(self, identifier, datestamp, deleted=False):
        self._id = identifier
        self._datestamp = _parse_datestamp(datestamp)
        self._deleted = deleted

    def isDeleted(self):
        return self._deleted

    def identifier(self):
        return self._id

    def datestamp(self):
        return self._datestamp

    def setSpec(self):
        return []


class SimpleMetadata:
    def __init__(self, metadata):
        # Maps from (key, value) to (key, [value])
        self._map = {}
        for k, v in metadata.items():
            self._map.setdefault(k, []).append(v)

    def getMap(self):
        return self._map


class InMemoryOAIServer:
    def __init__(self, baseURL=None):
        self._base = baseURL or ''

    def identify(self):
        return SimpleIdentify(self._base)

    def getRecord(self, identifier=None, metadataPrefix=None, **kw):
        rec = RECORDS.get(identifier)
        if not rec:
            raise oaipmh_error.NoRecordsMatchError(f'identifier {identifier} not found')
        header = SimpleHeader(identifier, rec['datestamp'])
        metadata = SimpleMetadata(rec['metadata'])
        return header, metadata, None

    def listMetadataFormats(self, **kw):
        return [('oai_dc', 'http://www.openarchives.org/OAI/2.0/oai_dc.xsd', DC_NS)]

    def listIdentifiers(self, metadataPrefix=None, **kw):
        for identifier, rec in RECORDS.items():
            yield SimpleHeader(identifier, rec['datestamp'])

    def listRecords(self, metadataPrefix=None, **kw):
        for identifier, rec in RECORDS.items():
            header = SimpleHeader(identifier, rec['datestamp'])
            metadata = SimpleMetadata(rec['metadata'])
            yield (header, metadata, None)


# register the oai_dc writer with the global metadata registry
# so OAIServer can serialize metadataPrefix=oai_dc
oaipmh_metadata.global_metadata_registry.registerWriter('oai_dc', oai_dc_writer)

# instantiate OAIPMH server wrapper
_impl = InMemoryOAIServer()

oaipmh_server = OAIServer(_impl)


@app.route('/oai', methods=['GET', 'POST'])
def oai_endpoint():
    # Accept both GET query params and POST form data
    params = request.args if request.method == 'GET' else request.form
    # build request keyword dict (values as str)
    request_kw = {str(k): str(v) for k, v in params.items()}
    try:
        result = oaipmh_server.handleRequest(request_kw)
        return Response(result, mimetype='text/xml; charset=utf-8')
    except Exception as e:
        print(e)
        # FIXME find out what we can actually get here and how to handle it
        # So far, oaipmh_server has handled everything.
        raise


if __name__ == '__main__':
    app.run(port=8000, debug=True)
