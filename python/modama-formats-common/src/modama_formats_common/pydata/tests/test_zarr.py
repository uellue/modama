"""Zarr and HyperSpy Zarr stores (spec formats/pydata-zarr), one test per scenario.

Run with -s to see each extraction's summary and the bytes it read.
"""

import json
import os
import threading
from pathlib import Path

import numpy
import pytest
import zarr
from modama_crawler.formats import zarr as core_zarr
from modama_crawler.walk import walk

from modama_formats_common.pydata import zarrstore

from .generate import ABTEM, abtem_like
from .test_extract import datasets, extracted, mapped, original


def group(path: Path, attributes: dict | None = None) -> Path:
    """A v2 group folder as the specification lays it out (`.zgroup`, `.zattrs`)."""
    path.mkdir(parents=True)
    (path / ".zgroup").write_text('{"zarr_format": 2}')
    if attributes is not None:
        (path / ".zattrs").write_text(json.dumps(attributes))
    return path


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
    assert original(v2)["array0.dtype"] == "<f4"
    assert original(v2)["array0.chunks"] == [8, 8, 16, 16]
    assert original(v2)["array0.compressor.id"] == "blosc"
    assert original(v3)["array0.data_type"] == "float32"
    assert original(v3)["array0.chunk_grid.configuration.chunk_shape"] == [8, 8, 16, 16]
    assert original(v3)["array0.codecs[1].name"] == "bytes"
    assert mapped(v2) == {"zarr_format": 2}
    assert mapped(v3) == {"zarr_format": 3}


def test_an_entry_nobody_has_seen(collection_tests, tmp_path):
    group(tmp_path / "s.zarr")
    group(tmp_path / "s.zarr" / "g", {"made_up_key": "made-up value"})
    x, _ = extracted(collection_tests, tmp_path, "s.zarr")
    assert original(x) == {"g.made_up_key": "made-up value"}


def test_a_nested_store(collection_tests, tmp_path):
    tree = collection_tests.materialise("zarr_stores", tmp_path)
    found = datasets(collection_tests, tree)
    assert "inner.zarr" not in found
    x, _ = extracted(collection_tests, tree, "nested.zarr")
    assert original(x)["inner.zarr.defocus"] == 50
    assert original(x)["inner.zarr.array0.shape"] == [2, 2]


# Only metadata files are read


@pytest.mark.parametrize("zarr_format", [2, 3])
def test_a_store_of_many_chunks(collection_tests, tmp_path, monkeypatch, zarr_format):
    g = zarr.create_group(store=str(tmp_path / "s.zarr"), zarr_format=zarr_format)
    g.attrs["title"] = "many chunks"
    a = g.create_array("a", shape=(64, 64, 8), chunks=(1, 1, 8), dtype="uint16")
    a[:] = numpy.ones((64, 64, 8), dtype="uint16")
    chunks = [p for p in (tmp_path / "s.zarr").rglob("*") if p.is_file()]
    assert len(chunks) > 4096
    metadata = sum(
        p.stat().st_size
        for p in chunks
        if p.name in ("zarr.json", ".zarray", ".zgroup", ".zattrs")
    )
    opened, listed = [], []
    real_open, real_scandir = os.open, os.scandir
    mine = threading.get_ident()

    def counting_open(path, flags, *args, **kwargs):
        if threading.get_ident() == mine:
            opened.append(os.fsdecode(path))
        return real_open(path, flags, *args, **kwargs)

    def counting_scandir(path="."):
        listed.append(path)
        return real_scandir(path)

    x, read = extracted(collection_tests, tmp_path, "s.zarr")
    monkeypatch.setattr(os, "open", counting_open)
    monkeypatch.setattr(os, "scandir", counting_scandir)
    zarrstore.described(str(tmp_path / "s.zarr"))
    names = {Path(p).name for p in opened}
    assert names <= {"s.zarr", "a", "zarr.json", ".zarray", ".zgroup", ".zattrs"}
    assert len(listed) == 1  # the root group only, never the array's folder
    assert read <= metadata
    assert original(x)["title"] == "many chunks"


def test_a_folder_in_a_store_that_is_no_node(collection_tests, tmp_path):
    tree = collection_tests.materialise("zarr_stores", tmp_path)
    x, _ = extracted(collection_tests, tree, "abtem_v3.zarr")
    assert not any(".ipynb_checkpoints" in k for k in original(x))
    assert mapped(x) == {"zarr_format": 3}


# Nothing is read from outside the store


def test_a_group_that_is_a_symlink(collection_tests, tmp_path):
    outside = group(tmp_path / "outside", {"secret": "from outside the store"})
    store = group(tmp_path / "tree" / "s.zarr", {"kept": 1})
    (store / "linked").symlink_to(outside)
    x, _ = extracted(collection_tests, tmp_path / "tree", "s.zarr")
    assert original(x) == {"kept": 1}


def test_a_metadata_file_that_is_a_fifo(collection_tests, tmp_path):
    store = group(tmp_path / "s.zarr", {"kept": 1})
    piped = group(store / "piped")
    os.mkfifo(piped / ".zattrs")
    group(store / "plain", {"also": "kept"})
    x, _ = extracted(collection_tests, tmp_path, "s.zarr")
    assert original(x) == {"kept": 1, "plain.also": "kept"}


# The walk of a store is bounded


def test_the_walk_stops_at_5000_nodes(collection_tests, tmp_path):
    store = group(tmp_path / "s.zarr")
    for i in range(6000):
        group(store / f"g{i:04}")
    x, _ = extracted(collection_tests, tmp_path, "s.zarr")
    assert original(x) == {}
    assert mapped(x) == {"zarr_format": 2, "walk": "cut at the object limit of 5000"}


def test_a_metadata_file_over_1_mib(collection_tests, tmp_path):
    store = group(tmp_path / "s.zarr", {"kept": 1})
    group(store / "large", {"text": "x" * (2 << 20)})
    group(store / "small", {"also": "kept"})
    x, _ = extracted(collection_tests, tmp_path, "s.zarr")
    assert original(x) == {"kept": 1, "small.also": "kept"}
    assert mapped(x)["not_read"] == ["large/.zattrs"]


# Unreadable metadata is reported


def test_a_broken_nested_node(collection_tests, tmp_path):
    store = group(tmp_path / "s.zarr", {"kept": 1})
    (store / "a").mkdir()
    (store / "a" / ".zarray").write_text("not json")
    x, _ = extracted(collection_tests, tmp_path, "s.zarr")
    assert original(x) == {"kept": 1}
    assert mapped(x)["unreadable"] == ["a"]


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


def test_a_credential_in_the_attributes(collection_tests, tmp_path):
    group(tmp_path / "s.zarr", {"password": "hunter2", "kept": 1})
    x, _ = extracted(collection_tests, tmp_path, "s.zarr")
    assert original(x) == {"kept": 1}


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
