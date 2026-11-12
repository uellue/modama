"""Extraction (spec formats/structured), one test per scenario, named after it."""

import json
import logging
import os
import time

import pytest
import yaml

from modama_formats_common.structured import LIMIT
from modama_formats_common.structured.entries import MAX_ENTRIES

from .helpers import described, described_tree, one

# Every entry of a JSON, YAML or TOML document is kept


def test_a_json_object_as_conda_writes_it(collection_tests, tmp_path):
    index = described(collection_tests, "conda_index", tmp_path)["/index.json"]
    assert index.original["name"] == "numpy"
    assert index.original["version"] == "1.26.4"
    assert index.original["build_number"] == 0
    assert index.original["depends"][0] == "libblas >=3.9.0,<4.0a0"
    assert len(index.original["depends"]) == 4
    assert index.mapped == {"documents": 1}


def test_lists_of_objects_are_numbered_from_1(collection_tests, tmp_path):
    d = one(
        collection_tests,
        tmp_path,
        "runs.json",
        '{"runs": [{"id": 1}, {"id": 2, "tags": []}], "shape": [4, 4]}',
    )
    assert d.original == {
        "runs[1].id": 1,
        "runs[2].id": 2,
        "runs[2].tags": [],
        "shape": [4, 4],
    }


def test_an_entry_nobody_has_seen_before(collection_tests, tmp_path):
    made_up = {"made_up_group": {"made_up_value": "42 zz", "made_up_empty": ""}}
    d = one(collection_tests, tmp_path, "made_up.json", json.dumps(made_up))
    assert d.original == {
        "made_up_group.made_up_value": "42 zz",
        "made_up_group.made_up_empty": "",
    }


def test_empty_values_are_kept(collection_tests, tmp_path):
    d = one(
        collection_tests,
        tmp_path,
        "empty.json",
        '{"a": {}, "b": [], "c": "", "d": null}',
    )
    assert d.original == {"a": {}, "b": [], "c": "", "d": None}


