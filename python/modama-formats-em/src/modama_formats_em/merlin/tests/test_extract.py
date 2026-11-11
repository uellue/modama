"""Merlin recognition and extraction (spec formats/merlin), one test per scenario.

Run with -s to see each description, its subjects and the bytes the extractor read.
"""

from modama_crawler.testing import recognise

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
