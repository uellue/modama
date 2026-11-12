"""Gatan Digital Micrograph files (DM3, DM4): single-file datasets, recognised by their header (dm.xml).

Extraction goes through RosettaSciIO's reader: it parses the tags and skips the
image data by seeking past it (D7; bytes read per file in the tests). Every
tag but one skip list (`skipped`: GMS's user-interface settings, values not
suitable for text) is kept as values, and a summary line from chosen tags of
the data image (`headline`, shared with K2IS) starts the description. `.dmw`
files, typed by their name, are claimed by `em/dmw` when they have a DM header
and described by their tags but the skip list (change recognition-checks-content, E1);
`.dmwx` files, ZIPs of a workspace and its images, by `em/dmwx` (E4).
"""

import io
import math
import os
import struct
import zipfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import suppress
from copy import deepcopy
from fnmatch import fnmatchcase
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

from ..values import textual

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
    skip: Callable[[tuple[str, ...], object], bool] = lambda path, value: False,
    path: tuple[str, ...] = (),
) -> Iterator[tuple[str, object]]:
    """(dotted path, value) of every tag below node in the reader's order, its values
    as the reader gives them (an empty one too: decision 161), without the tags and
    groups for which skip(path, value) is true."""
    for key, value in node.items():
        here = (*path, str(key))
        if skip(here, value):
            continue
        if isinstance(value, dict):
            yield from tag_paths(value, skip, here)
        else:
            yield ".".join(here), value


# The one skip list of DM files, K2IS tag files and workspaces: every tag is
# kept but these (decisions 129 and 235; @weber 2026-11-12: "not a positive
# list, but a negative 'skip these' list"; spec formats/dm, "What is left out"):
# 1. GMS's user-interface settings, by their dotted path (fnmatch patterns)
SETTINGS = (
    # the document's, page's and window's settings at the root of a DM file,
    # its thumbnails and the document's bookkeeping
    "ApplicationBounds",
    "DocumentObjectList",
    "HasWindowPosition",
    "Image Behavior",
    "ImageSourceList",
    "InImageMode",
    "LayoutType",
    "MinVersionList",
    "NextDocumentObjectID",
    "Page Behavior",
    "PageSetup",
    "SentinelList",
    "Thumbnails",
    "WindowPosition",
    # a workspace's windows (Window 0 (217, 84, 646, 536)); its frames stay
    "Window [0-9]*",
    # the definition of GMS's Session Info form (per field its label, tag
    # path, data type, precision, units, default value), under Microscope Info
    # in older GMS; the fields' values stay
    "Session Info.Items",
    "*.Session Info.Items",
    "Microscope Info.Items",
    "*.Microscope Info.Items",
)
# 2. a tag group of the image viewer's class: the window's and the screen's
#    relative position, zoom, auto zoom, view name, viewer class, its version
VIEWER_CLASSES = frozenset({"cm_stdviewerimagedisplayer"})
# 3. a value not suitable for text: too large, binary, an array not read (values.textual)


def skipped(path: tuple[str, ...], value) -> bool:
    """Whether a tag or tag group is on the skip list, for tag_paths."""
    dotted = ".".join(path)
    return (
        any(fnmatchcase(dotted, pattern) for pattern in SETTINGS)
        or (isinstance(value, dict) and value.get("Class Name") in VIEWER_CLASSES)
        or not textual(value)
    )


def kept(tags: dict) -> dict:
    """Every tag below tags but the skip list: dotted path -> value, for the values.
    The infinities and NaN, which JSON cannot hold, as Python writes them ("inf")."""

    def plain(value):
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        if isinstance(value, tuple | list):
            return type(value)(plain(v) for v in value)
        return value

    return {path: plain(value) for path, value in tag_paths(tags, skipped)}


def at(tags: dict, path: str):
    """The value at a dotted path of tag names, None if it is missing, a group or empty ([] for an empty string)."""
    node = tags
    for name in path.split("."):
        if not isinstance(node, dict) or name not in node:
            return None
        node = node[name]
    return None if isinstance(node, dict) or node in ("", []) else node