def test_a_path_met_twice(collection_tests, tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        d = one(collection_tests, tmp_path, "twice.json", '{"a": {"b": 1}, "a.b": 2}')
    assert d.original == {"a.b": 1, "a.b#2": 2}
    assert "a.b twice, the second kept as a.b#2" in caplog.text


def test_a_plain_value_as_the_document(collection_tests, tmp_path):
    d = one(collection_tests, tmp_path, "list.json", "[1, 2, 3]")
    assert d.original == {"$": [1, 2, 3]}


# Several documents in one file are numbered


def test_a_yaml_stream(collection_tests, tmp_path):
    stream = described(collection_tests, "yaml_config", tmp_path)["/stream.yml"]
    assert stream.original["[1].kind"] == "run"
    assert stream.original["[3].kind"] == "end"
    assert stream.mapped == {"documents": 3}


def test_json_lines_named_json(collection_tests, tmp_path):
    log = described(collection_tests, "json_lines", tmp_path)["/log.json"]
    assert log.dataset.format == "common/json"
    assert log.original["[1].event"] == "start"
    assert log.original["[5].event"] == "stop"
    assert log.mapped == {"documents": 5}


# Values as the file writes them


@pytest.fixture
def zone():
    """Sets the local time zone for the test, and back."""
    before = os.environ.get("TZ")

    def set_zone(name):
        os.environ["TZ"] = name
        time.tzset()

    yield set_zone
    if before is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = before
    time.tzset()


def test_a_toml_date_time_with_an_offset(collection_tests, tmp_path, zone):
    found = []
    for name in ("UTC", "Europe/Berlin"):
        zone(name)
        toml = described(collection_tests, "toml_example", tmp_path / name)
        found.append(toml["/example.toml"].original["owner.dob"])
    assert found == ["1979-05-27T07:32:00-08:00"] * 2


def test_a_yaml_timestamp(collection_tests, tmp_path):
    config = described(collection_tests, "yaml_config", tmp_path)["/config.yaml"]
    # As PyYAML's safe_dump wrote it, not parsed
    assert config.original["started"] == "2026-11-12 21:04:05.500000+01:00"
    d = one(
        collection_tests, tmp_path, "t.yaml", "started: 2026-11-12 21:04:05.5 +01:00\n"
    )
    assert d.original == {"started": "2026-11-12 21:04:05.5 +01:00"}


def test_yaml_keys_as_written(collection_tests, tmp_path):
    # YAML 1.1 reads these keys as True, None and 1.0 (GitHub Actions' on:)
    d = one(
        collection_tests,
        tmp_path,
        "keys.yaml",
        "on:\n  push: {}\nyes: 1\nnull: 2\n~: 3\n1.0: f\n2026-11-12: d\n",
    )
    assert d.original == {
        "on.push": {},
        "yes": 1,
        "null": 2,
        "~": 3,
        "1.0": "f",
        "2026-11-12": "d",
    }


def test_a_yaml_tag_of_an_application(collection_tests, tmp_path):
    # As in deploy/docker-compose.override.yml: Compose's own tags, which
    # PyYAML's safe loader refuses (ConstructorError)
    compose = (
        "services:\n"
        "  web:\n"
        "    ports: !override\n"
        '      - "8080:80"\n'
        "    command: !reset null\n"
        "    labels: !override {a: b}\n"
        "    image: !custom nginx\n"
    )
    d = one(collection_tests, tmp_path, "compose.yml", compose)
    assert d.original == {
        "services.web.ports": ["8080:80"],
        "services.web.command": "null",
        "services.web.labels.a": "b",
        "services.web.image": "nginx",
    }


def test_not_a_number(collection_tests, tmp_path):
    d = one(collection_tests, tmp_path, "nan.json", '{"a": NaN, "b": 1e999}')
    assert d.original == {"a": "NaN", "b": "1e999"}
    y = one(collection_tests, tmp_path / "y", "inf.yaml", "a: .inf\nb: .NaN\n")
    assert y.original == {"a": ".inf", "b": ".NaN"}


def test_json_numbers_as_written(collection_tests, tmp_path):
    d = one(
        collection_tests,
        tmp_path,
        "n.json",
        '{"a": 1.0E-3, "b": 0.00001, "c": 1.5, "d": 1.0, "e": 12, "f": -0}',
    )
    # A number where it prints as written, else its text
    assert d.original == {
        "a": "1.0E-3",
        "b": "0.00001",
        "c": 1.5,
        "d": 1.0,
        "e": 12,
        "f": 0,
    }
    toml = one(collection_tests, tmp_path / "t", "n.toml", "a = 1.0E-3\nb = 2.5\n")
    assert toml.original == {"a": "1.0E-3", "b": 2.5}


def test_yaml_values_as_written(collection_tests, tmp_path):
    # YAML 1.1 reads these as 630, 1.1, 10, False, 31, 1e-05 and None
    d = one(
        collection_tests,
        tmp_path,
        "v.yaml",
        "time: 10:30\nversion: 1.10\ncode: 012\ncountry: NO\nmask: 0x1F\n"
        "small: 0.00001\ntilde: ~\nempty:\n"
        "n: 12\nx: 1.5\nok: true\nnothing: null\nquoted: '012'\n",
    )
    assert d.original == {
        "time": "10:30",
        "version": "1.10",
        "code": "012",
        "country": "NO",
        "mask": "0x1F",
        "small": "0.00001",
        "tilde": "~",
        "empty": "",
        "n": 12,
        "x": 1.5,
        "ok": True,
        "nothing": None,
        "quoted": "012",
    }


# Every element and attribute of an XML document is kept


def test_a_namespaced_document(collection_tests, tmp_path):
    qe = described(collection_tests, "qe_pbtio3", tmp_path)["/PbTiO3_scf.xml"]
    qes = "http://www.quantum-espresso.org/ns/qes/qes-1.0"
    assert qe.original["@xmlns:qes"] == qes
    assert qe.original["input.control_variables.title"] == "PBTiO3_scf"
    assert qe.original["input.atomic_species.@ntyp"] == "3"
    assert qe.original["input.atomic_species.species[2].@name"] == "Ti"
    assert qe.mapped == {"root": "qes:espresso", "namespace": qes}


def test_a_default_namespace_and_a_prefixed_attribute(collection_tests, tmp_path):
    d = one(
        collection_tests,
        tmp_path,
        "image.xml",
        '<MicroscopeImage xmlns="urn:a" xmlns:i="urn:i"><x i:type="b">1</x></MicroscopeImage>',
    )
    assert d.original == {
        "@xmlns": "urn:a",
        "@xmlns:i": "urn:i",
        "x.@i:type": "b",
        "x": "1",
    }
    assert d.mapped == {"root": "MicroscopeImage", "namespace": "urn:a"}


def test_an_xml_element_nobody_has_seen_before(collection_tests, tmp_path):
    d = one(
        collection_tests,
        tmp_path,
        "made_up.xml",
        '<?xml version="1.0"?><root><made_up_group made_up_attribute="a">'
        "<made_up_value>42 zz</made_up_value><made_up_empty/></made_up_group></root>",
    )
    assert d.original == {
        "made_up_group.@made_up_attribute": "a",
        "made_up_group.made_up_value": "42 zz",
        "made_up_group.made_up_empty": "",
    }


# A CSV file is described by its header, never its data


def test_a_semicolon_separated_file_with_a_header(collection_tests, tmp_path):
    t = described(collection_tests, "csv_tables", tmp_path)["/temperature.csv"]
    assert t.original == {
        "column[1]": "Zeit",
        "column[2]": "Temperatur (°C)",
        "column[3]": "Strom (A)",
    }
    assert t.mapped == {
        "encoding": "latin-1",
        "delimiter": ";",
        "header": True,
        "columns": 3,
        "rows": 20,
    }
    # No value of a data row (12:00:00;20.0;0.0e+00 …)
    assert "12:0" not in t.description and "20.0" not in t.description


def test_numbers_without_a_header(collection_tests, tmp_path):
    n = described(collection_tests, "csv_tables", tmp_path)["/numbers.csv"]
    assert n.original == {}
    assert n.mapped == {
        "encoding": "utf-8",
        "delimiter": ",",
        "header": False,
        "columns": 4,
        "rows": 50,
    }


def test_a_csv_file_larger_than_the_bound(collection_tests, tmp_path):
    row = "1.0,2.0,3.0\n"
    rows = LIMIT // len(row) + 1000
    d = one(collection_tests, tmp_path, "big.csv", "a,b,c\n" + row * rows)
    assert d.mapped["header"] is True
    assert "rows" not in d.mapped
    assert 0 < d.mapped["rows_at_least"] < rows
    # rchar counts reading /proc/self/io too: a few hundred bytes
    assert d.bytes_read <= LIMIT + 1 + 1024


# Every key of an INI or .cfg file is kept


def test_sections_and_keys_as_found(collection_tests, tmp_path):
    ini = described(collection_tests, "ini_setup", tmp_path)["/setup.ini"]
    assert ini.original == {
        "DEFAULT.Operator": "ER-C",
        "Laser.Wavelength_nm": "532",
        "Laser.Comment": "%(not interpolated)s",
        "Stage.Axes": "X Y Z",
        "Stage.Limits": "-1.5\n1.5",
        "Spare": {},
    }
    assert ini.mapped == {"encoding": "utf-8"}


# Bounded reading


def test_a_json_file_over_the_bound(collection_tests, tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    with open(tree / "big.json", "wb") as f:
        f.write(b"[0")
        f.truncate(9 << 20)  # sparse: nothing is written but the start
    d = described_tree(collection_tests, tree.resolve())["/big.json"]
    assert d.extracted.values == {
        "mapped_metadata": {"not_read_larger_than_bytes": 8388608}
    }
    assert d.extracted.summary == []
    assert d.bytes_read < 1024  # rchar counts reading /proc/self/io too


def test_more_entries_than_the_bound(collection_tests, tmp_path):
    items = [{"i": i} for i in range(1500)]
    d = one(collection_tests, tmp_path, "many.json", json.dumps({"items": items}))
    assert len(d.original) == MAX_ENTRIES
    assert list(d.original)[-1] == "items[1000].i"
    assert d.mapped == {"documents": 1, "cut_at_entries": 1000}


def test_a_yaml_alias_bomb(collection_tests, tmp_path):
    for leaf, kept in (("x", 1000), ("x" * 1001, 0)):
        # 10 values, then 8 levels of 10 references each: 10^9 values; with
        # leaves not suitable for text, the walk's bound ends it with none kept
        lines = [f"a: &a [{', '.join([repr(leaf)] * 10)}]"]
        for i in range(1, 9):
            prev, name = chr(ord("a") + i - 1), chr(ord("a") + i)
            lines.append(f"{name}: &{name} [{', '.join([f'*{prev}'] * 10)}]")
        start = time.monotonic()
        d = one(collection_tests, tmp_path / str(kept), "bomb.yaml", "\n".join(lines))
        assert time.monotonic() - start < 1.0
        assert d.mapped["cut_at_entries"] == kept


def test_a_yaml_merge_key_bomb(collection_tests, tmp_path):
    # 10 pairs, then levels merging 10 copies of the level before: 10^9 pairs at
    # level 9, which the safe loader would flatten (the review's merge_bomb)
    lines = ["l0: &l0 {" + ", ".join(f"k{i}: {i}" for i in range(10)) + "}"]
    for n in range(1, 10):
        lines.append(f"l{n}: &l{n} {{<<: [" + ", ".join([f"*l{n - 1}"] * 10) + "]}")
    fmt = next(f for f in collection_tests.collection.formats if f.id == "common/yaml")
    start = time.monotonic()
    with pytest.raises(yaml.constructor.ConstructorError, match="merge keys give"):
        fmt.describe("\n".join(lines).encode(), "/bomb.yaml")
    assert time.monotonic() - start < 1.0
    # A merge as YAML files use it stays
    d = one(collection_tests, tmp_path, "m.yaml", "b: &b {x: 1}\nd: {<<: *b, y: 2}\n")
    assert d.original == {"b.x": 1, "d.x": 1, "d.y": 2}


# The summary line


def test_the_summary_line_of_a_json_document(collection_tests, tmp_path):
    index = described(collection_tests, "conda_index", tmp_path)["/index.json"]
    assert index.description.startswith(
        "x86_64, py312h0d1d6f8_0, build_number 0, BSD-3-Clause, numpy, linux, "
        "linux-64, timestamp 1707225498123; "
    )


def test_the_summary_line_of_an_xml_document(collection_tests, tmp_path):
    qe = described(collection_tests, "qe_pbtio3", tmp_path)["/PbTiO3_scf.xml"]
    assert qe.description.startswith(
        "qes:espresso, PBTiO3_scf, scf, from_scratch, pwscf, "
        "/scratch/pdelugas/espresso-xsd/pseudo/, /scratch/pdelugas/espresso-xsd/tempdir/, "
        "stress false, forces false; "
    )


def test_the_summary_line_of_a_csv_file(collection_tests, tmp_path):
    t = described(collection_tests, "csv_tables", tmp_path)["/temperature.csv"]
    assert t.description.startswith("Zeit, Temperatur (°C), Strom (A); ")


# What is left out


def test_a_value_whose_name_says_it_is_secret(collection_tests, tmp_path):
    document = {
        "db": {"user": "u", "Password": "p", "db_passwd": "p"},
        "api_token": "t",
        "client_secret": "s",
        "apiKey": "k",
        "private-key": "k",
        "credentials": {"id": "c"},
    }
    d = one(collection_tests, tmp_path, "config.json", json.dumps(document))
    # credentials.id too: any part of the path counts
    assert d.original == {"db.user": "u"}
    assert d.mapped["credentials_left_out"] == 7
    ini = one(
        collection_tests, tmp_path / "ini", "a.ini", "[db]\npassword = p\nhost = h\n"
    )
    assert ini.original == {"db.host": "h"}
    assert ini.mapped["credentials_left_out"] == 1


def test_a_credential_in_a_value(collection_tests, tmp_path):
    # The review's cases (values.credential, python/crawler/tests/test_values.py)
    compose = (
        b"services:\n  db:\n    environment:\n      - POSTGRES_PASSWORD=hunter2\n"
        b"      - POSTGRES_USER=u\n    command: --requirepass hunter2\n"
        b"    image: redis\n"
        b"  web:\n    url: postgres://admin:hunter2@db/x\n    auth: Basic aHVudGVyMg==\n"
    )
    d = one(collection_tests, tmp_path, "compose.yml", compose)
    assert d.original == {"services.db.image": "redis"}
    assert d.mapped["credentials_left_out"] == 4
    assert "hunter2" not in d.description


def test_a_long_text_and_a_long_list(collection_tests, tmp_path):
    document = {"long": "x" * 1001, "many": list(range(17)), "kept": 1}
    d = one(collection_tests, tmp_path, "long.json", json.dumps(document))
    assert d.original == {"kept": 1}
