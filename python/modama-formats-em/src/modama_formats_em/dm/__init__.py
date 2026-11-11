"""Gatan Digital Micrograph files (DM3, DM4): single-file datasets, recognised by their header (dm.xml).

Extraction goes through RosettaSciIO's reader, lazily: it parses the tags and
skips the image data by seeking past it (D7; bytes read per file in the tests).
"""

from collections.abc import Iterable
from pathlib import Path

from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format

HERE = Path(__file__).parent


class Dm(Format):
    """A DM file of the version its `type` names, as one dataset."""

    priority = 60
    extractor_version = "2"  # 2: the reader's names and numbers, no units added

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        for e in d.of_type(self.type):
            yield Dataset(anchor=e.rel, basis="Digital Micrograph header")

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """The acquisition values the tags hold (spec formats/dm, "DM metadata is extracted from the tags")."""
        from rsciio.digitalmicrograph import (
            file_reader,  # imports dask: in the worker only
        )

        image = file_reader(root + dataset.anchor, lazy=True)[0]
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
