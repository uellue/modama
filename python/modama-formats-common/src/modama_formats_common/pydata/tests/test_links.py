"""HDF5 files that link HDF5 files of their folder (change hdf5-links; spec formats/pydata), one test per scenario.

The fixture `linked_scan` and the variants built here are written by h5py
after the structure of a real Eiger 4M master (names and shapes only).
"""

import errno
import os
import subprocess
import sys
from pathlib import Path

import h5py
import numpy
import pytest
from modama_crawler import extraction, inspection
from modama_crawler import walk as walk_module
from modama_crawler.formats import (
    NOT_INSPECTED,
    WANTED_TWICE,
    Collection,
    Dataset,
    Format,
)
from modama_crawler.walk import walk

from modama_formats_common.pydata import Hdf5Links, links

from . import generate
from .test_extract import Opened, datasets, extracted

DATA = [f"scan_data_{i:06d}.h5" for i in range(1, 4)]


def original(x):
    return x.values["original_metadata"]


def mapped(x):
    return x.values["mapped_metadata"]


def names(ds) -> list[str]:
    return [m.rsplit("/", 1)[-1] for m in ds.members]


@pytest.fixture
def scan(collection_tests, tmp_path):
    return collection_tests.materialise("linked_scan", tmp_path)


@pytest.fixture
def pools(monkeypatch):
    """The inspection pools made, in this process."""
    made = []
    get = extraction.Pool.get

    def counted(self):
        if self._pool is None:
            made.append(self)
        return get(self)

    monkeypatch.setattr(extraction.Pool, "get", counted)
    return made


def h5(path: Path, **links_) -> None:
    """An HDF5 file with a dataset and the given external links (name -> (file, path))."""
    with h5py.File(path, "w", track_times=False) as f:
        f.create_dataset("data", data=numpy.zeros((2, 2), dtype="<u2"))
        for name, (file, target) in links_.items():
            f[name] = h5py.ExternalLink(file, target)


# External links are listed as written


def test_a_run_of_external_links(collection_tests, scan):
    x, _ = extracted(collection_tests, scan, "scan_master.h5")
    found = original(x)
    key = "entry.data.data_000001 … data_000012.external_link"
    assert found[key] == [
        "scan_data_000001.h5 … scan_data_000012.h5",
        "/entry/data/data",
    ]
    assert [k for k in found if k.endswith(".external_link")] == [key]


def test_links_outside_a_run(collection_tests, tmp_path):
    h5(
        tmp_path / "m.h5",
        a=("one.h5", "/x"),
        b=("two.h5", "/x"),
        c3=("c3.h5", "/y"),
        c4=("c4.h5", "/z"),
        d9=("d9.h5", "/x"),
        d10=("d10.h5", "/x"),
    )
    x, _ = extracted(collection_tests, tmp_path, "m.h5")
    found = {k: v for k, v in original(x).items() if k.endswith(".external_link")}
    assert found == {
        "a.external_link": ["one.h5", "/x"],
        "b.external_link": ["two.h5", "/x"],
        "c3.external_link": ["c3.h5", "/y"],
        "c4.external_link": ["c4.h5", "/z"],
        "d10.external_link": ["d10.h5", "/x"],
        "d9.external_link": ["d9.h5", "/x"],
    }


