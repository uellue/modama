import json
import os
import pwd
import re
import shutil
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import modama_formats_em
import pytest
from conftest import CRAWLER, DC, OAI, shell
from modama_crawler import selection
from modama_crawler.extraction import MAX_STRING
from modama_crawler.formats import Dataset, Extracted, Extraction, Format, Result
from modama_crawler.formats.collapse.tests import generate as collapse_fixtures
from modama_crawler.formats.zarr.tests import generate as zarr_fixtures
from modama_crawler.records import (
    MAX_LOCAL_ID,
    browse_url,
    build,
    creator,
    format_names,
    oai_identifier,
)
from modama_crawler.store import Stored, store
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
    identifier, metadata = build(dataset, {})
    assert identifier == oai_identifier("/x.txt")
    assert metadata["title"] == ["/x.txt"]
    assert metadata["format"] == ["text/plain"]
    assert metadata["type"] == ["Dataset"]
    assert metadata["date"] == ["1970-01-01T00:00:00Z"]
    assert metadata["identifier"] == [browse_url("/x.txt")]
    assert "relation" not in metadata


@pytest.fixture
def users(monkeypatch):
    """A user database of the test's own, {uid: (login name, GECOS)}, to fill."""
    passwd = {}

    def getpwuid(uid):
        login, gecos = passwd[uid]  # KeyError for an unknown uid, as pwd's
        return SimpleNamespace(pw_name=login, pw_gecos=gecos)

    monkeypatch.setattr(pwd, "getpwuid", getpwuid)
    creator.cache_clear()
    yield passwd
    creator.cache_clear()


def creator_of_a_file_of(uid: int) -> list[str]:
    dataset = Dataset(anchor="/x.txt", members=("/x.txt",), type="text/plain", uid=uid)
    return build(dataset, {})[1]["creator"]


# Records spec, "Dublin Core mapping" (decision 201), one test per scenario


def test_single_file(users):
    users[10001] = ("alice", "Alice Anderson")
    assert creator_of_a_file_of(10001) == ["Alice Anderson"]


@pytest.mark.parametrize("gecos", ["", ",,,", " ,room 1"])
def test_an_owner_without_a_full_name(users, gecos):
    users[1000] = ("dev", gecos)
    assert creator_of_a_file_of(1000) == ["dev"]


def test_a_full_name_with_a_comma(users):
    # the GECOS convention cuts it; the loss is accepted (design D10)
    users[20335] = ("weber", "Weber, Dieter")
    assert creator_of_a_file_of(20335) == ["Weber"]


def test_an_owner_without_a_name(users):
    assert creator_of_a_file_of(4242) == ["4242"]


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
    metadata = build(dataset, {})[1]
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
    (text,) = build(dataset, {})[1]["description"]
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
        extraction=extracted(
            ["voltage 300 kV"], ["Titan", "TEM", "Gatan Digital Micrograph"]
        ),
    )
    # One per term, the format's display name first, no duplicates
    names = {"em/dm": "Gatan Digital Micrograph"}
    assert build(dataset, names)[1]["subject"] == [
        "Gatan Digital Micrograph",
        "Titan",
        "TEM",
    ]
    # A format not among the enabled ones is named by its id
    assert build(dataset, {})[1]["subject"][0] == "em/dm"


def display_format(type: str, display_name: str = "") -> Format:
    fmt = Format()
    fmt.type, fmt.display_name, fmt.id = type, display_name, "t/f"
    return fmt


def test_a_format_s_display_name():
    # Its own, else its MIME type's comment, else its id
    assert format_names([display_format("text/plain", "Notes")]) == {"t/f": "Notes"}
    assert format_names([display_format("text/plain")]) == {
        "t/f": "Plain text document"
    }
    assert format_names([display_format("application/x.no-such-type")]) == {
        "t/f": "t/f"
    }


def test_a_failed_extraction_gives_no_subjects():
    dataset = Dataset(
        anchor="/broken.dm4",
        members=("/broken.dm4",),
        type="application/octet-stream",
        format="em/dm",
        uid=os.getuid(),
        extraction=Extraction("em/dm", "1", "", None, "ValueError('truncated')"),
    )
    metadata = build(dataset, {})[1]
    assert "subject" not in metadata
    assert metadata["description"][0].endswith("1 file, 0 B, in /")


