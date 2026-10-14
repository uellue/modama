"""OAI-PMH 2.0 repository serving the `records` table as a WSGI app.

Protocol: https://www.openarchives.org/OAI/2.0/openarchivesprotocol.htm
Only oai_dc, no sets, no deleted records, seconds granularity.
"""

import re
from datetime import UTC, datetime, timedelta

from lxml import etree
from psycopg_pool import ConnectionPool
from werkzeug.datastructures import MultiDict
from werkzeug.wrappers import Request, Response

from .records import format_datestamp

OAI_NS = "http://www.openarchives.org/OAI/2.0/"
OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DC_NS = "http://purl.org/dc/elements/1.1/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
XSI_SCHEMA_LOCATION = f"{{{XSI_NS}}}schemaLocation"
OAI_DC_SCHEMA = "http://www.openarchives.org/OAI/2.0/oai_dc.xsd"

REPOSITORY_NAME = "ER-C data (modama)"
GRANULARITY = "YYYY-MM-DDThh:mm:ssZ"
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# The elements of unqualified Dublin Core, in the order we render them
DC_ELEMENTS = (
    "title", "creator", "subject", "description", "publisher", "contributor",
    "date", "type", "format", "identifier", "source", "language", "relation",
    "coverage", "rights",
)  # fmt: skip

# verb: (required arguments, optional arguments, exclusive argument)
VERBS = {
    "Identify": (set(), set(), None),
    "ListMetadataFormats": (set(), {"identifier"}, None),
    "ListSets": (set(), set(), "resumptionToken"),
    "GetRecord": ({"identifier", "metadataPrefix"}, set(), None),
    "ListIdentifiers": (
        {"metadataPrefix"},
        {"from", "until", "set"},
        "resumptionToken",
    ),
    "ListRecords": ({"metadataPrefix"}, {"from", "until", "set"}, "resumptionToken"),
}

DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
SECOND_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
# Characters that XML 1.0 can't represent
INVALID_XML_RE = re.compile("[^\t\n\r\x20-퟿-�\U00010000-\U0010ffff]")


class OAIError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _xml_text(text: str) -> str:
    return INVALID_XML_RE.sub("�", text)


def _element(tag: str) -> etree._Element:
    return etree.Element(f"{{{OAI_NS}}}{tag}", nsmap={None: OAI_NS})


def _sub(parent, tag: str, text: str | None = None) -> etree._Element:
    element = etree.SubElement(parent, f"{{{OAI_NS}}}{tag}")
    if text is not None:
        element.text = _xml_text(text)
    return element


def parse_arguments(params: MultiDict) -> tuple[str, dict[str, str]]:
    verbs = params.getlist("verb")
    if len(verbs) != 1 or verbs[0] not in VERBS:
        raise OAIError("badVerb", "Missing, repeated or illegal verb")
    verb = verbs[0]
    args = {}
    for key in params:
        values = params.getlist(key)
        if len(values) > 1:
            raise OAIError("badArgument", f"Repeated argument {key}")
        if key != "verb":
            args[key] = values[0]

    required, optional, exclusive = VERBS[verb]
    if exclusive in args:
        if len(args) > 1:
            raise OAIError("badArgument", f"{exclusive} is an exclusive argument")
        return verb, args
    illegal = args.keys() - required - optional
    if illegal:
        raise OAIError("badArgument", f"Illegal arguments {sorted(illegal)}")
    missing = required - args.keys()
    if missing:
        raise OAIError("badArgument", f"Missing arguments {sorted(missing)}")
    return verb, args


def _parse_datestamp(value: str) -> tuple[datetime, bool]:
    """Parse a from/until argument. Returns the time and whether it has day granularity."""
    try:
        if DAY_RE.fullmatch(value):
            return datetime.fromisoformat(value).replace(tzinfo=UTC), True
        if SECOND_RE.fullmatch(value):
            return datetime.fromisoformat(value), False
    except ValueError:
        pass
    raise OAIError("badArgument", f"Illegal datestamp {value!r}")


