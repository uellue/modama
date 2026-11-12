"""Python and data-science files: NumPy, HDF5 (NeXus, HyperSpy, MATLAB 7.3), MATLAB,
Jupyter notebooks, Python scripts and pickles, each a single-file dataset (pydata.xml).

Extraction reads headers and metadata with the field's reader, never an array
(spec formats/pydata): the values are `original_metadata`, what the file says,
every entry but one skip list per format, and `mapped_metadata`, what we or a
reader compute; a summary line of a few chosen entries starts the description.
Files typed by their name only are checked by their first bytes during
recognition, and lose that type when they are not what it says
(Directory.not_of_type).
"""

from collections.abc import Iterable
from pathlib import Path

from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format

# The readers' modules import h5py, NumPy, SciPy and nbformat (0.2 s): in the
# extractors only, so that recognition and the other commands start without them
from .values import HDF5, ZIP, start

HERE = Path(__file__).parent


class Single(Format):
    """A file of the format's type as one dataset, described by `read`.

    With `head` > 0, recognition reads the file's first `head` bytes, and a
    file for which `fits` is false loses its type, for `reason`.
    """

    priority = 60
    basis = ""
    head = 0
    reason = ""

    def __init__(self):
        self.reacts_to = frozenset({self.type})

    def fits(self, data: bytes) -> bool:
        return True

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        for e in d.of_type(self.type):
            if self.head:
                if (data := start(d, e, self.head)) is None:
                    continue
                if not self.fits(data):
                    d.not_of_type(e, self.reason)
                    continue
            yield Dataset(anchor=e.rel, basis=self.basis)

    def read(self, path: str) -> tuple[dict, dict, list[str]]:
        """original_metadata, mapped_metadata and the summary line of the file at path."""
        raise NotImplementedError

    def terms(self, original: dict) -> list[str]:
        return []

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        original, mapped, summary = self.read(root + dataset.anchor)
        return Extracted(
            summary=summary,
            subjects=self.terms(original),
            values={"original_metadata": original, "mapped_metadata": mapped},
        )


class Npy(Single):
    type = "application/x-npy"
    basis = "NumPy magic"

    def read(self, path):
        from . import npy

        return npy.npy(path)


class Npz(Single):
    type = "application/x.npz"
    priority = 61  # before the formats that may claim a dropped file's type
    basis = "ZIP named .npz"
    head = len(ZIP)
    reason = "no ZIP signature"

    def fits(self, data):
        return data == ZIP

    def read(self, path):
        from . import npy

        return npy.npz(path)


class Hdf5(Single):
    type = "application/vnd.hdfgroup.hdf5"
    basis = "HDF5 signature"

    def read(self, path):
        from . import hdf5

        original, mapped = hdf5.described(path)
        return original, mapped, hdf5.summary(original)

    def terms(self, original):
        from . import hdf5

        return hdf5.terms(original)


class Nexus(Hdf5):
    type = "application/x.nexus"
    priority = 61  # before common/hdf5, which claims a dropped file with a user block
    basis = "HDF5 signature, named .nxs"
    head = len(HDF5)
    reason = "no HDF5 signature at its start"

    def fits(self, data):
        return data == HDF5


class Hspy(Nexus):
    """Content beats name: HyperSpy's root attribute `file_format` "HyperSpy", which
    HyperSpy writes first, has its value within the first 4 KiB of its files (at byte
    2,080 of RosettaSciIO's test files); searched as a magic rule with an offset range
    would search it, not parsed."""

    type = "application/x.hspy"
    basis = "HDF5 signature and HyperSpy, named .hspy"
    head = 4096
    reason = "no HDF5 signature at its start, or no HyperSpy in its first 4096 bytes"

    def fits(self, data):
        return data.startswith(HDF5) and b"HyperSpy" in data


class Matlab(Single):
    type = "application/x-matlab-data"
    priority = 61
    basis = "MATLAB header, or a version 4 file"
    head = 6
    reason = "no MATLAB header, not a version 4 file"

    def fits(self, data):
        # SciPy's matfile_version: a zero byte in the first 4 bytes is version 4
        return data.startswith(b"MATLAB") or 0 in data[:4]

    def read(self, path):
        from . import matlab

        return matlab.described(path)


class Notebook(Single):
    type = "application/x-ipynb+json"
    priority = 61
    basis = "JSON object named .ipynb"
    head = 64  # a byte order mark and white space before the {
    reason = "not a JSON object"

    def fits(self, data):
        return data.removeprefix(b"\xef\xbb\xbf").lstrip().startswith(b"{")

    def read(self, path):
        from . import notebook

        return notebook.described(path)


class Python(Single):
    type = "text/x-python"

    def read(self, path):
        from . import script

        return script.described(path)


class Python3(Python):
    type = "text/x-python3"


class Pickle(Single):
    type = "application/x-python-pickle"
    priority = 61
    basis = "pickle protocol 2 to 5"
    head = 2
    reason = "no pickle protocol 2 to 5 start"

    def fits(self, data):
        return len(data) == 2 and data[0] == 0x80 and 2 <= data[1] <= 5

    def read(self, path):
        # The PROTO opcode and its argument only; a pickle is never unpickled
        with open(path, "rb", buffering=0) as f:
            protocol = f.read(2)[1]
        return {"protocol": protocol}, {}, [f"protocol {protocol}"]


# This part of the collection, for its tests; the package's COLLECTION joins the parts
COLLECTION = Collection(
    "pydata",
    [
        Npy(),
        Npz(),
        Hdf5(),
        Nexus(),
        Hspy(),
        Matlab(),
        Notebook(),
        Python(),
        Python3(),
        Pickle(),
    ],
    mime_files=(HERE / "pydata.xml",),
)
