"""Direct Electron recognition (spec formats/de), one test per scenario."""

import time

from modama_crawler import files
from modama_crawler.formats import SLOW, Directory, Entry, run_post
from modama_crawler.testing import recognise

from modama_formats_em.de import INFO
from modama_formats_em.testing import claimed_first, stale

ACQUISITION = {
    "/20241021_00405_info.txt",
    "/20241021_00405_movie.mrc",
    "/20241021_00405_final.mrc",
    "/20241021_00405_ext1_Ext 1.mrc",
    "/20241021_00405_0_Virt 0_sum.mrc",
    "/20241021_00405_1_Virt 1_sum.mrc",
}


def test_an_acquisition_of_de_server_2_7_4(collection_tests, tmp_path):
    result = recognise(collection_tests, "acquisition_274", tmp_path)
    (d,) = result.datasets
    assert (d.anchor, d.type, d.format) == (
        "/20241021_00405_info.txt",
        "application/x.de-acquisition",
        "em/de",
    )
    assert set(d.members) == ACQUISITION
    assert d.basis == "DE-Server info, 6 file(s) 20241021_00405_*"
    assert result.all_warnings() == []


def test_a_numbered_movie_and_a_scan_coordinate_file(collection_tests, tmp_path):
    result = recognise(collection_tests, "xy_scan_275", tmp_path)
    (d,) = result.datasets
    assert d.format == "em/de"
    assert set(d.members) == {
        "/20250429_06699_info.txt",
        "/20250429_06699_0_movie.mrc",
        "/20250429_06699_scan_coordinates.csv",
    }


def test_a_file_nobody_has_seen_with_the_stem(collection_tests, tmp_path):
    result = recognise(collection_tests, "with_log", tmp_path)
    (d,) = result.datasets
    assert set(d.members) == {
        "/20241021_00405_info.txt",
        "/20241021_00405_movie.mrc",
        "/20241021_00405_processing.log",
    }


def test_a_filename_suffix_set_by_the_user(collection_tests, tmp_path):
    result = recognise(collection_tests, "with_suffix", tmp_path)
    (d,) = result.datasets
    assert d.anchor == "/20241021_00405_sampleA_info.txt"
    assert set(d.members) == {
        f"/20241021_00405_sampleA_{kind}"
        for kind in ("info.txt", "movie.mrc", "final.mrc")
    }


def test_stems_that_nest(collection_tests, tmp_path):
    result = recognise(collection_tests, "nested_stems", tmp_path)
    assert {d.anchor: set(d.members) for d in result.datasets} == {
        "/20241021_00405_info.txt": {
            "/20241021_00405_info.txt",
            "/20241021_00405_movie.mrc",
        },
        "/20241021_00405_x_info.txt": {
            "/20241021_00405_x_info.txt",
            "/20241021_00405_x_movie.mrc",
        },
    }


def test_an_info_file_of_a_longer_stem_that_cannot_be_read(
    collection_tests, tmp_path, monkeypatch
):
    # Review of read-limit-per-file: an info file that cannot be read (or is
    # refused over the read limit) keeps its stem's files out of the shorter
    # stem's acquisition; they stay as they are without em/de
    monkeypatch.setattr(
        files, "regular", stale("20241021_00405_x_info.txt", files.regular)
    )
    result = recognise(collection_tests, "nested_stems", tmp_path)
    assert {d.anchor: (d.format, set(d.members)) for d in result.datasets} == {
        "/20241021_00405_info.txt": (
            "em/de",
            {"/20241021_00405_info.txt", "/20241021_00405_movie.mrc"},
        ),
        "/20241021_00405_x_info.txt": ("", {"/20241021_00405_x_info.txt"}),
        "/20241021_00405_x_movie.mrc": ("", {"/20241021_00405_x_movie.mrc"}),
    }


