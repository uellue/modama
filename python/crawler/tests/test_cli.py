"""The records command (the `records-cli` spec), run as a subprocess like a user would."""

import os
import shutil
import subprocess
import sys

import pytest
from conftest import validate_oai
from lxml import etree
from modama_crawler.formats.zarr.tests import generate as zarr_fixtures
from modama_crawler.records import oai_identifier

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


def shell(command_line: str):
    """A command line typed as a user would, with pipes and redirections, in bash."""
    return subprocess.run(
        command_line,
        shell=True,
        executable="/bin/bash",
        capture_output=True,
        check=False,
        timeout=120,
    )


def formats_in(xml: bytes) -> list[str]:
    """The dc:format values of a ListRecords document, sorted."""
    return sorted(e.text for e in etree.fromstring(xml).iter(f"{DC}format"))


def titles_in(xml: bytes) -> list[str]:
    return [e.text for e in etree.fromstring(xml).iter(f"{DC}title")]


@pytest.fixture
def store(tmp_path):
    """A Zarr store with a text file beside it under store/; returns the tree."""
    zarr_fixtures.array(tmp_path / "store")
    return tmp_path


def test_default_invocation(tmp_path):
    (tmp_path / "notes.txt").write_text("hello\n")
    run = records("records", cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    validate_oai(run.stdout)
    assert titles_in(run.stdout) == ["/notes.txt"]
    doc = etree.fromstring(run.stdout)
    assert doc.find(f"{OAI}request").get("verb") == "ListRecords"


def test_verbose_diagnostics_travel_with_the_records(store):
    zarr_fixtures.corrupt(store / "broken")
    # Typed as the documentation shows it: the flag after the subcommand, through a pipe
    run = shell(f"{sys.executable} -m modama_crawler records --verbose {store} | cat")
    assert run.returncode == 0, run.stderr
    validate_oai(run.stdout)
    text = run.stdout.decode()
    # The properties users rely on: a comment per recognised dataset naming the
    # path and the format, directly before its record; a WARNING: comment before
    # the record it concerns; the counts at the end. Not the exact prose.
    note = text.index("<!-- /store/a.zarr: application/x-zarr by zarr/zarr")
    assert note < text.index(oai_identifier("/store/a.zarr"))
    warning = text.index("<!-- /broken/broken.zarr: WARNING: ")
    assert warning < text.index(oai_identifier("/broken/broken.zarr"))
    # A single file by its MIME type gets no comment of its own
    assert "<!-- /store/notes.txt" not in text
    assert "<!-- 3 records (1 single files by type), 1 warnings, 0 skipped -->" in text
    # Nothing to look for on standard error
    assert b"INFO" not in run.stderr and b"WARNING" not in run.stderr
    # Also accepted before the subcommand
    before = records("--verbose", "records", str(store))
    assert before.returncode == 0 and before.stdout.count(b"<!--") == text.count("<!--")


def test_options_in_any_order(store):
    config = store / "config" / "modama.toml"
    config.parent.mkdir()
    config.write_text(
        "[formats]\nselect = ['core', 'zarr']\n[crawl]\nexclude = ['/config/**']\n"
    )
    run = records("records", "--config", str(config), str(store), "--verbose")
    assert run.returncode == 0, run.stderr
    run = records(
        "records",
        "--ignore",
        "zarr",
        "--verbose",
        str(store),
        "--from",
        "2020-01-01",
        "--config",
        str(config),
    )
    assert run.returncode == 0, run.stderr
    validate_oai(run.stdout)
    assert formats_in(run.stdout) == ["application/json", "text/plain"]
    assert b"<!--" in run.stdout


def test_per_path_ignores_from_the_config(store):
    config = store / "config" / "modama.toml"
    config.parent.mkdir()
    config.write_text(
        '[formats.per-path-ignores]\n"/store/**" = ["zarr/zarr"]\n'
        "[crawl]\nexclude = ['/config/**']\n"
    )
    run = records("records", "--config", str(config), str(store))
    assert run.returncode == 0, run.stderr
    # Crawled and classified, but the Zarr format never ran on /store
    assert formats_in(run.stdout) == ["application/json", "text/plain"]


def test_ignore_overrides_selection(store):
    with_zarr = records("records", str(store)).stdout
    without = records("records", "--ignore", "zarr", str(store)).stdout
    assert formats_in(with_zarr) == ["application/x-zarr", "text/plain"]
    assert formats_in(without) == ["application/json", "text/plain"]
    only_core = records("records", "--select", "core", str(store)).stdout
    assert formats_in(only_core) == ["application/json", "text/plain"]


def test_from_until_filter(tmp_path):
    old = tmp_path / "old.txt"
    old.write_text("o")
    os.utime(old, (1_000_000_000, 1_000_000_000))
    (tmp_path / "new.txt").write_text("n")
    run = records("records", "--from", "2020-01-01", str(tmp_path))
    assert titles_in(run.stdout) == ["/new.txt"]
    run = records("records", "--until", "2020-01-01", str(tmp_path))
    assert titles_in(run.stdout) == ["/old.txt"]


def test_until_includes_the_last_second(tmp_path):
    # The filter compares what the record shows: whole seconds
    late = tmp_path / "late.txt"
    late.write_text("l")
    os.utime(late, (1577923199.7, 1577923199.7))  # 2020-01-01T23:59:59.7Z
    run = records("records", "--until", "2020-01-01", str(tmp_path))
    assert titles_in(run.stdout) == ["/late.txt"]


def test_closed_pipe_ends_quietly(tmp_path):
    for i in range(300):
        (tmp_path / f"f{i}.txt").write_text(str(i))
    # Typed as a user would: the output piped into a reader that stops early
    run = shell(
        f"{sys.executable} -m modama_crawler records {tmp_path} | head -c 200 >/dev/null; exit ${{PIPESTATUS[0]}}"
    )
    assert run.returncode == 0, run.stderr
    assert b"Broken pipe" not in run.stderr and b"Traceback" not in run.stderr


@pytest.mark.skipif(shutil.which("modama-crawler") is None, reason="script not on PATH")
def test_documented_entry_point(tmp_path):
    # The documentation says `modama-crawler ...`; one run through the real script
    (tmp_path / "a.txt").write_text("a")
    assert b"--verbose" in shell("modama-crawler records --help").stdout
    run = shell(
        f"cd {tmp_path} && modama-crawler records | head -c 200 >/dev/null; exit ${{PIPESTATUS[0]}}"
    )
    assert run.returncode == 0 and b"Traceback" not in run.stderr


def test_missing_path_fails(tmp_path):
    run = records("records", str(tmp_path / "no" / "such" / "path"))
    assert run.returncode != 0
    assert b"no/such/path" in run.stderr
    assert run.stdout == b""


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read anything")
def test_unreadable_path_fails(tmp_path):
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


def test_comma_separated_ids(store):
    venv = store / "venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("home = /usr\n")
    (venv / "x.py").write_text("x")
    commas = records("records", "--ignore", "collapse,zarr", str(store)).stdout
    repeated = records(
        "records", "--ignore", "collapse", "--ignore", "zarr", str(store)
    ).stdout
    assert formats_in(commas) == formats_in(repeated)
    assert "text/x-python" in formats_in(commas)  # the venv was not collapsed
    assert "application/x-zarr" not in formats_in(commas)


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
    merged = shell(f"{sys.executable} -m modama_crawler records {tmp_path} 2>&1").stdout
    assert (
        merged.index(b"</OAI-PMH>")
        < merged.index(b"WARNING")
        < merged.index(b"1 records, 1 warnings")
    )
    # With --verbose the warning is a comment of its own, before the store's recognition comment
    verbose = records("records", "--verbose", str(tmp_path)).stdout.decode()
    assert verbose.index("<!-- /broken.zarr: WARNING: ") < verbose.index(
        "<!-- /broken.zarr: application/x-zarr by zarr/zarr"
    )
