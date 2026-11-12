"""Recognition (spec formats/structured, "Structured files are datasets of their type", "A name that lies falls back to the content's type")."""

import pytest
from modama_crawler import mime, mimedb
from modama_crawler.testing import recognise
from modama_crawler.walk import walk

from modama_formats_common.structured import COLLECTION

TYPES = {
    "conda_index": {"/index.json": ("common/json", "application/json")},
    "json_schema": {
        "/settings.schema.json": ("common/jsonschema", "application/schema+json")
    },
    "yaml_config": {
        "/config.yaml": ("common/yaml", "application/yaml"),
        "/stream.yml": ("common/yaml", "application/yaml"),
    },
    "toml_example": {"/example.toml": ("common/toml", "application/toml")},
    "csv_tables": {
        "/numbers.csv": ("common/csv", "text/csv"),
        "/temperature.csv": ("common/csv", "text/csv"),
    },
    "qe_pbtio3": {"/PbTiO3_scf.xml": ("common/xml", "application/xml")},
    "ini_setup": {"/setup.ini": ("common/ini", "text/x-ini")},
    "setup_cfg": {
        "/empty.cfg": ("common/cfg", "text/x-config"),
        "/setup.cfg": ("common/cfg", "text/x-config"),
    },
}


def by_anchor(collection_tests, fixture, tmp_path):
    return {
        d.anchor: d for d in recognise(collection_tests, fixture, tmp_path).datasets
    }


def test_each_type_is_its_formats_dataset(collection_tests, tmp_path):
    for fixture, expected in TYPES.items():
        found = by_anchor(collection_tests, fixture, tmp_path / fixture)
        assert {a: (d.format, d.type) for a, d in found.items()} == expected, fixture


def test_a_web_page_named_json(collection_tests, tmp_path):
    result = recognise(collection_tests, "not_of_their_name", tmp_path)
    page = next(d for d in result.datasets if d.anchor == "/page.json")
    # The core's *.json globs of application/json and application/schema+json
    # tie, so the type does not come from the name alone and is kept, with a
    # warning (Directory.not_of_type); the file is not claimed
    assert (page.format, page.type) == ("", "application/json")
    assert (
        "/page.json",
        (
            "common/json: page.json is not application/json (no JSON value first), "
            "but that type does not come from its name alone; type kept"
        ),
    ) in result.warnings


def test_an_empty_json(collection_tests, tmp_path):
    result = recognise(collection_tests, "not_of_their_name", tmp_path)
    empty = next(d for d in result.datasets if d.anchor == "/empty.json")
    assert (empty.format, empty.type) == ("", "application/json")
    assert any(
        rel == "/empty.json" and "no JSON value first" in text
        for rel, text in result.warnings
    )


def test_text_named_xml(collection_tests, mime_database, tmp_path):
    # As deployed, modama-formats-em installed: EMPAD's *.xml glob ties with
    # application/xml's, so the type is kept with a warning (BACKLOG, "A name type
    # that a glob tie resolves to cannot be dropped")
    if "em" not in mime_database:
        pytest.fail("modama-formats-em is not installed: it is in every deployment")
    own = mime.database
    try:
        mimedb.build(mime_database.values(), tmp_path / "mime-all")
        tree = collection_tests.materialise("not_of_their_name", tmp_path)
        result = walk(tree, COLLECTION.formats)
    finally:
        mimedb.activate(own)
    notes = next(d for d in result.datasets if d.anchor == "/notes.xml")
    assert (notes.format, notes.type) == ("", "application/xml")
    assert (
        "/notes.xml",
        (
            "common/xml: notes.xml is not application/xml (no < first), "
            "but that type does not come from its name alone; type kept"
        ),
    ) in result.warnings
    # Without EMPAD's glob the core drops the type: the content's type
    own_only = by_anchor(collection_tests, "not_of_their_name", tmp_path / "own")
    assert own_only["/notes.xml"].type == "text/plain"
    assert "common/xml: not application/xml, no < first" in own_only["/notes.xml"].basis


def test_a_cfg_that_is_not_ini(collection_tests, tmp_path):
    found = by_anchor(collection_tests, "not_of_their_name", tmp_path)
    for name, fmt, named in (
        ("turtle.cfg", "common/cfg", "text/x-config"),
        ("keys.ini", "common/ini", "text/x-ini"),
    ):
        d = found[f"/{name}"]
        assert (d.format, d.type) == ("", "text/plain")
        assert f"{fmt}: not {named}, no [section] first" in d.basis


def test_formats_that_drop_types_run_before_text(mime_database):
    """A file these formats give text/plain is claimed by a format of text/plain
    only if that runs after them (recognition-checks-content D3): every installed
    format that reacts to text/plain has a lower priority. Holds trivially until
    the text area is merged."""
    ours = [f for f in COLLECTION.formats if f.head]
    text = [
        f
        for c in mime_database.values()
        for f in c.formats
        if "text/plain" in f.reacts_to
    ]
    for theirs in text:
        for mine in ours:
            assert mine.priority > theirs.priority, (mine.id, theirs.id)


def test_an_empty_cfg(collection_tests, tmp_path):
    empty = by_anchor(collection_tests, "setup_cfg", tmp_path)["/empty.cfg"]
    assert (empty.format, empty.type) == ("common/cfg", "text/x-config")
