#!/usr/bin/env python3
"""Clean OAI-PMH server (Flask) with path-based continuation tokens.

This provides a simple, readable OAI-PMH endpoint implementing all 6 verbs
(Identify, GetRecord, ListMetadataFormats, ListIdentifiers, ListRecords, ListSets)
with full resumptionToken pagination and selective harvesting support.

The server uses dynamic crawling with path-based continuation tokens for pagination
and supports selective harvesting via from/until date parameters.

Run:

    python python/crawler/src/modama_crawler/server.py

Then access: http://localhost:8000/oai?verb=Identify
"""
from flask import Flask, request, Response
from lxml import etree
import os
from datetime import datetime, timedelta
from urllib.parse import urlencode, parse_qs, unquote_plus, quote_plus
import pathlib
from typing import Optional, Tuple
import json

from oaipmh.datestamp import datestamp_to_datetime, datetime_to_datestamp

from modama_crawler.repository import get_identifier, get_publisher, path_from_identifier
from modama_crawler.recognition import guess, FileHandler
from modama_crawler.dirwalk import crawl, sanitize

app = Flask(__name__)

# Configuration
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', 10))
ROOT_PATH = pathlib.Path(os.environ.get('OAI_ROOT_PATH', '/storage/er-c-data'))

# XML Namespaces
OAI_NS = "http://www.openarchives.org/OAI/2.0/"
OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DC_NS = "http://purl.org/dc/elements/1.1/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

# --- Helper Functions ---

def _parse_datestamp(s: Optional[str]) -> Optional[datetime]:
    """Parse OAI-PMH datestamp string to datetime."""
    if s is None:
        return None
    if isinstance(s, datetime):
        return s
    if isinstance(s, str):
        return datestamp_to_datetime(s)
    raise TypeError(f'Unsupported datestamp value: {s!r}')


def _format_datestamp(timestamp: float) -> str:
    """Format timestamp as OAI-PMH datestamp."""
    return datetime_to_datestamp(datetime.fromtimestamp(timestamp))


