"""Gatan Digital Micrograph files (DM3, DM4): single-file datasets, recognised by their header (dm.xml).

Extraction goes through RosettaSciIO's reader: it parses the tags and skips the
image data by seeking past it (D7; bytes read per file in the tests). `.dmw`
files, typed by their name, are claimed by `em/dmw` when they have a DM header
and described by all their tags (change recognition-checks-content, E1);
`.dmwx` files, ZIPs of a workspace and its images, by `em/dmwx` (E4).
"""

import io
import os
import struct
import zipfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from typing import BinaryIO

from modama_crawler.formats import (
    Collection,
    Dataset,
    Directory,
    Entry,
    Extracted,
    Format,
)

HERE = Path(__file__).parent
# Python sizes a file's buffer from st_blksize, 1 MiB on NFS: every seek in the tag
# tree then refills up to 1 MiB (staging run 3, F14: 1,168 kB per file). 64 KiB is
# NFS's read size; smaller buffers read less but need more round trips.
BUFFER = 64 * 1024
HEADER = 16  # bytes version() needs: the DM4 header's byte order flag ends at 16
DMW = "application/x.dm-dmw"
DMWX = "application/x.dm-dmwx"
# A ZIP's local file header (APPNOTE 4.3.7): 30 bytes, then the member's name
LOCAL = struct.Struct("<4s22xHH")  # signature, ..., name length, extra length
ZIP_HEAD = LOCAL.size + 1024  # with a first member's name of up to 1,024 bytes


def first_member(data: bytes) -> str | None:
    """The name of a ZIP's first member from its first bytes, None if they are not a ZIP's local header."""
    if len(data) < LOCAL.size:
        return None
    signature, n, _ = LOCAL.unpack_from(data)
    name = data[LOCAL.size : LOCAL.size + n]
    if signature != b"PK\3\4" or len(name) < n:
        return None
    return name.decode("utf-8", "replace")


def version(data: bytes) -> int | None:
    """3 or 4 when data starts with the DM3 or DM4 header as dm.xml's magic tests it, else None.

    The version (big32) at 0, then the byte order flag (big32, 0 or 1) at 8 in
    DM3 and at 12 in DM4, after the file size.
    """
    v = int.from_bytes(data[:4], "big") if len(data) >= 4 else None
    flag = {3: data[8:12], 4: data[12:16]}.get(v)
    return v if flag in (bytes(4), b"\0\0\0\1") else None


def header(d: Directory, e: Entry, n: int = HEADER) -> bytes | None:
    """The first n bytes of e, or None if it cannot be read: then it keeps its type, the crawl warns
    at it, and the directory is recognised again next crawl (Directory.cannot_read), while the format's
    other datasets stand (change recognition-checks-content, code review finding 1)."""
    try:
        return d.read(e, n)
    except OSError as error:
        d.cannot_read(e, error)
        return None


def tag_paths(
    node: dict,
    skip: Callable[[tuple[str, ...], dict], bool] = lambda path, group: False,
    path: tuple[str, ...] = (),
) -> Iterator[tuple[str, object]]:
    """(dotted path, value) of every tag below node in the reader's order, its values
    as the reader gives them (an empty one too: decision 161), without the groups
    for which skip(path, group) is true."""
    for key, value in node.items():
        here = (*path, str(key))
        if isinstance(value, dict):
            if not skip(here, value):
                yield from tag_paths(value, skip, here)
        else:
            yield ".".join(here), value


def parsed(path: str):
    """RosettaSciIO's DM reader with the file's tag tree parsed, from our own handle.

    A small buffer and readahead off (F14); the image data is never read.
    """
    with open(path, "rb", buffering=BUFFER) as f:
        # The advice is an optimisation: a file system that refuses it, or a
        # platform without it, still reads the file (as mime.py)
        if hasattr(os, "posix_fadvise"):
            with suppress(OSError):
                os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_RANDOM)
        return parsed_from(f)


