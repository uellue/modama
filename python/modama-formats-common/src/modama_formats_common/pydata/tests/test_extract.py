"""Recognition and extraction of the pydata formats (spec formats/pydata), one test per scenario.

Run with -s to see each extraction's summary and the bytes it read.
"""

import ctypes
import json
import os
import pickle
import shutil
import time
from pathlib import Path

import h5py
import nbformat
import numpy
from modama_crawler.walk import walk

from modama_formats_common.pydata import notebook, values

FIXTURES = Path(__file__).parent / "fixtures"


def rchar() -> int:
    """Bytes this process has read so far, from /proc/self/io (Linux)."""
    for line in Path("/proc/self/io").read_text().splitlines():
        key, _, value = line.partition(":")
        if key == "rchar":
            return int(value)
    raise RuntimeError("no rchar in /proc/self/io")


class Opened:
    """Whether a file is opened after this starts watching it, by inotify (Linux)."""

    IN_OPEN = 0x20
    IN_NONBLOCK = 0o4000

    def __init__(self, path: Path):
        self._libc = ctypes.CDLL(None, use_errno=True)
        self._fd = self._libc.inotify_init1(self.IN_NONBLOCK)
        assert self._fd >= 0, os.strerror(ctypes.get_errno())
        watch = self._libc.inotify_add_watch(self._fd, os.fsencode(path), self.IN_OPEN)
        assert watch >= 0, os.strerror(ctypes.get_errno())

    def seen(self) -> bool:
        """Whether it was opened; ends the watch."""
        try:
            return len(os.read(self._fd, 4096)) > 0
        except BlockingIOError:
            return False
        finally:
            os.close(self._fd)


def datasets(ct, tree: Path) -> dict:
    """The datasets of a directory by file name."""
    return {
        d.anchor.rsplit("/", 1)[-1]: d
        for d in walk(tree, ct.collection.formats).datasets
    }


def extracted(ct, tree: Path, name: str):
    """The extraction of the dataset of file `name` in tree, and the bytes it read.

    Run once before measuring, so that imports and caches don't count.
    """
    d = datasets(ct, tree)[name]
    fmt = next(f for f in ct.collection.formats if f.id == d.format)
    fmt.extract(d, str(tree))
    before = rchar()
    own = rchar() - before  # rchar's own read of /proc/self/io
    before = rchar()
    x = fmt.extract(d, str(tree))
    read = rchar() - before - own
    json.dumps([x.summary, x.subjects, x.values], allow_nan=False)  # storable
    print(f"{name}: {x.summary} {x.subjects}, {read} bytes read")
    return x, read


def original(x) -> dict:
    return x.values["original_metadata"]


def mapped(x) -> dict:
    return x.values["mapped_metadata"]


# NumPy


def test_a_numpy_array_file(collection_tests, tmp_path):
    found = datasets(
        collection_tests, collection_tests.materialise("npy_arrays", tmp_path)
    )
    for name in ("frames.npy", "frames.bin"):
        assert (found[name].type, found[name].format) == (
            "application/x-npy",
            "common/npy",
        )


def test_the_header_only(collection_tests, tmp_path):
    a = numpy.asfortranarray(numpy.ones((1000, 1000)))
    numpy.save(tmp_path / "big.npy", a)
    x, read = extracted(collection_tests, tmp_path, "big.npy")
    assert x.summary == ["shape [1000, 1000]", "float64", "fortran_order True"]
    assert original(x) == {
        "descr": "<f8",
        "fortran_order": True,
        "shape": [1000, 1000],
        "version": "1.0",
    }
    assert mapped(x) == {"dtype": "float64"}
    assert read < 4096


def test_a_header_over_numpys_default_limit(collection_tests, tmp_path):
    # As NumPy's own test of a large header (test_format.py): 600 fields
    many = numpy.dtype([(f"field{i}", "<f4") for i in range(600)])
    numpy.save(tmp_path / "fields.npy", numpy.zeros(2, dtype=many))
    assert (tmp_path / "fields.npy").stat().st_size > 10_000 + 2 * many.itemsize
    x, _ = extracted(collection_tests, tmp_path, "fields.npy")
    # The descr of 600 fields, and NumPy's name of it, are more than textual keeps
    assert original(x) == {"fortran_order": False, "shape": [2], "version": "1.0"}
    assert x.summary == ["shape [2]"] and mapped(x) == {}


