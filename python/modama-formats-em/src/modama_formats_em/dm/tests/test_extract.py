"""DM3 and DM4 recognition and extraction (spec formats/dm), one test per scenario.

Run with -s to see each description, its subjects and the bytes the extractor read.
"""

import errno
import math
import os
import zipfile
from copy import deepcopy

import pytest
from modama_crawler import extraction
from modama_crawler.formats import Dataset, Extracted
from modama_crawler.records import description
from modama_crawler.testing import recognise
from modama_crawler.walk import walk

from modama_formats_em import dm
from modama_formats_em.dm import first_image, parsed, settings, tag_paths, version
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
    extraction.extract(
        result, ct.collection.formats, str(tree), identity="test", workers=1
    )
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
    # The values as the file holds them, a number after its tag's name
    assert image.description.startswith(
        "IMAGING, SCANNING, SEM, 3kV, 2.5kx, STEM Camera Length 1.0, 5/14/2021, "
        "11:41:07 AM; "
    )
    assert image.subjects == [
        "Gatan Digital Micrograph (DM4)",
        "Zeiss SEM COM",
        "SEM",
        "CL",
        "IMAGING",
    ]
    # 119 image tags, without the 18 of the Session Info form; then
    # RosettaSciIO's mapping, labelled (decision 230)
    values = image.dataset.extraction.extracted.values
    assert list(values) == ["original_metadata", "metadata", "axes"]
    tags = values["original_metadata"]
    assert len(tags) == 101
    assert tags["Acquisition.Monarc Spectrometer.Grating"] == "300"
    assert values["metadata"]["Acquisition_instrument.SEM.beam_energy"] == 3.0
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
    # Scenario "A tag that is missing or empty": no camera model, no exposure,
    # no parameter set; Session Info.Operator and Specimen empty
    assert image.description.startswith(
        "DIFFRACTION, SCANNING, STEM NANOPROBE, 200kV, 225kx, STEM Camera Length 135.0, "
        "8/8/2016, 4:26:37 PM; "
    )
    assert image.subjects == [
        "Gatan Digital Micrograph (DM3)",
        "FEI Titan",
        "STEM",
        "DIFFRACTION",
    ]
    assert_tags_read(image, "/test_STEM_image.dm3")


def test_no_unit_the_reader_does_not_give(monkeypatch):
    # The voltage as Formatted Voltage gives it; Voltage (300000.0) not
    # converted, nor RosettaSciIO's beam_energy (300.0) shown
    summary = from_camera(monkeypatch).summary
    assert "300kV" in summary
    assert not [p for p in summary if "300.0" in p or "300000" in p]


# Tags of a DM4 image from a camera, as RosettaSciIO's reader gives them, from
# ncempy's list of 2018-7-17 15_29_0000.dm4 (staging, a K2 summit on an FEI
# Tecnai; .claude/field-tests/browse/ncempy-2018-7-17.txt): the groups the
# summary line and the user-interface rule read, not the whole file
CAMERA = {
    "Acquisition": {
        "Device": {"Name": "K2-0001", "Source Model": "K2 summit"},
        "Parameters": {
            "Objects": {
                "TagGroup0": {
                    "Class Name": "cm_imgproc_finalcombine",
                    "Frame Combine Style": "Copy",
                    "Parameter 1": 0.1,
                },
                "TagGroup1": {
                    "Class Name": "cm_stdviewerimagedisplayer",
                    "Do Auto Zoom": 0,
                    "Screen Relative Position": (0.0, 0.0),
                    "Version": 34078720,
                    "View Name": "View",
                    "Viewer Class": "view",
                    "Window Relative Position": (0.0, 0.0),
                    "Zoom": 1.0,
                },
                "TagGroup2": {"Class Name": "cm_imgproc_histogram"},
            },
            "High Level": {"Exposure (s)": 2.0, "Exposure Live Time": math.inf},
            "Parameter Set Name": "Search",
            "Parameter Set Tag Path": "Imaging:View:Search",
        },
    },
    "DataBar": {
        "Acquisition Date": "7/17/2018",
        "Acquisition Time": "3:29:20 PM",
        "Device Name": "K2-0001",
        "Exposure Time (s)": 2.0,
    },
    "Microscope Info": {
        "Formatted Indicated Mag": "11.5kx",
        "Formatted Voltage": "300kV",
        "Illumination Mode": "TEM NANOPROBE",
        "Imaging Mode": "Lorentz",
        "Indicated Magnification": 11500.0,
        "Name": "FEI Tecnai Remote",
        "Operation Mode": "Lorentz",
        "Voltage": 300000.0,
    },
    "Session Info": {
        "Items": {
            f"TagGroup{i}": {
                "Data Type": 20,
                "Label": label,
                "Precision": 0,
                "Tag path": f"Session Info:{label}",
                "Units": [],
                "Value": [],
            }
            for i, label in enumerate(("Specimen", "Operator", "Microscope"))
        },
        "Microscope": [],
        "Operator": [],
        "Specimen": [],
    },
}