def parsed_from(f: BinaryIO):
    """RosettaSciIO's DM reader with the tag tree of the open file f parsed (a file, or a ZIP member's bytes)."""
    from rsciio.digitalmicrograph._api import (  # imports dask: in the worker only
        DigitalMicrographReader,
    )

    dm = DigitalMicrographReader(f)
    dm.parse_file()
    return dm


def first_image(path: str) -> dict:
    """What RosettaSciIO's `file_reader(path)[0]` gives, except the data, from our own handle.

    The same steps as `rsciio.digitalmicrograph.file_reader` (0.15.0) on a file
    opened with a small buffer and readahead off, without `get_data`, which
    maps the image (and refuses RGBA images when lazy). Identical results on
    RosettaSciIO's 98 DM test files that `file_reader` reads (F14); a test
    compares the two on this part's fixtures.
    """
    from rsciio.digitalmicrograph._api import ImageObject

    dm = parsed(path)
    image = ImageObject(dm.get_image_dictionaries()[0], dm.f, order=None)
    image.filename = path
    # As file_reader: ImageList moves to the end of the tags
    del dm.tags_dict["ImageList"]
    dm.tags_dict["ImageList"] = {"TagGroup0": image.imdict.to_dict()}
    metadata = image.get_metadata()
    metadata["General"]["original_filename"] = os.path.basename(path)
    return {
        "axes": image.get_axes_dict(),
        "metadata": deepcopy(metadata),
        "original_metadata": deepcopy(dm.tags_dict),
        "mapping": image.get_mapping(),
    }


class Dm(Format):
    """A DM file of the version its `type` names, as one dataset."""

    priority = 60

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        for e in d.of_type(self.type):
            yield Dataset(anchor=e.rel, basis="Digital Micrograph header")

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """The acquisition values the tags hold (spec formats/dm, "DM metadata is extracted from the tags")."""
        image = first_image(root + dataset.anchor)
        tags = mapped(image["original_metadata"], image["mapping"])
        instrument = {
            k.split(".", 2)[2]: v
            for k, v in tags.items()
            if k.startswith(
                ("Acquisition_instrument.TEM.", "Acquisition_instrument.SEM.")
            )
        }
        summary, subjects = [], []
        # The reader's names and numbers as it gives them, not rounded, no unit
        # added (README, "Values and units"). TODO: units and meaning (BACKLOG,
        # "Units and meaning")
        for name in ("beam_energy", "magnification", "camera_length"):
            if (value := instrument.get(name)) is not None:
                summary.append(f"{name} {value}")
        axes = image["axes"]
        x = next((a for a in axes if a["name"] == "x"), None)
        if x is not None and x["units"] and x["units"] != "<undefined>":
            summary.append(f"{float(x['scale'])} {x['units']}/pixel")
        summary.append("×".join(str(a["size"]) for a in reversed(axes)))
        databar = image["original_metadata"]["ImageList"]["TagGroup0"]["ImageTags"].get(
            "DataBar", {}
        )
        if detector := databar.get("Device Name"):
            summary.append(detector)
        if microscope := instrument.get("microscope"):
            summary.append(microscope)
            subjects.append(microscope)
        if "General.date" in tags:
            summary.append(
                f"{tags['General.date']} {tags.get('General.time', '')[:5]}".strip()
            )
        if mode := instrument.get("acquisition_mode"):
            subjects.append(mode)
        if signal := image["metadata"]["Signal"].get("signal_type"):
            subjects.append(signal)
        values = {
            "tags": tags,
            "axes": [
                {
                    "name": a["name"],
                    "size": a["size"],
                    "scale": float(a["scale"]),
                    "units": a["units"],
                }
                for a in axes
            ],
            "detector": detector,
        }
        return Extracted(summary=summary, subjects=subjects, values=values)


class Dm3(Dm):
    type = "application/x.dm3"
    display_name = "Gatan Digital Micrograph (DM3)"
    reacts_to = frozenset({type})


class Dm4(Dm):
    type = "application/x.dm4"
    display_name = "Gatan Digital Micrograph (DM4)"
    reacts_to = frozenset({type})