def _convert_to_timestamps(
    from_: Optional[datetime],
    until: Optional[datetime]
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """Convert OAI-PMH datestamps to filesystem timestamps for filtering.

    Returns (c_since, c_until, m_since, m_until) for creation and modification times.
    """
    c_since = c_until = m_since = m_until = None

    if from_ is not None:
        m_since = from_.timestamp()
        c_since = from_.timestamp()

    if until is not None:
        # until is inclusive, so add one day to make it exclusive for filtering
        until_exclusive = until + timedelta(days=1)
        m_until = until_exclusive.timestamp()
        c_until = until_exclusive.timestamp()

    return c_since, c_until, m_since, m_until


def _encode_resumption_token(
    continuation: Optional[pathlib.Path],
    metadataPrefix: Optional[str] = None,
    from_: Optional[str] = None,
    until: Optional[str] = None
) -> Optional[str]:
    """Encode resumption token with continuation path and request parameters.
    
    Following OAI-PMH spec, the resumptionToken encodes all parameters except verb.
    All special characters are URL-encoded so the token can be pasted directly into a URL.
    Uses quote_plus to ensure proper encoding for query string parameters.
    """
    if continuation is None:
        return None
    
    token_data = {'continuation': str(continuation)}
    if metadataPrefix:
        token_data['metadataPrefix'] = metadataPrefix
    if from_:
        token_data['from'] = from_
    if until:
        token_data['until'] = until
    
    as_json = json.dumps(token_data)
    return quote_plus(as_json)


def _decode_resumption_token(token: str) -> Tuple[Optional[pathlib.Path], dict]:
    """Decode resumption token to continuation path and parameters.
    
    The token is URL-encoded with quote_plus, so we use unquote_plus to decode.
    """

    unquoted = unquote_plus(token)

    as_data = json.loads(unquoted)

    keys = 'continuation', 'metadataPrefix', 'from', 'until'
    result = {}

    for key in keys:
        try:
            result[key] = as_data.pop(key)
        except KeyError:
            pass
    continuation_str = result.pop('continuation', '')
    continuation = pathlib.Path(continuation_str) if continuation_str else None
    return continuation, result


def _get_crawl_results(
    continuation: Optional[pathlib.Path],
    from_: Optional[datetime],
    until: Optional[datetime],
    n: int = BATCH_SIZE
) -> Tuple[dict, Optional[pathlib.Path]]:
    """Get crawl results with optional date filtering.

    Args:
        continuation: Path continuation token from previous crawl
        from_: Minimum date for selective harvesting (inclusive)
        until: Maximum date for selective harvesting (inclusive)
        n: Maximum number of records to return

    Returns:
        Tuple of (records dict, new continuation path or None)
    """
    c_since, c_until, m_since, m_until = _convert_to_timestamps(from_, until)

    if continuation is None:
        continuation = pathlib.Path('')

    # Perform the crawl with date filtering
    records, new_continuation = crawl(
        root=ROOT_PATH,
        continuation=continuation,
        n=n,
        c_since=c_since,
        c_until=c_until,
        m_since=m_since,
        m_until=m_until
    )

    return records, new_continuation


# --- OAI-PMH Server Implementation ---

class SimpleServer:
    """Simple OAI-PMH server with direct method implementations."""

    def __init__(self, base_url: str = ''):
        self._base = base_url

    def identify(self) -> dict:
        """Return repository identification information."""
        return {
            'repositoryName': 'Modama OAI-PMH server',
            'baseURL': self._base,
            'protocolVersion': '2.0',
            'adminEmails': [os.environ.get('OAI_ADMIN_EMAIL', 'admin@example.org')],
            'earliestDatestamp': datetime.fromtimestamp(0),
            'deletedRecord': 'no',
            'granularity': 'YYYY-MM-DDThh:mm:ssZ',
            'compression': ['identity'],
            'descriptions': []
        }

    def getRecord(self, identifier: str) -> dict:
        """Get a single record by identifier."""
        path = pathlib.Path(path_from_identifier(identifier))
        path = sanitize(root=ROOT_PATH, path=path)
        guesses = guess(ROOT_PATH / path)
        handler = FileHandler.create(ROOT_PATH, path, guesses)
        
        return {
            'header': self._make_header(handler),
            'metadata': self._make_metadata(handler)
        }

    def listMetadataFormats(self) -> list:
        """List available metadata formats."""
        return [('oai_dc', 'http://www.openarchives.org/OAI/2.0/oai_dc.xsd', DC_NS)]

    def listIdentifiers(
        self,
        from_: Optional[datetime] = None,
        until: Optional[datetime] = None,
        continuation: Optional[str] = None,
        batch_size: int = BATCH_SIZE
    ) -> Tuple[list, Optional[str]]:
        """List record headers with optional date filtering and pagination."""
        # Decode continuation token if present
        cont_path = None
        if continuation:
            cont_path = continuation

        # Get crawl results
        records, new_continuation = _get_crawl_results(
            continuation=cont_path,
            from_=from_,
            until=until,
            n=batch_size
        )

        # Build headers
        headers = [self._make_header(handler) for handler in records.values()]

        # Encode new resumption token
        new_token = new_continuation

        return headers, new_token

    def listRecords(
        self,
        metadataPrefix: str,
        from_: Optional[datetime] = None,
        until: Optional[datetime] = None,
        continuation: Optional[str] = None,
        batch_size: int = BATCH_SIZE
    ) -> Tuple[list, Optional[str]]:
        """List full records with optional date filtering and pagination."""
        # Decode continuation token if present
        cont_path = None
        if continuation:
            cont_path = continuation

        # Get crawl results
        records, new_continuation = _get_crawl_results(
            continuation=cont_path,
            from_=from_,
            until=until,
            n=batch_size
        )

        # Build records
        recs = []
        for handler in records.values():
            recs.append({
                'header': self._make_header(handler),
                'metadata': self._make_metadata(handler)
            })

        # Encode new resumption token
        new_token = _encode_resumption_token(new_continuation)

        return recs, new_token

    def listSets(self) -> list:
        """List available sets (empty for this implementation)."""
        return []

    def _make_header(self, handler: FileHandler) -> dict:
        """Create header dict from FileHandler."""
        return {
            'identifier': get_identifier(handler.path),
            'datestamp': _format_datestamp(handler.mtime),
            'setSpec': [],
            'isDeleted': False
        }

    def _make_metadata(self, handler: FileHandler) -> dict:
        """Create metadata dict (oai_dc) from FileHandler."""
        return {
            'title': handler.get_titles(),
            'creator': handler.get_creators(),
            'date': [_format_datestamp(d) for d in handler.get_dates()],
            'format': handler.get_formats(),
            'identifier': [get_identifier(handler.path)],
            'description': handler.get_descriptions(),
            'publisher': [get_publisher()]
        }


# Instantiate server
_server = SimpleServer()


# --- XML Response Generation ---

def _make_oai_response(verb: str, children: list, request_args: dict = None) -> str:
    """Generate OAI-PMH XML response."""
    nsmap = {
        None: OAI_NS,
        'oai_dc': OAI_DC_NS,
        'dc': DC_NS,
        'xsi': XSI_NS,
    }
    
    root = etree.Element(f'{{{OAI_NS}}}OAI-PMH', nsmap=nsmap)
    
    # Response date
    response_date = etree.SubElement(root, f'{{{OAI_NS}}}responseDate')
    response_date.text = _format_datestamp(datetime.now().timestamp())
    
    # Request
    request_elem = etree.SubElement(root, f'{{{OAI_NS}}}request')
    request_elem.set(f'{{{XSI_NS}}}type', 'xsd:anyURI')
    request_elem.text = request_args.get('base_url', '')
    for key, value in request_args.items():
        # base_url is passed as value, not attribute
        if key not in ('base_url', ) and value:
            request_elem.set(key, quote_plus(value))
    
    # Verb element
    verb_elem = etree.SubElement(root, f'{{{OAI_NS}}}{verb}')
    
    # Add children
    for child in children:
        if isinstance(child, etree._Element):
            verb_elem.append(child)
        elif isinstance(child, dict):
            _add_dict_to_element(verb_elem, child)
    
    return etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)