def parse_range(
    from_arg: str | None, until_arg: str | None
) -> tuple[datetime | None, datetime | None]:
    """Inclusive bounds for selective harvesting, at seconds resolution."""
    from_ = until = None
    granularities = set()
    if from_arg is not None:
        from_, is_day = _parse_datestamp(from_arg)
        granularities.add(is_day)
    if until_arg is not None:
        until, is_day = _parse_datestamp(until_arg)
        granularities.add(is_day)
        if is_day:
            until += timedelta(days=1, seconds=-1)
    if len(granularities) > 1:
        raise OAIError("badArgument", "from and until have different granularities")
    if from_ is not None and until is not None and from_ > until:
        raise OAIError("badArgument", "from is later than until")
    return from_, until


def _timestamp(value: datetime | None) -> str:
    return "" if value is None else str(int(value.timestamp()))


def _from_timestamp(value: str) -> datetime | None:
    return None if value == "" else datetime.fromtimestamp(int(value), UTC)


def encode_token(from_, until, last_datestamp: datetime, last_id: int) -> str:
    return ",".join(
        (_timestamp(from_), _timestamp(until), _timestamp(last_datestamp), str(last_id))
    )


def decode_token(token: str):
    """Returns (from, until, (last datestamp, last dataset id))."""
    try:
        from_, until, last_datestamp, last_id = token.split(",")
        return (
            _from_timestamp(from_),
            _from_timestamp(until),
            (datetime.fromtimestamp(int(last_datestamp), UTC), int(last_id)),
        )
    except (ValueError, OverflowError, OSError):
        raise OAIError("badResumptionToken", "Invalid resumptionToken") from None


