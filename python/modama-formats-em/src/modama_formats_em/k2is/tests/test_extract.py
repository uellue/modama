"""K2IS recognition and extraction (spec formats/k2is), one test per scenario.

Run with -s to see each description, its subjects and the bytes the extractor read.
"""

from modama_crawler.testing import recognise

from modama_formats_em.testing import described


def test_a_capture_with_its_8_sectors(collection_tests, tmp_path):
    result = recognise(collection_tests, "capture", tmp_path)
    (d,) = result.datasets
    assert (d.type, d.format, d.anchor) == (
        "application/x.k2is",
        "em/k2is",
        "/Capture52_.gtg",
    )
    assert d.members == (
        "/Capture52_.gtg",
        *(f"/Capture52_{n}.bin" for n in range(1, 9)),
    )
    assert result.warnings == []


def test_sector_files_without_their_tag_file(collection_tests, tmp_path):
    result = recognise(collection_tests, "sectors_without_tags", tmp_path)
    assert [d.format for d in result.datasets] == [""] * 8
    ((where, text),) = result.warnings
    assert where == "/" and "8 K2IS sector file(s) without a .gtg file" in text


def test_a_tag_file_without_sectors(collection_tests, tmp_path):
    result = recognise(collection_tests, "lone_tags", tmp_path)
    (d,) = result.datasets
    assert (d.type, d.format, d.members) == (
        "application/x.dm-gtg",
        "",
        ("/IDES_DMS_Config.gtg",),
    )
    assert result.warnings == []


def test_another_bin_file(collection_tests, tmp_path):
    types = {
        d.anchor: d.type
        for d in recognise(collection_tests, "other_bin", tmp_path).datasets
    }
    assert types["/data.bin"] != "application/x.k2is-sector"
    assert types["/sector.dat"] == "application/x.k2is-sector"


def test_a_representative_capture(collection_tests, tmp_path):
    (capture,) = described(collection_tests, "capture", tmp_path)
    assert capture.description.startswith(
        "SI Dimensions.Size X 64, SI Dimensions.Size Y 32, Microscope Info.Voltage 300000; "
        "K2IS acquisition, 9 files"
    )
    assert capture.subjects == ["Gatan K2 IS"]
    # The .gtg's tags; the sector files only by their sizes, not read
    assert capture.bytes_read < 2_000
