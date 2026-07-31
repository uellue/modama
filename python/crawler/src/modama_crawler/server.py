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
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote_plus, quote_plus
import pathlib
from typing import Optional, Sequence, Tuple
import json
import warnings

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv

from oaipmh.datestamp import datestamp_to_datetime, datetime_to_datestamp
from xdg import Mime

from modama_crawler.repository import (
    get_identifier,
    get_publisher,
    path_from_identifier,
    sanitize,
    RepositoryConfig,
)
from modama_crawler.recognition import guess, FileHandler, _get_mime_types_from_db
from .database import PostgresConfig


# Load environment variables from .env file
load_dotenv()

# MODAMA_DATA_ROOT: Absolute path where files are stored in the database and on filesystem

# PostgreSQL configuration is now handled via PostgresConfig dataclass passed to create_app

# XML Namespaces
OAI_NS = "http://www.openarchives.org/OAI/2.0/"
OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DC_NS = "http://purl.org/dc/elements/1.1/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

# --- Helper Functions ---


def _parse_datestamp(s: str) -> datetime:
    """Parse OAI-PMH datestamp string to datetime."""
    if isinstance(s, str):
        return datestamp_to_datetime(s)
    raise TypeError(f"Unsupported datestamp value: {s!r}")


def _format_datestamp(datestamp: datetime | float | int) -> str:
    """Format date as OAI-PMH datestamp.

    Accepts either a datetime object, or Unix timestamp (int/float)
    Converts timezone-aware datetimes and timestamps to naive UTC datetimes for OAI-PMH compatibility.
    """
    if isinstance(datestamp, datetime):
        # Convert timezone-aware to naive UTC
        if datestamp.tzinfo is not None:
            datestamp = datestamp.astimezone(timezone.utc).replace(tzinfo=None)
        return datetime_to_datestamp(datestamp)
    elif isinstance(datestamp, (int, float)):
        # Assume it's a Unix timestamp
        return datetime_to_datestamp(datetime.fromtimestamp(datestamp))
    else:
        raise TypeError(f"Invalid argument {datestamp} {type(datestamp)}")


# --- OAI-PMH Server Implementation ---