def test_a_link_is_never_followed(collection_tests, tmp_path):
    elsewhere, tree = tmp_path / "elsewhere", tmp_path / "tree"
    elsewhere.mkdir()
    tree.mkdir()
    secret = elsewhere / "secret.h5"
    with h5py.File(secret, "w") as s:
        s["value"] = 42
        s.create_dataset("data", data=numpy.arange(4), maxshape=(None,))
    with h5py.File(tree / "m.h5", "w") as f:
        f["relative"] = h5py.ExternalLink("../elsewhere/secret.h5", "/value")
        f["absolute"] = h5py.ExternalLink(str(secret), "/value")
        layout = h5py.VirtualLayout(shape=(4,), dtype="<i8")
        layout[:] = h5py.VirtualSource(str(secret), "data", shape=(4,))
        f.create_virtual_dataset("virtual", layout)
    opened = Opened(secret)
    x, _ = extracted(collection_tests, tree, "m.h5")
    found = original(x)
    assert found["relative.external_link"] == ["../elsewhere/secret.h5", "/value"]
    assert found["absolute.external_link"] == [str(secret), "/value"]
    assert found["virtual.virtual_sources"] == [[str(secret), "data"]]
    assert 42 not in found.values()
    assert not opened.seen()


# Virtual-dataset sources are listed as written


def test_a_virtual_datasets_sources(collection_tests, tmp_path):
    parts = [f"part_{i:03d}.h5" for i in range(1, 5)]
    for name in parts:
        with h5py.File(tmp_path / name, "w") as f:
            f.create_dataset("entry/data/data", data=numpy.zeros((2, 3), "<u2"))
    vds = tmp_path / "vds.h5"
    with h5py.File(vds, "w") as f:
        f.create_dataset("mask", data=numpy.zeros(3, "<u2"))
        layout = h5py.VirtualLayout(shape=(9, 3), dtype="<u2")
        for i, name in enumerate(parts):
            layout[2 * i : 2 * i + 2] = h5py.VirtualSource(
                name, "/entry/data/data", shape=(2, 3)
            )
        layout[8] = h5py.VirtualSource(".", "/mask", shape=(3,))
        f.create_virtual_dataset("entry/data/data", layout)
    watched = [Opened(tmp_path / name) for name in parts]
    x, _ = extracted(collection_tests, tmp_path, "vds.h5")
    assert original(x)["entry.data.data.virtual_sources"] == [
        ["part_001.h5 … part_004.h5", "/entry/data/data"]
    ]
    # the parts are the dataset's members: read as such, never through the link
    assert mapped(x)["virtual_sources"] == 4
    del watched


# A run of links is one entry


def test_runs_whatever_the_stored_order(collection_tests, scan):
    with h5py.File(scan / "scan_master.h5", "r") as f:
        stored = []
        group = f["entry/data"]  # kept: a temporary group's id is closed too soon
        group.id.links.iterate(
            lambda n: stored.append(n.decode()), order=h5py.h5.ITER_NATIVE
        )
    assert stored != sorted(stored)  # the dense form: the names' hash order
    x, _ = extracted(collection_tests, scan, "scan_master.h5")
    runs = [k for k in original(x) if k.endswith(".external_link")]
    assert runs == ["entry.data.data_000001 … data_000012.external_link"]


def test_runs_of_names():
    found = links.runs(
        [
            ("d02", "f02.h5", "/x"),
            ("d01", "f01.h5", "/x"),
            ("d03", "f03.h5", "/x"),
            ("d9", "f9.h5", "/x"),
            ("d10", "f10.h5", "/x"),
            ("e01", "g01.h5", "/x"),
            ("e02", "g02.h5", "/y"),
        ]
    )
    # in byte order d10 comes before d9, and their widths differ: no run
    assert found == [
        ["d01", "d03", "f01.h5", "f03.h5", "/x", 3],
        ["d10", "d10", "f10.h5", "f10.h5", "/x", 1],
        ["d9", "d9", "f9.h5", "f9.h5", "/x", 1],
        ["e01", "e01", "g01.h5", "g01.h5", "/x", 1],
        ["e02", "e02", "g02.h5", "g02.h5", "/y", 1],
    ]


# Links are counted


def test_a_master_whose_data_files_are_all_missing(collection_tests, tmp_path):
    generate.scan_master(tmp_path / "scan_master.h5")
    ds = datasets(collection_tests, tmp_path)["scan_master.h5"]
    assert ds.format == "common/hdf5"
    x, _ = extracted(collection_tests, tmp_path, "scan_master.h5")
    assert mapped(x)["external_links"] == 12
    assert mapped(x)["dangling"] == 12
    assert mapped(x)["found"] == 0


