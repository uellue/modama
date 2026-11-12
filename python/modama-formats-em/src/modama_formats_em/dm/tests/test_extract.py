"""DM3 and DM4 recognition and extraction (spec formats/dm), one test per scenario.

Run with -s to see each description, its subjects and the bytes the extractor read.
"""

import errno
import os
import zipfile

import pytest
from modama_crawler import extraction
from modama_crawler.records import description
from modama_crawler.testing import recognise
from modama_crawler.walk import walk

from modama_formats_em.dm import first_image, parsed, version
from modama_formats_em.testing import described, stale

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_a_dm4_file_from_an_instrument(collection_tests, tmp_path):
    (d,) = recognise(collection_tests, "cl_image_dm4", tmp_path).datasets
    assert (d.type, d.format, d.members) == (
        "application/x.dm4",
        "em/dm4",
        ("/test-MonarcCL_mono-image.dm4",),
    )


def test_a_misnamed_file(collection_tests, tmp_path):
    (d,) = recognise(collection_tests, "misnamed", tmp_path).datasets
    assert d.type == "text/plain" and d.format == ""


def test_a_dmw_file_with_the_dm4_header(collection_tests, tmp_path):
    # The name decides over the DM4 header; the DM4 format does not take it (F15),
    # em/dmw does (decision 173)
    result = recognise(collection_tests, "workspace", tmp_path)
    (d,) = result.datasets
    assert (d.type, d.format) == ("application/x.dm-dmw", "em/dmw")
    assert result.all_warnings() == []
    # Its record names the .dmw type, not a DM image, and its extraction does not fail
    (dmw,) = described(collection_tests, "workspace", tmp_path / "x")
    assert dmw.description.endswith(
        "; Gatan Digital Micrograph workspace, 1 file, 846 B, in /"
    )
    assert "Digital Micrograph (DM" not in dmw.description
    # One name for the type, in the subject as in the description (code review finding 7)
    assert dmw.subjects == ["Gatan Digital Micrograph workspace"]


# A workspace as GMS writes it (2026-11-12): root tags only, no ImageList
WORKSPACE = [
    "File count 2",
    "File name 0 .\\exemplary_workspace\\h1.dm4",
    "File name 1 .\\exemplary_workspace\\100 deg C.dm4",
    "Frame 0 None",
    "Frame 1 None",
    "Window 0 (217, 84, 646, 536)",
    "Window 1 (641, -17, 835, 207)",
    "Workspace name exemplary_workspace",
]


def test_a_representative_dmw_file(collection_tests, tmp_path):
    (dmw,) = described(collection_tests, "workspace", tmp_path)
    assert dmw.dataset.basis == "Digital Micrograph header"
    # Every tag as the reader gives it, in its order (decision 173), the Windows
    # paths with their backslashes; the images it names are not there
    assert dmw.dataset.extraction.extracted.summary == WORKSPACE
    assert dmw.description == (
        ", ".join(WORKSPACE)
        + "; Gatan Digital Micrograph workspace, 1 file, 846 B, in /"
    )
    assert_tags_read(dmw, "/exemplary_workspace.dmw")


def stored(ct, fixture, tmp_path):
    """The dataset of a fixture as a crawl stores it: recognised, then extracted in a worker."""
    tree = ct.materialise(fixture, tmp_path)
    result = walk(tree, ct.collection.formats)
    extraction.extract(result, ct.collection.formats, str(tree), workers=1)
    assert result.all_warnings() == []
    (d,) = result.datasets
    return d


def test_the_stored_dmw_description(collection_tests, tmp_path):
    # What the extraction stores (code review finding 5): the workspace as it is
    d = stored(collection_tests, "workspace", tmp_path)
    assert d.extraction.extracted.summary == WORKSPACE


def test_a_tag_longer_than_storage_keeps(collection_tests, tmp_path):
    # Each phrase cut to 4,096 characters (extraction.MAX_STRING): the DM3
    # stand-in's colour table, 6,053 characters as the extractor gives it
    summary = stored(collection_tests, "dm3_dmw", tmp_path).extraction.extracted.summary
    assert len(summary) == 236 <= extraction.MAX_ITEMS
    (cut,) = [p for p in summary if len(p) == extraction.MAX_STRING]
    clut = "DocumentObjectList.TagGroup0.ImageDisplayInfo.CLUT [(0, 0, 0), "
    assert cut.startswith(clut)
    assert max(len(p) for p in summary) == extraction.MAX_STRING