class OAIFileDBBackend:
    """OAI-PMH backend that reads from file system and database."""

    def __init__(self, pool: ConnectionPool, root: pathlib.Path):
        self._pool = pool

        self._root = root

    def _get_handler_for_path(
        self,
        conn: psycopg.Connection,
        path: pathlib.Path,
        guesses: Optional[Sequence[Mime.MIMEtype]] = None,
    ) -> FileHandler:
        """Create a FileHandler for a path using database MIME types.

        Args:
            conn: Database connection
            path: Relative path to create handler for
            guesses: Optional MIME type guesses (e.g., from client)

        Returns:
            FileHandler instance
        """
        # Convert relative path to absolute for database query and filesystem access
        abs_path = self._root / path

        # Try to get MIME types from database using absolute path
        db_guesses = _get_mime_types_from_db(conn, abs_path)
        if db_guesses:
            guesses = db_guesses
        elif guesses is None:
            # Fall back to filesystem-based guessing
            guesses = guess(abs_path)

        # Create handler with absolute filesystem root and relative path
        # FileHandler will construct abspath as root / path
        return FileHandler.create(self._root, path, guesses, conn)

    def getRecord(self, identifier: str) -> dict:
        """Get a single record by identifier."""
        with self._pool.connection() as conn:
            path = pathlib.Path(path_from_identifier(identifier))
            path = sanitize(root=self._root, path=path)
            handler = self._get_handler_for_path(conn, path)

            return {
                "header": self._make_header(handler),
                "metadata": self._make_metadata(handler),
            }

    def listMetadataFormats(self) -> list:
        """List available metadata formats."""
        return [("oai_dc", "http://www.openarchives.org/OAI/2.0/oai_dc.xsd", DC_NS)]

    def listIdentifiers(
        self,
        from_: Optional[datetime] = None,
        until: Optional[datetime] = None,
        continuation: Optional[str] = None,
        batch_size: int = 10,
    ) -> Tuple[list, Optional[pathlib.Path]]:
        """List record headers with optional date filtering and pagination."""
        # Decode continuation token if present
        cont_path = pathlib.Path(continuation) if continuation else None
        next_path = None
        # Get database connection for this request
        with self._pool.connection() as conn:
            # Query database for dataset paths
            paths, next_path = self._query_datasets_from_db(
                cont_path, from_, until, batch_size
            )

            # Build headers
            headers = []
            for path in paths:
                handler = self._get_handler_for_path(conn, path)
                headers.append(self._make_header(handler))

        return headers, next_path

    def listRecords(
        self,
        metadataPrefix: str,
        from_: Optional[datetime] = None,
        until: Optional[datetime] = None,
        continuation: Optional[str] = None,
        batch_size: int = 10,
    ) -> Tuple[list, Optional[str]]:
        """List full records with optional date filtering and pagination."""
        # Decode continuation token if present
        cont_path = pathlib.Path(continuation) if continuation else None

        # Query database for dataset paths using connection pool
        with self._pool.connection() as conn:
            paths, next_path = self._query_datasets_from_db(
                cont_path, from_, until, batch_size
            )

            # Build records
            recs = []
            for path in paths:
                try:
                    handler = self._get_handler_for_path(conn, path)
                    recs.append(
                        {
                            "header": self._make_header(handler),
                            "metadata": self._make_metadata(handler),
                        }
                    )
                except FileNotFoundError as e:
                    warnings.warn(f"Exception: {e}")

        return recs, next_path

    def listSets(self) -> list:
        """List available sets (empty for this implementation)."""
        return []

    def supports_deleted_records(self) -> bool:
        """Return whether this backend supports deleted records."""
        return False

    def _query_datasets_from_db(
        self,
        continuation: Optional[pathlib.Path],
        from_: Optional[datetime],
        until: Optional[datetime],
        batch_size: int,
    ) -> Tuple[list[pathlib.Path], Optional[pathlib.Path]]:
        """Query dataset paths from database with pagination and date filtering.

        Args:
            continuation: Last path from previous batch (for pagination)
            from_: Minimum mtime (inclusive)
            until: Maximum mtime (exclusive)
            batch_size: Maximum number of paths to return

        Returns:
            Tuple of (list of relative paths, next continuation path or None)
            Paths are relative to self._root for client exposure.
        """
        with self._pool.connection() as conn:
            cur = conn.cursor(row_factory=dict_row)

            # Build WHERE clause
            where_clauses = []
            params = []

            # Get the database root path prefix to strip
            db_root_str = str(self._root)
            if not db_root_str.endswith("/"):
                db_root_str += "/"

            # Pagination: paths greater than continuation (in database format)
            if continuation is not None:
                # Convert relative continuation to absolute for database query
                abs_continuation = self._root / continuation
                where_clauses.append("f.path > %s")
                params.append(str(abs_continuation))

            # Date filtering on mtime
            if from_ is not None:
                where_clauses.append("f.mtime >= %s")
                params.append(from_.timestamp())

            if until is not None:
                # until is inclusive in OAI-PMH, but we make it exclusive for SQL
                until_exclusive = until + timedelta(days=1)
                where_clauses.append("f.mtime < %s")
                params.append(until_exclusive.timestamp())

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            # Query for dataset paths (one path per dataset)
            # Return absolute paths from database, we'll convert to relative below
            sql = f"""
                SELECT DISTINCT f.path, f.mtime
                FROM files f
                JOIN datasets d ON f.path_id = d.path_id
                WHERE {where_clause}
                ORDER BY f.path
                LIMIT %s
            """
            params.append(batch_size)

            cur.execute(sql, params)
            rows = cur.fetchall()

            if not rows:
                return [], None

            # Convert absolute database paths to relative paths for client exposure
            paths = []
            for row in rows:
                abs_path = pathlib.Path(row["path"])
                # Strip the database root prefix
                try:
                    rel_path = abs_path.relative_to(self._root)
                except ValueError:
                    # Path is not under self._root, use as-is
                    rel_path = abs_path
                paths.append(rel_path)

            # For continuation, we need the last absolute path for database comparison
            next_path = paths[-1] if len(paths) == batch_size else None

        return paths, next_path

    def _make_header(self, handler: FileHandler) -> dict:
        """Create header dict from FileHandler.

        Returns Unix timestamp (float) for datestamp.
        """
        return {
            "identifier": get_identifier(handler.path),
            "datestamp": handler.mtime,
            "setSpec": [],
            "isDeleted": False,
        }

    def _make_metadata(self, handler: FileHandler) -> dict:
        """Create metadata dict (oai_dc) from FileHandler.

        Returns list of Unix timestamps (floats) for date field.
        """
        return {
            "title": handler.get_titles(),
            "creator": handler.get_creators(),
            "date": handler.get_dates(),
            "format": handler.get_formats(),
            "identifier": [get_identifier(handler.path)],
            "description": handler.get_descriptions(),
            "publisher": [get_publisher()],
        }