def test_stored_and_compressed_archives(collection_tests, tmp_path):
    rng = numpy.random.default_rng(0)
    arrays = {
        "image": rng.integers(0, 65535, (512, 512), dtype="<u2"),
        "energy": rng.random(2048, dtype="<f4"),
    }
    numpy.savez(tmp_path / "stored.npz", **arrays)
    numpy.savez_compressed(tmp_path / "compressed.npz", **arrays)
    for name in ("stored.npz", "compressed.npz"):
        x, read = extracted(collection_tests, tmp_path, name)
        found = original(x)
        assert found["image.shape"] == [512, 512]
        assert found["image.descr"] == "<u2"
        assert found["energy.shape"] == [2048]
        assert x.summary == ["image.shape [512, 512]", "energy.shape [2048]"]
        assert read < (tmp_path / name).stat().st_size / 10


def test_a_text_file_named_like_an_archive(collection_tests, tmp_path):
    d = datasets(collection_tests, collection_tests.materialise("misnamed", tmp_path))[
        "notes.npz"
    ]
    assert d.type == "text/plain" and d.format == ""
    assert "no ZIP signature" in d.basis


# HDF5 types


def test_hdf5_whatever_the_name(collection_tests, tmp_path):
    found = datasets(
        collection_tests, collection_tests.materialise("hdf5_names", tmp_path)
    )
    found |= datasets(collection_tests, collection_tests.materialise("hdf4", tmp_path))
    for name in ("scan.h5", "velox.emd", "old.hdf", "blocked.h5"):
        assert (found[name].type, found[name].format) == (
            "application/vnd.hdfgroup.hdf5",
            "common/hdf5",
        )
    assert found["legacy.hdf"].type == "application/x-hdf"


def test_a_nexus_file_and_a_hyperspy_file(collection_tests, tmp_path):
    found = datasets(
        collection_tests, collection_tests.materialise("nexus_named", tmp_path)
    )
    found |= datasets(
        collection_tests, collection_tests.materialise("hyperspy", tmp_path)
    )
    assert (found["example.nxs"].type, found["example.nxs"].format) == (
        "application/x.nexus",
        "common/nexus",
    )
    assert (found["example2_v3.1.hspy"].type, found["example2_v3.1.hspy"].format) == (
        "application/x.hspy",
        "common/hspy",
    )


def test_a_file_named_hspy_that_hyperspy_did_not_write(collection_tests, tmp_path):
    with h5py.File(tmp_path / "other.hspy", "w") as f:
        f["data"] = numpy.zeros(3)
    d = datasets(collection_tests, tmp_path)["other.hspy"]
    assert (d.type, d.format) == ("application/vnd.hdfgroup.hdf5", "common/hdf5")
    assert "no HyperSpy" in d.basis


def test_a_text_file_named_like_a_nexus_file(collection_tests, tmp_path):
    d = datasets(collection_tests, collection_tests.materialise("misnamed", tmp_path))[
        "notes.nxs"
    ]
    assert d.type == "text/plain" and "no HDF5 signature" in d.basis


# The HDF5 walk


def test_a_nexus_files_attributes_and_datasets(collection_tests, tmp_path):
    tree = collection_tests.materialise("nexus_examples", tmp_path)
    x, _ = extracted(collection_tests, tree, "simple_example_basic.nexus.hdf5")
    found = original(x)
    assert {
        "creator": "simple_example_basic_write.py",
        "entry.NX_class": "NXentry",
        "entry.mr_scan.mr_indices": [0],
        "entry.mr_scan.I00.shape": [31],
        "entry.mr_scan.I00.dtype": "<i4",
        "entry.mr_scan.I00.units": "counts",
        "entry.title": "1-D scan of I00 v. mr",
    }.items() <= found.items()
    assert x.summary[0] == "1-D scan of I00 v. mr"


def test_an_attribute_nobody_has_seen_before(collection_tests, tmp_path):
    with h5py.File(tmp_path / "new.h5", "w") as f:
        f.create_group("g").attrs["never_seen_before"] = "value"
        f.attrs["blank"] = h5py.Empty("f")
    x, _ = extracted(collection_tests, tmp_path, "new.h5")
    assert original(x)["g.never_seen_before"] == "value"
    assert original(x)["blank"] == ""