def test_targets_in_other_folders(collection_tests, tmp_path):
    h5(
        tmp_path / "m.h5",
        a=("../raw/a.h5", "/x"),
        c=("sub/c.h5", "/x"),
        c2=("./c.h5", "/x"),
        b=("/acquisition/pc/b.h5", "/x"),
        b2=("/other/pc/b.h5", "/x"),
    )
    (tmp_path / "c.h5").write_text("not looked at\n")
    h5(tmp_path / "b.h5")
    x, _ = extracted(collection_tests, tmp_path, "m.h5")
    assert mapped(x)["elsewhere"] == 3
    assert mapped(x)["found"] == 1
    assert "c.h5" in datasets(collection_tests, tmp_path)


def test_the_folder_is_listed_once_and_no_target_opened(
    collection_tests, scan, monkeypatch
):
    d = datasets(collection_tests, scan)["scan_master.h5"]
    fmt = next(f for f in collection_tests.collection.formats if f.id == d.format)
    listed = []
    real = os.scandir
    monkeypatch.setattr(
        os, "scandir", lambda path=".": listed.append(path) or real(path)
    )
    watched = [Opened(scan / name) for name in DATA[1:]]  # not the first member
    x = fmt.extract(d, str(scan))
    assert listed == [str(scan)]
    assert mapped(x)["found"] == 3
    assert not any(w.seen() for w in watched)


def test_a_listing_gives_the_same_answer_every_time(scan):
    from modama_crawler import files

    answers = []
    for _ in range(3):
        with files.Counted(files.regular(str(scan / "scan_master.h5"))) as f:
            answers.append(links.listed(f))
    assert answers[0] == answers[1] == answers[2]
    assert len(answers[0]["external"]) == 12 and not answers[0]["cut"]


def test_a_windows_path(collection_tests, tmp_path):
    h5(tmp_path / "m.h5", x=("C:\\data\\x.h5", "/x"))
    h5(tmp_path / "x.h5")
    x, _ = extracted(collection_tests, tmp_path, "m.h5")
    assert mapped(x)["dangling"] == 1
    assert datasets(collection_tests, tmp_path)["x.h5"].format == "common/hdf5"


# Dangling links are no error


def test_a_stopped_acquisition(collection_tests, scan):
    result = walk(scan, collection_tests.collection.formats)
    assert not result.all_warnings()
    x, _ = extracted(collection_tests, scan, "scan_master.h5")
    assert mapped(x)["external_links"] == 12
    assert mapped(x)["found"] == 3
    assert mapped(x)["dangling"] == 9


# HDF5 files linked by a file of their folder are one dataset


def test_an_acquisition_with_its_master(collection_tests, scan):
    found = datasets(collection_tests, scan)
    assert list(found) == ["scan_master.h5"]
    ds = found["scan_master.h5"]
    assert ds.format == "common/hdf5links"
    assert ds.type == "application/vnd.hdfgroup.hdf5"
    assert names(ds) == [*DATA, "scan_master.h5"]
    assert ds.basis.startswith("external links to 3 HDF5 files of this folder")


def test_not_by_name(collection_tests, scan):
    (scan / "scan_master.h5").rename(scan / "run7.h5")
    h5(scan / "run7_master.h5")
    found = datasets(collection_tests, scan)
    assert names(found["run7.h5"]) == ["run7.h5", *DATA]
    assert found["run7_master.h5"].format == "common/hdf5"


def test_a_nexus_file_is_no_anchor(collection_tests, scan, pools):
    (scan / "scan_master.h5").rename(scan / "scan.nxs")
    found = datasets(collection_tests, scan)
    assert found["scan.nxs"].format == "common/nexus"
    assert {found[n].format for n in DATA} == {"common/hdf5"}


