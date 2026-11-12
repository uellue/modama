"""K2IS recognition and extraction (spec formats/k2is), one test per scenario.

Run with -s to see each description, its subjects and the bytes the extractor read.
"""

from modama_crawler.testing import recognise

from modama_formats_em.testing import described


def test_a_capture_with_its_8_sectors(collection_tests, tmp_path):
    result = recognise(collection_tests, "capture52", tmp_path)
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


def test_a_tag_file_with_7_or_9_sector_files(collection_tests, tmp_path):
    result = recognise(collection_tests, "wrong_count", tmp_path)
    assert {d.format for d in result.datasets} == {""}
    assert len(result.datasets) == 2 + 7 + 9
    # Said at the .gtg, with what is wrong; no warning that the .gtg is missing
    assert sorted(result.warnings) == [
        (
            "/Capture7_.gtg",
            "Capture7_.gtg: 7 sector files Capture7_*.bin, a K2IS acquisition has 8",
        ),
        (
            "/Capture9_.gtg",
            "Capture9_.gtg: 9 sector files Capture9_*.bin, a K2IS acquisition has 8",
        ),
    ]


def test_an_incomplete_capture_next_to_a_complete_one(collection_tests, tmp_path):
    result = recognise(collection_tests, "nested_incomplete", tmp_path)
    (capture,) = [d for d in result.datasets if d.format == "em/k2is"]
    assert capture.members == (
        "/scan_.gtg",
        *(f"/scan_{n}.bin" for n in range(1, 9)),
    )
    assert len(result.datasets) == 1 + 1 + 7
    assert result.warnings == [
        (
            "/scan_2_.gtg",
            "scan_2_.gtg: 7 sector files scan_2_*.bin, a K2IS acquisition has 8",
        )
    ]


def test_extensions_in_upper_case(collection_tests, tmp_path):
    result = recognise(collection_tests, "upper_case", tmp_path)
    assert sorted((d.anchor, len(d.members)) for d in result.datasets) == [
        ("/UPPER_.GTG", 9),
        ("/mixed_.gtg", 9),
    ]
    assert result.warnings == []


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
    (capture,) = described(collection_tests, "capture52", tmp_path)
    assert capture.description.startswith(
        "SI Dimensions.Size X 35, SI Dimensions.Size Y 34, Microscope Info.Cs(mm) 0, "
    )
    assert (
        "Microscope Info.Formatted Voltage 300kV, " in capture.description
        and "Microscope Info.Stage Position" not in capture.description
    )
    assert capture.description.endswith("; K2IS acquisition, 9 files, 27.3 kB, in /")
    assert capture.subjects == ["Gatan K2 IS", "FEI Tecnai Remote"]
    # The .gtg read whole (26,931 bytes, tags only); the fixture's sectors are 40-byte headers
    assert capture.bytes_read < 28_000