def test_credentials_are_left_out(collection_tests, tmp_path):
    with h5py.File(tmp_path / "config.h5", "w") as f:
        f.attrs["password"] = "hunter2"
        f.attrs["server"] = "postgres://admin:hunter2@db/data"
        f.attrs["operator"] = "someone"
    (tmp_path / "settings.py").write_text('__token__ = "abc123"\n__version__ = "1"\n')
    x, _ = extracted(collection_tests, tmp_path, "config.h5")
    y, _ = extracted(collection_tests, tmp_path, "settings.py")
    assert original(x) == {"operator": "someone"}
    assert original(y) == {"__version__": "1", "imports": []}


def test_values_not_suitable_for_text(collection_tests, tmp_path, monkeypatch):
    with h5py.File(tmp_path / "odd.h5", "w") as f:
        f.attrs["hundred"] = numpy.arange(100)
        f.attrs["opaque"] = numpy.void(b"\x00\x01\x02")
        f["long"] = "x" * 1001
        f.create_dataset("reference", data=f.ref, dtype=h5py.ref_dtype)  # no JSON
        f["huge"] = numpy.bytes_(b"x" * 100_000)  # a scalar of 100,000 bytes
        f.attrs["kept"] = 1
    read_names = []
    get = h5py.AttributeManager.__getitem__

    def recording(self, name):
        read_names.append(name)
        return get(self, name)

    monkeypatch.setattr(h5py.AttributeManager, "__getitem__", recording)
    x, read = extracted(collection_tests, tmp_path, "odd.h5")
    assert original(x) == {"kept": 1}
    assert "hundred" not in read_names and "opaque" in read_names
    assert read < 100_000  # the large scalar is not read


def test_arrays_are_never_read(collection_tests, tmp_path):
    with h5py.File(tmp_path / "big.h5", "w") as f:
        data = f.create_dataset("frames", data=numpy.ones((2000, 2000), dtype="<f8"))
        data.attrs["units"] = "counts"
    size = (tmp_path / "big.h5").stat().st_size
    x, read = extracted(collection_tests, tmp_path, "big.h5")
    assert original(x) == {
        "frames.shape": [2000, 2000],
        "frames.dtype": "<f8",
        "frames.units": "counts",
    }
    assert size > 32_000_000 and read < 256 * 1024


def test_the_walk_stops_at_1000_entries(collection_tests, tmp_path):
    with h5py.File(tmp_path / "many.h5", "w") as f:
        for i in range(1500):
            f.create_group(f"g{i:04}").attrs["n"] = i
    x, _ = extracted(collection_tests, tmp_path, "many.h5")
    assert len(original(x)) == 1000
    assert mapped(x) == {"walk": "cut at the entry limit of 1000"}
    with h5py.File(tmp_path / "crowded.h5", "w") as f:
        crowded = f.create_group("crowded")  # all on one object
        for i in range(1500):
            crowded.attrs[f"a{i:04}"] = i
    y, _ = extracted(collection_tests, tmp_path, "crowded.h5")
    assert len(original(y)) == 1000
    assert mapped(y) == {"walk": "cut at the entry limit of 1000"}


def test_the_walk_stops_at_5000_objects(collection_tests, tmp_path):
    with h5py.File(tmp_path / "empty.h5", "w") as f:
        for i in range(6000):
            f.create_group(f"g{i:04}")
    x, _ = extracted(collection_tests, tmp_path, "empty.h5")
    assert original(x) == {}
    assert mapped(x) == {"walk": "cut at the object limit of 5000"}


def test_a_group_on_the_skip_list_is_not_entered(collection_tests, tmp_path):
    path = tmp_path / "cells.mat"
    with h5py.File(path, "w", userblock_size=512) as f:
        refs = f.create_group("#refs#")
        for i in range(6000):  # more than the object limit, if entered
            refs.create_group(f"r{i:04}")
        f["x"] = numpy.zeros(3)
        f["x"].attrs["MATLAB_class"] = numpy.bytes_("double")
    with open(path, "r+b") as f:
        f.write(b"MATLAB 7.3 MAT-file".ljust(116) + bytes(8) + b"\x00\x02IM")
    x, _ = extracted(collection_tests, tmp_path, "cells.mat")
    assert original(x)["x.MATLAB_class"] == "double"
    assert mapped(x) == {}


def test_the_walk_stops_after_its_time(collection_tests, tmp_path, monkeypatch):
    with h5py.File(tmp_path / "slow.h5", "w") as f:
        for i in range(10):
            f.create_group(f"g{i}").attrs["n"] = i
    monkeypatch.setattr(values, "SECONDS", -1.0)  # up before the first object
    x, _ = extracted(collection_tests, tmp_path, "slow.h5")
    assert original(x) == {}
    assert mapped(x) == {"walk": "cut at the time limit of -1 s"}


