"""DM3 and DM4 recognition and extraction (spec formats/dm), one test per scenario.

Run with -s to see each description, its subjects and the bytes the extractor read.
"""

import errno
import os

import pytest
from modama_crawler.testing import recognise

from modama_formats_em.dm import first_image, parsed
from modama_formats_em.testing import described

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
    # The name decides over the DM4 header; the DM4 format does not take it (F15)
    (d,) = recognise(collection_tests, "dmw_file", tmp_path).datasets
    assert (d.type, d.format) == ("application/x.dm-dmw", "")
    assert described(collection_tests, "dmw_file", tmp_path / "x") == []


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


def test_a_representative_dm3_image(collection_tests, tmp_path):
    (image,) = described(collection_tests, "stem_image_dm3", tmp_path)
    assert image.description.startswith(
        "beam_energy 200.0, magnification 225000.0, camera_length 135.0, "
        "0.24853801727294922 nm/pixel, 68×68, DigiScan, FEI Titan, 2016-08-08 16:26; "
    )
    assert image.subjects == ["Gatan Digital Micrograph (DM3)", "FEI Titan", "STEM"]


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