def test_an_emd_file_is_not_listed(collection_tests, tmp_path, pools):
    h5(tmp_path / "a.emd", d1=("d1.h5", "/data"))
    h5(tmp_path / "d1.h5")
    found = datasets(collection_tests, tmp_path)
    assert found["a.emd"].format == "common/hdf5"
    assert found["d1.h5"].format == "common/hdf5"


def test_a_generic_name_linked_by_an_absolute_path(collection_tests, tmp_path):
    shared, tree = tmp_path / "calibration" / "shared", tmp_path / "tree"
    shared.mkdir(parents=True)
    tree.mkdir()
    h5(shared / "flatfield.h5")
    h5(tree / "scan.h5", flatfield=(str(shared / "flatfield.h5"), "/data"))
    h5(tree / "flatfield.h5")
    opened = Opened(shared / "flatfield.h5")
    found = datasets(collection_tests, tree)
    assert names(found["scan.h5"]) == ["flatfield.h5", "scan.h5"]
    extracted(collection_tests, tree, "scan.h5")
    assert not opened.seen()


def test_a_virtual_dataset_over_files_of_the_folder(collection_tests, tmp_path):
    parts = [f"part_{i:03d}.h5" for i in range(1, 5)]
    for name in parts:
        with h5py.File(tmp_path / name, "w") as f:
            f.create_dataset("data", data=numpy.zeros((2, 3), "<u2"))
    with h5py.File(tmp_path / "vds.h5", "w") as f:
        layout = h5py.VirtualLayout(shape=(8, 3), dtype="<u2")
        for i, name in enumerate(parts):
            layout[2 * i : 2 * i + 2] = h5py.VirtualSource(name, "data", shape=(2, 3))
        f.create_virtual_dataset("data", layout)
    found = datasets(collection_tests, tmp_path)
    assert names(found["vds.h5"]) == [*parts, "vds.h5"]
    assert "virtual-dataset sources" in found["vds.h5"].basis


def test_a_self_link(collection_tests, tmp_path):
    h5(tmp_path / "m.h5", me=("m.h5", "/data"), d1=("d1.h5", "/data"))
    h5(tmp_path / "d1.h5")
    found = datasets(collection_tests, tmp_path)
    assert names(found["m.h5"]) == ["d1.h5", "m.h5"]
    x, _ = extracted(collection_tests, tmp_path, "m.h5")
    assert mapped(x)["found"] == 1
    assert mapped(x)["external_links"] == 2


def test_a_link_back_to_the_master(collection_tests, scan):
    with h5py.File(scan / DATA[0], "a") as f:
        f["master"] = h5py.ExternalLink("scan_master.h5", "/entry")
    found = datasets(collection_tests, scan)
    assert names(found["scan_master.h5"]) == [*DATA, "scan_master.h5"]


def test_two_files_that_name_each_other(collection_tests, tmp_path):
    h5(tmp_path / "a.h5", b=("b.h5", "/data"))
    h5(tmp_path / "b.h5", a=("a.h5", "/data"))
    found = datasets(collection_tests, tmp_path)
    assert found["a.h5"].format == found["b.h5"].format == "common/hdf5"
    assert "names b.h5, named by b.h5: no anchor" in found["a.h5"].basis
    assert "names a.h5, named by a.h5: no anchor" in found["b.h5"].basis


def test_a_target_that_is_not_hdf5(collection_tests, tmp_path):
    h5(tmp_path / "m.h5", d1=("d1.h5", "/data"), d2=("d2.h5", "/data"))
    h5(tmp_path / "d1.h5")
    (tmp_path / "d2.h5").write_text("a text file\n")
    found = datasets(collection_tests, tmp_path)
    assert names(found["m.h5"]) == ["d1.h5", "m.h5"]
    assert found["d2.h5"].format != "common/hdf5"
    x, _ = extracted(collection_tests, tmp_path, "m.h5")
    assert mapped(x)["found"] == 2


