"""EMPAD extraction (spec formats/empad, "EMPAD metadata is extracted from the header")."""

from modama_formats_em.testing import described


def test_a_representative_empad_acquisition(collection_tests, tmp_path):
    (scan,) = described(collection_tests, "scan_v1_2_2", tmp_path)
    assert scan.description.startswith(
        "scan of 32×64 positions, 128×128 pixel frames, 1 ms exposure, 2026-03-25 16:47; "
    )
    assert scan.subjects == ["empad", "4D-STEM"]
    # Only the header is read, not the raw file of 136 MB
    assert scan.bytes_read < 64 * 1024


def test_a_series(collection_tests, tmp_path):
    (series,) = described(collection_tests, "pair", tmp_path)
    assert series.description.startswith(
        "series of 4 frames, 128×128 pixel frames, 1 ms exposure, 2022-05-02 17:28; "
    )
    assert series.subjects == ["empad"]