def test_a_representative_compressed_workspace(collection_tests, tmp_path):
    # Decision 190: the inner workspace's tags, then the members; no image read
    (dmwx,) = described(collection_tests, "compressed_workspace", tmp_path)
    d = dmwx.dataset
    assert (d.type, d.format, d.basis) == (
        "application/x.dm-dmwx",
        "em/dmwx",
        "ZIP, first member a .dmw",
    )
    image = "exemplary_workspace/files/test-MonarcCL_mono-image.dm4"
    size = os.path.getsize(
        os.path.join(FIXTURES, "cl_image_dm4", os.path.basename(image))
    )
    assert d.extraction.extracted.summary == [
        *WORKSPACE,
        "member exemplary_workspace/exemplary_workspace.dmw 846 B",
        "member exemplary_workspace/files/ 0 B",
        f"member {image} {size} B",
    ]
    assert dmwx.subjects == ["Gatan Digital Micrograph workspace (compressed)"]
    # The archive's own size depends on zlib's compression
    assert "; Gatan Digital Micrograph workspace (compressed), 1 file, " in (
        dmwx.description
    )
    # The end record, the central directory and the workspace: less than the image
    with zipfile.ZipFile(
        tmp_path / "compressed_workspace/exemplary_workspace.dmwx"
    ) as z:
        compressed = z.getinfo(image).compress_size
        dmw = z.getinfo("exemplary_workspace/exemplary_workspace.dmw").compress_size
    assert dmwx.bytes_read < compressed
    assert set(dmwx.reads) == {"/exemplary_workspace.dmwx"}
    assert max(dmwx.reads["/exemplary_workspace.dmwx"]) <= max(dmw, 4096)


@pytest.mark.parametrize(
    "fixture, name, kept",
    [
        ("text_dmwx", "notes", "text/plain"),
        ("zip_without_workspace", "other", "application/zip"),
    ],
)
def test_a_file_named_like_a_compressed_workspace(
    collection_tests, tmp_path, fixture, name, kept
):
    result = recognise(collection_tests, fixture, tmp_path)
    (d,) = result.datasets
    assert (d.anchor, d.type, d.format) == (f"/{name}.dmwx", kept, "")
    assert d.basis == (
        "single file; em/dmwx: not application/x.dm-dmwx, no .dmw first in a ZIP"
    )
    assert result.all_warnings() == []


def test_a_compressed_workspace_that_cannot_be_read(
    collection_tests, tmp_path, monkeypatch
):
    # As for .dmw (code review finding 1): it keeps its type, the other stands
    from modama_crawler import formats

    tree = collection_tests.materialise("compressed_workspace", tmp_path)
    (tree / "broken.dmwx").write_text("hello\n")
    monkeypatch.setattr(formats, "open", stale("broken.dmwx"), raising=False)
    result = walk(tree, collection_tests.collection.formats)
    datasets = {d.anchor: d for d in result.datasets}
    assert datasets["/exemplary_workspace.dmwx"].format == "em/dmwx"
    assert (datasets["/broken.dmwx"].type, datasets["/broken.dmwx"].basis) == (
        "application/x.dm-dmwx",
        "single file",
    )
    assert result.all_warnings() == [
        (
            "/broken.dmwx",
            "em/dmwx: cannot read broken.dmwx: Stale file handle; type kept",
        )
    ]
    assert result.listings["/"].retry


def test_a_dmw_file_that_cannot_be_read(collection_tests, tmp_path, monkeypatch):
    # Code review finding 1: one unreadable .dmw keeps its type, and the other's dataset stands
    from modama_crawler import formats

    tree = collection_tests.materialise("workspace", tmp_path)
    (tree / "broken.dmw").write_text("hello\n")
    monkeypatch.setattr(formats, "open", stale("broken.dmw"), raising=False)
    result = walk(tree, collection_tests.collection.formats)
    datasets = {d.anchor: d for d in result.datasets}
    assert datasets["/exemplary_workspace.dmw"].format == "em/dmw"
    broken = datasets["/broken.dmw"]
    assert (broken.type, broken.format, broken.basis) == (
        "application/x.dm-dmw",
        "",
        "single file",
    )
    assert result.all_warnings() == [
        ("/broken.dmw", "em/dmw: cannot read broken.dmw: Stale file handle; type kept")
    ]
    assert result.listings["/"].retry


def test_a_dmw_file_with_the_dm3_header(collection_tests, tmp_path):
    result = recognise(collection_tests, "dm3_dmw", tmp_path)
    assert result.all_warnings() == []
    (dmw,) = described(collection_tests, "dm3_dmw", tmp_path / "x")
    assert (dmw.dataset.type, dmw.dataset.format) == ("application/x.dm-dmw", "em/dmw")
    # Handled, and marked as a file of interest (decision 174)
    assert dmw.dataset.basis == (
        "Digital Micrograph header; file of interest: DM3, no .dmw in DM3 seen yet"
    )
    summary = dmw.dataset.extraction.extracted.summary
    assert len(summary) == 236
    name = "ImageList.TagGroup1.ImageTags.Microscope Info.Name FEI Tecnai Remote"
    assert name in summary


@pytest.mark.parametrize(
    "fixture, name", [("text_dmw", "notes"), ("empty_dmw", "empty")]
)
def test_a_file_named_like_a_workspace(collection_tests, tmp_path, fixture, name):
    # Without a DM header it is not a .dmw file: the type it has without the
    # name rule, the reason in its basis, no warning (spec formats/dm)
    result = recognise(collection_tests, fixture, tmp_path)
    (d,) = result.datasets
    assert (d.anchor, d.type, d.format) == (f"/{name}.dmw", "text/plain", "")
    assert d.basis == "single file; em/dmw: not application/x.dm-dmw, no DM header"
    assert description(d).startswith("Plain text document, 1 file, ")
    assert result.all_warnings() == []


