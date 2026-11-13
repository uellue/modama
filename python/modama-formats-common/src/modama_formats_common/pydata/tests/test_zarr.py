"""Zarr and HyperSpy Zarr stores (spec formats/pydata-zarr), one test per scenario.

Run with -s to see each extraction's summary and the bytes it read.
"""

import json
import os
import shutil
from pathlib import Path

import numpy
import pytest
import zarr
from modama_crawler.formats import zarr as core_zarr
from modama_crawler.walk import walk

from modama_formats_common.pydata import zarrstore

from .generate import ABTEM, abtem_like
from .test_extract import FIXTURES, Opened, datasets, extracted, mapped, original

METADATA = {"zarr.json", ".zarray", ".zgroup", ".zattrs"}


def group(path: Path, attributes: dict | None = None) -> Path:
    """A v2 group folder as the specification lays it out (`.zgroup`, `.zattrs`)."""
    path.mkdir(parents=True)
    (path / ".zgroup").write_text('{"zarr_format": 2}')
    if attributes is not None:
        (path / ".zattrs").write_text(json.dumps(attributes))
    return path


def array_v2(path: Path, compressor: dict | None = None) -> Path:
    """A v2 array folder of 4 x 4 uint16 with its metadata only."""
    path.mkdir(parents=True)
    document = {
        "zarr_format": 2, "shape": [4, 4], "chunks": [2, 2], "dtype": "<u2",
        "compressor": compressor, "fill_value": 0, "order": "C", "filters": None,
    }  # fmt: skip
    (path / ".zarray").write_text(json.dumps(document))
    return path


def zspy(target: Path, name: str) -> Path:
    """The RosettaSciIO-written fixture under another name."""
    shutil.copytree(FIXTURES / "zspy" / "scan.zspy", target / name)
    return target / name


# A Zarr store is a described collapsed dataset


def test_a_version_2_group_store(collection_tests, tmp_path):
    g = zarr.create_group(store=str(tmp_path / "sim.zarr"), zarr_format=2)
    g.attrs.update(ABTEM)
    a = g.create_array("array0", shape=(64, 64), chunks=(1, 1), dtype="uint8")
    a[:] = numpy.ones((64, 64), dtype="uint8")
    found = datasets(collection_tests, tmp_path)
    assert list(found) == ["sim.zarr"]
    assert found["sim.zarr"].format == "common/zarr"
    assert found["sim.zarr"].collapsed


def test_without_the_common_collection(collection_tests, tmp_path):
    abtem_like(tmp_path / "sim.zarr", 2)
    result = walk(tmp_path, core_zarr.COLLECTION.formats)
    assert [(d.anchor, d.format) for d in result.datasets] == [
        ("/sim.zarr", "zarr/zarr")
    ]


def test_both_zarr_json_and_zgroup(collection_tests, tmp_path):
    store = group(tmp_path / "both.zarr", {"v": 2})
    (store / "zarr.json").write_text(
        json.dumps({"zarr_format": 3, "node_type": "group", "attributes": {"v": 3}})
    )
    d = datasets(collection_tests, tmp_path)["both.zarr"]
    assert d.basis.startswith("zarr.json")
    x, _ = extracted(collection_tests, tmp_path, "both.zarr")
    assert original(x) == {"zarr_format": 3, "v": 3}


# A HyperSpy Zarr store is typed by name and content


def test_a_store_written_by_rosettasciio(collection_tests, tmp_path):
    tree = collection_tests.materialise("zspy", tmp_path)
    d = datasets(collection_tests, tree)["scan.zspy"]
    assert (d.format, d.type, d.collapsed) == (
        "common/zspy",
        "application/x.zspy",
        True,
    )


def test_a_zspy_store_that_hyperspy_did_not_write(collection_tests, tmp_path):
    group(tmp_path / "other.zspy", {"file_format": "something else"})
    d = datasets(collection_tests, tmp_path)["other.zspy"]
    assert (d.format, d.type) == ("common/zarr", "application/x-zarr")


