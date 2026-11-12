"""Merlin acquisitions: the text header (merlin.xml) with its .mib frame files, as one dataset anchored at the header.

The frames belong to a header by LiberTEM's naming rule (MIBDataSet): the
.mib files whose names start with the header's stem (`acq.hdr`: `acq*.mib`).
Extraction reads the header itself (`read_header`) and the first frame's
header through RosettaSciIO.
"""

import os
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format

HERE = Path(__file__).parent
# The header is read whole; real headers are a few kB
MAX_HEADER = 64 << 10
HEADER = "application/x.merlin-header"
FRAMES = "application/x.merlin-mib"
# "(day, mnth, yr, hr, min, s)" or "(yr, mnth, day, hr, min, s)" follows; the value is day/month/year in both
DATE = "Time and Date Stamp"


def read_header(path: str) -> dict[str, str]:
    """The header's `key<TAB>value` lines, as RosettaSciIO's parse_hdr_file reads them, but in Latin-1.

    parse_hdr_file decodes in the locale's encoding (UTF-8), and the Merlin
    software writes "µ" as the single byte 0xB5 (spec formats/merlin, "A
    header that is not UTF-8"). Latin-1 decodes every byte, and µ stays µ;
    cp1252 would fail on the bytes it leaves undefined (0x81, 0x8D, 0x8F,
    0x90, 0x9D). Keys lose a trailing ":"; some have none ("Sensor Bias (V, µA)").
    """
    size = os.stat(path).st_size
    if size > MAX_HEADER:
        raise ValueError(f"header of {size:,} bytes, over {MAX_HEADER:,}")
    header = {}
    with open(path, encoding="latin-1") as f:
        for line in f:
            if line.startswith(("HDR", "End\t")):
                continue
            key, value = line.split("\t", 1)
            header[key.rstrip(":")] = value.rstrip("\n")
    return header


class Merlin(Format):
    type = HEADER
    display_name = "Quantum Detectors Merlin"
    priority = 60
    reacts_to = frozenset({HEADER, FRAMES})

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        frames = d.of_type(FRAMES)
        claimed = set()
        # The longest stem first, so that acq1.hdr keeps acq1*.mib from acq.hdr
        for header in sorted(d.of_type(HEADER), key=lambda e: -len(e.name)):
            stem = header.name.rpartition(".")[0]
            mine = [
                f.rel
                for f in frames
                if f.rel not in claimed and f.name.startswith(stem)
            ]
            if not mine:
                continue
            claimed.update(mine)
            yield Dataset(
                anchor=header.rel,
                members=(header.rel, *mine),
                basis=f"{len(mine)} frame file(s) {stem}*.mib",
            )
        orphans = sorted(f.name for f in frames if f.rel not in claimed)
        if orphans:
            d.warn(
                d.rel,
                f"{len(orphans)} .mib file(s) without a Merlin header (.hdr), "
                f"for example {orphans[0]}",
            )

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """Frames, frame size, bit depth and time (spec formats/merlin, "Merlin metadata is extracted from the header")."""
        from rsciio.quantumdetector._api import MIBProperties

        hdr = read_header(root + dataset.anchor)
        first = MIBProperties()
        first.parse_file(root + next(m for m in dataset.members if m != dataset.anchor))
        frames = int(hdr["Frames in Acquisition (Number)"])
        height, width = first.merlin_size
        depth = int(hdr["Counter Depth (number)"])
        readout = hdr.get("Readout System", "").strip()
        # The key by its start (spec formats/merlin, "The date key names its
        # fields in another order"); a value in another form fails, naming it
        date = next((k for k in hdr if k.startswith(DATE)), None)
        if date is None:
            raise KeyError(DATE)
        stamp = hdr[date].strip()
        try:
            acquired = datetime.strptime(stamp, "%d/%m/%Y %H:%M:%S")
        except ValueError as e:
            raise ValueError(f"{date}: {stamp!r} is not dd/mm/yyyy hh:mm:ss ({e})")
        summary = [
            f"{frames:,} frame{'' if frames == 1 else 's'}",
            f"{width}×{height} pixels",
            f"{depth}-bit",
        ]
        if readout:
            summary.append(readout)
        summary.append(acquired.strftime("%Y-%m-%d %H:%M"))
        values = {
            "frames": frames,
            "frame": [width, height],
            "counter_depth": depth,
            "readout": readout,
            "acquired": acquired.isoformat(),
        }
        return Extracted(
            summary=summary, subjects=[readout] if readout else [], values=values
        )


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [Merlin()], mime_files=(HERE / "merlin.xml",))
