"""Hitachi pairs, recognition and extraction (spec formats/hitachi), one test per scenario.

Run with -s to see each description and the bytes the extractor read.
"""

import errno
import os
from pathlib import Path
from unittest import mock

from modama_crawler.formats import Directory
from modama_crawler.walk import walk
from modama_formats_common import image, text
from modama_formats_common.image.tests.generate import hitachi_lines, hitachi_tif

from modama_formats_em import hitachi
from modama_formats_em.hitachi.tests import generate
from modama_formats_em.testing import claimed_first, described, rchar

TIF = f"/{generate.TIF}"
TXT = "/grid2_x50.0k_HAADF_0007.txt"
SUMMARY = [
    "HF3300",
    "HAADF",
    "Analysis",
    "Accelerating voltage 300000 (unit unknown)",
    "Magnification 50000",
    "PixelSize 0.5 (unit unknown)",
    "Au on C",
    "ImageWidth 64",
    "ImageLength 96",
    "BitsPerSample 8",
    "2024/01/15",
    "09:30:00",
]


def everything(ct):
    """This part's format with the image and text areas, which take what it leaves (TEMPLATE, rule 11)."""
    return ct.collection.formats + image.COLLECTION.formats + text.COLLECTION.formats


def by_anchor(result) -> dict:
    return {d.anchor: d for d in result.datasets}


# A Hitachi image and its header are one dataset


def test_a_pair(collection_tests, tmp_path):
    tree = collection_tests.materialise("pair", tmp_path)
    reads = []
    real = Directory.read

    def spy(self, entry, n):
        reads.append((entry.name, n))
        return real(self, entry, n)

    with mock.patch.object(Directory, "read", spy):
        result = walk(tree, everything(collection_tests))
    (d,) = result.datasets
    assert (d.format, d.type, d.anchor, d.members, d.basis) == (
        "em/hitachi",
        "application/x-hitachi-sem",
        TIF,
        (TIF, TXT),
        "header grid2_x50.0k_HAADF_0007.txt",
    )
    assert reads == [("grid2_x50.0k_HAADF_0007.txt", 14)]
    assert result.all_warnings() == []


def test_only_the_last_suffix_is_replaced(collection_tests, tmp_path):
    tree = collection_tests.materialise("last_suffix", tmp_path)
    found = by_anchor(walk(tree, everything(collection_tests)))
    assert found["/a_x50.0k_0001.tif"].members == (
        "/a_x50.0k_0001.tif",
        "/a_x50.0k_0001.txt",
    )
    assert found["/a_x50.txt"].format == "common/text"
    assert set(found) == {"/a_x50.0k_0001.tif", "/a_x50.txt"}


def test_a_text_of_the_same_name_that_is_not_the_header(collection_tests, tmp_path):
    tree = collection_tests.materialise("notes_beside_tif", tmp_path)
    result = walk(tree, everything(collection_tests))
    found = {a: d.format for a, d in by_anchor(result).items()}
    assert found == {TIF: "common/tiff", TXT: "common/text"}
    assert result.all_warnings() == []


def test_a_tiff_without_its_header(collection_tests, tmp_path):
    tree = collection_tests.materialise("lone_tif", tmp_path)
    (d,) = walk(tree, everything(collection_tests)).datasets
    assert (d.format, d.type) == ("common/tiff", "image/tiff")
    formats = {f.id: f for f in everything(collection_tests)}
    assert formats[d.format].extract(d, str(tree)).summary == SUMMARY


def test_a_header_without_its_tiff(collection_tests, tmp_path):
    tree = collection_tests.materialise("lone_txt", tmp_path)
    (d,) = walk(tree, everything(collection_tests)).datasets
    assert (d.format, d.type, d.anchor) == ("common/text", "text/plain", TXT)


def test_the_header_cannot_be_read(collection_tests, tmp_path):
    tree = collection_tests.materialise("pair", tmp_path)
    real = open

    def refused(path, *args, **kwargs):
        if os.path.basename(path) == TXT[1:]:
            raise PermissionError(errno.EACCES, "Permission denied")
        return real(path, *args, **kwargs)

    with mock.patch("modama_crawler.formats.open", refused, create=True):
        result = walk(tree, everything(collection_tests))
    found = {a: d.format for a, d in by_anchor(result).items()}
    assert found == {TIF: "common/tiff", TXT: "common/text"}
    assert result.all_warnings() == [
        (
            TXT,
            (
                "em/hitachi: cannot read grid2_x50.0k_HAADF_0007.txt: "
                "Permission denied; type kept"
            ),
        )
    ]


def test_the_pairs_files_are_not_offered_to_the_formats_after_it(
    collection_tests, tmp_path
):
    tree = collection_tests.materialise("pair", tmp_path)
    result = walk(tree, everything(collection_tests))
    assert [d.format for d in result.datasets] == ["em/hitachi"]
    assert result.all_warnings() == []


def test_the_header_claimed_by_another_format(collection_tests, tmp_path):
    result = claimed_first(collection_tests, "pair", tmp_path, TXT[1:])
    found = {a: d.format for a, d in by_anchor(result).items()}
    assert found == {TIF: "", TXT: "probe/claim"}
    assert result.all_warnings() == [
        (
            TIF,
            (
                "em/hitachi: grid2_x50.0k_HAADF_0007.txt is claimed by probe/claim; "
                "two formats want it"
            ),
        )
    ]


# The pair's values are its TIFF's


def test_the_summary_line_of_a_pair(collection_tests, tmp_path):
    (pair,) = described(collection_tests, "pair", tmp_path)
    extracted = pair.dataset.extraction.extracted
    assert extracted.summary == SUMMARY
    assert "SemImageFile.Instrument name" in extracted.values["original_metadata"]


def test_a_value_the_two_files_disagree_on(tmp_path):
    tif, txt = generate.write_pair(tmp_path)
    hitachi_tif(tif, "\r".join(hitachi_lines(tif.name, Magnification="60000")))
    (d,) = walk(tmp_path, hitachi.COLLECTION.formats).datasets
    extracted = hitachi.Hitachi().extract(d, str(tmp_path))
    assert extracted.values["original_metadata"]["SemImageFile.Magnification"] == (
        "60000"
    )
    assert "Magnification 60000" in extracted.summary
    assert "Magnification=50000" in txt.read_text()


# Only the headers are read


def test_a_large_tiff(tmp_path):
    tif, _ = generate.write_pair(tmp_path)
    os.truncate(tif, 1 << 30)  # sparse: nothing written
    (d,) = walk(tmp_path, hitachi.COLLECTION.formats).datasets
    fmt = hitachi.Hitachi()
    fmt.extract(d, str(tmp_path))  # once first: rchar counts the reads of imports too
    before = rchar()
    fmt.extract(d, str(tmp_path))
    read = rchar() - before
    print(f"{Path(tif).name}: {read} bytes read of {Path(tif).stat().st_size}")
    assert read < 256 * 1024