class Dmw(Format):
    """A .dmw file (a DM workspace) with a DM header, as one dataset described by all its tags (decision 173).

    The name decides the type without reading the file; recognition reads its
    header, and a file without one gets the type it has without the name rule
    (Directory.not_of_type). Its name, in the subject and the description,
    is the type's comment in dm.xml, one name in both (Gatan's own name is to
    be confirmed with fresh files, open items 155 and 184).
    """

    type = DMW
    # Before em/dm3 and em/dm4 (60), which may claim a dropped file (decision 165)
    priority = 61
    reacts_to = frozenset({type})

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        # By type, not by name: the glob matches any case (Up.DMW)
        for e in d.of_type(self.type):
            if (data := header(d, e)) is None:
                continue
            match version(data):
                case 4:
                    yield Dataset(anchor=e.rel, basis="Digital Micrograph header")
                case 3:
                    # Handled, and a file of interest (decision 174; BACKLOG,
                    # "Suspicious results for manual follow-up")
                    yield Dataset(
                        anchor=e.rel,
                        basis="Digital Micrograph header; file of interest: "
                        "DM3, no .dmw in DM3 seen yet",
                    )
                case _:
                    d.not_of_type(e, "no DM header")

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """Every tag of the file, as the reader gives them (spec formats/dm, "A .dmw file is described by all its tags")."""
        # Everything for now (decision 173). TODO: filter to the relevant tags
        # (BACKLOG, ".dmw description")
        found = tag_paths(parsed(root + dataset.anchor).tags_dict)
        return Extracted(summary=[f"{p} {v}" for p, v in found], subjects=[], values={})


class Dmwx(Format):
    """A compressed workspace: a ZIP whose first member is a .dmw, as one dataset (decision 190).

    Described by the inner workspace's tags and the archive's members; the
    images in it are never read (spec formats/dm, "A compressed workspace is
    described by its workspace and its members").
    """

    type = DMWX
    priority = 61  # as em/dmw (decision 165)
    reacts_to = frozenset({type})

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        for e in d.of_type(self.type):
            if (data := header(d, e, ZIP_HEAD)) is None:
                continue
            name = first_member(data)
            if name is not None and name.lower().endswith(".dmw"):
                yield Dataset(anchor=e.rel, basis="ZIP, first member a .dmw")
            else:
                d.not_of_type(e, "no .dmw first in a ZIP")

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """The inner workspace's tags, then each member's name and size: the central directory and the .dmw are read, no image."""
        # Unbuffered: zipfile then reads what it asks for, the end record, the
        # central directory and the one member, nothing of the images around it
        with (
            open(root + dataset.anchor, "rb", buffering=0) as f,
            zipfile.ZipFile(f) as z,
        ):
            members = z.infolist()
            inner = next(i for i in members if i.filename.lower().endswith(".dmw"))
            workspace = parsed_from(io.BytesIO(z.read(inner))).tags_dict
        summary = [f"{p} {v}" for p, v in tag_paths(workspace)]
        summary += [f"member {i.filename} {i.file_size} B" for i in members]
        return Extracted(summary=summary, subjects=[], values={})


class Tags(dict):
    """A tag group as HyperSpy's metadata tree hands it to RosettaSciIO's conversions:
    spaces in keys as underscores, `get` by a dotted path."""

    @classmethod
    def of(cls, node: dict) -> "Tags":
        return cls(
            (str(k).replace(" ", "_"), cls.of(v) if isinstance(v, dict) else v)
            for k, v in node.items()
        )

    def get(self, path, default=None):
        node = self
        for part in path.replace(" ", "_").split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def mapped(original: dict, mapping: dict) -> dict:
    """RosettaSciIO's mapping applied as HyperSpy applies it: tag path -> (metadata path, conversion).

    Values that are missing, or that the conversion turns into None, are left out.
    """
    tags = Tags.of(original)
    out = {}
    for path, (target, convert) in mapping.items():
        value = tags.get(path)
        if value is None:
            continue
        value = convert(value) if convert else value
        if value is not None and value != []:
            out[target] = value.item() if hasattr(value, "item") else value
    return out


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection(
    "em", [Dm3(), Dm4(), Dmw(), Dmwx()], mime_files=(HERE / "dm.xml",)
)