def _add_dict_to_element(parent: etree._Element, data: dict, tag_prefix: str = ''):
    """Recursively add dictionary data to XML element."""
    for key, value in data.items():
        if isinstance(value, dict):
            child = etree.SubElement(parent, f'{{{OAI_NS}}}{key}')
            _add_dict_to_element(child, value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    child = etree.SubElement(parent, f'{{{OAI_NS}}}{key}')
                    _add_dict_to_element(child, item)
                else:
                    child = etree.SubElement(parent, f'{{{OAI_NS}}}{key}')
                    child.text = str(item)
        else:
            child = etree.SubElement(parent, f'{{{OAI_NS}}}{key}')
            child.text = str(value)


def _make_error(code: str, message: str) -> str:
    """Generate OAI-PMH error response."""
    nsmap = {None: OAI_NS}
    root = etree.Element(f'{{{OAI_NS}}}OAI-PMH', nsmap=nsmap)
    
    response_date = etree.SubElement(root, f'{{{OAI_NS}}}responseDate')
    response_date.text = _format_datestamp(datetime.now().timestamp())
    
    request_elem = etree.SubElement(root, f'{{{OAI_NS}}}request')
    request_elem.text = ''
    
    error = etree.SubElement(root, f'{{{OAI_NS}}}error')
    error.set('code', code)
    error.text = message
    
    return etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)


# --- Flask Endpoint ---

@app.route('/oai', methods=['GET', 'POST'])
def oai_endpoint():
    """Handle OAI-PMH requests."""
    params = request.args if request.method == 'GET' else request.form
    request_args = {str(k): str(v) for k, v in params.items()}
    
    verb = request_args.get('verb')
    if not verb:
        return Response(_make_error('badVerb', 'Missing verb parameter'), 
                       mimetype='text/xml; charset=utf-8')
    
    # Add base URL to request args
    request_args['base_url'] = request.url.split('?')[0]
    
    try:
        if verb == 'Identify':
            return _handle_identify(request_args)
        elif verb == 'GetRecord':
            return _handle_getrecord(request_args)
        elif verb == 'ListMetadataFormats':
            return _handle_listmetadataformats(request_args)
        elif verb == 'ListIdentifiers':
            return _handle_listidentifiers(request_args)
        elif verb == 'ListRecords':
            return _handle_listrecords(request_args)
        elif verb == 'ListSets':
            return _handle_listsets(request_args)
        else:
            return Response(_make_error('badVerb', f'Unknown verb: {verb}'),
                           mimetype='text/xml; charset=utf-8')
    except Exception as e:
        raise
        return Response(_make_error('badArgument', str(e)),
                       mimetype='text/xml; charset=utf-8')


