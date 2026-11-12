"""Fixture generators: files written by the software that writes them in practice (NumPy,
h5py, pickle), the NeXus example under its own extension, and reproducers.

The content is fixed, so that the recorded extractions do not change between runs.
"""

import pickle
import shutil
from pathlib import Path

import h5py
import numpy

FIXTURES = Path(__file__).parent / "fixtures"
NEXUS = FIXTURES / "nexus_examples" / "simple_example_basic.nexus.hdf5"


def npy_arrays(target: Path) -> None:
    """An array file as numpy.save writes it, and the same file under another name."""
    target.mkdir(parents=True)
    frames = numpy.asfortranarray(numpy.arange(24, dtype="<f8").reshape(4, 6))
    numpy.save(target / "frames.npy", frames)
    shutil.copyfile(target / "frames.npy", target / "frames.bin")
    numpy.save(
        target / "events.npy",
        numpy.zeros(3, dtype=[("x", "<u2"), ("y", "<u2"), ("t", "<f4")]),
    )


def npz_archives(target: Path) -> None:
    """Archives as numpy.savez and numpy.savez_compressed write them."""
    target.mkdir(parents=True)
    arrays = {
        "image": numpy.zeros((8, 8), dtype="<u2"),
        "energy": numpy.linspace(0, 1, 16, dtype="<f4"),
    }
    numpy.savez(target / "stored.npz", **arrays)
    numpy.savez_compressed(target / "compressed.npz", **arrays)


def nexus_named(target: Path) -> None:
    """The NeXus example file under the extension .nxs, unchanged."""
    target.mkdir(parents=True)
    shutil.copyfile(NEXUS, target / "example.nxs")


def hdf5_names(target: Path) -> None:
    """HDF5 files as h5py writes them, under names of HDF5 files in the wild, one with a user block."""
    target.mkdir(parents=True)
    for name, block in (
        ("scan.h5", 0),
        ("velox.emd", 0),
        ("old.hdf", 0),
        ("blocked.h5", 512),
    ):
        with h5py.File(
            target / name, "w", userblock_size=block, track_times=False
        ) as f:
            f.attrs["creator"] = "generate.py"
            f.create_dataset("data", data=numpy.zeros((2, 3), dtype="<u2"))


def hdf4(target: Path) -> None:
    """The start of an HDF4 file (its signature, 0x0e031301) named .hdf, padded."""
    target.mkdir(parents=True)
    (target / "legacy.hdf").write_bytes(b"\x0e\x03\x13\x01" + bytes(252))


def pickles(target: Path) -> None:
    """Pickles of protocols 2 to 5 as the pickle module writes them."""
    target.mkdir(parents=True)
    state = {"frames": 4, "name": "scan"}
    for protocol in (2, 3, 4, 5):
        (target / f"state{protocol}.pkl").write_bytes(pickle.dumps(state, protocol))
    (target / "state.pickle").write_bytes(pickle.dumps([1, 2], 4))


def misnamed(target: Path) -> None:
    """Text files named like each type checked by its start, and a protocol 0 pickle."""
    target.mkdir(parents=True)
    for name in ("notes.npz", "notes.nxs", "notes.hspy", "notes.mat", "notes.ipynb"):
        (target / name).write_text("hello\n")
    (target / "old.pkl").write_bytes(pickle.dumps({"a": 1}, protocol=0))


# A MATLAB 7.3 header as MATLAB writes one (SciPy's testhdf5_7.4_GLNX86.mat):
# the text padded with spaces to 116 bytes, 8 bytes of subsystem offset, the
# version 0x0200 and the endian indicator "IM", then the rest of the user block
HEADER_73 = (
    (
        b"MATLAB 7.3 MAT-file, Platform: GLNXA64, Created on: Thu Nov 12 09:00:00 2026 "
        b"HDF5 schema 1.00 ."
    ).ljust(116)
    + bytes(8)
    + b"\x00\x02IM"
)


def matlab73_refs(target: Path) -> None:
    """A MATLAB 7.3 file laid out as MATLAB writes a cell array: the variable holds
    references into the group #refs#, which holds the cells."""
    target.mkdir(parents=True)
    path = target / "cells.mat"
    with h5py.File(path, "w", userblock_size=512, track_times=False) as f:
        refs = f.create_group("#refs#")
        a = refs.create_dataset("a", data=numpy.arange(3.0).reshape(3, 1))
        a.attrs["MATLAB_class"] = numpy.bytes_("double")
        cells = f.create_dataset("cells", data=[[a.ref]], dtype=h5py.ref_dtype)
        cells.attrs["MATLAB_class"] = numpy.bytes_("cell")
    with open(path, "r+b") as f:
        f.write(HEADER_73)


def python2(target: Path) -> None:
    """A Python 2 script."""
    target.mkdir(parents=True)
    (target / "legacy.py").write_text(
        '#!/usr/bin/env python\n"""Print the version."""\nprint "1.0"\n'
    )
