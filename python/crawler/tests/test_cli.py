"""The records command (the `records-cli` spec), run as a subprocess like a user would."""

import subprocess
import sys
from pathlib import Path

from lxml import etree
from modama_crawler.formats.empad import cheat
from modama_crawler.testing import validate_oai

SCHEMAS = Path(__file__).parent / "schemas"
OAI = "{http://www.openarchives.org/OAI/2.0/}"
DC = "{http://purl.org/dc/elements/1.1/}"


def records(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "modama_crawler", *args],
        check=False,
        capture_output=True,
        cwd=cwd,
        timeout=120,
    )


def formats_in(xml: bytes) -> list[str]:
    """The dc:format values of a ListRecords document, sorted."""
    return sorted(e.text for e in etree.fromstring(xml).iter(f"{DC}format"))


def test_default_invocation(tmp_path):
    (tmp_path / "notes.txt").write_text("hello\n")
    run = records("records", cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    validate_oai(run.stdout, SCHEMAS)
    doc = etree.fromstring(run.stdout)
    assert [e.text for e in doc.iter(f"{DC}title")] == ["/notes.txt"]
    assert doc.find(f"{OAI}request").get("verb") == "ListRecords"


def test_verbose_diagnostics_travel_with_the_records(tmp_path):
    cheat.pair(tmp_path / "scan")
    cheat.header_only(tmp_path / "copying")
    # Typed as the documentation shows it: the flag after the subcommand, through a pipe
    run = subprocess.run(
        f"{sys.executable} -m modama_crawler records --verbose {tmp_path} | cat",
        shell=True,
        executable="/bin/bash",
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr
    validate_oai(run.stdout, SCHEMAS)
    text = run.stdout.decode()
    note = "<!-- /scan/SCA2_rings.xml: application/x.empad+xml by empad/empad 1, basis: raw_file points to series_x4.raw -->"
    assert note in text
    # The note comes directly before its record, the warning directly before the note of the header it concerns
    assert text.index(note) < text.index(oai_identifier_of("/scan/SCA2_rings.xml"))
    warning = "<!-- /copying/SCA2_rings.xml: WARNING: raw file series_x4.raw named by the header is missing -->"
    assert warning in text
    assert text.index(warning) < text.index(
        oai_identifier_of("/copying/SCA2_rings.xml")
    )
    # A single file by its MIME type gets no comment of its own
    assert "<!-- /copying/SCA2_rings.xml: application" not in text
    assert "<!-- 2 records (1 single files by type), 1 warnings, 0 skipped -->" in text
    # Nothing to look for on standard error
    assert b"INFO" not in run.stderr and b"WARNING" not in run.stderr
    # Also accepted before the subcommand
    before = records("--verbose", "records", str(tmp_path))
    assert before.returncode == 0 and before.stdout.count(b"<!--") == text.count("<!--")


def oai_identifier_of(path: str) -> str:
    from modama_crawler.records import oai_identifier

    return oai_identifier(path)


def test_options_in_any_order(tmp_path):
    cheat.pair(tmp_path / "scan")
    config = tmp_path / "config" / "modama.toml"
    config.parent.mkdir()
    config.write_text(
        "[formats]\nselect = ['core', 'empad']\n[crawl]\nexclude = ['/config/**']\n"
    )
    run = records("records", "--config", str(config), str(tmp_path), "--verbose")
    assert run.returncode == 0, run.stderr
    run = records(
        "records",
        "--ignore",
        "empad",
        "--verbose",
        str(tmp_path),
        "--from",
        "2020-01-01",
        "--config",
        str(config),
    )
    assert run.returncode == 0, run.stderr
    validate_oai(run.stdout, SCHEMAS)
    doc = etree.fromstring(run.stdout)
    assert sorted(e.text for e in doc.iter(f"{DC}format")) == [
        "application/octet-stream",
        "application/xml",
    ]
    assert b"<!--" in run.stdout


def test_ignore_overrides_selection(tmp_path):
    cheat.pair(tmp_path / "scan")
    with_empad = records("records", str(tmp_path)).stdout
    without = records("records", "--ignore", "empad", str(tmp_path)).stdout
    assert formats_in(with_empad) == ["application/x.empad+xml"]
    # The whole collection is off, its MIME definitions too: generic types remain
    assert formats_in(without) == ["application/octet-stream", "application/xml"]
    only_core = records("records", "--select", "core", str(tmp_path)).stdout
    assert formats_in(only_core) == ["application/octet-stream", "application/xml"]


def test_from_until_filter(tmp_path):
    import os

    old = tmp_path / "old.txt"
    old.write_text("o")
    os.utime(old, (1_000_000_000, 1_000_000_000))
    (tmp_path / "new.txt").write_text("n")
    doc = etree.fromstring(
        records("records", "--from", "2020-01-01", str(tmp_path)).stdout
    )
    assert [e.text for e in doc.iter(f"{DC}title")] == ["/new.txt"]
    doc = etree.fromstring(
        records("records", "--until", "2020-01-01", str(tmp_path)).stdout
    )
    assert [e.text for e in doc.iter(f"{DC}title")] == ["/old.txt"]


def test_closed_pipe_ends_quietly(tmp_path):
    for i in range(300):
        (tmp_path / f"f{i}.txt").write_text(str(i))
    # Typed as a user would: the output piped into a reader that stops early
    run = subprocess.run(
        f"{sys.executable} -m modama_crawler records {tmp_path} | head -c 200 >/dev/null; exit ${{PIPESTATUS[0]}}",
        shell=True,
        executable="/bin/bash",
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr
    assert b"Broken pipe" not in run.stderr and b"Traceback" not in run.stderr


def test_missing_path_fails(tmp_path):
    run = records("records", str(tmp_path / "no" / "such" / "path"))
    assert run.returncode != 0
    assert b"no/such/path" in run.stderr
    assert run.stdout == b""


def test_unreadable_path_fails(tmp_path):
    import os

    if os.geteuid() == 0:
        return  # root can read anything
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        run = records("records", str(locked))
    finally:
        locked.chmod(0o700)
    assert run.returncode != 0
    assert b"locked" in run.stderr and b"Traceback" not in run.stderr
    assert run.stdout == b""


def test_comma_separated_ids(tmp_path):
    cheat.pair(tmp_path / "scan")
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("home = /usr\n")
    (venv / "x.py").write_text("x")
    commas = records("records", "--ignore", "collapse,empad", str(tmp_path)).stdout
    repeated = records(
        "records", "--ignore", "collapse", "--ignore", "empad", str(tmp_path)
    ).stdout
    assert formats_in(commas) == formats_in(repeated)
    assert "text/x-python" in formats_in(commas)  # the venv was not collapsed
    assert "application/x.empad+xml" not in formats_in(commas)


def test_unknown_format_id_fails(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    run = records("records", "--select", "nosuch", str(tmp_path))
    assert run.returncode != 0
    assert b"nosuch" in run.stderr and b"Traceback" not in run.stderr
    assert run.stdout == b""
    config = tmp_path / "modama.toml"
    config.write_text("[formats]\nignore = ['collapse/vnev']\n")
    run = records("records", "--config", str(config), str(tmp_path))
    assert run.returncode != 0
    assert b"collapse/vnev" in run.stderr and run.stdout == b""


def test_missing_config_file_fails(tmp_path):
    run = records(
        "records", "--config", str(tmp_path / "no" / "such.toml"), str(tmp_path)
    )
    assert run.returncode != 0
    assert b"no/such.toml" in run.stderr and b"Traceback" not in run.stderr
    assert run.stdout == b""


def test_help_lists_every_option():
    run = records("records", "--help")
    assert run.returncode == 0
    for option in (
        b"--verbose",
        b"--config",
        b"--select",
        b"--ignore",
        b"--from",
        b"--until",
    ):
        assert option in run.stdout


def test_dataset_warnings_are_reported_without_verbose(tmp_path):
    store = tmp_path / "broken.zarr"
    store.mkdir()
    (store / "zarr.json").write_text("{not json")
    run = records("records", str(tmp_path))
    assert run.returncode == 0, run.stderr
    assert b"WARNING /broken.zarr: zarr.json cannot be parsed" in run.stderr
    assert b"1 records, 1 warnings" in run.stderr
    # On a terminal the warnings and the summary come after the document, where the eye lands
    merged = subprocess.run(
        f"{sys.executable} -m modama_crawler records {tmp_path} 2>&1",
        shell=True,
        executable="/bin/bash",
        capture_output=True,
        check=False,
        timeout=120,
    ).stdout
    assert (
        merged.index(b"</OAI-PMH>")
        < merged.index(b"WARNING")
        < merged.index(b"1 records, 1 warnings")
    )
    # With --verbose the warning is a comment of its own, before the store's recognition comment
    verbose = records("records", "--verbose", str(tmp_path)).stdout.decode()
    assert verbose.index(
        "<!-- /broken.zarr: WARNING: zarr.json cannot be parsed"
    ) < verbose.index("<!-- /broken.zarr: application/x-zarr by zarr/zarr")