def _handle_identify(args: dict) -> Response:
    """Handle Identify verb."""
    info = _server.identify()
    children = [
        {'repositoryName': info['repositoryName']},
        {'baseURL': info['baseURL']},
        {'protocolVersion': info['protocolVersion']},
        {'adminEmails': [{'adminEmail': email} for email in info['adminEmails']]},
        {'earliestDatestamp': _format_datestamp(info['earliestDatestamp'].timestamp())},
        {'deletedRecord': info['deletedRecord']},
        {'granularity': info['granularity']},
        {'compression': [{'compression': c} for c in info['compression']]},
    ]
    return Response(_make_oai_response('Identify', children, args),
                   mimetype='text/xml; charset=utf-8')


def _handle_getrecord(args: dict) -> Response:
    """Handle GetRecord verb."""
    identifier = args.get('identifier')
    if not identifier:
        return Response(_make_error('badArgument', 'Missing identifier parameter'),
                       mimetype='text/xml; charset=utf-8')
    
    record = _server.getRecord(identifier)
    children = [_make_record_element(record)]
    
    return Response(_make_oai_response('GetRecord', children, args),
                   mimetype='text/xml; charset=utf-8')


def _handle_listmetadataformats(args: dict) -> Response:
    """Handle ListMetadataFormats verb."""
    formats = _server.listMetadataFormats()
    children = [
        {'metadataFormat': {
            'metadataPrefix': fmt[0],
            'schema': fmt[1],
            'metadataNamespace': fmt[2]
        }} for fmt in formats
    ]
    
    return Response(_make_oai_response('ListMetadataFormats', children, args),
                   mimetype='text/xml; charset=utf-8')


def _handle_listidentifiers(args: dict) -> Response:
    """Handle ListIdentifiers verb."""
    resumption_token = args.get('resumptionToken')
    from_arg = args.get('from')
    until_arg = args.get('until')
    metadata_prefix_arg = args.get('metadataPrefix')
    
    # If resumptionToken is present, decode it and use those parameters
    if resumption_token:
        continuation, token_params = _decode_resumption_token(resumption_token)
        
        # Check for conflicting parameters
        if from_arg or until_arg or metadata_prefix_arg:
            return Response(
                _make_error('badArgument', 
                           'Cannot mix resumptionToken with from, until, or metadataPrefix parameters'),
                mimetype='text/xml; charset=utf-8'
            )
        
        # Use parameters from resumption token
        from_ = _parse_datestamp(token_params.get('from'))
        until = _parse_datestamp(token_params.get('until'))
        metadata_prefix = token_params.get('metadataPrefix')
    else:
        # Use provided parameters
        continuation = None
        from_ = _parse_datestamp(from_arg)
        until = _parse_datestamp(until_arg)
        metadata_prefix = metadata_prefix_arg
    
    # Validate metadataPrefix (required for ListIdentifiers in OAI-PMH 2.0)
    if not metadata_prefix:
        return Response(_make_error('badArgument', 'Missing metadataPrefix parameter'),
                       mimetype='text/xml; charset=utf-8')
    
    headers, new_token = _server.listIdentifiers(
        from_=from_,
        until=until,
        continuation=continuation
    )
    
    # Encode resumption token with all parameters (except verb)
    encoded_token = _encode_resumption_token(
        continuation=new_token,
        metadataPrefix=metadata_prefix,
        from_=from_arg,
        until=until_arg
    )
    
    children = [_make_header_element(h) for h in headers]
    
    # Add resumption token if present
    if encoded_token:
        children.append({'resumptionToken': encoded_token})
    
    return Response(_make_oai_response('ListIdentifiers', children, args),
                   mimetype='text/xml; charset=utf-8')