def from_camera(monkeypatch, **session) -> Extracted:
    """The DM4 extraction of an image with CAMERA's tags, Session Info's fields as given:
    the image of stem_image_dm3 with these tags."""
    image = first_image(os.path.join(FIXTURES, "stem_image_dm3", "test_STEM_image.dm3"))
    tags = deepcopy(CAMERA)
    tags["Session Info"].update(session)
    image["original_metadata"]["ImageList"]["TagGroup0"]["ImageTags"] = tags
    monkeypatch.setattr(dm, "first_image", lambda path: image)
    return dm.Dm4().extract(Dataset(anchor="/2018-7-17 15_29_0000.dm4"), "/nowhere")


def test_the_summary_line_of_an_image_from_a_camera(monkeypatch):
    extracted = from_camera(monkeypatch)
    # As the file holds them (decision 230): Lorentz, the imaging and the
    # operation mode, once; a number after its tag's name
    assert extracted.summary == [
        "Lorentz",
        "TEM NANOPROBE",
        "300kV",
        "11.5kx",
        "K2 summit",
        "Exposure Time (s) 2.0",
        "Search",
        "7/17/2018",
        "3:29:20 PM",
    ]
    assert extracted.subjects[-2:] == ["Lorentz", "K2 summit"]


def test_empty_tags_and_infinities(monkeypatch):
    tags = from_camera(monkeypatch).values["original_metadata"]
    assert tags["Session Info.Operator"] == []
    assert tags["Acquisition.Parameters.High Level.Exposure Live Time"] == "inf"


def test_user_interface_settings_are_left_out_of_the_values(monkeypatch):
    tags = from_camera(monkeypatch).values["original_metadata"]
    objects = "Acquisition.Parameters.Objects."
    assert tags[objects + "TagGroup0.Frame Combine Style"] == "Copy"
    assert tags[objects + "TagGroup2.Class Name"] == "cm_imgproc_histogram"
    assert not [p for p in tags if p.startswith(objects + "TagGroup1.")]
    assert not [p for p in tags if p.startswith("Session Info.Items")]
    assert tags["Session Info.Specimen"] == []


def test_the_data_image_not_the_thumbnail(collection_tests, tmp_path):
    # ImageList.TagGroup0 is the thumbnail (Thumbnails names it) with one tag
    # group of its own; the values are the data image's, TagGroup1, and hold
    # nothing of the document, page or window settings, which are not in ImageTags
    (image,) = described(collection_tests, "cl_image_dm4", tmp_path)
    file = parsed(
        os.path.join(FIXTURES, "cl_image_dm4", "test-MonarcCL_mono-image.dm4")
    )
    assert file.tags_dict["Thumbnails"]["TagGroup0"]["ImageIndex"] == 0
    images = file.tags_dict["ImageList"]
    assert list(images["TagGroup0"]["ImageTags"]) == ["GMS Version"]
    data = images["TagGroup1"]["ImageTags"]
    assert image.dataset.extraction.extracted.values["original_metadata"] == dict(
        tag_paths(data, settings)
    )
    assert len(data["Session Info"]["Items"]) == 3  # the form, left out


def test_empty_specimen_and_operator_are_left_out_of_the_summary_line(
    collection_tests, tmp_path
):
    (image,) = described(collection_tests, "cl_image_dm4", tmp_path)
    # The time ends the line: nothing for the empty fields
    summary = image.dataset.extraction.extracted.summary
    assert summary[-1] == "11:41:07 AM"
    assert "[]" not in image.description
    tags = image.dataset.extraction.extracted.values["original_metadata"]
    assert tags["Session Info.Specimen"] == tags["Session Info.Operator"] == []


def test_filled_specimen_and_operator_are_in_the_summary_line(monkeypatch):
    extracted = from_camera(monkeypatch, Specimen="FeGe lamella", Operator="A. Person")
    assert extracted.summary[-3:] == ["3:29:20 PM", "FeGe lamella", "A. Person"]


def test_an_rgba_image(collection_tests, tmp_path):
    # RosettaSciIO's file_reader refuses RGBA images when lazy; the tags are
    # still read (F14). Its image tags are empty: no summary line
    (image,) = described(collection_tests, "rgba_image_dm4", tmp_path)
    assert image.description.startswith("Gatan Digital Micrograph file, version 4")
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
