"""The per-deployment MIME database (the `mime-database` spec)."""

from pathlib import Path

import pytest
from modama_crawler import mimedb, selection
from modama_crawler.formats import Collection
from modama_crawler.mime import detect, detect_with_tie

PNG = b"\x89PNG\r\n\x1a\n" + bytes(32)


def xml(types: str) -> str:
    return f"<?xml version='1.0'?><mime-info xmlns='http://www.freedesktop.org/standards/shared-mime-info'>{types}</mime-info>"


@pytest.fixture
def rebuild(tmp_path, mime_database):
    """Build a database from the given collections; restore the session database afterwards."""
    built = []

    def build(*collections):
        mimedb.build(collections, tmp_path / f"db{len(built)}")
        built.append(True)

    yield build
    mimedb.build(mime_database.values(), tmp_path / "restore")


def test_host_definitions_are_ignored(tmp_path, rebuild):
    host = Collection("host", [], (tmp_path / "host.xml",))
    (tmp_path / "host.xml").write_text(
        xml('<mime-type type="application/x-foo"><glob pattern="*.foo"/></mime-type>')
    )
    (tmp_path / "x.foo").write_bytes(b"\0\1\2")
    rebuild(selection.discover()["core"], host)
    assert detect(str(tmp_path / "x.foo")) == "application/x-foo"
    rebuild(selection.discover()["core"])
    assert detect(str(tmp_path / "x.foo")) == "application/octet-stream"


def test_png_from_vendored_definitions(tmp_path, rebuild):
    rebuild(selection.discover()["core"])
    (tmp_path / "a.png").write_bytes(PNG)
    (tmp_path / "noext").write_bytes(PNG)
    assert detect(str(tmp_path / "a.png")) == "image/png"
    assert detect(str(tmp_path / "noext")) == "image/png"


def test_longest_pattern_wins(tmp_path, mime_database):
    import gzip

    (tmp_path / "a.tar.gz").write_bytes(gzip.compress(b""))
    assert detect(str(tmp_path / "a.tar.gz")) == "application/x-compressed-tar"


def test_tie_resolves_to_common_ancestor(tmp_path, rebuild):
    two = Collection("two", [], (tmp_path / "two.xml",))
    (tmp_path / "two.xml").write_text(
        xml(
            '<mime-type type="application/x.h5-a"><sub-class-of type="application/x-hdf"/><glob pattern="*.tie"/></mime-type>'
            '<mime-type type="application/x.h5-b"><sub-class-of type="application/x-hdf"/><glob pattern="*.tie"/></mime-type>'
        )
    )
    rebuild(selection.discover()["core"], two)
    (tmp_path / "x.tie").write_bytes(b"\0" * 64)
    assert detect_with_tie(str(tmp_path / "x.tie")) == (
        "application/x-hdf",
        ("application/x.h5-a", "application/x.h5-b"),
    )


def test_executable_binary_is_octet_stream(tmp_path, mime_database):
    f = tmp_path / "frame_0001"
    f.write_bytes(bytes(range(256)))
    f.chmod(0o755)
    assert detect(str(f)) == "application/octet-stream"
    t = tmp_path / "notes"
    t.write_text("just text\n")
    assert detect(str(t)) == "text/plain"


def test_vendored_file_is_packaged():
    core = selection.discover()["core"]
    assert (
        Path(core.mime_files[0]).name == "freedesktop.org.xml"
        and core.mime_files[0].exists()
    )
    assert (core.mime_files[0].parent / "LICENSE.freedesktop.org.xml").exists()
