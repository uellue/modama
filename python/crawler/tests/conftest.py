import functools
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from lxml import etree
from modama_crawler.formats import Dataset
from modama_crawler.records import build
from modama_crawler.server import OAIServer
from modama_crawler.store import ensure_tables
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from werkzeug.serving import make_server
from werkzeug.test import Client

SCHEMAS = Path(__file__).parent / "schemas"
OAI = "{http://www.openarchives.org/OAI/2.0/}"
DC = "{http://purl.org/dc/elements/1.1/}"
BASE_URL = "http://localhost/oai"

# path: datestamp; boundaries for selective harvesting and paging with page size 2
RECORDS = {
    "/a.txt": "2024-01-01T00:00:00Z",
    "/b.txt": "2024-06-01T00:00:00Z",
    "/c d.txt": "2024-06-01T12:00:00Z",
    "/e:f.txt": "2024-06-01T23:59:59Z",
    "/g+h%.txt": "2024-06-02T00:00:00Z",
}


@pytest.fixture(scope="session", autouse=True)
def _mime_database(mime_database):
    """Every test classifies with the MIME database of the installed collections (plugin fixture)."""
    return mime_database


@pytest.fixture
def conn(postgresql):
    ensure_tables(postgresql)
    return postgresql


@pytest.fixture
def add_record(conn):
    """Insert a record with the given datestamp, bypassing the crawl. Returns its identifier."""

    def add(path: str, datestamp: str) -> str:
        dataset = Dataset(
            anchor=path,
            members=(path,),
            type="text/plain",
            basis="single file",
            uid=os.getuid(),
        )
        identifier, metadata = build(dataset)
        conn.execute(
            "INSERT INTO records (identifier, datestamp, metadata) VALUES (%s, %s, %s)",
            (identifier, datestamp, Jsonb(metadata)),
        )
        conn.commit()
        return identifier

    return add


@pytest.fixture
def records(add_record) -> list[str]:
    return [add_record(path, datestamp) for path, datestamp in RECORDS.items()]


@pytest.fixture
def server(conn):
    conninfo = make_conninfo(conn.info.dsn, password=conn.info.password or "")
    with ConnectionPool(conninfo, min_size=1, open=True) as pool:
        yield OAIServer(pool, BASE_URL, "admin@example.org", page_size=2)


@functools.cache
def _oai_schema() -> etree.XMLSchema:
    class LocalSchemas(etree.Resolver):
        def resolve(self, url, public_id, context):
            return self.resolve_filename(str(SCHEMAS / url.rsplit("/", 1)[-1]), context)

    parser = etree.XMLParser()
    parser.resolvers.add(LocalSchemas())
    return etree.XMLSchema(etree.parse(str(SCHEMAS / "oai-pmh-oai-dc.xsd"), parser))


def validate_oai(xml: bytes) -> None:
    """Validate an OAI-PMH response against the local XSDs."""
    _oai_schema().assertValid(etree.fromstring(xml))


@pytest.fixture(scope="session")
def oai_schema():
    return _oai_schema()


@pytest.fixture
def oai(server, oai_schema):
    """Send a request to the server, check that the response is valid OAI-PMH, and parse it."""
    client = Client(server)

    def request(method="GET", **params):
        if method == "GET":
            response = client.get("/oai", query_string=params)
        else:
            response = client.open("/oai", method=method, data=params)
        assert response.status_code == 200
        assert response.content_type == "text/xml; charset=utf-8"
        document = etree.fromstring(response.data)
        oai_schema.assertValid(document)
        return document

    return request


@pytest.fixture
def base_url(server):
    """Serve over HTTP for the client libraries. Returns the base URL."""
    http = make_server("localhost", 0, server, threaded=True)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    yield f"http://localhost:{http.server_port}/oai"
    http.shutdown()


EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


CRAWLER = f"{sys.executable} -m modama_crawler"


@pytest.fixture
def env(conn, monkeypatch):
    """The environment that points the crawler at the test database, for subprocesses and in-process calls."""
    info = conn.info
    values = {
        "MODAMA_CRAWLER_DB": info.dbname,
        "POSTGRES_ADMIN": info.user,
        "POSTGRES_PASSWORD": info.password or "",
        "POSTGRES_ADDRESS": info.host,
        "POSTGRES_PORT": str(info.port),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return {**os.environ, **values}


def shell(command_line: str, env: dict):
    return subprocess.run(
        command_line,
        shell=True,
        executable="/bin/bash",
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env=env,
    )


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "data"
    (root / "sub").mkdir(parents=True)
    for name in ("a.txt", "b.txt", "sub/c.txt"):
        (root / name).write_text(name)
    return root