def test_a_hyperspy_store_named_zarr(collection_tests, tmp_path):
    zspy(tmp_path, "scan.zarr")
    d = datasets(collection_tests, tmp_path)["scan.zarr"]
    assert (d.format, d.type) == ("common/zarr", "application/x-zarr")
    x, _ = extracted(collection_tests, tmp_path, "scan.zarr")
    assert not any("._HyperSpy." in f".{k}." for k in original(x))
    assert x.summary == ["4D-STEM scan", "electron_diffraction", "shape [4, 4, 16, 16]"]


# A change of any metadata file is noticed


def test_a_metadata_file_below_the_first_level_changes(collection_tests, tmp_path):
    g = zarr.create_group(store=str(tmp_path / "s.zarr"), zarr_format=2)
    b = g.create_group("a").create_group("b")
    b.attrs["x"] = 1
    data = b.create_array("data", shape=(4,), chunks=(2,), dtype="uint8")
    data[:] = numpy.ones(4, dtype="uint8")

    def stamp() -> str:
        return datasets(collection_tests, tmp_path)["s.zarr"].stamp

    before = stamp()
    chunk = next(p for p in (tmp_path / "s.zarr/a/b/data").iterdir() if p.is_file()
                 and p.name not in METADATA)  # fmt: skip
    chunk.write_bytes(b"\x02" * chunk.stat().st_size)
    os.utime(chunk, (1e9, 1e9))
    assert stamp() == before  # a chunk is no part of it
    attributes = tmp_path / "s.zarr/a/b/.zattrs"
    folder_times = os.stat(tmp_path / "s.zarr/a").st_mtime_ns
    with open(attributes, "r+") as f:  # in place, same size: no folder's time changes
        text = f.read().replace("1", "2")
        f.seek(0)
        f.write(text)
    os.utime(attributes, (2e9, 2e9))
    assert os.stat(tmp_path / "s.zarr/a").st_mtime_ns == folder_times
    assert stamp() != before


# A store is described by its metadata files


def test_version_2_and_version_3_stores(collection_tests, tmp_path):
    tree = collection_tests.materialise("zarr_stores", tmp_path)
    v2, _ = extracted(collection_tests, tree, "abtem_v2.zarr")
    v3, _ = extracted(collection_tests, tree, "abtem_v3.zarr")
    for x in (v2, v3):
        assert original(x)["metadata0.energy"] == 300000.0
        assert original(x)["metadata0.axes.axis_0.units"] == "Å"
        assert original(x)["metadata0.axes.axis_0.sampling"] == 0.1
        assert original(x)["array0.shape"] == [8, 8, 16, 16]
        assert not [k for k in original(x) if k.endswith((".zarr_format", "node_type"))]
    assert original(v2)["zarr_format"] == 2
    assert original(v2)["array0.dtype"] == "<f4"
    assert original(v2)["array0.chunks"] == [8, 8, 16, 16]
    assert original(v2)["array0.compressor.id"] == "blosc"
    assert original(v3)["zarr_format"] == 3
    assert original(v3)["array0.data_type"] == "float32"
    assert original(v3)["array0.chunk_grid.configuration.chunk_shape"] == [8, 8, 16, 16]
    assert original(v3)["array0.codecs[1].name"] == "bytes"
    assert mapped(v2) == mapped(v3) == {}


def test_an_entry_nobody_has_seen(collection_tests, tmp_path):
    group(tmp_path / "s.zarr")
    group(tmp_path / "s.zarr" / "g", {"made_up_key": "made-up value"})
    x, _ = extracted(collection_tests, tmp_path, "s.zarr")
    assert original(x) == {"zarr_format": 2, "g.made_up_key": "made-up value"}


