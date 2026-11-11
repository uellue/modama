"""Gatan Digital Micrograph files (DM3, DM4): single-file datasets, recognised by their header (dm.xml).

Extraction goes through RosettaSciIO's reader: it parses the tags and skips the
image data by seeking past it (D7; bytes read per file in the tests).
"""

import os
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path

from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format

HERE = Path(__file__).parent
# Python sizes a file's buffer from st_blksize, 1 MiB on NFS: every seek in the tag
# tree then refills up to 1 MiB (staging run 3, F14: 1,168 kB per file). 64 KiB is
# NFS's read size; smaller buffers read less but need more round trips.
BUFFER = 64 * 1024


def parsed(path: str):
    """RosettaSciIO's DM reader with the file's tag tree parsed, from our own handle.

    A small buffer and readahead off (F14); the image data is never read.
    """
    from rsciio.digitalmicrograph._api import (  # imports dask: in the worker only
        DigitalMicrographReader,
    )

    with open(path, "rb", buffering=BUFFER) as f:
        os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_RANDOM)
        dm = DigitalMicrographReader(f)
        dm.parse_file()
    return dm


def first_image(path: str) -> dict:
    """What RosettaSciIO's `file_reader(path)[0]` gives, except the data, from our own handle.

    The same steps as `rsciio.digitalmicrograph.file_reader` (0.15.0) on a file
    opened with a small buffer and readahead off, without `get_data`, which
    maps the image (and refuses RGBA images when lazy). Identical results on
    RosettaSciIO's 98 DM test files that `file_reader` reads (F14).
    """
    from rsciio.digitalmicrograph._api import ImageObject

    dm = parsed(path)
    image = ImageObject(dm.get_image_dictionaries()[0], dm.f, order=None)
    image.filename = path
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
    # 2: the reader's names and numbers, no units added; 3: our own handle (F14),
    # so RGBA images, which file_reader refused when lazy, are extracted again
    extractor_version = "3"

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
        # The reader's names and numbers as it gives them, no unit added (README,
        # "Values and units"). TODO: units and meaning (BACKLOG, "Units and meaning")
        for name in ("beam_energy", "magnification", "camera_length"):
            if (value := instrument.get(name)) is not None:
                summary.append(f"{name} {value:g}")
        axes = image["axes"]
        x = next((a for a in axes if a["name"] == "x"), None)
        if x is not None and x["units"] and x["units"] != "<undefined>":
            summary.append(f"{x['scale']:.3g} {x['units']}/pixel")
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
COLLECTION = Collection("em", [Dm3(), Dm4()], mime_files=(HERE / "dm.xml",))
