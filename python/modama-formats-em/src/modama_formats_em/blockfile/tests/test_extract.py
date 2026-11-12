"""Block file recognition and extraction (spec formats/blockfile), one test per scenario.

Run with -s to see each description, its subjects and the bytes the extractor read.
"""

import os

from modama_crawler.testing import recognise
from modama_crawler.walk import walk

from modama_formats_em.testing import described, rchar


def test_a_block_file_from_astar(collection_tests, tmp_path):
    (d,) = recognise(collection_tests, "scan", tmp_path).datasets
    assert (d.type, d.format, d.members, d.basis) == (
        "application/x.blockfile",
        "em/blockfile",
        ("/test2.blo",),
        "IMGBLO header",
    )


def test_a_text_file_named_like_a_block_file(collection_tests, tmp_path):
    result = recognise(collection_tests, "text_blo", tmp_path)
    (d,) = result.datasets
    assert (d.anchor, d.type, d.format) == ("/notes.blo", "text/plain", "")
    assert result.all_warnings() == []


def test_a_representative_block_file(collection_tests, tmp_path):
    (scan,) = described(collection_tests, "scan", tmp_path)
    assert scan.description.startswith(
        "scan of 3×2 positions, step 64.0×64.0 nm, 5×5 pixel diffraction patterns, "
        "beam energy 200.0 kV, camera length 0.2 m, scan rotation 25.0°, "
        "2015-12-01 15:43; "
    )
    assert scan.subjects == ["NanoMegas ASTAR block file", "4D-STEM"]


def test_a_scan_rotation_of_0_is_left_out(collection_tests, tmp_path):
    # Not a scenario of its own: the requirement's "where it is not 0"
    tree = collection_tests.materialise("scan", tmp_path)
    with open(tree / "test2.blo", "r+b") as f:
        f.seek(28)  # Scan_rotation, uint16 (get_header_dtype_list)
        f.write(bytes(2))
    (d,) = walk(tree, collection_tests.collection.formats).datasets
    (blockfile,) = collection_tests.collection.formats
    summary = blockfile.extract(d, str(tree)).summary
    assert summary[-2:] == ["camera length 0.2 m", "2015-12-01 15:43"]


def test_the_header_not_the_data(collection_tests, tmp_path):
    (whole,) = described(collection_tests, "scan", tmp_path / "whole")
    (cut,) = described(collection_tests, "header_only", tmp_path / "cut")
    assert cut.dataset.size == 0x1000
    assert cut.dataset.extraction.extracted.summary == (
        whole.dataset.extraction.extracted.summary
    )
    assert cut.subjects == whole.subjects
    # A large file: the header with the read buffer of the file RosettaSciIO
    # opens, not the patterns (16 MiB of zeros after the scan, sparse)
    tree = collection_tests.materialise("scan", tmp_path / "large")
    os.truncate(tree / "test2.blo", 16 << 20)
    (d,) = walk(tree, collection_tests.collection.formats).datasets
    (blockfile,) = collection_tests.collection.formats
    blockfile.extract(d, str(tree))  # once first: rchar counts the imports' reads too
    before = rchar()
    blockfile.extract(d, str(tree))
    assert rchar() - before < 1 << 20
