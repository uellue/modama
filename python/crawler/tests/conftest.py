import os
import threading
from importlib import reload
from pathlib import Path

import modama_crawler.recognition
import pytest
import xdg
from lxml import etree
from modama_crawler.database import ensure_dataset_tables
from modama_crawler.records import dc_metadata, oai_identifier
from modama_crawler.server import OAIServer
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

# MIME type for the self test of the handler installation
CANARY_MIME = xdg.Mime.MIMEtype("application", "x.modamatestfile")


class Canary(modama_crawler.recognition.FileHandler):
    file_types = (CANARY_MIME,)

    @staticmethod
    def xdg_mimeinfo():
        return """
<mime-type type="application/x.modamatestfile">
  <comment>Canary file type to test database installation effect</comment>
  <glob pattern="*.modamatestfile"/>
</mime-type>
"""


@pytest.fixture(scope="session", autouse=True)
def install_handlers(tmp_path_factory):
    """Install the handlers' MIME info into a temporary XDG directory, not the user's."""
    os.environ["XDG_DATA_HOME"] = str(tmp_path_factory.mktemp("localshare"))
    reload(xdg.BaseDirectory)
    modama_crawler.recognition.FileHandler.install_mime_info()
    assert xdg.Mime.get_type_by_name("/home/whatever.modamatestfile") == CANARY_MIME


@pytest.fixture
def conn(postgresql):
    ensure_dataset_tables(postgresql)
    return postgresql


@pytest.fixture
def add_record(conn):
    """Insert a record with the given datestamp, bypassing the crawl. Returns its identifier."""

    def add(path: str, datestamp: str) -> str:
        ((path_id,),) = conn.execute(
            "INSERT INTO files (path, mtime, uid) VALUES (%s, 0, %s) RETURNING path_id",
            (path, os.getuid()),
        )
        ((dataset_id,),) = conn.execute(
            "INSERT INTO datasets (path_id) VALUES (%s) RETURNING dataset_id",
            (path_id,),
        )
        identifier = oai_identifier(path)
        metadata = dc_metadata(path, 0.0, os.getuid(), ["text/plain"])
        conn.execute(
            "INSERT INTO records VALUES (%s, %s, %s, %s)",
            (dataset_id, identifier, datestamp, Jsonb(metadata)),
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


@pytest.fixture(scope="session")
def oai_schema():
    class LocalSchemas(etree.Resolver):
        def resolve(self, url, public_id, context):
            return self.resolve_filename(str(SCHEMAS / url.rsplit("/", 1)[-1]), context)

    parser = etree.XMLParser()
    parser.resolvers.add(LocalSchemas())
    return etree.XMLSchema(etree.parse(str(SCHEMAS / "oai-pmh-oai-dc.xsd"), parser))


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