class OAIServer:
    """OAI-PMH server that handles all HTTP request processing and XML generation."""

    def __init__(self, backend: OAIFileDBBackend, config: RepositoryConfig):
        self._backend = backend
        self._config = config

    # --- OAI-PMH Protocol Methods ---

    def identify(self) -> dict:
        """Return repository identification information for OAI-PMH Identify response.

        This method implements the OAI-PMH Identify verb directly using the
        RepositoryConfig, separating protocol concerns from data storage concerns.

        Returns:
            Dictionary containing all Identify response fields
        """
        return {
            "repositoryName": self._config.repository_name,
            "protocolVersion": "2.0",
            "adminEmails": [self._config.admin_email],
            "earliestDatestamp": self._config.earliest_datestamp,
            "deletedRecord": "yes"
            if self._backend.supports_deleted_records()
            else "no",
            "granularity": self._config.granularity,
            "compression": self._config.compression,
            "baseURL": self._config.base_url,
        }

    # --- Resumption Token Helpers ---

    @staticmethod
    def _encode_resumption_token(
        continuation: Optional[pathlib.Path],
        metadataPrefix: Optional[str] = None,
        from_: Optional[str] = None,
        until: Optional[str] = None,
    ) -> Optional[str]:
        """Encode resumption token with continuation path and request parameters.

        Following OAI-PMH spec, the resumptionToken encodes all parameters except verb.
        All special characters are URL-encoded so the token can be pasted directly into a URL.
        Uses quote_plus to ensure proper encoding for query string parameters.
        """
        if continuation is None:
            return None

        token_data = {"continuation": str(continuation)}
        if metadataPrefix:
            token_data["metadataPrefix"] = metadataPrefix
        if from_:
            token_data["from"] = from_
        if until:
            token_data["until"] = until

        as_json = json.dumps(token_data)
        return quote_plus(as_json)

    @staticmethod
    def _decode_resumption_token(token: str) -> Tuple[Optional[pathlib.Path], dict]:
        """Decode resumption token to continuation path and parameters.

        The token is URL-encoded with quote_plus, so we use unquote_plus to decode.
        """
        unquoted = unquote_plus(token)

        as_data = json.loads(unquoted)

        keys = "continuation", "metadataPrefix", "from", "until"
        result = {}

        for key in keys:
            try:
                result[key] = as_data.pop(key)
            except KeyError:
                pass
        continuation_str = result.pop("continuation", "")
        continuation = pathlib.Path(continuation_str) if continuation_str else None
        return continuation, result

    # --- XML Response Generation ---

    def _make_oai_response(
        self, verb: str, children: list, request_args: Optional[dict] = None
    ) -> str:
        """Generate OAI-PMH XML response."""
        nsmap = {
            None: OAI_NS,
            "oai_dc": OAI_DC_NS,
            "dc": DC_NS,
            "xsi": XSI_NS,
        }

        root = etree.Element(f"{{{OAI_NS}}}OAI-PMH", nsmap=nsmap)

        # Add schemaLocation attribute to root element
        schema_location = f"{OAI_NS} http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd"
        root.set(f"{{{XSI_NS}}}schemaLocation", schema_location)

        # Response date
        response_date = etree.SubElement(root, f"{{{OAI_NS}}}responseDate")
        response_date.text = _format_datestamp(datetime.now().timestamp())

        # Request
        request_elem = etree.SubElement(root, f"{{{OAI_NS}}}request")
        request_elem.set(f"{{{XSI_NS}}}type", "xsd:anyURI")
        request_elem.text = request_args.get("base_url", "")
        for key, value in request_args.items():
            # base_url is passed as value, not attribute
            if key not in ("base_url",) and value:
                request_elem.set(key, quote_plus(value))

        # Verb element
        verb_elem = etree.SubElement(root, f"{{{OAI_NS}}}{verb}")
        # Add empty text to prevent lxml from using self-closing tags for empty elements
        verb_elem.text = ""

        # Add children
        for child in children:
            if isinstance(child, etree._Element):
                verb_elem.append(child)
            elif isinstance(child, dict):
                self._add_dict_to_element(verb_elem, child)

        return etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", pretty_print=True
        )

    def _add_dict_to_element(
        self, parent: etree._Element, data: dict, tag_prefix: str = ""
    ):
        """Recursively add dictionary data to XML element."""
        for key, value in data.items():
            if isinstance(value, dict):
                child = etree.SubElement(parent, f"{{{OAI_NS}}}{key}")
                self._add_dict_to_element(child, value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        child = etree.SubElement(parent, f"{{{OAI_NS}}}{key}")
                        self._add_dict_to_element(child, item)
                    else:
                        child = etree.SubElement(parent, f"{{{OAI_NS}}}{key}")
                        child.text = str(item)
            else:
                child = etree.SubElement(parent, f"{{{OAI_NS}}}{key}")
                child.text = str(value)

    def _make_error(self, code: str, message: str) -> str:
        """Generate OAI-PMH error response."""
        nsmap = {None: OAI_NS}
        root = etree.Element(f"{{{OAI_NS}}}OAI-PMH", nsmap=nsmap)

        response_date = etree.SubElement(root, f"{{{OAI_NS}}}responseDate")
        response_date.text = _format_datestamp(datetime.now().timestamp())

        request_elem = etree.SubElement(root, f"{{{OAI_NS}}}request")
        request_elem.text = ""

        error = etree.SubElement(root, f"{{{OAI_NS}}}error")
        error.set("code", code)
        error.text = message

        return etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", pretty_print=True
        )

    def _make_header_element(self, header: dict) -> etree._Element:
        """Create header XML element."""
        header_elem = etree.Element(f"{{{OAI_NS}}}header")
        if header.get("isDeleted"):
            header_elem.set("status", "deleted")

        id_elem = etree.SubElement(header_elem, f"{{{OAI_NS}}}identifier")
        id_elem.text = header["identifier"]

        datestamp_elem = etree.SubElement(header_elem, f"{{{OAI_NS}}}datestamp")
        # Handle both datetime objects (from backend) and formatted strings
        if isinstance(header["datestamp"], datetime):
            datestamp_elem.text = _format_datestamp(header["datestamp"])
        else:
            datestamp_elem.text = header["datestamp"]

        for set_spec in header.get("setSpec", []):
            set_elem = etree.SubElement(header_elem, f"{{{OAI_NS}}}setSpec")
            set_elem.text = set_spec

        return header_elem

    def _make_record_element(self, record: dict) -> etree._Element:
        """Create record XML element with header and metadata."""
        record_elem = etree.Element(f"{{{OAI_NS}}}record")

        # Add header
        record_elem.append(self._make_header_element(record["header"]))

        # Add metadata
        if "metadata" in record:
            metadata_elem = etree.SubElement(record_elem, f"{{{OAI_NS}}}metadata")
            oai_dc_elem = etree.SubElement(
                metadata_elem,
                f"{{{OAI_DC_NS}}}dc",
                nsmap={"oai_dc": OAI_DC_NS, "dc": DC_NS},
            )

            for key, value in record["metadata"].items():
                if isinstance(value, list):
                    for item in value:
                        dc_elem = etree.SubElement(oai_dc_elem, f"{{{DC_NS}}}{key}")
                        # Format datetime objects for OAI-PMH
                        if isinstance(item, datetime):
                            dc_elem.text = _format_datestamp(item)
                        else:
                            dc_elem.text = str(item)
                else:
                    dc_elem = etree.SubElement(oai_dc_elem, f"{{{DC_NS}}}{key}")
                    # Format datetime objects for OAI-PMH
                    if isinstance(value, datetime):
                        dc_elem.text = _format_datestamp(value)
                    else:
                        dc_elem.text = str(value)

        return record_elem

    # --- OAI-PMH Verb Handlers ---

    def handle_identify(self, args: dict) -> Response:
        """Handle Identify verb."""
        info = self.identify()
        children = [
            {"repositoryName": info["repositoryName"]},
            {"baseURL": self._config.base_url},
            {"protocolVersion": info["protocolVersion"]},
            {"adminEmails": [{"adminEmail": email} for email in info["adminEmails"]]},
            {"earliestDatestamp": _format_datestamp(info["earliestDatestamp"])},
            {"deletedRecord": info["deletedRecord"]},
            {"granularity": info["granularity"]},
            {"compression": [{"compression": c} for c in info["compression"]]},
        ]
        return Response(
            self._make_oai_response("Identify", children, args),
            mimetype="text/xml; charset=utf-8",
        )

    def handle_getrecord(self, args: dict) -> Response:
        """Handle GetRecord verb."""
        identifier = args.get("identifier")
        if not identifier:
            return Response(
                self._make_error("badArgument", "Missing identifier parameter"),
                mimetype="text/xml; charset=utf-8",
            )

        record = self._backend.getRecord(identifier)
        children = [self._make_record_element(record)]

        return Response(
            self._make_oai_response("GetRecord", children, args),
            mimetype="text/xml; charset=utf-8",
        )

    def handle_listmetadataformats(self, args: dict) -> Response:
        """Handle ListMetadataFormats verb."""
        formats = self._backend.listMetadataFormats()
        children = [
            {
                "metadataFormat": {
                    "metadataPrefix": fmt[0],
                    "schema": fmt[1],
                    "metadataNamespace": fmt[2],
                }
            }
            for fmt in formats
        ]

        return Response(
            self._make_oai_response("ListMetadataFormats", children, args),
            mimetype="text/xml; charset=utf-8",
        )

    def _process_list_verb(
        self,
        verb: str,
        backend_method: callable,
        make_element: callable,
        args: dict,
    ) -> Response:
        """Common logic for ListIdentifiers and ListRecords verbs.

        Args:
            verb: OAI-PMH verb name ("ListIdentifiers" or "ListRecords")
            backend_method: Backend method to call (listIdentifiers or listRecords)
            make_element: Function to convert items to XML elements
            args: Request arguments
        """
        resumption_token = args.get("resumptionToken")
        from_arg = args.get("from")
        until_arg = args.get("until")
        metadata_prefix_arg = args.get("metadataPrefix")

        # If resumptionToken is present, decode it and use those parameters
        if resumption_token:
            continuation, token_params = self._decode_resumption_token(resumption_token)

            # Check for conflicting parameters
            if from_arg or until_arg or metadata_prefix_arg:
                return Response(
                    self._make_error(
                        "badArgument",
                        "Cannot mix resumptionToken with from, until, or metadataPrefix parameters",
                    ),
                    mimetype="text/xml; charset=utf-8",
                )

            # Use parameters from resumption token
            from_ = _parse_datestamp(token_params.get("from"))
            until = _parse_datestamp(token_params.get("until"))
            metadata_prefix = token_params.get("metadataPrefix")
        else:
            # Use provided parameters
            continuation = None
            from_ = _parse_datestamp(from_arg)
            until = _parse_datestamp(until_arg)
            metadata_prefix = metadata_prefix_arg

        # Validate metadataPrefix (required for ListIdentifiers in OAI-PMH 2.0)
        if not metadata_prefix:
            return Response(
                self._make_error("badArgument", "Missing metadataPrefix parameter"),
                mimetype="text/xml; charset=utf-8",
            )

        items, next_path = backend_method(
            metadataPrefix=metadata_prefix,
            from_=from_,
            until=until,
            continuation=str(continuation) if continuation else None,
        )

        children = [make_element(item) for item in items]

        # Encode and add resumption token if present
        if next_path:
            from_str = _format_datestamp(from_.timestamp()) if from_ else None
            until_str = _format_datestamp(until.timestamp()) if until else None
            encoded_token = self._encode_resumption_token(
                next_path, metadata_prefix, from_str, until_str
            )
            children.append({"resumptionToken": encoded_token})

        return Response(
            self._make_oai_response(verb, children, args),
            mimetype="text/xml; charset=utf-8",
        )

    def handle_listidentifiers(self, args: dict) -> Response:
        """Handle ListIdentifiers verb."""
        return self._process_list_verb(
            "ListIdentifiers",
            self._backend.listIdentifiers,
            self._make_header_element,
            args,
        )

    def handle_listrecords(self, args: dict) -> Response:
        """Handle ListRecords verb."""
        return self._process_list_verb(
            "ListRecords",
            self._backend.listRecords,
            self._make_record_element,
            args,
        )

    def handle_listsets(self, args: dict) -> Response:
        """Handle ListSets verb."""
        sets = self._backend.listSets()
        children = [{"set": {}} for _ in sets]  # Empty sets list

        return Response(
            self._make_oai_response("ListSets", children, args),
            mimetype="text/xml; charset=utf-8",
        )