def test_raw_data_stored_in_another_file(collection_tests, tmp_path):
    elsewhere, tree = tmp_path / "elsewhere", tmp_path / "tree"
    elsewhere.mkdir()
    tree.mkdir()
    raw = elsewhere / "raw.bin"
    raw.write_bytes(b"SECRET42" + bytes(64))
    with h5py.File(tree / "external.h5", "w") as f:
        # h5py's create_dataset ignores external= for a scalar: HDF5's own calls
        dcpl = h5py.h5p.create(h5py.h5p.DATASET_CREATE)
        dcpl.set_external(os.fsencode(raw), 0, 8)
        text = h5py.h5t.C_S1.copy()
        text.set_size(8)
        scalar = h5py.h5s.create(h5py.h5s.SCALAR)
        h5py.h5d.create(f.id, b"label", text, scalar, dcpl=dcpl)
        f.create_dataset("frames", shape=(8,), dtype="u1", external=[(str(raw), 0, 8)])
    opened = Opened(raw)
    x, _ = extracted(collection_tests, tree, "external.h5")
    assert "SECRET42" not in json.dumps(x.values)
    assert original(x) == {
        "label.shape": [],
        "label.dtype": "|S8",
        "frames.shape": [8],
        "frames.dtype": "|u1",
    }
    assert not opened.seen()


def test_a_virtual_dataset(collection_tests, tmp_path):
    elsewhere, tree = tmp_path / "elsewhere", tmp_path / "tree"
    elsewhere.mkdir()
    tree.mkdir()
    source = elsewhere / "src0.h5"
    with h5py.File(source, "w") as s:
        s.create_dataset("data", data=numpy.arange(4), maxshape=(None,))
        s["value"] = 42
    with h5py.File(tree / "virtual.h5", "w") as f:
        unlimited = h5py.VirtualLayout(shape=(4,), maxshape=(None,), dtype="<i8")
        part = h5py.VirtualSource(str(source), "data", shape=(4,), maxshape=(None,))
        unlimited[0 : h5py.h5s.UNLIMITED] = part[0 : h5py.h5s.UNLIMITED]
        f.create_virtual_dataset("unlimited", unlimited)
        scalar = h5py.VirtualLayout(shape=(), dtype="<i8")
        scalar[()] = h5py.VirtualSource(str(source), "value", shape=())
        f.create_virtual_dataset("scalar", scalar)
    opened = Opened(source)
    x, _ = extracted(collection_tests, tree, "virtual.h5")
    assert original(x)["unlimited.dtype"] == "<i8"
    assert original(x)["scalar.dtype"] == "<i8"
    assert 42 not in original(x).values()
    assert not opened.seen()


def test_external_links_are_not_followed(collection_tests, tmp_path):
    with h5py.File(tmp_path / "other.h5", "w") as f:
        f.create_dataset("counts", data=numpy.arange(3)).attrs["units"] = "counts"
        f.attrs["other_file"] = "yes"
    with h5py.File(tmp_path / "master.h5", "w") as f:
        f["linked"] = h5py.ExternalLink("other.h5", "/counts")
        f.attrs["master_file"] = "yes"
    x, _ = extracted(collection_tests, tmp_path, "master.h5")
    assert original(x) == {"master_file": "yes"}


# HyperSpy


def test_rosettasciios_test_file(collection_tests, tmp_path):
    tree = collection_tests.materialise("hyperspy", tmp_path)
    x, _ = extracted(collection_tests, tree, "example2_v3.1.hspy")
    found = original(x)
    assert x.summary == ["test_diffraction_pattern", "shape [16, 16]"]
    assert found["file_format"] == "HyperSpy"
    exp = "Experiments.test_diffraction_pattern.metadata"
    assert found[f"{exp}.Acquisition_instrument.TEM.microscope"] == "FEI Tecnai"
    # An older HyperSpy file named .hdf5 has the same skip list
    y, _ = extracted(collection_tests, tree, "with_lists_etc.hdf5")
    for found in (original(x), original(y)):
        assert not [k for k in found if "_HyperSpy" in k]
        assert "_None_" not in found.values()


