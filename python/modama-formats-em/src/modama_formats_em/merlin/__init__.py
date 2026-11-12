"""Merlin acquisitions: the text header (merlin.xml) with its .mib frame files, as one dataset anchored at the header.

The frames belong to a header by LiberTEM's naming rule (MIBDataSet): the
.mib files whose names start with the header's stem (`acq.hdr`: `acq*.mib`).
Extraction reads the header and the first frame's header through RosettaSciIO.
"""

import os
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format

HERE = Path(__file__).parent
# parse_hdr_file reads the whole file; real headers are a few kB
MAX_HEADER = 64 << 10
HEADER = "application/x.merlin-header"
FRAMES = "application/x.merlin-mib"


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
        from rsciio.quantumdetector._api import MIBProperties, parse_hdr_file

        size = os.stat(root + dataset.anchor).st_size
        if size > MAX_HEADER:
            raise ValueError(f"header of {size:,} bytes, over {MAX_HEADER:,}")
        hdr = parse_hdr_file(root + dataset.anchor)
        first = MIBProperties()
        first.parse_file(root + next(m for m in dataset.members if m != dataset.anchor))
        frames = int(hdr["Frames in Acquisition (Number)"])
        height, width = first.merlin_size
        depth = int(hdr["Counter Depth (number)"])
        readout = hdr.get("Readout System", "").strip()
        acquired = datetime.strptime(
            hdr["Time and Date Stamp (day, mnth, yr, hr, min, s)"].strip(),
            "%d/%m/%Y %H:%M:%S",
        )
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