def test_a_nested_store(collection_tests, tmp_path):
    tree = collection_tests.materialise("zarr_stores", tmp_path)
    found = datasets(collection_tests, tree)
    assert "inner.zarr" not in found
    x, _ = extracted(collection_tests, tree, "nested.zarr")
    assert original(x)["inner.zarr.defocus"] == 50
    assert original(x)["inner.zarr.array0.shape"] == [2, 2]
    # A nested store of another version says so
    v3 = zarr.create_group(store=str(tmp_path / "mixed.zarr" / "v3"), zarr_format=3)
    v3.attrs["kind"] = "newer"
    group_file = tmp_path / "mixed.zarr" / ".zgroup"
    group_file.write_text('{"zarr_format": 2}')
    y, _ = extracted(collection_tests, tmp_path, "mixed.zarr")
    assert original(y) == {"zarr_format": 2, "v3.zarr_format": 3, "v3.kind": "newer"}


def test_an_unknown_codec_and_an_unknown_data_type(collection_tests, tmp_path):
    store = group(tmp_path / "v2.zarr")
    array_v2(store / "a", {"id": "imagecodecs_jpeg2k", "level": 0})
    array_v2(store / "b", {"id": "blosc", "cname": "lz4"})
    x, _ = extracted(collection_tests, tmp_path, "v2.zarr")
    assert original(x)["a.compressor.id"] == "imagecodecs_jpeg2k"
    assert original(x)["b.compressor.id"] == "blosc"
    g = zarr.create_group(store=str(tmp_path / "v3.zarr"), zarr_format=3)
    g.create_array("b", shape=(4,), chunks=(4,), dtype="uint8")
    (tmp_path / "v3.zarr" / "a").mkdir()
    document = json.loads((tmp_path / "v3.zarr" / "b" / "zarr.json").read_text())
    (tmp_path / "v3.zarr" / "a" / "zarr.json").write_text(
        json.dumps({**document, "data_type": "made_up_type"})
    )
    y, _ = extracted(collection_tests, tmp_path, "v3.zarr")
    assert original(y)["a.data_type"] == "made_up_type"
    assert original(y)["b.data_type"] == "uint8"


def test_consolidated_metadata_is_not_read(collection_tests, tmp_path):
    g = zarr.create_group(store=str(tmp_path / "s.zarr"), zarr_format=2)
    g.attrs["kept"] = 1
    zarr.consolidate_metadata(str(tmp_path / "s.zarr"))
    consolidated = tmp_path / "s.zarr" / ".zmetadata"
    content = json.loads(consolidated.read_text())
    content["metadata"][".zattrs"] = {"kept": 2, "only_consolidated": True}
    consolidated.write_text(json.dumps(content))
    datasets(collection_tests, tmp_path)  # recognition reads the listing
    watch = Opened(consolidated)
    x = zarrstore.described(str(tmp_path / "s.zarr"))[0]
    assert not watch.seen()
    assert x == {"zarr_format": 2, "kept": 1}


# Only metadata files are read


@pytest.mark.parametrize("zarr_format", [2, 3])
def test_a_store_of_many_chunks(collection_tests, tmp_path, zarr_format):
    g = zarr.create_group(store=str(tmp_path / "s.zarr"), zarr_format=zarr_format)
    g.attrs["title"] = "many chunks"
    a = g.create_array("a", shape=(64, 64, 8), chunks=(1, 1, 8), dtype="uint16")
    a[:] = numpy.ones((64, 64, 8), dtype="uint16")
    files = [p for p in (tmp_path / "s.zarr").rglob("*") if p.is_file()]
    assert len(files) > 4096
    metadata = sum(p.stat().st_size for p in files if p.name in METADATA)
    x, read = extracted(collection_tests, tmp_path, "s.zarr")
    assert read <= metadata
    assert original(x)["title"] == "many chunks"


def test_a_folder_in_a_store_that_is_no_node(collection_tests, tmp_path):
    tree = collection_tests.materialise("zarr_stores", tmp_path)
    checkpoint = tree / "abtem_v3.zarr" / ".ipynb_checkpoints" / "zarr-checkpoint.json"
    watch = Opened(checkpoint)
    x, _ = extracted(collection_tests, tree, "abtem_v3.zarr")
    assert not watch.seen()
    assert not any(".ipynb_checkpoints" in k for k in original(x))
    assert mapped(x) == {}


