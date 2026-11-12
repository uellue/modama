"""NanoMegas ASTAR block files (.blo): single-file datasets, recognised by their header (blockfile.xml).

Extraction goes through RosettaSciIO's blockfile reader, lazily: it reads the
header and the note after it, and maps the diffraction patterns without
loading them (spec formats/blockfile, "The header, not the data").
"""

from collections.abc import Iterable
from pathlib import Path

from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format

from ..dm import mapped, tag_paths

HERE = Path(__file__).parent
TYPE = "application/x.blockfile"
TEM = "Acquisition_instrument.TEM."


class Blockfile(Format):
    type = TYPE
    priority = 60
    reacts_to = frozenset({TYPE})

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        for e in d.of_type(TYPE):
            yield Dataset(anchor=e.rel, basis="IMGBLO header")

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """Scan, step, pattern size, beam energy, camera length, rotation and time (spec formats/blockfile)."""
        # Imports dask and scikit-image: in the worker only
        from rsciio.blockfile import file_reader

        (scan,) = file_reader(root + dataset.anchor, lazy=True)
        # The metadata as the reader gives it, then its mapping applied, which
        # converts the header's fields: V to kV, 10 × mm to m, 100 × degrees to
        # degrees (blockfile/_api.py, mapping and get_header_dtype_list). The
        # date and time are in the process's local time zone, UTC in the image
        tags = {
            **dict(tag_paths(scan["metadata"])),
            **mapped(scan["original_metadata"], scan["mapping"]),
        }
        y, x, dy, dx = scan["axes"]  # lazy: never squeezed
        summary = [
            f"scan of {x['size']}×{y['size']} positions",
            f"step {float(x['scale'])}×{float(y['scale'])} {x['units']}",
            f"{dx['size']}×{dy['size']} pixel diffraction patterns",
            f"beam energy {tags[TEM + 'beam_energy']} kV",
            f"camera length {tags[TEM + 'camera_length']} m",
        ]
        if rotation := tags[TEM + "rotation"]:
            summary.append(f"scan rotation {rotation}°")
        summary.append(f"{tags['General.date']} {tags['General.time'][:5]}")
        values = {
            "tags": tags,
            "axes": [
                {
                    "name": a["name"],
                    "size": a["size"],
                    "scale": float(a["scale"]),
                    "units": a["units"],
                }
                for a in scan["axes"]
            ],
        }
        return Extracted(summary=summary, subjects=["4D-STEM"], values=values)


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [Blockfile()], mime_files=(HERE / "blockfile.xml",))