def create_app(
    pool: ConnectionPool,
    repo_config: Optional[RepositoryConfig] = None,
    config: Optional[dict] = None,
) -> Flask:
    """Create and configure the OAI-PMH Flask application.

    Args:
        config: Optional dictionary of configuration values
        db_config: Optional PostgresConfig for database connection. If provided,
                   will override the global postgres_config for this app instance.

    Returns:
        Configured Flask app instance
    """
    # Apply configuration override
    if config is None:
        config = {}

    if repo_config is None:
        # Create RepositoryConfig from environment variables
        repo_config = RepositoryConfig.from_env()

    app = Flask(__name__)
    app.config.update(config)

    backend = OAIFileDBBackend(pool=pool, root=app.config["MODAMA_DATA_ROOT"])

    # Create server instance for this app
    _server = OAIServer(backend, config=repo_config)

    @app.route("/oai", methods=["GET", "POST"])
    def oai_endpoint():
        """Handle OAI-PMH requests."""
        params = request.args if request.method == "GET" else request.form
        request_args = {str(k): str(v) for k, v in params.items()}

        verb = request_args.get("verb")
        if not verb:
            return Response(
                _server._make_error("badVerb", "Missing verb parameter"),
                mimetype="text/xml; charset=utf-8",
            )

        # Add base URL to request args
        request_args["base_url"] = request.url.split("?")[0]

        try:
            if verb == "Identify":
                return _server.handle_identify(request_args)
            elif verb == "GetRecord":
                return _server.handle_getrecord(request_args)
            elif verb == "ListMetadataFormats":
                return _server.handle_listmetadataformats(request_args)
            elif verb == "ListIdentifiers":
                return _server.handle_listidentifiers(request_args)
            elif verb == "ListRecords":
                return _server.handle_listrecords(request_args)
            elif verb == "ListSets":
                return _server.handle_listsets(request_args)
            else:
                return Response(
                    _server._make_error("badVerb", f"Unknown verb: {verb}"),
                    mimetype="text/xml; charset=utf-8",
                )
        except Exception as e:
            raise
            return Response(
                _server._make_error("badArgument", str(e)),
                mimetype="text/xml; charset=utf-8",
            )

    return app


if __name__ == "__main__":
    with ConnectionPool(
        conninfo=PostgresConfig.from_env().connection_string(),
        open=True,
    ) as pool:
        # Expose default app for backward compatibility (legacy usage)
        app = create_app(
            pool=pool,
        )
        app.run(port=7654, debug=True)