def test_a_file_with_an_hdf5_name_that_hdf5_cannot_open(collection_tests, tmp_path):
    h5(tmp_path / "m.h5", d1=("d1.h5", "/data"), broken=("broken.h5", "/data"))
    h5(tmp_path / "d1.h5")
    h5(tmp_path / "whole.h5")
    with open(tmp_path / "whole.h5", "rb") as f:
        (tmp_path / "broken.h5").write_bytes(f.read(100))
    (tmp_path / "whole.h5").unlink()
    found = datasets(collection_tests, tmp_path)
    assert names(found["m.h5"]) == ["d1.h5", "m.h5"]
    assert found["broken.h5"].format == "common/hdf5"


# A file that two anchors name stays its own dataset


def test_a_file_two_masters_link(collection_tests, tmp_path):
    h5(tmp_path / "a.h5", s=("shared.h5", "/data"), o=("only_a.h5", "/data"))
    h5(tmp_path / "b.h5", s=("shared.h5", "/data"))
    h5(tmp_path / "shared.h5")
    h5(tmp_path / "only_a.h5")
    found = datasets(collection_tests, tmp_path)
    assert names(found["a.h5"]) == ["a.h5", "only_a.h5"]
    shared = "shared.h5 is also linked by {}, so it is in neither's dataset"
    assert shared.format("b.h5") in found["a.h5"].basis
    assert found["b.h5"].format == found["shared.h5"].format == "common/hdf5"
    # b.h5 names nothing but shared.h5: no dataset of its own links, the same note
    assert shared.format("a.h5") in found["b.h5"].basis
    for name in ("a.h5", "b.h5"):
        x, _ = extracted(collection_tests, tmp_path, name)
        assert mapped(x)["dangling"] == 0


# A target name is never opened


def test_a_target_name_that_climbs_out(collection_tests, tmp_path):
    tree = tmp_path / "a" / "b"
    tree.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    h5(outside / "x.h5")
    h5(tree / "m.h5", up=("../../outside/x.h5", "/data"), x=("x.h5", "/data"))
    h5(tree / "x.h5")
    opened = Opened(outside / "x.h5")
    found = datasets(collection_tests, tree)
    assert names(found["m.h5"]) == ["m.h5", "x.h5"]
    x, _ = extracted(collection_tests, tree, "m.h5")
    assert mapped(x)["elsewhere"] == 1
    assert not opened.seen()


# Recognition of links is bounded


def test_one_hdf5_file_alone_is_not_opened(collection_tests, tmp_path, pools):
    h5(tmp_path / "m.h5", d1=("d1.h5", "/data"))
    (tmp_path / "notes.txt").write_text("notes\n")
    datasets(collection_tests, tmp_path)
    assert pools == []


class ClaimsNotes(Format):
    """A probe at priority 70 that claims notes.txt, as common/docx claims a .docx."""

    type = "x/notes"
    priority = 70
    reacts_to = frozenset({"text/plain"})

    def recognize(self, d):
        for e in d.of_type("text/plain"):
            yield Dataset(anchor=e.rel, basis="probe")


def test_one_hdf5_file_alone_is_not_opened_beside_a_claimed_file(
    collection_tests, tmp_path, pools
):
    # Second code review, S2: a claimed file of another kind is no HDF5 file
    h5(tmp_path / "m.h5", d1=("d1.h5", "/data"))
    (tmp_path / "notes.txt").write_text("notes\n")
    probe = ClaimsNotes()
    Collection("t", [probe])
    walk(tmp_path, [*collection_tests.collection.formats, probe])
    assert pools == []


