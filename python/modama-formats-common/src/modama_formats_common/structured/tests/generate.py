"""Fixture generators: structured files written by the writers that write them in practice (json, PyYAML, csv, configparser)."""

import configparser
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml


def conda_index(target: Path) -> None:
    """A conda package's info/index.json, as conda-build writes it (json.dump, indent 2, keys sorted)."""
    target.mkdir(parents=True)
    index = {
        "arch": "x86_64",
        "build": "py312h0d1d6f8_0",
        "build_number": 0,
        "depends": [
            "libblas >=3.9.0,<4.0a0",
            "libgcc-ng >=12",
            "python >=3.12,<3.13.0a0",
            "python_abi 3.12.* *_cp312",
        ],
        "license": "BSD-3-Clause",
        "name": "numpy",
        "platform": "linux",
        "subdir": "linux-64",
        "timestamp": 1707225498123,
        "version": "1.26.4",
    }
    with open(target / "index.json", "w") as f:
        json.dump(index, f, indent=2, sort_keys=True)


def json_schema(target: Path) -> None:
    """A JSON schema, written by json.dump as conda's menuinst ships them (*.schema.json in the tree)."""
    target.mkdir(parents=True)
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Settings",
        "type": "object",
        "properties": {"exposure": {"type": "number", "minimum": 0}},
        "required": ["exposure"],
    }
    with open(target / "settings.schema.json", "w") as f:
        json.dump(schema, f)


def json_lines(target: Path) -> None:
    """A log of JSON Lines in a file named .json, one json.dumps per line."""
    target.mkdir(parents=True)
    events = ["start", "frame", "frame", "frame", "stop"]
    with open(target / "log.json", "w") as f:
        f.writelines(
            json.dumps({"t": 1731417319.33 + i, "event": event}) + "\n"
            for i, event in enumerate(events)
        )


def not_of_their_name(target: Path) -> None:
    """Files whose names give a type their content does not have."""
    target.mkdir(parents=True)
    (target / "page.json").write_text(
        "<!DOCTYPE html>\n<html><head><title>404 Not Found</title></head>"
        "<body>Not Found</body></html>\n"
    )
    (target / "empty.json").write_bytes(b"")
    (target / "notes.xml").write_text("Notes on the measurement, not XML.\n")
    # As Python's Lib/turtledemo/turtle.cfg: keys without a section
    (target / "turtle.cfg").write_text(
        "width = 800\nheight = 600\ncanvwidth = 1200\ncanvheight = 900\nshape = arrow\n"
    )
    (target / "keys.ini").write_text("; settings\nGain=4\nOffset=0\n")


def yaml_config(target: Path) -> None:
    """A configuration and a stream of three documents, written by PyYAML."""
    target.mkdir(parents=True)
    config = {
        "name": "in-situ heating",
        "started": datetime(
            2026, 11, 12, 21, 4, 5, 500000, tzinfo=timezone(timedelta(hours=1))
        ),
        "detector": {"model": "K2 IS", "binning": [2, 2], "exposure_s": 0.0025},
        "steps": [
            {"temperature_C": 300, "hold_min": 10},
            {"temperature_C": 500, "hold_min": 5},
        ],
        "notes": "",
        "spare": None,
    }
    with open(target / "config.yaml", "w") as f:
        yaml.safe_dump(config, f, sort_keys=False)
    documents = [
        {"kind": "run", "id": 1},
        {"kind": "run", "id": 2, "tags": ["dark", "gain"]},
        {"kind": "end"},
    ]
    with open(target / "stream.yml", "w") as f:
        yaml.safe_dump_all(documents, f, sort_keys=False)


def csv_tables(target: Path) -> None:
    """Two tables written by csv.writer: semicolon-separated in Latin-1 with a header, as
    German Windows software exports them; comma-separated numbers without one."""
    target.mkdir(parents=True)
    with open(target / "temperature.csv", "w", encoding="latin-1", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Zeit", "Temperatur (°C)", "Strom (A)"])
        for i in range(20):
            w.writerow([f"12:{i:02d}:00", f"{20 + i * 0.5:.1f}", f"{i * 1e-6:.1e}"])
    with open(target / "numbers.csv", "w", newline="") as f:
        w = csv.writer(f)
        for i in range(50):
            w.writerow([i, i * 0.25, i * i, -i])


def ini_setup(target: Path) -> None:
    """An instrument's setup.ini, written by configparser."""
    target.mkdir(parents=True)
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser["DEFAULT"] = {"Operator": "ER-C"}
    parser["Laser"] = {
        "Wavelength_nm": "532",
        "Comment": "%(not interpolated)s",
    }
    parser["Stage"] = {"Axes": "X Y Z", "Limits": "-1.5\n1.5"}
    parser["Spare"] = {}
    with open(target / "setup.ini", "w") as f:
        parser.write(f)


def setup_cfg(target: Path) -> None:
    """A Python project's setup.cfg, written by configparser, and an empty one."""
    target.mkdir(parents=True)
    parser = configparser.ConfigParser(interpolation=None)
    parser["metadata"] = {"name": "example", "version": "0.1.0"}
    parser["options"] = {"install_requires": "\nnumpy\nscipy"}
    with open(target / "setup.cfg", "w") as f:
        parser.write(f)
    (target / "empty.cfg").write_bytes(b"")
