"""Direct Electron extraction (spec formats/de), one test per scenario.

Run with -s to see each description, its subjects and the bytes the extractor read.
"""

import logging
import os
import shutil

from modama_crawler.walk import walk

from modama_formats_em.testing import described, rchar, recorded_reads

from .generate import ACQUISITION

SUMMARY_274 = (
    "DESim, Integrating, Instrument Accelerating Voltage (V) 300000, "
    "Exposure Time (seconds) 0.045712, Frames Per Second 700, Raster, "
    "Scan - Size X 8, Scan - Size Y 4, Mon Oct 21 14:36:50 2024; "
)


def values(acq) -> dict:
    return acq.dataset.extraction.extracted.values


def test_a_representative_acquisitions_values(collection_tests, tmp_path):
    (acq,) = described(collection_tests, "acquisition_274", tmp_path)
    original = values(acq)["original_metadata"]
    assert original["Server Software Version"] == "2.7.4.10190 (Debug Build)"
    assert original["Exposure Rate (e-/pix/s)"] == "212.755735"
    assert original["Camera SN"] == ""
    # The file's 552 entries but the 6 option lists of the skip list (3 `…
    # Allowed Values`, `Preset - List`, `Scan - Preset List`, `Scan - Virtual
    # Detector Preset List`)
    assert len(original) == 546
    assert list(original)[:3] == [
        "Server Software Version",
        "Timestamp (seconds since Epoch)",
        "Local time",
    ]


def test_a_representative_acquisition(collection_tests, tmp_path):
    (acq,) = described(collection_tests, "acquisition_274", tmp_path)
    assert acq.description.startswith(SUMMARY_274)
    assert acq.subjects == ["Direct Electron acquisition", "DESim"]


def test_an_entry_nobody_has_seen(collection_tests, tmp_path):
    (acq,) = described(collection_tests, "new_entry", tmp_path)
    assert values(acq)["original_metadata"]["Made Up Entry (units)"] == "42"


def test_option_lists_are_left_out(collection_tests, tmp_path):
    (acq,) = described(collection_tests, "acquisition_274", tmp_path)
    original = values(acq)["original_metadata"]
    for key in (
        "Instrument Accelerating Voltage (V) Allowed Values",
        "Preset - List",
        "Scan - Preset List",
    ):
        assert key not in original
    assert original["Instrument Accelerating Voltage (V)"] == "300000"
    assert original["Preset - Current"] == "Custom"


def test_the_movie_is_not_read(collection_tests, tmp_path):
    # A movie of 1 GiB, sparse: the extraction reads the info file (ours and
    # RosettaSciIO's read) and nothing of the movie
    tree = tmp_path / "big"
    tree.mkdir()
    info = tree / "20241021_00405_info.txt"
    shutil.copyfile(ACQUISITION / info.name, info)
    with open(tree / "20241021_00405_movie.mrc", "wb") as f:
        f.truncate(1 << 30)
    (d,) = walk(tree, collection_tests.collection.formats).datasets
    (fmt,) = collection_tests.collection.formats
    fmt.extract(d, str(tree))  # once first: imports
    before = rchar()
    fmt.extract(d, str(tree))
    read = rchar() - before
    print(f"{read} bytes read of {d.size}")
    assert read <= 2 * os.path.getsize(info) + (64 << 10)
    with recorded_reads(tree) as reads:
        fmt.extract(d, str(tree))
    assert "/20241021_00405_movie.mrc" not in reads


def test_a_raster_scan(collection_tests, tmp_path):
    (acq,) = described(collection_tests, "acquisition_274", tmp_path)
    mapped = values(acq)["mapped_metadata"]
    assert mapped["Acquisition_instrument.TEM.detector"] == "DESim"
    assert mapped["General.timestamp"] == "1729539410"
    assert [(a["name"], a["size"]) for a in values(acq)["axes"]] == [
        ("y", 4),
        ("x", 8),
        ("ky", 4),
        ("kx", 8),
    ]


def test_a_scan_that_is_not_a_raster(collection_tests, tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="modama_formats_em.de"):
        (acq,) = described(collection_tests, "xy_scan_275", tmp_path)
    assert list(values(acq)) == ["original_metadata"]
    assert acq.description.startswith(
        "DESim, Integrating, Instrument Accelerating Voltage (V) 300000, "
        "Exposure Time (seconds) 30, Frames Per Second 1, XY File, "
        "Scan - Size X 5, Scan - Size Y 5; "
    )
    assert any(
        "no mapping by RosettaSciIO" in r.getMessage()
        and "Scan position file is required" in r.getMessage()
        for r in caplog.records
    )
    assert set(acq.reads) == {"/20250429_06699_info.txt"}


def test_a_renamed_info_file(collection_tests, tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="modama_formats_em.de"):
        (acq,) = described(collection_tests, "renamed_info", tmp_path)
    assert values(acq)["original_metadata"]["Dataset Name"] == "20241021_00405"
    assert any(
        "Dataset Name 20241021_00405" in r.getMessage()
        and "20241021_00406_info.txt" in r.getMessage()
        for r in caplog.records
    )


def test_an_info_file_of_de_server_2_7_2(collection_tests, tmp_path):
    # Spec formats/de, "An info file of DE-Server 2.7.2 alone": CRLF line ends,
    # no voltage and no local time in this version
    (acq,) = described(collection_tests, "lone_info_272", tmp_path)
    assert acq.description.startswith(
        "CeleritasXS, Integrating, Exposure Time (seconds) 0.3325952, "
        "Frames Per Second 40000, Raster, Scan - Size X 8, Scan - Size Y 32; "
    )
    assert values(acq)["original_metadata"]["Camera SN"] == "812"
