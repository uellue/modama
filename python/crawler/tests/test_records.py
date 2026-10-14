import os
import re
from datetime import UTC, datetime, timedelta

import pytest
from modama_crawler.records import (
    MAX_LOCAL_ID,
    browse_url,
    oai_identifier,
    publish_records,
)

PREFIX = "oai:er-c-data-mgmt.fz-juelich.de:"


def test_browse_url_example():
    # From the production deployment
    assert (
        browse_url("/adhoc/livecalibration/generate.ipynb")
        == "https://er-c-data-mgmt.fz-juelich.de/browse/?path=/adhoc/livecalibration/generate.ipynb"
    )


def test_browse_url_quotes_like_mgmtinterface():
    assert browse_url("/a b+c#d:e%ä").endswith("?path=/a+b%2Bc%23d:e%25%C3%A4")


def test_oai_identifier_example():
    path = "/adhoc/livecalibration/generate.ipynb"
    assert oai_identifier(path) == PREFIX + path


def test_oai_identifier_escapes_colon():
    # The EOSC harvester keeps only the part after the last ":"
    assert oai_identifier("/12:30 run.tif") == PREFIX + "/12%3A30+run.tif"


@pytest.mark.parametrize("length", [1, 254])
def test_oai_identifier_not_shortened(length):
    path = "/" + "x" * (length - 1)
    assert oai_identifier(path) == PREFIX + path


@pytest.mark.parametrize("length", [255, 256, 1000])
def test_oai_identifier_shortened(length):
    path = "/" + "x" * (length - 1)
    local = oai_identifier(path).removeprefix(PREFIX)
    assert len(local) == MAX_LOCAL_ID
    assert re.fullmatch(r"/x+~[0-9a-f]{32}", local)


@pytest.mark.parametrize("offset", [0, 1, 2])
def test_oai_identifier_keeps_escapes_whole(offset):
    """The cut lands at each position of an escape: "ä" is quoted as "%C3%A4"."""
    path = "/" + "x" * (219 + offset) + "ä" * 20
    local = oai_identifier(path).removeprefix(PREFIX)
    assert len(local) == MAX_LOCAL_ID
    assert re.fullmatch(r"(?:[^%~]|%[0-9A-F]{2})+~[0-9a-f]{32,34}", local)


def test_shortened_identifiers_differ():
    path = "/" + "x" * 300
    assert oai_identifier(path + "1") != oai_identifier(path + "2")


def test_publish_records(conn, tmp_path):
    ((path_id,),) = conn.execute(
        "INSERT INTO files (path, mtime, uid, mime) VALUES (%s, 0, %s, 'text/plain') "
        "RETURNING path_id",
        (str(tmp_path / "x.txt"), os.getuid()),
    )
    conn.execute("INSERT INTO datasets (path_id) VALUES (%s)", (path_id,))
    conn.commit()

    assert publish_records(conn, tmp_path) == 1
    ((identifier, metadata),) = conn.execute("SELECT identifier, metadata FROM records")
    assert identifier == oai_identifier("/x.txt")
    assert metadata["format"] == ["text/plain"]

    # Unchanged metadata keeps its datestamp
    conn.execute("UPDATE records SET datestamp = '2000-01-01T00:00:00Z'")
    conn.commit()
    assert publish_records(conn, tmp_path) == 0
    ((datestamp,),) = conn.execute("SELECT datestamp FROM records")
    assert datestamp == datetime(2000, 1, 1, tzinfo=UTC)

    # Changed metadata gets the current time
    conn.execute("UPDATE files SET mtime = 1e9")
    conn.commit()
    assert publish_records(conn, tmp_path) == 1
    ((datestamp,),) = conn.execute("SELECT datestamp FROM records")
    assert datetime.now(UTC) - datestamp < timedelta(minutes=1)