def test_a_variance_signal_in_the_metadata(collection_tests, tmp_path):
    # RosettaSciIO's hspy reader reads this signal whole, lazy or not (A1)
    path = tmp_path / "variance.hspy"
    shutil.copyfile(FIXTURES / "hyperspy" / "with_lists_etc.hdf5", path)
    variance = "Experiments/__unnamed__/metadata/Signal/Noise_properties/_sig_variance"
    with h5py.File(path, "r+") as f:
        del f[f"{variance}/data"]
        f.create_dataset(
            f"{variance}/data", data=numpy.ones(4_000_000), chunks=(500_000,)
        )
    x, read = extracted(collection_tests, tmp_path, "variance.hspy")
    name = variance.replace("/", ".")
    assert original(x)[f"{name}.data.shape"] == [4_000_000]
    assert read < 256 * 1024


# MATLAB


def test_a_matlab_5_file(collection_tests, tmp_path, monkeypatch):
    tree = collection_tests.materialise("matlab", tmp_path)
    header = (
        "MATLAB 5.0 MAT-file, Platform: GLNX86, Created on: Fri Feb 20 15:26:59 2009"
    )
    for zone in ("UTC", "Europe/Berlin"):
        monkeypatch.setenv("TZ", zone)
        time.tzset()
        x, _ = extracted(collection_tests, tree, "testmulti_7.4_GLNX86.mat")
        assert x.summary == [header]
        assert original(x) == {
            "header": header,
            "theta.shape": [1, 9],
            "theta.class": "double",
            "a.shape": [3, 5],
            "a.class": "double",
        }
    monkeypatch.delenv("TZ")
    time.tzset()


def test_a_matlab_73_file(collection_tests, tmp_path):
    tree = collection_tests.materialise("matlab", tmp_path / "a")
    x, _ = extracted(collection_tests, tree, "testhdf5_7.4_GLNX86.mat")
    assert original(x) == {
        "header": "MATLAB 7.0 MAT-file, Platform: GLNX86, Created on: Sat Oct  4 "
        "19:01:58 2008 HDF5 schema 0.05 .",
        "testdouble.shape": [9, 1],
        "testdouble.dtype": "<f8",
        "testdouble.MATLAB_class": "double",
    }
    tree = collection_tests.materialise("matlab73_refs", tmp_path / "b")
    y, _ = extracted(collection_tests, tree, "cells.mat")
    assert original(y)["cells.MATLAB_class"] == "cell"
    assert not [k for k in original(y) if k.startswith("#refs#")]


def test_a_matlab_4_file(collection_tests, tmp_path):
    tree = collection_tests.materialise("matlab", tmp_path)
    x, _ = extracted(collection_tests, tree, "testdouble_4.2c_SOL2.mat")
    assert original(x) == {"testdouble.shape": [1, 9], "testdouble.class": "double"}


def test_a_text_file_named_like_a_matlab_file(collection_tests, tmp_path):
    d = datasets(collection_tests, collection_tests.materialise("misnamed", tmp_path))[
        "notes.mat"
    ]
    assert d.type == "text/plain"


# Notebooks


def test_a_file_named_like_a_notebook_that_is_not_json(collection_tests, tmp_path):
    d = datasets(collection_tests, collection_tests.materialise("misnamed", tmp_path))[
        "notes.ipynb"
    ]
    assert d.type == "text/plain"


def test_a_version_4_notebook(collection_tests, tmp_path):
    tree = collection_tests.materialise("notebooks", tmp_path)
    x, _ = extracted(collection_tests, tree, "test4.5.ipynb")
    found = original(x)
    assert found["kernelspec.display_name"] == "Python 3 (ipykernel)"
    assert found["language_info.version"] == "3.10.0"
    assert (found["nbformat"], found["nbformat_minor"]) == (4, 5)
    assert mapped(x) == {
        "cells.code": 4,
        "cells.markdown": 5,
        "first_heading": "nbconvert latex test",
    }
    assert x.summary == ["nbconvert latex test", "Python 3 (ipykernel)"]
    # No output: the notebook's outputs hold "text/plain" data
    assert "text/plain" not in json.dumps(x.values).replace('"text/x-python"', "")


def test_a_version_3_notebook(collection_tests, tmp_path):
    tree = collection_tests.materialise("notebooks", tmp_path)
    x, _ = extracted(collection_tests, tree, "test3.ipynb")
    assert original(x)["nbformat"] == 3
    assert mapped(x)["cells.markdown"] == 5  # its heading cells among them
    assert mapped(x)["first_heading"] == "nbconvert latex test"