def _handle_listrecords(args: dict) -> Response:
    """Handle ListRecords verb."""
    resumption_token = args.get('resumptionToken')
    from_arg = args.get('from')
    until_arg = args.get('until')
    metadata_prefix_arg = args.get('metadataPrefix')
    
    # If resumptionToken is present, decode it and use those parameters
    if resumption_token:
        continuation, token_params = _decode_resumption_token(resumption_token)
        
        # Check for conflicting parameters
        if from_arg or until_arg or metadata_prefix_arg:
            return Response(
                _make_error('badArgument', 
                           'Cannot mix resumptionToken with from, until, or metadataPrefix parameters'),
                mimetype='text/xml; charset=utf-8'
            )
        
        # Use parameters from resumption token
        from_ = _parse_datestamp(token_params.get('from'))
        until = _parse_datestamp(token_params.get('until'))
        metadata_prefix = token_params.get('metadataPrefix')
    else:
        # Use provided parameters
        continuation = None
        from_ = _parse_datestamp(from_arg)
        until = _parse_datestamp(until_arg)
        metadata_prefix = metadata_prefix_arg
    
    # Validate metadataPrefix
    if not metadata_prefix:
        return Response(_make_error('badArgument', 'Missing metadataPrefix parameter'),
                       mimetype='text/xml; charset=utf-8')
    
    records, new_token = _server.listRecords(
        metadataPrefix=metadata_prefix,
        from_=from_,
        until=until,
        continuation=continuation
    )
    
    # Encode resumption token with all parameters (except verb)
    encoded_token = _encode_resumption_token(
        continuation=new_token,
        metadataPrefix=metadata_prefix,
        from_=from_arg,
        until=until_arg
    )
    
    children = [_make_record_element(r) for r in records]
    
    # Add resumption token if present
    if encoded_token:
        children.append({'resumptionToken': encoded_token})
    
    return Response(_make_oai_response('ListRecords', children, args),
                   mimetype='text/xml; charset=utf-8')


def _handle_listsets(args: dict) -> Response:
    """Handle ListSets verb."""
    sets = _server.listSets()
    children = [{'set': {}} for _ in sets]  # Empty sets list
    
    return Response(_make_oai_response('ListSets', children, args),
                   mimetype='text/xml; charset=utf-8')


def _make_header_element(header: dict) -> etree._Element:
    """Create header XML element."""
    header_elem = etree.Element(f'{{{OAI_NS}}}header')
    if header.get('isDeleted'):
        header_elem.set('status', 'deleted')
    
    id_elem = etree.SubElement(header_elem, f'{{{OAI_NS}}}identifier')
    id_elem.text = header['identifier']
    
    datestamp_elem = etree.SubElement(header_elem, f'{{{OAI_NS}}}datestamp')
    datestamp_elem.text = header['datestamp']
    
    for set_spec in header.get('setSpec', []):
        set_elem = etree.SubElement(header_elem, f'{{{OAI_NS}}}setSpec')
        set_elem.text = set_spec
    
    return header_elem


def _make_record_element(record: dict) -> etree._Element:
    """Create record XML element with header and metadata."""
    record_elem = etree.Element(f'{{{OAI_NS}}}record')
    
    # Add header
    record_elem.append(_make_header_element(record['header']))
    
    # Add metadata
    if 'metadata' in record:
        metadata_elem = etree.SubElement(record_elem, f'{{{OAI_NS}}}metadata')
        oai_dc_elem = etree.SubElement(metadata_elem, f'{{{OAI_DC_NS}}}dc',
                                       nsmap={'oai_dc': OAI_DC_NS, 'dc': DC_NS})
        
        for key, value in record['metadata'].items():
            if isinstance(value, list):
                for item in value:
                    dc_elem = etree.SubElement(oai_dc_elem, f'{{{DC_NS}}}{key}')
                    dc_elem.text = str(item)
            else:
                dc_elem = etree.SubElement(oai_dc_elem, f'{{{DC_NS}}}{key}')
                dc_elem.text = str(value)
    
    return record_elem


if __name__ == '__main__':
    app.run(port=8000, debug=True)
