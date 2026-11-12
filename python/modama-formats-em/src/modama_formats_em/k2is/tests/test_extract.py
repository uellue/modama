"""K2IS recognition and extraction (spec formats/k2is), one test per scenario.

Run with -s to see each description, its subjects and the bytes the extractor read.
"""

import subprocess
import sys
from types import SimpleNamespace

import pytest
from modama_crawler import extraction
from modama_crawler.formats import Dataset
from modama_crawler.records import description
from modama_crawler.testing import recognise
from modama_crawler.walk import walk

from modama_formats_em import k2is
from modama_formats_em.testing import described, stale


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
    assert (
        description(d)
        == "Gatan Digital Micrograph .gtg tag file, 1 file, 26.9 kB, in /"
    )
    assert result.warnings == []


def crawled(ct, fixture, tmp_path):
    """Recognise and extract a fixture as a crawl does; the result carries the extraction failures as warnings."""
    tree = ct.materialise(fixture, tmp_path)
    result = walk(tree, ct.collection.formats)
    extraction.extract(
        result, ct.collection.formats, str(tree), identity="test", workers=1
    )
    return result


@pytest.mark.parametrize(
    "fixture, name", [("text_tags", "notes"), ("empty_tags", "empty")]
)
def test_a_file_named_like_a_tag_file(collection_tests, tmp_path, fixture, name):
    # A lone .gtg without the DM4 header is not a tag file (decision 172)
    result = recognise(collection_tests, fixture, tmp_path)
    (d,) = result.datasets
    assert (d.anchor, d.type, d.format) == (f"/{name}.gtg", "text/plain", "")
    assert d.basis == "single file; em/k2is: not application/x.dm-gtg, no DM header"
    assert description(d).startswith("Plain text document, 1 file, ")
    assert result.all_warnings() == []


def test_records_comments_a_single_file_whose_name_type_was_dropped(tmp_path):
    # Spec records-cli, "A single file whose name type was dropped": the command as typed
    (tmp_path / "notes.gtg").write_text("hello\n")
    run = subprocess.run(
        [sys.executable, "-m", "modama_crawler", "records", "--verbose", str(tmp_path)],
        capture_output=True,
        check=True,
        timeout=120,
    )
    out = run.stdout.decode()
    comment = (
        "<!-- /notes.gtg: text/plain, basis: single file; "
        "em/k2is: not application/x.dm-gtg, no DM header -->"
    )
    assert out.split(comment, 1)[1].lstrip().startswith("<record>")
    assert "<!-- 1 records (1 single files by type), 0 warnings, 0 skipped; " in out


@pytest.mark.parametrize("module", ["format's read", "new type's detection"])
def test_a_lone_tag_file_that_cannot_be_read(
    collection_tests, tmp_path, monkeypatch, module
):
    # Code review finding 1: a stray notes.gtg that cannot be read (stale handle, or
    # moved away after the listing) keeps its type, and the capture next to it stands
    from modama_crawler import formats, mime

    tree = collection_tests.materialise("capture52", tmp_path)
    (tree / "notes.gtg").write_text("hello\n")
    where = formats if module == "format's read" else mime
    monkeypatch.setattr(where, "open", stale("notes.gtg"), raising=False)
    result = walk(tree, collection_tests.collection.formats)
    datasets = {d.anchor: d for d in result.datasets}
    assert set(datasets) == {"/Capture52_.gtg", "/notes.gtg"}
    capture = datasets["/Capture52_.gtg"]
    assert (capture.format, len(capture.members)) == ("em/k2is", 9)
    notes = datasets["/notes.gtg"]
    assert (notes.type, notes.basis) == ("application/x.dm-gtg", "single file")
    assert result.all_warnings() == [
        ("/notes.gtg", "em/k2is: cannot read notes.gtg: Stale file handle; type kept")
    ]
    assert result.listings["/"].retry  # recognised again next crawl


def test_an_empty_tag_file_with_its_8_sectors(collection_tests, tmp_path):
    # A broken capture, not 9 single files (decision 172): reported at extraction
    result = crawled(collection_tests, "empty_capture", tmp_path)
    (d,) = result.datasets
    assert (d.format, d.anchor, len(d.members)) == ("em/k2is", "/Capture7_.gtg", 9)
    ((where, text),) = result.all_warnings()
    assert where == "/Capture7_.gtg"
    assert text.startswith("em/k2is extraction failed: ")