def test_too_many_hdf5_files_in_a_folder(collection_tests, tmp_path, pools):
    h5(tmp_path / "m.h5", d1=("f0001.h5", "/data"), d2=("f0002.h5", "/data"))
    for i in range(1, 201):
        h5(tmp_path / f"f{i:04d}.h5")
    result = walk(tmp_path, collection_tests.collection.formats)
    assert pools == []
    assert {d.format for d in result.datasets} == {"common/hdf5"}
    assert any(
        "201 HDF5 files, over the limit of 200" in text
        for _, text in result.all_warnings()
    )


def test_a_file_of_many_objects(collection_tests, tmp_path):
    with h5py.File(tmp_path / "m.h5", "w", track_times=False) as f:
        f["c"] = h5py.ExternalLink("c.h5", "/data")
        deep = f.create_group("deep")
        for i in range(6000):
            deep.create_group(f"g{i:04d}")
        deep.create_group("zz")["d"] = h5py.ExternalLink("d.h5", "/data")
    h5(tmp_path / "c.h5")
    h5(tmp_path / "d.h5")
    result = walk(tmp_path, collection_tests.collection.formats)
    found = {d.anchor.rsplit("/", 1)[-1]: d for d in result.datasets}
    assert names(found["m.h5"]) == ["c.h5", "m.h5"]
    assert found["d.h5"].format == "common/hdf5"
    assert any(
        "links listed up to 5000 objects" in w for w in found["m.h5"].warnings
    ) or any("links listed up to 5000 objects" in t for _, t in result.all_warnings())


def test_a_file_over_its_budget(collection_tests, scan, monkeypatch):
    monkeypatch.setattr(Hdf5Links, "read_limit", 1000)
    result = walk(scan, collection_tests.collection.formats)
    found = {d.anchor.rsplit("/", 1)[-1]: d for d in result.datasets}
    assert found["scan_master.h5"].format == "common/hdf5"
    assert {found[n].format for n in DATA} == {"common/hdf5"}
    warned = [t for r, t in result.all_warnings() if r.endswith("scan_master.h5")]
    assert (
        "common/hdf5links: scan_master.h5 over its read limit of 1000 bytes; "
        "not read further"
    ) in warned
    # The same file gives the same outcome: not marked as tried again (340)
    assert not any(NOT_INSPECTED in t for t in warned)
    assert not any(listing.retry for listing in result.listings.values())


def corrupt(path: Path) -> None:
    """One byte of a link name flipped: HDF5's checksum of the link storage fails."""
    data = bytearray(path.read_bytes())
    data[data.find(b"data_000005") + 3] ^= 0xFF
    path.write_bytes(bytes(data))


def test_a_corrupt_master_is_a_final_result(collection_tests, scan):
    # Code review of hdf5-links, S1: a deterministic error of the library while
    # listing is the result for that state of the file, not retried every crawl
    corrupt(scan / "scan_master.h5")
    result = walk(scan, collection_tests.collection.formats)
    found = {d.anchor.rsplit("/", 1)[-1]: d for d in result.datasets}
    assert found["scan_master.h5"].format == "common/hdf5"
    warned = [t for r, t in result.all_warnings() if r.endswith("scan_master.h5")]
    assert any("links not listed" in t and "checksum" in t for t in warned)
    assert not any(NOT_INSPECTED in t for t in warned)
    assert not any(listing.retry for listing in result.listings.values())


def test_an_error_of_our_own_code_is_not_final(scan, monkeypatch):
    # Second code review, nit: only h5py's errors are a final result; ours raise,
    # and the inspection's outcome "failed" is tried again next crawl
    from modama_crawler import files

    def broken(file, virtual=False):
        raise KeyError("a bug of ours")

    monkeypatch.setattr(links, "matched", broken)
    with (
        files.Counted(files.regular(str(scan / "scan_master.h5"))) as f,
        pytest.raises(KeyError),
    ):
        links.listed(f)


