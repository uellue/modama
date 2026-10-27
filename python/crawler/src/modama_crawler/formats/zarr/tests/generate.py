"""Fixture generators of the zarr collection, written by zarr-python at test time."""

from pathlib import Path

import numpy
import zarr


def array(target: Path) -> None:
    target.mkdir(parents=True)
    a = zarr.create_array(
        store=str(target / "a.zarr"), shape=(4, 4), chunks=(2, 2), dtype="float32"
    )
    a[:] = numpy.zeros((4, 4), dtype="float32")
    (target / "notes.txt").write_text("next to a store\n")


def group_with_array(target: Path) -> None:
    target.mkdir(parents=True)
    g = zarr.create_group(store=str(target / "g.zarr"))
    inner = g.create_array("inner", shape=(2, 2), chunks=(2, 2), dtype="int8")
    inner[:] = numpy.zeros((2, 2), dtype="int8")


def v2_group_with_array(target: Path) -> None:
    target.mkdir(parents=True)
    g = zarr.create_group(store=str(target / "g.zarr"), zarr_format=2)
    g.attrs["kind"] = "simulation"
    inner = g.create_array("array0", shape=(2, 2), chunks=(2, 2), dtype="int8")
    inner[:] = numpy.zeros((2, 2), dtype="int8")


def corrupt(target: Path) -> None:
    (target / "broken.zarr" / "c" / "0").mkdir(parents=True)
    (target / "broken.zarr" / "zarr.json").write_text("not json")
    (target / "broken.zarr" / "c" / "0" / "0").write_bytes(b"\0" * 16)