def test_a_broken_capture_next_to_a_complete_one(collection_tests, tmp_path):
    result = crawled(collection_tests, "broken_next_to_complete", tmp_path)
    captures = {d.anchor: d for d in result.datasets}
    assert sorted((a, d.format, len(d.members)) for a, d in captures.items()) == [
        ("/scan_.gtg", "em/k2is", 9),
        ("/scan_2_.gtg", "em/k2is", 9),
    ]
    assert captures["/scan_.gtg"].extraction.extracted is not None
    ((where, text),) = result.all_warnings()
    assert where == "/scan_2_.gtg"
    assert text.startswith("em/k2is extraction failed: ")


def test_another_bin_file(collection_tests, tmp_path):
    types = {
        d.anchor: d.type
        for d in recognise(collection_tests, "other_bin", tmp_path).datasets
    }
    assert types["/data.bin"] != "application/x.k2is-sector"
    assert types["/sector.dat"] == "application/x.k2is-sector"


def test_a_representative_capture(collection_tests, tmp_path):
    (capture,) = described(collection_tests, "capture52", tmp_path)
    # The summary line of DM files' tags (spec formats/dm), the scan as the size
    assert capture.description == (
        "IMAGING, SCANNING, STEM NANOPROBE, 300kV, 320kx, STEM Camera Length 275.0, "
        "K2-IS, K2-IS-0001, Exposure Time (s) 0.0025, Search, Size X 35, Size Y 34, "
        "3/29/2018, 1:28:03 PM; K2IS acquisition, 9 files, 27.3 kB, in /"
    )
    # The tags as values, under their paths, the values not rounded (decision 129)
    tags = capture.dataset.extraction.extracted.values["original_metadata"]
    assert {
        "SI Dimensions.Size X": 35,
        "Microscope Info.Voltage": 300000.0,
        "Acquisition.Device.Active Size (pixels)": (1920, 1792),
        "Microscope Info.Stage Position.Stage Alpha": -2.4043772802208405,
        "DataBar.Acquisition Date": "3/29/2018",
        "DataBar.Device Name": "K2-IS-0001",
        "SI Image Tags.SI.Acquisition.Pixel time (s)": 0.0025,
    }.items() <= tags.items()
    # 359 tags: 52 of them user-interface settings; the 11 without a value are kept (decision 161)
    assert len(tags) == 307
    assert tags["Session Info.Operator"] == []
    # JSON holds no infinity: as Python writes it
    assert tags["Acquisition.Parameters.High Level.Exposure Live Time"] == "inf"
    assert capture.subjects == ["Gatan K2 IS", "FEI Tecnai Remote", "IMAGING", "K2-IS"]
    # The .gtg read whole (26,931 bytes, tags only), and no sector file
    assert capture.bytes_read < 28_000
    assert set(capture.reads) == {"/Capture52_.gtg"}


def test_user_interface_settings_are_left_out(collection_tests, tmp_path):
    (capture,) = described(collection_tests, "capture52", tmp_path)
    tags = capture.dataset.extraction.extracted.values["original_metadata"]
    summary = [f"{path} {value}" for path, value in tags.items()]
    # The image viewer (Acquisition.Parameters.Objects.TagGroup1, and the
    # same under SI Image Tags) and the definition of the Session Info form
    for setting in (
        "cm_stdviewerimagedisplayer",
        "Window Relative Position",
        "Screen Relative Position",
        ".Zoom 1.0",
        "Do Auto Zoom",
        "View Name",
        "Viewer Class",
        "Objects.TagGroup1.",
        "Session Info.Items",
    ):
        assert not [p for p in summary if setting in p], setting
    # The acquisition's processing objects next to the viewer stay, and so does
    # DigiScan's zoom factor, a scan setting
    assert (
        "Acquisition.Parameters.Objects.TagGroup0.Frame Combine Style Copy" in summary
        and "SI Image Tags.DigiScan.Zoom factor 0.06730239987373351" in summary
    )
    # Tags without a value stay, as the reader gives them (decision 161): [] for an empty string
    assert len([p for p in summary if p.endswith(" []")]) == 11


def test_the_groups_at_the_root_whatever_the_tag_order(monkeypatch):
    # Groups of the same names deeper down and earlier in the tree are not the
    # scan shape or the microscope: LiberTEM reads the root (.SI Dimensions)
    tags = {
        "Acquisition": {
            "Microscope Info": {"Name": "nested"},
            "SI Dimensions": {"Size X": 1, "Size Y": 2},
        },
        "Microscope Info": {"Name": "FEI Tecnai Remote"},
        "SI Dimensions": {"Size X": 35, "Size Y": 34},
    }
    monkeypatch.setattr(k2is, "parsed", lambda path: SimpleNamespace(tags_dict=tags))
    extracted = k2is.K2is().extract(Dataset(anchor="/X_.gtg"), "/nowhere")
    assert extracted.subjects == ["FEI Tecnai Remote"]
    assert extracted.summary == ["Size X 35", "Size Y 34"]
