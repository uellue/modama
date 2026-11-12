"""Block file recognition and extraction (spec formats/blockfile), one test per scenario.

Run with -s to see each description, its subjects and the bytes the extractor read.
"""

import os
import time

from modama_crawler.testing import recognise
from modama_crawler.walk import walk

from modama_formats_em.testing import described, rchar

SCAN = (
    "NX 3, NY 2, SX 64.0, SY 64.0, DP_SZ 5, Beam_energy 200000, Camera_length 2000, "
    "Scan_rotation 2500, 2015-12-01 15:43"
)
# RosettaSciIO 0.15.0's warning for a MAGIC other than 258
UNKNOWN_MAGIC = (
    "Blockfile has unrecognized header signature. "
    "Will attempt to read, but correctness not guaranteed!"
)


def extracted(collection_tests, tree):
    (d,) = walk(tree, collection_tests.collection.formats).datasets
    (blockfile,) = collection_tests.collection.formats
    return blockfile.extract(d, str(tree))


def test_a_block_file_from_an_instrument(collection_tests, tmp_path):
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
    assert scan.description.startswith(SCAN + "; ")
    assert scan.subjects == ["NanoMegas block file", "4D-STEM"]
    values = scan.dataset.extraction.extracted.values
    assert list(values)[:2] == ["original_metadata", "mapped_metadata"]
    original = values["original_metadata"]
    assert (
        original["blockfile_header.ID"],
        original["blockfile_header.MAGIC"],
        original["blockfile_header.Beam_energy"],
    ) == ("IMGBLO", 258, 200000)
    assert values["mapped_metadata"]["Acquisition_instrument.TEM.beam_energy"] == 200.0


def test_every_field_the_reader_gives(collection_tests, tmp_path, monkeypatch):
    # Every entry minus a skip list, which is empty here (decision of
    # 2026-11-12): all the reader's fields, and one nobody has seen before
    import rsciio.blockfile

    from modama_formats_em.dm import tag_paths

    real = rsciio.blockfile.file_reader

    def with_a_new_field(*args, **kwargs):
        (scan,) = real(*args, **kwargs)
        scan["original_metadata"]["blockfile_header"]["New_field"] = 7
        return [scan]

    tree = collection_tests.materialise("scan", tmp_path)
    (theirs,) = real(str(tree / "test2.blo"), lazy=True)
    monkeypatch.setattr(rsciio.blockfile, "file_reader", with_a_new_field)
    original = extracted(collection_tests, tree).values["original_metadata"]
    assert list(original) == [
        *(k for k, _ in tag_paths(theirs["original_metadata"])),
        "blockfile_header.New_field",
    ]
    assert original["blockfile_header.New_field"] == 7


def test_a_scan_rotation_of_0_is_left_out(collection_tests, tmp_path):
    # Not a scenario of its own: the requirement's "where it is not 0"
    tree = collection_tests.materialise("scan", tmp_path)
    with open(tree / "test2.blo", "r+b") as f:
        f.seek(28)  # Scan_rotation, uint16 (get_header_dtype_list)
        f.write(bytes(2))
    summary = extracted(collection_tests, tree).summary
    assert summary[-2:] == ["Camera_length 2000", "2015-12-01 15:43"]


def test_the_acquisition_time_as_written(collection_tests, tmp_path, monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    try:
        tree = collection_tests.materialise("scan", tmp_path)
        out = extracted(collection_tests, tree)
    finally:
        monkeypatch.undo()
        time.tzset()
    assert out.summary[-1] == "2015-12-01 15:43"
    assert out.values["acquired"] == "2015-12-01T15:43:09.828000"
    assert not any(k.startswith("General.time") for k in out.values["mapped_metadata"])


def test_the_16_bit_variant(collection_tests, tmp_path):
    # The header of the staging file that started this format (decision 232)
    (scan,) = described(collection_tests, "stingray", tmp_path)
    assert scan.description.startswith(
        "NX 7, NY 11, SX 12.5, SY 12.5, DP_SZ 576, Beam_energy 60000, "
        f"Camera_length 6000, 2024-09-17 00:00, reader warning: {UNKNOWN_MAGIC}; "
    )
    values = scan.dataset.extraction.extracted.values
    assert (
        "Blo Bit Depth: 16 bits" in values["original_metadata"]["blockfile_header.Note"]
    )
    assert values["original_metadata"]["blockfile_header.MAGIC"] == 259
    assert values["reader_warnings"] == [UNKNOWN_MAGIC]


def test_the_header_not_the_data(collection_tests, tmp_path):
    (whole,) = described(collection_tests, "scan", tmp_path / "whole")
    (cut,) = described(collection_tests, "header_only", tmp_path / "cut")
    assert cut.dataset.size == 0x1000
    assert cut.dataset.extraction.extracted.summary == (
        whole.dataset.extraction.extracted.summary
    )
    assert cut.subjects == whole.subjects
    # A large file: the header with one read buffer of the file RosettaSciIO
    # opens (128 KiB here, plus np.fromfile's), not the patterns (16 MiB of
    # zeros after the scan, sparse)
    tree = collection_tests.materialise("scan", tmp_path / "large")
    os.truncate(tree / "test2.blo", 16 << 20)
    extracted(collection_tests, tree)  # once first: rchar counts the imports' reads too
    before = rchar()
    extracted(collection_tests, tree)
    assert rchar() - before < 1 << 20