def test_the_dm_header():
    assert version(b"\0\0\0\4" + bytes(8) + b"\0\0\0\1") == 4
    assert version(b"\0\0\0\3" + bytes(4) + b"\0\0\0\0" + bytes(4)) == 3
    # The flag at the other version's place, a wrong flag, too short
    assert version(b"\0\0\0\4" + bytes(4) + b"\0\0\0\1" + b"\0\0\0\7") is None
    assert version(b"\0\0\0\3" + bytes(4) + b"\0\0\0\2") is None
    assert version(b"\0\0\0\4") is None
    assert version(b"") is None


def test_a_representative_dm4_image(collection_tests, tmp_path):
    (image,) = described(collection_tests, "cl_image_dm4", tmp_path)
    assert image.description.startswith(
        # The numbers as the reader gives them, not rounded
        "beam_energy 3.0, magnification 2500.0, camera_length 1.0, "
        "18.325349807739258 µm/pixel, 2×2, DigiScan, Zeiss SEM COM, 2021-05-14 11:41; "
    )
    assert image.subjects == [
        "Gatan Digital Micrograph (DM4)",
        "Zeiss SEM COM",
        "SEM",
        "CL",
    ]
    # The tags, not the whole file (D7), in a small buffer: 143,372 bytes with
    # RosettaSciIO's file_reader on a local disk, 1 MiB per refill on NFS (F14)
    assert image.bytes_read < 100_000
    # in reads no larger than NFS's read size, from this file only
    assert_tags_read(image, "/test-MonarcCL_mono-image.dm4")


def assert_tags_read(image, path):
    """The scenario "The tags, not the image data": each read at most 64 KiB, of the file only."""
    assert set(image.reads) == {path}
    assert 0 < max(image.reads[path]) <= 64 * 1024


def test_a_representative_dm3_image(collection_tests, tmp_path):
    (image,) = described(collection_tests, "stem_image_dm3", tmp_path)
    assert image.description.startswith(
        "beam_energy 200.0, magnification 225000.0, camera_length 135.0, "
        "0.24853801727294922 nm/pixel, 68×68, DigiScan, FEI Titan, 2016-08-08 16:26; "
    )
    assert image.subjects == ["Gatan Digital Micrograph (DM3)", "FEI Titan", "STEM"]
    assert_tags_read(image, "/test_STEM_image.dm3")


def test_an_rgba_image(collection_tests, tmp_path):
    # RosettaSciIO's file_reader refuses RGBA images when lazy; the tags are still read (F14)
    (image,) = described(collection_tests, "rgba_image_dm4", tmp_path)
    assert image.description.startswith("2×2; Gatan Digital Micrograph file, version 4")
    assert image.subjects == ["Gatan Digital Micrograph (DM4)"]


@pytest.mark.parametrize("advice", ["refused", "missing"])
def test_without_the_readahead_advice(monkeypatch, advice):
    # posix_fadvise is an optimisation: refused by the file system, or missing
    # on the platform, the tags are read all the same
    if advice == "refused":

        def refuse(*args):
            raise OSError(errno.EINVAL, "refused")

        monkeypatch.setattr(os, "posix_fadvise", refuse)
    else:
        monkeypatch.delattr(os, "posix_fadvise")
    dm = parsed(os.path.join(FIXTURES, "cl_image_dm4", "test-MonarcCL_mono-image.dm4"))
    assert "ImageList" in dm.tags_dict


def _order(node):
    """The key order of a tag tree, at every level."""
    if not isinstance(node, dict):
        return None
    return [(k, _order(v)) for k, v in node.items()]


def _mapping(mapping: dict) -> dict:
    """A mapping comparable across calls: tag path -> (metadata path, conversion's name)."""
    return {
        path: (target, getattr(convert, "__qualname__", convert))
        for path, (target, convert) in mapping.items()
    }


@pytest.mark.parametrize(
    "fixture",
    [
        "cl_image_dm4/test-MonarcCL_mono-image.dm4",
        "stem_image_dm3/test_STEM_image.dm3",
        "rgba_image_dm4/test-8.dm4",
    ],
)
def test_first_image_is_what_file_reader_gives(fixture):
    # first_image repeats file_reader's steps with RosettaSciIO's private
    # classes (pinned exactly, pyproject.toml): a release that changes them
    # shows here first
    from rsciio.digitalmicrograph import file_reader

    path = os.path.join(FIXTURES, fixture)
    mine = first_image(path)
    if fixture.startswith("rgba"):
        # Why first_image exists: file_reader refuses RGBA images when lazy (F14)
        with pytest.raises(ValueError, match="RGBA"):
            file_reader(path, lazy=True)
        return
    (theirs,) = file_reader(path, lazy=True)
    assert mine["axes"] == theirs["axes"]
    assert mine["metadata"] == theirs["metadata"]
    assert mine["original_metadata"] == theirs["original_metadata"]
    assert _order(mine["original_metadata"]) == _order(theirs["original_metadata"])
    assert _mapping(mine["mapping"]) == _mapping(theirs["mapping"])
