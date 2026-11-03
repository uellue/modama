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

from .render import (
    OAI_DC_NS,
    OAI_DC_SCHEMA,
    document,
    element,
    format_datestamp,
    header,
    record,
    sub,
    xml_text,
)

REPOSITORY_NAME = "ER-C data (modama)"
GRANULARITY = "YYYY-MM-DDThh:mm:ssZ"
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

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


class OAIError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


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
        root, request = document(self.base_url, None, {})
        try:
            verb, args = parse_arguments(params)
            request.set("verb", verb)
            for key, value in args.items():
                request.set(key, xml_text(value))
            root.append(getattr(self, verb)(args))
        except OAIError as error:
            # The request element must not have attributes for these errors
            if error.code in ("badVerb", "badArgument"):
                request.attrib.clear()
            error_element = sub(root, "error", error.message)
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
        identify = element("Identify")
        sub(identify, "repositoryName", REPOSITORY_NAME)
        sub(identify, "baseURL", self.base_url)
        sub(identify, "protocolVersion", "2.0")
        sub(identify, "adminEmail", self.admin_email)
        sub(identify, "earliestDatestamp", format_datestamp(earliest or EPOCH))
        sub(identify, "deletedRecord", "no")
        sub(identify, "granularity", GRANULARITY)
        return identify

    def ListMetadataFormats(self, args):
        if "identifier" in args:
            self._check_exists(args["identifier"])
        formats = element("ListMetadataFormats")
        metadata_format = sub(formats, "metadataFormat")
        sub(metadata_format, "metadataPrefix", "oai_dc")
        sub(metadata_format, "schema", OAI_DC_SCHEMA)
        sub(metadata_format, "metadataNamespace", OAI_DC_NS)
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
        get_record = element("GetRecord")
        record(get_record, *rows[0])
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
            conditions.append("(datestamp, record_id) > (%s, %s)")
            params.extend(after)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._query(
            f"""
            SELECT identifier, datestamp, metadata, record_id FROM records {where}
            ORDER BY datestamp, record_id LIMIT %s
            """,
            (*params, self.page_size + 1),
        )
        if not rows:
            raise OAIError("noRecordsMatch", "No records match the request")

        result = element(verb)
        for identifier, datestamp, metadata, _ in rows[: self.page_size]:
            if verb == "ListRecords":
                record(result, identifier, datestamp, metadata)
            else:
                header(result, identifier, datestamp)
        if len(rows) > self.page_size:
            _, datestamp, _, record_id = rows[self.page_size - 1]
            sub(
                result,
                "resumptionToken",
                encode_token(from_, until, datestamp, record_id),
            )
        elif "resumptionToken" in args:
            # The last part of an incomplete list has an empty token
            sub(result, "resumptionToken")
        return result


def _check_prefix(prefix: str):
    if prefix != "oai_dc":
        raise OAIError(
            "cannotDisseminateFormat", f"Unsupported metadataPrefix {prefix!r}"
        )