# Nothing is read from outside the store


def test_a_group_that_is_a_symlink(collection_tests, tmp_path):
    outside = group(tmp_path / "outside", {"secret": "from outside the store"})
    store = group(tmp_path / "tree" / "s.zarr", {"kept": 1})
    (store / "linked").symlink_to(outside)
    watch = Opened(outside / ".zattrs")
    x, _ = extracted(collection_tests, tmp_path / "tree", "s.zarr")
    assert not watch.seen()
    assert original(x) == {"zarr_format": 2, "kept": 1}


def test_a_metadata_file_that_is_a_symlink(collection_tests, tmp_path):
    secret = tmp_path / "secret.json"
    secret.write_text('{"secret": "from outside the store"}')
    store = group(tmp_path / "tree" / "s.zarr")
    (group(store / "g") / ".zattrs").symlink_to(secret)
    watch = Opened(secret)
    x, _ = extracted(collection_tests, tmp_path / "tree", "s.zarr")
    assert not watch.seen()
    assert original(x) == {"zarr_format": 2}


def test_a_metadata_file_that_is_a_fifo(collection_tests, tmp_path):
    store = group(tmp_path / "s.zarr", {"kept": 1})
    os.mkfifo(group(store / "piped") / ".zattrs")
    group(store / "plain", {"also": "kept"})
    x, _ = extracted(collection_tests, tmp_path, "s.zarr")
    assert original(x) == {"zarr_format": 2, "kept": 1, "plain.also": "kept"}


# The walk of a store is bounded


def test_the_walk_stops_at_5000_nodes(collection_tests, tmp_path, monkeypatch):
    store = group(tmp_path / "s.zarr")
    for i in range(6000):
        group(store / f"g{i:04}")
    x, _ = extracted(collection_tests, tmp_path, "s.zarr")
    assert original(x) == {"zarr_format": 2}
    assert mapped(x) == {"walk": "cut at the object limit of 5000"}
    # The root's listing is read up to one name more than the room of 4,999 objects
    # (each group below it is listed too, holding its .zgroup)
    listings: list[list[str]] = []
    real_scandir = os.scandir
    monkeypatch.setattr(
        os, "scandir", lambda folder: Counted(real_scandir(folder), listings)
    )
    zarrstore.described(str(store))
    assert max(len(names) for names in listings) == 5001


class Counted:
    """A listing (os.scandir) that notes the names it hands out, one list per listing."""

    def __init__(self, listing, listings: list):
        self.listing, self.seen = listing, []
        listings.append(self.seen)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.listing.close()

    def __iter__(self):
        return self

    def __next__(self):
        entry = next(self.listing)
        self.seen.append(entry.name)
        return entry


def test_the_walk_stops_after_16_mib(collection_tests, tmp_path):
    store = group(tmp_path / "s.zarr")
    for i in range(20):
        attributes = group(store / f"g{i:02}") / ".zattrs"
        text = json.dumps({"text": ""})
        attributes.write_text(text[:-2] + "x" * ((1 << 20) - len(text)) + '"}')
        assert attributes.stat().st_size == 1 << 20
    x, read = extracted(collection_tests, tmp_path, "s.zarr")
    assert mapped(x) == {"walk": "cut at the byte limit of 16 MiB"}
    assert read <= 16 << 20


def test_a_metadata_file_over_1_mib(collection_tests, tmp_path):
    store = group(tmp_path / "s.zarr", {"kept": 1})
    group(store / "large", {"text": "x" * (2 << 20)})
    group(store / "small", {"also": "kept"})
    x, read = extracted(collection_tests, tmp_path, "s.zarr")
    assert original(x) == {"zarr_format": 2, "kept": 1, "small.also": "kept"}
    assert mapped(x) == {"not_read": ["large/.zattrs"]}
    assert read < 1 << 20