def test_one_group_of_many_links(collection_tests, tmp_path):
    # Code review, S2: the links of one large group are counted as HDF5 hands them
    # over and cut at 5,000; the extraction says its walk was cut. (100,000 links
    # still read 20 MB when cut at 5,000, each link's value looked up by name:
    # such a file is over its budget of 4 MiB, the same on every crawl.)
    with h5py.File(tmp_path / "m.h5", "w", libver="latest", track_times=False) as f:
        for i in range(20_000):  # in the root group, the last the walk sees
            f[f"l{i:06d}"] = h5py.ExternalLink("d1.h5", "/data")
    h5(tmp_path / "d1.h5")
    from modama_crawler import files

    with files.Counted(files.regular(str(tmp_path / "m.h5"))) as f:
        assert links.listed(f)["cut"]
        # the iteration stopped: 592,133 bytes, against 792,325 when all 20,000
        # were collected first (h5py 3.16.0, HDF5 2.0.0)
        assert f.read_bytes < 700_000
    result = walk(tmp_path, collection_tests.collection.formats)
    found = {d.anchor.rsplit("/", 1)[-1]: d for d in result.datasets}
    assert names(found["m.h5"]) == ["d1.h5", "m.h5"]
    assert any("links listed up to 5000 objects" in t for _, t in result.all_warnings())
    x, _ = extracted(collection_tests, tmp_path, "m.h5")
    assert "object limit" in mapped(x)["walk"]  # the counts are not complete


class ClaimsD1(Format):
    """A probe at priority 70 that claims d1.h5 before common/hdf5links (344)."""

    type = "x/claimed"
    priority = 70
    reacts_to = frozenset({"application/vnd.hdfgroup.hdf5"})

    def recognize(self, d):
        for e in d.of_type("application/vnd.hdfgroup.hdf5"):
            if e.name == "d1.h5":
                yield Dataset(anchor=e.rel, basis="probe")


def test_a_link_target_another_format_claimed(collection_tests, tmp_path):
    # Code review, S3: the warning of 344 also when it is the only target
    h5(tmp_path / "m.h5", d1=("d1.h5", "/data"))
    h5(tmp_path / "d1.h5")
    probe = ClaimsD1()
    Collection("t", [probe])
    result = walk(tmp_path, [*collection_tests.collection.formats, probe])
    found = {d.anchor.rsplit("/", 1)[-1]: d for d in result.datasets}
    assert found["m.h5"].format == "common/hdf5"
    assert (
        "/m.h5",
        f"common/hdf5links: d1.h5 is claimed by t/claimsd1; {WANTED_TWICE}",
    ) in result.all_warnings()


@pytest.mark.parametrize("code", [errno.EIO, errno.ESTALE])
def test_a_member_that_does_not_answer_at_extraction(
    collection_tests, scan, monkeypatch, code
):
    # Second code review, S1: a temporary read error fails the extraction, to be
    # tried again next crawl (extractor-identity D9), not stored as `not_read`
    from modama_crawler import files

    d = datasets(collection_tests, scan)["scan_master.h5"]
    fmt = next(f for f in collection_tests.collection.formats if f.id == d.format)
    real = files.regular

    def failing(path):
        if path.endswith(DATA[0]):
            raise OSError(code, os.strerror(code), path)
        return real(path)

    monkeypatch.setattr(files, "regular", failing)
    with pytest.raises(OSError) as raised:
        fmt.extract(d, str(scan))
    assert raised.value.errno == code


@pytest.mark.parametrize("change", ["removed", "a symlink"])
def test_a_member_gone_at_extraction(collection_tests, scan, change):
    # Code review, S4: the master's values stay, the member is said not read
    d = datasets(collection_tests, scan)["scan_master.h5"]
    fmt = next(f for f in collection_tests.collection.formats if f.id == d.format)
    first = scan / DATA[0]
    first.unlink()
    if change == "a symlink":
        first.symlink_to(scan / DATA[1])
    x = fmt.extract(d, str(scan))
    assert mapped(x)["not_read"] == [DATA[0]]
    # the next member of the run gives the linked data's structure
    assert original(x)["entry.data.data_000001.shape"] == [2, 8, 6]
    assert "entry.instrument.detector.description" in original(x)
    assert mapped(x)["dangling"] == 10