# "The file's tags go into a second description" (change tags-in-the-record)


def tagged(original_metadata) -> Dataset:
    values = (
        {} if original_metadata is None else {"original_metadata": original_metadata}
    )
    return Dataset(
        anchor="/tem/scan.dm4",
        members=("/tem/scan.dm4",),
        type="application/octet-stream",
        format="em/dm",
        uid=os.getuid(),
        extraction=Extraction("em/dm", "1", "", Extracted(["300kV"], [], values)),
    )


def descriptions(dataset: Dataset) -> list[str]:
    return build(dataset, {})[1]["description"]


def test_a_dataset_with_tags_gets_a_second_description():
    dataset = tagged(
        {
            "Microscope Info.Voltage": 300000.0,
            "DataBar.Device Name": "K2-IS-0001",
            # No list of wanted tags: whatever the format kept is shown
            "Foo Vendor.New Setting": 7,
        }
    )
    summary, tags = descriptions(dataset)
    assert summary.startswith("300kV; ")
    assert tags == (
        "DataBar.Device Name: K2-IS-0001\n"
        "Foo Vendor.New Setting: 7\n"
        "Microscope Info.Voltage: 300000.0"
    )


@pytest.mark.parametrize("original_metadata", [None, {}, {"a": "", "b": []}])
def test_a_dataset_without_tags_gets_none(original_metadata):
    assert len(descriptions(tagged(original_metadata))) == 1
    # Nor one without an extraction
    assert len(descriptions(replace(tagged(None), extraction=None))) == 1


def test_empty_values_are_left_out():
    dataset = tagged(
        {
            "Session Info.Operator": [],
            "QuickSaved.fields.minitext": "",
            "Session Info.Specimen": "Au",
        }
    )
    assert descriptions(dataset)[1] == "Session Info.Specimen: Au"


def test_sorted_by_name():
    dataset = tagged({"b.y": 2, "B.z": 3, "a.x": 1, "a w": 0})
    assert descriptions(dataset)[1] == "B.z: 3\na w: 0\na.x: 1\nb.y: 2"


def test_values_as_stored():
    dataset = tagged(
        {
            "Acquisition.Device.Active Size (pixels)": [1920, 1792],
            "Microscope Info.Stage Position.Stage Alpha": -2.4043772802208405,
            "Acquisition.Parameters.High Level.Exposure Live Time": "inf",
            "Session Info.Specimen": "Au µm",
        }
    )
    assert descriptions(dataset)[1].splitlines() == [
        "Acquisition.Device.Active Size (pixels): [1920, 1792]",
        "Acquisition.Parameters.High Level.Exposure Live Time: inf",
        "Microscope Info.Stage Position.Stage Alpha: -2.4043772802208405",
        "Session Info.Specimen: Au µm",
    ]


def test_a_very_long_value_is_cut():
    values = list(range(2000))
    text = json.dumps(values)
    assert len(text) > MAX_STRING
    (line,) = descriptions(tagged({"Huge.Array": values}))[1].splitlines()
    assert line == "Huge.Array: " + text[:MAX_STRING] + "…"


def test_numbers_as_the_database_gives_them_back(conn):
    # JSONB keeps a number's digits, not its type: what a fresh extraction
    # gives and what the next crawl reads back make the same lines
    dataset = replace(
        tagged(
            {
                "DataBar.Acquisition Time (OS)": 1.316679648365784e17,
                "Huge": [1e20, -0.0, 1e-07, 300000.0, 7],
                "Stage Alpha": -0.0,
                "Group": {"Inner": 2.5e16},
            }
        ),
        stamp="s",
    )
    store(conn, Result([dataset]), {})
    stored = Stored(conn).extractions([dataset.anchor])[dataset.anchor]
    again = replace(dataset, extraction=stored)
    assert descriptions(again) == descriptions(dataset)
    assert descriptions(dataset)[1].splitlines() == [
        "DataBar.Acquisition Time (OS): 131667964836578400",
        'Group: {"Inner": 25000000000000000}',
        "Huge: [100000000000000000000, 0.0, 1e-07, 300000.0, 7]",
        "Stage Alpha: 0.0",
    ]


