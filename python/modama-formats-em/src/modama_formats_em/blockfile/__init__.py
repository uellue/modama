"""NanoMegas ASTAR block files (.blo): single-file datasets, recognised by their header (blockfile.xml).

Extraction goes through RosettaSciIO's blockfile reader, lazily: it reads the
header and the note after it, and maps the diffraction patterns without
loading them (spec formats/blockfile, "The header, not the data").
"""

import warnings
from collections.abc import Iterable
from pathlib import Path

from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format

from ..dm import mapped, tag_paths

HERE = Path(__file__).parent
TYPE = "application/x.blockfile"
# The header's fields the summary shows, under the reader's names, as found
# (decision 230); Scan_rotation only where it is not 0
SUMMARY = ("NX", "NY", "SX", "SY", "DP_SZ", "Beam_energy", "Camera_length")
# The reader's date and time, converted to the process's local time zone
# (rsciio.utils._date_time.serial_date_to_ISO_format); the file states no zone
LOCAL = ("General.date", "General.time", "General.time_zone")


def plain(value):
    """A header field as a JSON value: bytes as Latin-1 text, a NumPy scalar as a Python one."""
    if isinstance(value, bytes):
        return value.decode("latin-1")
    return value.item() if hasattr(value, "item") else value


class Blockfile(Format):
    type = TYPE
    priority = 60
    reacts_to = frozenset({TYPE})

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        for e in d.of_type(TYPE):
            yield Dataset(anchor=e.rel, basis="IMGBLO header")

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """The header's fields as the reader gives them, the mapped metadata second (spec formats/blockfile)."""
        # Imports dask and scikit-image: in the worker only
        from rsciio.blockfile import file_reader
        from rsciio.utils._date_time import serial_date_to_datetime

        # The reader's warnings go into the record, not only to stderr (a
        # MAGIC it does not know: spec formats/blockfile, the 16-bit variant)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            (scan,) = file_reader(root + dataset.anchor, lazy=True)
        said = [str(w.message) for w in caught]
        # Every field the reader gives, flat under its dotted path; nothing
        # skipped: the header has no GUI settings or arrays (decision 230,
        # "every entry minus a skip list")
        original = {k: plain(v) for k, v in tag_paths(scan["original_metadata"])}
        header = {k.removeprefix("blockfile_header."): v for k, v in original.items()}
        # The serial date as written, without the reader's conversion to the
        # local time zone
        acquired = serial_date_to_datetime(header["Acquisition_time"]).replace(
            tzinfo=None
        )
        summary = [f"{name} {header[name]}" for name in SUMMARY]
        if header["Scan_rotation"]:
            summary.append(f"Scan_rotation {header['Scan_rotation']}")
        summary.append(acquired.strftime("%Y-%m-%d %H:%M"))
        summary += [f"reader warning: {text}" for text in said]
        values = {
            "original_metadata": original,
            # HyperSpy's names; the conversions are RosettaSciIO's (its mapping)
            "mapped_metadata": {
                **{k: v for k, v in tag_paths(scan["metadata"]) if k not in LOCAL},
                **mapped(scan["original_metadata"], scan["mapping"]),
            },
            "axes": [
                {
                    "name": a["name"],
                    "size": a["size"],
                    "scale": float(a["scale"]),
                    "units": a["units"],
                }
                for a in scan["axes"]
            ],
            "acquired": acquired.isoformat(),
            "reader_warnings": said,
        }
        return Extracted(summary=summary, subjects=["4D-STEM"], values=values)


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [Blockfile()], mime_files=(HERE / "blockfile.xml",))