def test_three_files_that_name_each_other_in_a_ring(collection_tests, tmp_path):
    # Code review, nit: as two files that name each other, each with a remark
    h5(tmp_path / "a.h5", b=("b.h5", "/data"))
    h5(tmp_path / "b.h5", c=("c.h5", "/data"))
    h5(tmp_path / "c.h5", a=("a.h5", "/data"))
    found = datasets(collection_tests, tmp_path)
    assert {d.format for d in found.values()} == {"common/hdf5"}
    assert "names b.h5, named by c.h5: no anchor" in found["a.h5"].basis
    assert "names c.h5, named by a.h5: no anchor" in found["b.h5"].basis
    assert "names a.h5, named by b.h5: no anchor" in found["c.h5"].basis


def test_a_listing_that_times_out(collection_tests, scan, monkeypatch):
    def short(workers=None, stopping=None):
        return inspection.Inspector(workers, time_limit=0.01, stopping=stopping)

    monkeypatch.setattr(walk_module, "Inspector", short)
    result = walk(scan, collection_tests.collection.formats)
    found = {d.anchor.rsplit("/", 1)[-1]: d for d in result.datasets}
    assert {d.format for d in found.values()} == {"common/hdf5"}
    assert len(found) == 4  # no record lost on a first crawl
    warned = [t for r, t in result.all_warnings() if r.endswith("scan_master.h5")]
    assert any(NOT_INSPECTED in t and "timed out" in t for t in warned)
    assert any(listing.retry for listing in result.listings.values())


def test_recognition_in_a_process_of_its_own_ends_cleanly(scan):
    command = Path(sys.executable).parent / "modama-crawler"
    done = subprocess.run(
        [str(command), "records", str(scan)],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "MODAMA_CRAWLER_CONFIG": ""},
    )
    assert done.returncode == 0, done.stderr
    assert "scan_master.h5" in done.stdout


# The linked data is described from the members


def test_the_linked_datas_structure(collection_tests, scan):
    assert not h5py.h5z.filter_avail(generate.BITSHUFFLE)
    x, _ = extracted(collection_tests, scan, "scan_master.h5")
    assert original(x)["entry.data.data_000001.shape"] == [2, 8, 6]
    assert original(x)["entry.data.data_000001.dtype"] == "<u4"


def test_a_target_path_that_leaves_the_member(collection_tests, scan, tmp_path):
    first = scan / DATA[0]
    with h5py.File(first, "a") as f:
        f["raw"] = f["entry/data/data"]
        del f["entry/data/data"]
        f["entry/data"]["data"] = h5py.SoftLink("/raw")
    x, _ = extracted(collection_tests, scan, "scan_master.h5")
    assert "entry.data.data_000001.shape" not in original(x)
    outside = tmp_path / "outside.h5"
    h5(outside)
    with h5py.File(first, "a") as f:
        del f["entry/data"]["data"]
        f["entry/data"]["data"] = h5py.ExternalLink(str(outside), "/data")
    opened = Opened(outside)
    x, _ = extracted(collection_tests, scan, "scan_master.h5")
    assert "entry.data.data_000001.shape" not in original(x)
    assert not opened.seen()


# The summary line (MODIFIED: An HDF5 file without a title is summarised by its structure)


def test_a_master_with_dangling_links(collection_tests, scan):
    x, _ = extracted(collection_tests, scan, "scan_master.h5")
    assert x.summary == [
        "Test detector 4M",
        "entry.data.data_000001 [2, 8, 6] <u4",
        "entry.instrument.detector.detectorSpecific.flatfield [8, 6] <f4",
        "entry.instrument.detector.detectorSpecific.pixel_mask [8, 6] <u4",
        "external_links 12",
        "dangling 9",
    ]
