"""DM3 and DM4 recognition and extraction (spec formats/dm), one test per scenario.

Run with -s to see each description, its subjects and the bytes the extractor read.
"""

from modama_crawler.testing import recognise

from modama_formats_em.testing import described


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
        "beam_energy 3, magnification 2500, camera_length 1, 18.3 µm/pixel, 2×2, "
        "DigiScan, Zeiss SEM COM, 2021-05-14 11:41; "
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
        "beam_energy 200, magnification 225000, camera_length 135, 0.249 nm/pixel, "
        "68×68, DigiScan, FEI Titan, 2016-08-08 16:26; "
    )
    assert image.subjects == ["Gatan Digital Micrograph (DM3)", "FEI Titan", "STEM"]


def test_an_rgba_image(collection_tests, tmp_path):
    # RosettaSciIO's file_reader refuses RGBA images when lazy; the tags are still read (F14)
    (image,) = described(collection_tests, "rgba_image_dm4", tmp_path)
    assert image.description.startswith("2×2; Gatan Digital Micrograph file, version 4")
    assert image.subjects == ["Gatan Digital Micrograph (DM4)"]
