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
import pathlib

from oaipmh.server import Server as OAIServer
from oaipmh.server import oai_dc_writer
from oaipmh import error as oaipmh_error
from oaipmh import metadata as oaipmh_metadata
from oaipmh.datestamp import datestamp_to_datetime, datetime_to_datestamp

from modama_crawler.repository import get_identifier, get_publisher
from modama_crawler.recognition import BaseFileHandler
from modama_crawler.dirwalk import crawl

app = Flask(__name__)

# Example in-memory records. Replace with modama_crawler datasource.
RECORDS, cont = crawl(root=pathlib.Path('/storage/er-c-data'), continuation='', n=100)

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
    if s is None:
        return None
    if isinstance(s, datetime):
        return s
    if isinstance(s, str):
        return datestamp_to_datetime(s)
    raise TypeError(f'Unsupported datestamp value: {s!r}')


def _format_datestamp(timestamp: float):
    return datetime_to_datestamp(datetime.fromtimestamp(timestamp))


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
        return datetime.fromtimestamp(0)

    def deletedRecord(self):
        return 'no'

    def granularity(self):
        return 'YYYY-MM-DDThh:mm:ssZ'

    def compression(self):
        return ['identity']

    def descriptions(self):
        return []


class SimpleHeader:
    def __init__(self, handler: BaseFileHandler):
        self._handler = handler

    def isDeleted(self):
        return False

    def identifier(self):
        return get_identifier(self._handler.path, self._handler.root)

    def datestamp(self):
        return datetime.fromtimestamp(self._handler.mtime)

    def setSpec(self):
        return []


class SimpleMetadata:
    def __init__(self, handler: BaseFileHandler):
        self._handler = handler

    def getMap(self):
        handler = self._handler
        result = {
            'title': handler.get_titles(),
            'creator': handler.get_creators(),
            'date': [_format_datestamp(d) for d in handler.get_dates()],
            'format': handler.get_formats(),
            'identifier': [get_identifier(handler.path, handler.root)],
            'description': handler.get_descriptions(),
            # subject, contributor, source, language, relation, coverage and
            # rights mapping are not implemented yet
        }
        result['publisher'] = [get_publisher()]
        return result


class InMemoryOAIServer:
    def __init__(self, baseURL=None):
        self._base = baseURL or ''

    def identify(self):
        return SimpleIdentify(self._base)

    def getRecord(self, identifier, metadataPrefix, **kw):
        print(metadataPrefix)
        handler = RECORDS.get(identifier)
        if not handler:
            raise oaipmh_error.NoRecordsMatchError(f'identifier {identifier} not found')
        header = SimpleHeader(handler)
        metadata = SimpleMetadata(handler)
        return header, metadata, None

    def listMetadataFormats(self, **kw):
        return [('oai_dc', 'http://www.openarchives.org/OAI/2.0/oai_dc.xsd', DC_NS)]

    def listIdentifiers(self, metadataPrefix, **kw):
        print(metadataPrefix)
        for identifier, handler in RECORDS.items():
            yield SimpleHeader(handler)

    def listRecords(self, metadataPrefix, **kw):
        print(metadataPrefix)
        for identifier, handler in RECORDS.items():
            header = SimpleHeader(handler)
            metadata = SimpleMetadata(handler)
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
