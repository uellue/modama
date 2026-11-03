"""The per-deployment MIME database (the `mime-database` spec)."""

from pathlib import Path

import pytest
from modama_crawler import mime, mimedb, selection
from modama_crawler.formats import Collection
from modama_crawler.mime import detect, detect_with_tie
from modama_crawler.walk import walk

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


def test_only_enabled_collections_define_types(tmp_path, rebuild):
    # mimedb.activate points pyxdg at the built database alone (the host's /usr/share/mime is never read)
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
    # The walk reports the tie as a warning naming both candidates
    result = walk(tmp_path, [])
    assert (
        "/x.tie",
        "type is ambiguous between application/x.h5-a, application/x.h5-b; using application/x-hdf",
    ) in result.warnings


def test_vendored_file_is_packaged():
    core = selection.discover()["core"]
    assert (
        Path(core.mime_files[0]).name == "freedesktop.org.xml"
        and core.mime_files[0].exists()
    )
    assert (core.mime_files[0].parent / "LICENSE.freedesktop.org.xml").exists()


def test_detection_without_a_database_refuses(tmp_path):
    # Silently falling back to the host's /usr/share/mime would contradict Q12
    (tmp_path / "a.png").write_bytes(PNG)
    active = mime.database
    mime.database = None
    try:
        with pytest.raises(RuntimeError, match="no MIME database active"):
            detect(str(tmp_path / "a.png"))
    finally:
        mime.database = active
    assert detect(str(tmp_path / "a.png")) == "image/png"