def test_a_root_document_over_1_mib(collection_tests, tmp_path):
    store = tmp_path / "s.zarr"
    store.mkdir()
    root = {
        "zarr_format": 3,
        "node_type": "group",
        "attributes": {"text": "x" * (2 << 20)},
    }
    (store / "zarr.json").write_text(json.dumps(root))
    zarr.create_group(store=str(store / "g"), zarr_format=3).attrs["also"] = "kept"
    x, _ = extracted(collection_tests, tmp_path, "s.zarr")
    assert original(x) == {"zarr_format": 3, "g.also": "kept"}
    assert mapped(x) == {"not_read": ["zarr.json"]}


# Unreadable metadata is reported


def test_a_broken_nested_node(collection_tests, tmp_path):
    store = group(tmp_path / "s.zarr", {"kept": 1})
    (store / "a").mkdir()
    (store / "a" / ".zarray").write_text("not json")
    x, _ = extracted(collection_tests, tmp_path, "s.zarr")
    assert original(x) == {"zarr_format": 2, "kept": 1}
    assert mapped(x) == {"unreadable": ["a"]}


def test_deep_nesting(collection_tests, tmp_path):
    store = group(tmp_path / "s.zarr")
    deep = group(store / "deep") / ".zattrs"
    deep.write_text('{"a":' * 100_000 + "1" + "}" * 100_000)
    chain = store
    for depth in range(1, 151):
        chain = group(chain / "g", {"depth": depth})
    x, _ = extracted(collection_tests, tmp_path, "s.zarr")
    depths = sorted(v for k, v in original(x).items() if k.endswith("depth"))
    assert depths == list(range(1, 101))
    assert mapped(x) == {
        "unreadable": ["deep"],
        "too_deep": ["/".join(["g"] * 100)],
    }


def test_a_broken_root(collection_tests, tmp_path):
    tree = collection_tests.materialise("zarr_broken_root", tmp_path)
    d = datasets(collection_tests, tree)["broken.zarr"]
    assert d.collapsed and d.format == "common/zarr"
    assert any("cannot be parsed" in w for w in d.warnings)
    fmt = next(f for f in collection_tests.collection.formats if f.id == d.format)
    with pytest.raises(zarrstore.Unreadable, match="zarr.json"):
        fmt.extract(d, str(tree))


# What the Zarr walk leaves out


def test_hyperspys_internal_state(collection_tests, tmp_path):
    tree = collection_tests.materialise("zspy", tmp_path)
    x, _ = extracted(collection_tests, tree, "scan.zspy")
    values = original(x)
    assert not any("._HyperSpy." in f".{k}." for k in values)
    assert "_None_" not in values.values()
    prefix = "Experiments.4D-STEM scan."
    assert values[prefix + "metadata.Signal.signal_type"] == "electron_diffraction"
    made_up = prefix + "original_metadata.made_up_section.made_up_key"
    assert values[made_up] == "made-up value"
    # Zarr's storage parameters stay (@weber, 322)
    assert values[prefix + "data.compressor.id"] == "blosc"


def test_a_credential_in_the_attributes(collection_tests, tmp_path):
    group(tmp_path / "s.zarr", {"password": "hunter2", "kept": 1})
    x, _ = extracted(collection_tests, tmp_path, "s.zarr")
    assert original(x) == {"zarr_format": 2, "kept": 1}


# The summary line of a store


def test_a_hyperspy_store(collection_tests, tmp_path):
    tree = collection_tests.materialise("zspy", tmp_path)
    x, _ = extracted(collection_tests, tree, "scan.zspy")
    assert x.summary == ["4D-STEM scan", "electron_diffraction", "shape [4, 4, 16, 16]"]
    assert x.subjects == ["electron_diffraction"]


def test_an_abtem_like_store(collection_tests, tmp_path):
    abtem_like(tmp_path / "sim.zarr", 3)
    x, _ = extracted(collection_tests, tmp_path, "sim.zarr")
    assert x.summary == ["shape [8, 8, 16, 16]", "float32"]