def test_editor_state(collection_tests, tmp_path):
    nb = nbformat.v4.new_notebook()
    nb.metadata = {
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "widgets": {"application/vnd.jupyter.widget-state+json": {"state": {}}},
        "toc": {"number_sections": True},
    }
    nbformat.write(nb, tmp_path / "state.ipynb")
    x, _ = extracted(collection_tests, tmp_path, "state.ipynb")
    assert set(original(x)) == {
        "kernelspec.name",
        "kernelspec.display_name",
        "nbformat",
        "nbformat_minor",
    }


def test_a_large_notebook(collection_tests, tmp_path, monkeypatch):
    nb = nbformat.v4.new_notebook()
    nb.metadata = {"kernelspec": {"name": "python3", "display_name": "Python 3"}}
    cell = nbformat.v4.new_code_cell("print(1)")
    cell.outputs = [nbformat.v4.new_output("stream", text="x" * 200_000)]
    nb.cells = [nbformat.v4.new_markdown_cell("# Big"), cell]
    nbformat.write(nb, tmp_path / "big.ipynb")
    monkeypatch.setattr(notebook, "MAX_WHOLE", 100_000)
    x, read = extracted(collection_tests, tmp_path, "big.ipynb")
    assert original(x)["kernelspec.display_name"] == "Python 3"
    assert "cells.code" not in mapped(x) and "read" in mapped(x)
    assert x.summary == ["Python 3"]
    assert read <= notebook.TAIL
    # A writer that puts the metadata first: not in the tail
    text = json.dumps({"metadata": nb.metadata, "cells": nb.cells, "nbformat": 4})
    (tmp_path / "first.ipynb").write_text(text)
    y, _ = extracted(collection_tests, tmp_path, "first.ipynb")
    assert original(y) == {}
    assert mapped(y)["read"].endswith("notebook metadata not found in the tail")


# Python scripts


def test_a_script(collection_tests, tmp_path):
    written = tmp_path / "written"
    (tmp_path / "tool.py").write_text(
        "#!/usr/bin/env python3\n"
        '"""Tool to convert scans.\n\nMore text."""\n'
        "import os\n"
        "def convert():\n"
        "    import scipy\n"
        "import numpy as np\n"
        "from .tools import x\n"
        '__version__ = "1.2"\n'
        "__author__ = 'Someone'\n"
        f"open({str(written)!r}, 'w').write('ran')\n"
    )
    x, _ = extracted(collection_tests, tmp_path, "tool.py")
    assert original(x) == {
        "shebang": "#!/usr/bin/env python3",
        "docstring": "Tool to convert scans.\n\nMore text.",
        "__version__": "1.2",
        "__author__": "Someone",
        # In source order: the import in the function before the later ones
        "imports": ["os", "scipy", "numpy", ".tools"],
    }
    assert x.summary == ["Tool to convert scans."]
    assert not written.exists()


def test_a_python_2_script(collection_tests, tmp_path):
    tree = collection_tests.materialise("python2", tmp_path)
    x, _ = extracted(collection_tests, tree, "legacy.py")
    assert original(x) == {"shebang": "#!/usr/bin/env python"}
    assert mapped(x)["not_parsed"].endswith("(line 3)")


def test_a_large_script(collection_tests, tmp_path):
    (tmp_path / "huge.py").write_text("#!/usr/bin/python\n" + "x = 1\n" * 200_000)
    x, read = extracted(collection_tests, tmp_path, "huge.py")
    assert original(x) == {"shebang": "#!/usr/bin/python"}
    assert mapped(x) == {"not_parsed": "larger than 1048576 bytes"}
    assert read <= (1 << 20) + 1


# Pickles


class Touch:
    """Unpickling it creates the file at path."""

    def __init__(self, path):
        self.path = path

    def __reduce__(self):
        return (Path.touch, (self.path,))


def test_a_pickle(collection_tests, tmp_path):
    target = tmp_path / "touched"
    (tmp_path / "state.pkl").write_bytes(pickle.dumps(Touch(target), protocol=4))
    d = datasets(collection_tests, tmp_path)["state.pkl"]
    assert d.type == "application/x-python-pickle"
    x, _ = extracted(collection_tests, tmp_path, "state.pkl")
    assert x.summary == ["protocol 4"]
    assert original(x) == {"protocol": 4}
    assert not target.exists()


def test_a_protocol_0_pickle(collection_tests, tmp_path):
    d = datasets(collection_tests, collection_tests.materialise("misnamed", tmp_path))[
        "old.pkl"
    ]
    assert d.type != "application/x-python-pickle"
    assert "no pickle protocol 2 to 5 start" in d.basis