def test_the_sum_claimed_by_another_format(collection_tests, tmp_path):
    # Spec recognition, decision 344: built of the other files, the one the
    # probe took flagged for review
    result = claimed_first(
        collection_tests, "acquisition_274", tmp_path, "20241021_00405_final.mrc"
    )
    by_anchor = {d.anchor: d for d in result.datasets}
    assert by_anchor["/20241021_00405_final.mrc"].format == "probe/claim"
    acq = by_anchor["/20241021_00405_info.txt"]
    assert set(acq.members) == ACQUISITION - {"/20241021_00405_final.mrc"}
    assert result.all_warnings() == [
        (
            "/20241021_00405_info.txt",
            (
                "em/de: 20241021_00405_final.mrc is claimed by probe/claim; "
                "two formats want it"
            ),
        )
    ]


def test_a_claimed_file_of_a_longer_stem(collection_tests, tmp_path):
    # Review, S1: flagged at the acquisition whose stem it belongs to, the
    # longest, as membership is decided; not at the shorter stem too
    result = claimed_first(
        collection_tests, "nested_stems", tmp_path, "20241021_00405_x_movie.mrc"
    )
    by_anchor = {d.anchor: d for d in result.datasets}
    assert set(by_anchor["/20241021_00405_info.txt"].members) == {
        "/20241021_00405_info.txt",
        "/20241021_00405_movie.mrc",
    }
    assert by_anchor["/20241021_00405_x_info.txt"].members == (
        "/20241021_00405_x_info.txt",
    )
    assert result.all_warnings() == [
        (
            "/20241021_00405_x_info.txt",
            (
                "em/de: 20241021_00405_x_movie.mrc is claimed by probe/claim; "
                "two formats want it"
            ),
        )
    ]


def test_many_acquisitions_in_one_folder(collection_tests, tmp_path):
    # Review, M2: recognition grew with the square of the acquisitions in a
    # folder (16,000: about 90 s); each file is now assigned to its stem once
    n = 16_000
    entries = []
    for i in range(n):
        for kind, mime, text in (
            ("info.txt", INFO, b"Server Software Version = 2.7.4\n"),
            ("movie.mrc", "application/octet-stream", b""),
        ):
            name = f"20241021_{i:05}_{kind}"
            path = tmp_path / name
            path.write_bytes(text)
            entries.append(
                Entry(name, str(path), f"/{name}", "file", len(text), 1.0, 1.0, 7, mime)
            )
    d = Directory("/", str(tmp_path), entries, [], "post", uid=7, mtime=1.0)
    start = time.monotonic()
    datasets, _ = run_post(d, collection_tests.collection.formats, SLOW)
    elapsed = time.monotonic() - start
    print(f"{n} acquisitions recognised in {elapsed:.2f} s")
    assert len(datasets) == n
    assert all(len(ds.members) == 2 for ds in datasets)
    assert d.warnings == []
    assert elapsed < 5


def test_another_programs_files_with_a_date_prefix(collection_tests, tmp_path):
    result = recognise(collection_tests, "other_program", tmp_path)
    by_anchor = {d.anchor: d for d in result.datasets}
    assert set(by_anchor) == {"/20240619_1736_info.txt", "/20240619_1736_HAADF.mrc"}
    info = by_anchor["/20240619_1736_info.txt"]
    assert (info.type, info.format) == ("text/plain", "")
    assert info.basis == (
        "single file; em/de: not application/x.de-info, no DE-Server first line"
    )
    assert by_anchor["/20240619_1736_HAADF.mrc"].members == (
        "/20240619_1736_HAADF.mrc",
    )
    assert result.all_warnings() == []


def test_an_info_file_of_de_server_2_7_2_alone(collection_tests, tmp_path):
    result = recognise(collection_tests, "lone_info_272", tmp_path)
    (d,) = result.datasets
    assert (d.anchor, d.format, d.members) == (
        "/20230925_01497_info.txt",
        "em/de",
        ("/20230925_01497_info.txt",),
    )