CAPTURE52 = Path(modama_formats_em.__file__).parent / "k2is/tests/fixtures/capture52"
FIRST_TAG = "Acquisition.Device.Active Size (pixels): [1920, 1792]"


def test_a_stored_extraction_gives_the_same_record(conn, env, oai, tmp_path):
    # Crawled as typed, twice: the first crawl builds the record from the
    # extraction it ran, the second from the stored one (JSONB, which keeps
    # no order of its own)
    shutil.copytree(CAPTURE52, tmp_path / "k2is")
    run = shell(f"{CRAWLER} crawl --root {tmp_path / 'k2is'}", env)
    assert run.returncode == 0, run.stderr
    conn.commit()
    conn.execute("UPDATE records SET datestamp = '2000-01-01T00:00:00Z'")
    conn.commit()
    run = shell(f"{CRAWLER} crawl --root {tmp_path / 'k2is'}", env)
    assert run.returncode == 0, run.stderr
    conn.commit()
    assert conn.execute("SELECT datestamp FROM records").fetchall() == [
        (datetime(2000, 1, 1, tzinfo=UTC),)
    ]
    # The served record: the summary, then the tags
    record = oai(
        verb="GetRecord",
        identifier=oai_identifier("/Capture52_.gtg"),
        metadataPrefix="oai_dc",
    )
    summary, tags = (e.text for e in record.iter(f"{DC}description"))
    assert summary.startswith("IMAGING, SCANNING, STEM NANOPROBE, 300kV")
    assert tags.splitlines()[0] == FIRST_TAG
    assert len(tags.splitlines()) == len(set(tags.splitlines())) > 200


def test_collection_relations():
    parent = Dataset(
        anchor="/series", parts=("/series/a", "/series/b"), type="x/series"
    )
    part = Dataset(
        anchor="/series/a", members=("/series/a",), type="text/plain", parent="/series"
    )
    assert build(parent, {})[1]["relation"] == [
        browse_url("/series/a"),
        browse_url("/series/b"),
    ]
    assert build(part, {})[1]["relation"] == [browse_url("/series")]


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
    assert store(conn, Result([a, b]), {}) == 2
    # Every record changed by one call carries the same datestamp, taken just
    # before the write, so a harvester's window is the upsert plus commit
    assert len({d for (d,) in conn.execute("SELECT datestamp FROM records")}) == 1
    conn.execute("UPDATE records SET datestamp = '2000-01-01T00:00:00Z'")
    conn.commit()

    # Unchanged content keeps its datestamp
    assert store(conn, Result([a, b]), {}) == 0
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
            {},
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
    zarr_fixtures.array(tmp_path / "store")
    collapse_fixtures.venv(tmp_path / "env")
    zarr_fixtures.corrupt(tmp_path / "broken")
    formats = selection.enabled_formats(
        selection.discover().values(), selection.Config()
    )
    result = walk(tmp_path, formats)
    assert store(conn, result, format_names(formats)) == len(result.datasets)
    expected = {oai_identifier(d.anchor) for d in result.datasets}
    assert set(harvest_identifiers(oai)) == expected
    record = oai(
        verb="GetRecord",
        identifier=oai_identifier("/store/a.zarr"),
        metadataPrefix="oai_dc",
    )
    assert record.find(f".//{DC}format").text == "application/x-zarr"
    before = dict(conn.execute("SELECT identifier, datestamp FROM records"))

    # The store's marker disappears: the store's record goes, the file left in
    # it becomes a record of its own, everything else keeps its datestamp
    (tmp_path / "broken" / "broken.zarr" / "zarr.json").unlink()
    store(conn, walk(tmp_path, formats), format_names(formats))
    after = dict(conn.execute("SELECT identifier, datestamp FROM records"))
    assert oai_identifier("/broken/broken.zarr") not in after
    assert oai_identifier("/broken/broken.zarr/c/0/0") in after
    unchanged = set(before) & set(after)
    assert unchanged and all(before[i] == after[i] for i in unchanged)