class OAIServer:
    def __init__(
        self,
        pool: ConnectionPool,
        base_url: str,
        admin_email: str,
        page_size: int = 100,
    ):
        self.pool = pool
        self.base_url = base_url
        self.admin_email = admin_email
        self.page_size = page_size

    def __call__(self, environ, start_response):
        request = Request(environ)
        if request.method == "GET":
            body = self.respond(request.args)
        elif request.method == "POST":
            body = self.respond(request.form)
        else:
            response = Response(status=405, headers={"Allow": "GET, POST"})
            return response(environ, start_response)
        response = Response(body, content_type="text/xml; charset=utf-8")
        return response(environ, start_response)

    def respond(self, params: MultiDict) -> bytes:
        root = etree.Element(
            f"{{{OAI_NS}}}OAI-PMH", nsmap={None: OAI_NS, "xsi": XSI_NS}
        )
        root.set(
            XSI_SCHEMA_LOCATION,
            f"{OAI_NS} http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd",
        )
        _sub(root, "responseDate", format_datestamp(datetime.now(UTC)))
        request = _sub(root, "request", self.base_url)
        try:
            verb, args = parse_arguments(params)
            request.set("verb", verb)
            for key, value in args.items():
                request.set(key, _xml_text(value))
            root.append(getattr(self, verb)(args))
        except OAIError as error:
            # The request element must not have attributes for these errors
            if error.code in ("badVerb", "badArgument"):
                request.attrib.clear()
            error_element = _sub(root, "error", error.message)
            error_element.set("code", error.code)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    def _query(self, sql: str, params=()) -> list[tuple]:
        with self.pool.connection() as conn:
            return conn.execute(sql, params).fetchall()

    def _check_exists(self, identifier: str):
        if not self._query(
            "SELECT 1 FROM records WHERE identifier = %s", (identifier,)
        ):
            raise OAIError("idDoesNotExist", f"No record {identifier}")

    def Identify(self, args):
        ((earliest,),) = self._query("SELECT min(datestamp) FROM records")
        identify = _element("Identify")
        _sub(identify, "repositoryName", REPOSITORY_NAME)
        _sub(identify, "baseURL", self.base_url)
        _sub(identify, "protocolVersion", "2.0")
        _sub(identify, "adminEmail", self.admin_email)
        _sub(identify, "earliestDatestamp", format_datestamp(earliest or EPOCH))
        _sub(identify, "deletedRecord", "no")
        _sub(identify, "granularity", GRANULARITY)
        return identify

    def ListMetadataFormats(self, args):
        if "identifier" in args:
            self._check_exists(args["identifier"])
        formats = _element("ListMetadataFormats")
        metadata_format = _sub(formats, "metadataFormat")
        _sub(metadata_format, "metadataPrefix", "oai_dc")
        _sub(metadata_format, "schema", OAI_DC_SCHEMA)
        _sub(metadata_format, "metadataNamespace", OAI_DC_NS)
        return formats

    def ListSets(self, args):
        raise OAIError("noSetHierarchy", "This repository does not support sets")

    def GetRecord(self, args):
        _check_prefix(args["metadataPrefix"])
        rows = self._query(
            "SELECT identifier, datestamp, metadata FROM records WHERE identifier = %s",
            (args["identifier"],),
        )
        if not rows:
            raise OAIError("idDoesNotExist", f"No record {args['identifier']}")
        get_record = _element("GetRecord")
        _record(get_record, *rows[0])
        return get_record

    def ListIdentifiers(self, args):
        return self._list("ListIdentifiers", args)

    def ListRecords(self, args):
        return self._list("ListRecords", args)

    def _list(self, verb, args):
        if "resumptionToken" in args:
            from_, until, after = decode_token(args["resumptionToken"])
        else:
            _check_prefix(args["metadataPrefix"])
            if "set" in args:
                raise OAIError(
                    "noSetHierarchy", "This repository does not support sets"
                )
            from_, until = parse_range(args.get("from"), args.get("until"))
            after = None

        conditions, params = [], []
        if from_ is not None:
            conditions.append("datestamp >= %s")
            params.append(from_)
        if until is not None:
            conditions.append("datestamp <= %s")
            params.append(until)
        if after is not None:
            conditions.append("(datestamp, dataset_id) > (%s, %s)")
            params.extend(after)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._query(
            f"""
            SELECT identifier, datestamp, metadata, dataset_id FROM records {where}
            ORDER BY datestamp, dataset_id LIMIT %s
            """,
            (*params, self.page_size + 1),
        )
        if not rows:
            raise OAIError("noRecordsMatch", "No records match the request")

        result = _element(verb)
        for identifier, datestamp, metadata, _ in rows[: self.page_size]:
            if verb == "ListRecords":
                _record(result, identifier, datestamp, metadata)
            else:
                _header(result, identifier, datestamp)
        if len(rows) > self.page_size:
            _, datestamp, _, dataset_id = rows[self.page_size - 1]
            _sub(
                result,
                "resumptionToken",
                encode_token(from_, until, datestamp, dataset_id),
            )
        elif "resumptionToken" in args:
            # The last part of an incomplete list has an empty token
            _sub(result, "resumptionToken")
        return result


def _check_prefix(prefix: str):
    if prefix != "oai_dc":
        raise OAIError(
            "cannotDisseminateFormat", f"Unsupported metadataPrefix {prefix!r}"
        )


def _header(parent, identifier: str, datestamp: datetime):
    header = _sub(parent, "header")
    _sub(header, "identifier", identifier)
    _sub(header, "datestamp", format_datestamp(datestamp))


def _record(parent, identifier: str, datestamp: datetime, metadata: dict):
    record = _sub(parent, "record")
    _header(record, identifier, datestamp)
    dc = etree.SubElement(
        _sub(record, "metadata"),
        f"{{{OAI_DC_NS}}}dc",
        nsmap={"oai_dc": OAI_DC_NS, "dc": DC_NS, "xsi": XSI_NS},
    )
    dc.set(XSI_SCHEMA_LOCATION, f"{OAI_DC_NS} {OAI_DC_SCHEMA}")
    for name in DC_ELEMENTS:
        for value in metadata.get(name, ()):
            etree.SubElement(dc, f"{{{DC_NS}}}{name}").text = _xml_text(value)
