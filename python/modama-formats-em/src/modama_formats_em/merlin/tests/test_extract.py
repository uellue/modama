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
        "Frames in Acquisition (Number) 1, frame 256, 256, Counter Depth (number) 6, "
        "Merlin Quad, 15/04/2021 14:43:23; "
    )
    assert acq.subjects == ["Quantum Detectors Merlin", "Merlin Quad"]
    values = acq.dataset.extraction.extracted.values
    assert list(values) == ["original_metadata", "mapped_metadata"]
    original = values["original_metadata"]
    assert len(original) == 27
    assert original["Counter Depth (number)"] == "6"
    assert original["Sensor Bias (V)"] == "120 V"
    assert values["mapped_metadata"] == {
        "frames": 1,
        "frame": [256, 256],
        "counter_depth": 6,
        "readout": "Merlin Quad",
        "acquired": "2021-04-15T14:43:23",
    }


def test_every_header_entry_as_the_file_writes_it(collection_tests, tmp_path):
    (acq,) = described(collection_tests, "single_frame", tmp_path)
    original = acq.dataset.extraction.extracted.values["original_metadata"]
    assert original["Assembly Size (NX1, 2X2)"] == "   1x1"
    assert original["Dead Time File"] == r"Dummy (C:\<NUL>\)"
    assert original["Flat Field File"] == "None"
    assert original["Humidity (%)"] == "Board Humidity 14.690918 "


def edited(ct, fixture: str, workdir, old: bytes, new: bytes):
    """The extraction of a fixture's header with old replaced by new, once."""
    tree = ct.materialise(fixture, workdir)
    (hdr,) = tree.glob("*.hdr")
    hdr.write_bytes(hdr.read_bytes().replace(old, new, 1))
    (d,) = walk(tree, ct.collection.formats).datasets
    (merlin,) = ct.collection.formats
    return merlin.extract(d, str(tree))


def test_an_entry_nobody_has_seen_before(collection_tests, tmp_path):
    made_up = b"Made-up Setting (a, b):\tmade-up value\r\nMade-up Empty:\t\r\nEnd\t"
    extracted = edited(collection_tests, "single_frame", tmp_path, b"End\t", made_up)
    original = extracted.values["original_metadata"]
    assert original["Made-up Setting (a, b)"] == "made-up value"
    # Empty, and kept as empty text (decision 161)
    assert original["Made-up Empty"] == ""
    assert len(original) == 29


def test_a_value_not_suitable_for_text_is_left_out(collection_tests, tmp_path):
    made_up = b"Made-up Bytes:\t\x01\x02\x03\r\nEnd\t"
    extracted = edited(collection_tests, "single_frame", tmp_path, b"End\t", made_up)
    original = extracted.values["original_metadata"]
    assert "Made-up Bytes" not in original
    assert len(original) == 27


def test_a_blank_line_or_a_line_without_a_tab(collection_tests, tmp_path):
    lines = b"\r\nMade-up line without a tab\r\nEnd\t"
    extracted = edited(collection_tests, "single_frame", tmp_path, b"End\t", lines)
    original = extracted.values["original_metadata"]
    # The blank line is skipped, the line without a tab is a key with an empty value
    assert original["Made-up line without a tab"] == ""
    assert len(original) == 28


def test_a_header_that_is_not_utf8(collection_tests, tmp_path):
    (acq,) = described(collection_tests, "not_utf8", tmp_path)
    assert acq.description.startswith(
        "Frames in Acquisition (Number) 1, frame 256, 256, Counter Depth (number) 6, "
        "Merlin Quad, "
    )
    assert acq.subjects == ["Quantum Detectors Merlin", "Merlin Quad"]
    original = acq.dataset.extraction.extracted.values["original_metadata"]
    assert original["Sensor Bias (V, µA)"] == "120 V"


def test_the_date_key_names_its_fields_in_another_order(collection_tests, tmp_path):
    (acq,) = described(collection_tests, "not_utf8", tmp_path / "a")
    assert acq.description.startswith(
        "Frames in Acquisition (Number) 1, frame 256, 256, Counter Depth (number) 6, "
        "Merlin Quad, 22/02/2019 10:27:28; "
    )
    values = acq.dataset.extraction.extracted.values
    assert values["mapped_metadata"]["acquired"] == "2019-02-22T10:27:28"


def test_a_date_in_another_form(collection_tests, tmp_path, caplog):
    # With AM/PM appended: shown as written, not guessed at, with a warning
    extracted = edited(
        collection_tests, "not_utf8", tmp_path, b"10:27:28", b"10:27:28 AM"
    )
    assert extracted.summary[-1] == "22/02/2019 10:27:28 AM"
    assert "acquired" not in extracted.values["mapped_metadata"]
    original = extracted.values["original_metadata"]
    assert original["Time and Date Stamp (yr, mnth, day, hr, min, s)"] == (
        "22/02/2019 10:27:28 AM"
    )
    (warning,) = caplog.records
    assert "'22/02/2019 10:27:28 AM'" in warning.getMessage()


def test_an_oversized_header_is_not_parsed(collection_tests, tmp_path):
    # Not a scenario of its own: the header is read whole (review 2026-11-11, 5)
    tree = collection_tests.materialise("single_frame", tmp_path)
    (d,) = walk(tree, collection_tests.collection.formats).datasets
    with open(str(tree) + d.anchor, "ab") as f:
        f.write(b" " * MAX_HEADER)
    (merlin,) = collection_tests.collection.formats
    with pytest.raises(ValueError, match="header of"):
        merlin.extract(d, str(tree))
