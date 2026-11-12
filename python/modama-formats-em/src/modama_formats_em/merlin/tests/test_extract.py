"""Merlin recognition and extraction (spec formats/merlin), one test per scenario.

Run with -s to see each description, its subjects and the bytes the extractor read.
"""

import pytest
from modama_crawler.testing import recognise
from modama_crawler.walk import walk

from modama_formats_em.merlin import MAX_HEADER
from modama_formats_em.testing import described


def test_a_frame_series_with_its_header(collection_tests, tmp_path):
    result = recognise(collection_tests, "frame_series", tmp_path)
    (d,) = result.datasets
    assert (d.anchor, d.format, len(d.members)) == ("/acq.hdr", "em/merlin", 201)
    assert set(d.members) == {"/acq.hdr", *(f"/acq_{n}.mib" for n in range(1, 201))}


def test_frames_without_a_header(collection_tests, tmp_path):
    result = recognise(collection_tests, "frames_without_header", tmp_path)
    assert [(d.anchor, d.type, d.format) for d in result.datasets] == [
        ("/acq_1.mib", "application/x.merlin-mib", ""),
        ("/acq_2.mib", "application/x.merlin-mib", ""),
    ]
    ((where, text),) = result.warnings
    assert where == "/" and "without a Merlin header" in text


def test_a_representative_acquisition(collection_tests, tmp_path):
    (acq,) = described(collection_tests, "single_frame", tmp_path)
    assert acq.description.startswith(
        "1 frame, 256×256 pixels, 6-bit, Merlin Quad, 2021-04-15 14:43; "
    )
    assert acq.subjects == ["Quantum Detectors Merlin", "Merlin Quad"]


def test_a_header_that_is_not_utf8(collection_tests, tmp_path):
    (acq,) = described(collection_tests, "not_utf8", tmp_path)
    assert acq.description.startswith("1 frame, 256×256 pixels, 6-bit, Merlin Quad, ")
    assert acq.subjects == ["Quantum Detectors Merlin", "Merlin Quad"]


def test_the_date_key_names_its_fields_in_another_order(collection_tests, tmp_path):
    (acq,) = described(collection_tests, "not_utf8", tmp_path / "a")
    assert acq.description.startswith(
        "1 frame, 256×256 pixels, 6-bit, Merlin Quad, 2019-02-22 10:27; "
    )
    # A value in another form, here with AM/PM appended, is not guessed at
    tree = collection_tests.materialise("not_utf8", tmp_path / "b")
    hdr = tree / "acq.hdr"
    hdr.write_bytes(hdr.read_bytes().replace(b"10:27:28", b"10:27:28 AM"))
    (d,) = walk(tree, collection_tests.collection.formats).datasets
    (merlin,) = collection_tests.collection.formats
    with pytest.raises(ValueError, match="22/02/2019 10:27:28 AM"):
        merlin.extract(d, str(tree))


def test_an_oversized_header_is_not_parsed(collection_tests, tmp_path):
    # Not a scenario of its own: the header is read whole (review 2026-11-11, 5)
    tree = collection_tests.materialise("single_frame", tmp_path)
    (d,) = walk(tree, collection_tests.collection.formats).datasets
    with open(str(tree) + d.anchor, "ab") as f:
        f.write(b" " * MAX_HEADER)
    (merlin,) = collection_tests.collection.formats
    with pytest.raises(ValueError, match="header of"):
        merlin.extract(d, str(tree))
