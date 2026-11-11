import os
import re
from datetime import UTC, datetime, timedelta

import pytest
from conftest import DC, OAI
from modama_crawler import selection
from modama_crawler.formats import Dataset, Extracted, Extraction, Result
from modama_crawler.formats.collapse.tests import generate as collapse_fixtures
from modama_crawler.formats.empad import cheat
from modama_crawler.formats.zarr.tests import generate as zarr_fixtures
from modama_crawler.records import MAX_LOCAL_ID, browse_url, build, oai_identifier
from modama_crawler.store import store
from modama_crawler.walk import walk

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


def test_dublin_core_mapping():
    dataset = Dataset(
        anchor="/x.txt",
        members=("/x.txt",),
        type="text/plain",
        mtime=0.0,
        uid=os.getuid(),
    )
    identifier, metadata = build(dataset)
    assert identifier == oai_identifier("/x.txt")
    assert metadata["title"] == ["/x.txt"]
    assert metadata["format"] == ["text/plain"]
    assert metadata["type"] == ["Dataset"]
    assert metadata["date"] == ["1970-01-01T00:00:00Z"]
    assert metadata["identifier"] == [browse_url("/x.txt")]
    assert "relation" not in metadata


def extracted(summary, subjects) -> Extraction:
    return Extraction("em/dm", "1", "", Extracted(summary, subjects, {}))


def test_a_file_without_an_extractor():
    dataset = Dataset(
        anchor="/notes/todo.txt",
        members=("/notes/todo.txt",),
        type="text/plain",
        size=1234,
        uid=os.getuid(),
    )
    metadata = build(dataset)[1]
    assert metadata["description"] == ["Plain text document, 1 file, 1.2 kB, in notes/"]
    assert "subject" not in metadata


def test_a_file_with_extracted_metadata():
    dataset = Dataset(
        anchor="/tem/scan.dm4",
        members=("/tem/scan.dm4",),
        type="application/octet-stream",
        format="em/dm",
        size=5_000_000,
        uid=os.getuid(),
        extraction=extracted(
            ["acceleration voltage 300 kV", "magnification 50,000"], []
        ),
    )
    (text,) = build(dataset)[1]["description"]
    assert text == (
        "acceleration voltage 300 kV, magnification 50,000; "
        "Unknown, 1 file, 5.0 MB, in tem/"
    )


def test_subjects_of_an_extracted_record():
    dataset = Dataset(
        anchor="/tem/scan.dm4",
        members=("/tem/scan.dm4",),
        type="application/octet-stream",
        format="em/dm",
        uid=os.getuid(),
        extraction=extracted(["voltage 300 kV"], ["Titan", "TEM", "dm"]),
    )
    # One per term, the format's name first, no duplicates
    assert build(dataset)[1]["subject"] == ["dm", "Titan", "TEM"]


def test_a_failed_extraction_gives_no_subjects():
    dataset = Dataset(
        anchor="/broken.dm4",
        members=("/broken.dm4",),
        type="application/octet-stream",
        format="em/dm",
        uid=os.getuid(),
        extraction=Extraction("em/dm", "1", "", None, "ValueError('truncated')"),
    )
    metadata = build(dataset)[1]
    assert "subject" not in metadata
    assert metadata["description"][0].endswith("1 file, 0 B, in /")


def test_collection_relations():
    parent = Dataset(
        anchor="/series", parts=("/series/a", "/series/b"), type="x/series"
    )
    part = Dataset(
        anchor="/series/a", members=("/series/a",), type="text/plain", parent="/series"
    )
    assert build(parent)[1]["relation"] == [
        browse_url("/series/a"),
        browse_url("/series/b"),
    ]
    assert build(part)[1]["relation"] == [browse_url("/series")]


def test_store_keeps_datestamps_and_drops_deleted(conn):
    a = Dataset(
        anchor="/a.txt",
        members=("/a.txt",),
        type="text/plain",
        mtime=1e9,
        uid=os.getuid(),
    )
    b = Dataset(
        anchor="/b.txt",
        members=("/b.txt",),
        type="text/plain",
        mtime=1e9,
        uid=os.getuid(),
    )
    assert store(conn, Result([a, b])) == 2
    # Every record changed by one call carries the same datestamp, taken just
    # before the write, so a harvester's window is the upsert plus commit
    assert len({d for (d,) in conn.execute("SELECT datestamp FROM records")}) == 1
    conn.execute("UPDATE records SET datestamp = '2000-01-01T00:00:00Z'")
    conn.commit()

    # Unchanged content keeps its datestamp
    assert store(conn, Result([a, b])) == 0
    assert {d for (d,) in conn.execute("SELECT datestamp FROM records")} == {
        datetime(2000, 1, 1, tzinfo=UTC)
    }

    # A deleted dataset leaves; a changed one gets the current time
    assert (
        store(
            conn,
            Result(
                [
                    Dataset(
                        anchor="/a.txt",
                        members=("/a.txt",),
                        type="text/csv",
                        mtime=1e9,
                        uid=os.getuid(),
                    )
                ]
            ),
        )
        == 2
    )
    rows = conn.execute("SELECT identifier, datestamp FROM records").fetchall()
    assert [identifier for identifier, _ in rows] == [oai_identifier("/a.txt")]
    assert datetime.now(UTC) - rows[0][1] < timedelta(minutes=1)
    assert conn.execute("SELECT count(*) FROM datasets").fetchone() == (1,)


def harvest_identifiers(oai) -> list[str]:
    """Every identifier the server lists, following resumption tokens."""
    found = []
    doc = oai(verb="ListIdentifiers", metadataPrefix="oai_dc")
    while True:
        found += [e.text for e in doc.iter(f"{OAI}identifier")]
        token = doc.find(f".//{OAI}resumptionToken")
        if token is None or not token.text:
            return found
        doc = oai(verb="ListIdentifiers", resumptionToken=token.text)


def test_recognised_tree_reaches_the_harvester(conn, oai, tmp_path):
    # The whole path once: real formats on a tree, stored, served, re-crawled
    cheat.pair(tmp_path / "scan")
    zarr_fixtures.array(tmp_path / "store")
    collapse_fixtures.venv(tmp_path / "env")
    zarr_fixtures.corrupt(tmp_path / "broken")
    formats = selection.enabled_formats(
        selection.discover().values(), selection.Config()
    )
    result = walk(tmp_path, formats)
    assert store(conn, result) == len(result.datasets)
    expected = {oai_identifier(d.anchor) for d in result.datasets}
    assert set(harvest_identifiers(oai)) == expected
    record = oai(
        verb="GetRecord",
        identifier=oai_identifier("/scan/SCA2_rings.xml"),
        metadataPrefix="oai_dc",
    )
    assert record.find(f".//{DC}format").text == "application/x.empad+xml"
    before = dict(conn.execute("SELECT identifier, datestamp FROM records"))

    # The header disappears: its record goes, the raw file becomes a record of
    # its own, everything else keeps its datestamp
    (tmp_path / "scan" / "SCA2_rings.xml").unlink()
    store(conn, walk(tmp_path, formats))
    after = dict(conn.execute("SELECT identifier, datestamp FROM records"))
    assert oai_identifier("/scan/SCA2_rings.xml") not in after
    assert oai_identifier("/scan/series_x4.raw") in after
    unchanged = set(before) & set(after)
    assert unchanged and all(before[i] == after[i] for i in unchanged)