# The tags of the summary line, in its order (spec formats/dm, "The summary
# line of a DM file's tags"): the one positive list, by nature; choosing them
# is the line's only editorial step (decision 230). A tuple: the first of its
# tags present (decision 235: older GMS writes no Formatted tags, and Specimen
# and Operator under Microscope Info). SIZE: where the image's size goes
SIZE = "size"
HEADLINE = (
    "Microscope Info.Imaging Mode",
    "Microscope Info.Operation Mode",
    "Microscope Info.Illumination Mode",
    ("Microscope Info.Formatted Voltage", "Microscope Info.Voltage"),
    (
        "Microscope Info.Formatted Indicated Mag",
        "Microscope Info.Indicated Magnification",
    ),
    "Microscope Info.STEM Camera Length",
    "Acquisition.Device.Source Model",
    "DataBar.Device Name",
    "DataBar.Exposure Time (s)",
    "Acquisition.Parameters.Parameter Set Name",
    "SI Dimensions.Size X",
    "SI Dimensions.Size Y",
    SIZE,
    "DataBar.Acquisition Date",
    "DataBar.Acquisition Time",
    ("Session Info.Specimen", "Microscope Info.Specimen"),
    ("Session Info.Operator", "Microscope Info.Operator"),
)


def headline(tags: dict, size: Iterable[str] = ()) -> list[str]:
    """The summary line of a DM image's ImageTags or a K2IS tag file's tags: the values of
    the HEADLINE tags present, as the file holds them, size at SIZE, a value repeated once.

    A text as it is (`300kV`, `Lorentz`); a number after its tag's name
    (`Exposure Time (s) 2.0`), as the number alone says nothing, and not at all
    when it is 0, which GMS writes where it has no value (`STEM Camera Length
    0.0`). No word of ours, no conversion (decision 230).
    """
    phrases = []
    for entry in HEADLINE:
        if entry == SIZE:
            phrases += size
            continue
        paths = (entry,) if isinstance(entry, str) else entry
        found = ((p, v) for p in paths if (v := at(tags, p)) is not None)
        if (hit := next(found, None)) is None:
            continue
        path, value = hit
        if isinstance(value, str):
            phrases.append(value)
        elif value != 0:
            phrases.append(f"{path.rsplit('.', 1)[-1]} {value}")
    return list(dict.fromkeys(phrases))


def terms(tags: dict) -> list[str]:
    """Subjects from a DM image's or a K2IS tag file's tags: the imaging mode and the camera model."""
    found = (
        at(tags, "Microscope Info.Imaging Mode"),
        at(tags, "Acquisition.Device.Source Model"),
    )
    return [str(t) for t in found if t is not None]


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
        """Every tag but the skip list, a summary line from the data image's tags
        (spec formats/dm, "DM metadata is extracted from the tags")."""
        image = first_image(root + dataset.anchor)
        original = image["original_metadata"]
        # The data image's, not the thumbnail's: first_image's ImageList holds
        # the image RosettaSciIO's reader takes (get_image_dictionaries); a
        # stack builder's image keeps its tags in `source`, where the reader's
        # get_mapping reads them
        tags = original["ImageList"]["TagGroup0"]["ImageTags"]
        source = tags.get("source")
        created = source.get("Tags at creation") if isinstance(source, dict) else None
        if isinstance(created, dict):
            tags = created
        metadata = mapped(original, image["mapping"])
        instrument = {
            k.split(".", 2)[2]: v
            for k, v in metadata.items()
            if k.startswith(
                ("Acquisition_instrument.TEM.", "Acquisition_instrument.SEM.")
            )
        }
        axes = image["axes"]
        subjects = [
            instrument.get("microscope"),
            instrument.get("acquisition_mode"),
            image["metadata"]["Signal"].get("signal_type"),
        ]
        subjects = [s for s in subjects if s] + terms(tags)
        axes = [
            {
                "name": a["name"],
                "size": a["size"],
                "scale": float(a["scale"]),
                "units": a["units"],
            }
            for a in axes
        ]
        # The size as the reader gives it (decision 235): each axis's name and
        # size, then its scale where it has a unit
        size = [f"{a['name']} {a['size']}" for a in axes] + [
            f"scale {a['scale']} {a['units']}"
            for a in axes
            if a["units"] and a["units"] != "<undefined>"
        ]
        # What the file says first, RosettaSciIO's mapping second, labelled
        # (decision 230)
        values = {
            "original_metadata": kept(original),
            # without what is not suitable for text, as the original (the CL
            # saturation fraction of 16,384 values maps to a list too)
            "mapped_metadata": {k: v for k, v in metadata.items() if textual(v)},
            "axes": axes,
        }
        return Extracted(summary=headline(tags, size), subjects=subjects, values=values)


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
        """Every tag of the file but the skip list, as the reader gives them (spec formats/dm,
        "A .dmw file is described by all its tags"; "What is left out")."""
        # Everything not obviously uninteresting (decisions 173, 235). TODO:
        # filter to the relevant tags (BACKLOG, ".dmw description")
        found = tag_paths(parsed(root + dataset.anchor).tags_dict, skipped)
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
        summary = [f"{p} {v}" for p, v in tag_paths(workspace, skipped)]
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
