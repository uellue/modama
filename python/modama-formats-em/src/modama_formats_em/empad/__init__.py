"""EMPAD acquisitions: an XML header and the raw frame file it names, as one dataset anchored at the header."""

import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path, PurePosixPath

import defusedxml.ElementTree as ET
from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format

HERE = Path(__file__).parent
HEADER = "application/x.empad+xml"
HEADER_LIMIT = 1 << 20  # headers seen are a few kB
FRAME = (
    128,
    128,
)  # the detector's frame, not in the header (as RosettaSciIO 0.15.0 reads it)


class Empad(Format):
    type = HEADER
    display_name = "EMPAD"
    priority = 60
    reacts_to = frozenset({HEADER})

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        for header in d.of_type(HEADER):
            try:
                root = ET.fromstring(d.read(header, 64 * 1024))
                raw_name = PurePosixPath(root.find("raw_file").attrib["filename"]).name
            except Exception as e:  # noqa: BLE001  any unreadable header is reported, not fatal
                d.warn(
                    header.rel, f"cannot read the raw file name from the header: {e!r}"
                )
                continue
            raw = d.entry(raw_name)
            if raw is None or raw.kind != "file":
                d.warn(
                    header.rel, f"raw file {raw_name} named by the header is missing"
                )
                continue
            yield Dataset(
                anchor=header.rel,
                members=(header.rel, raw.rel),
                basis=f"raw_file points to {raw_name}",
            )

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """Scan size or frame count, frame size, exposure and time from the header (spec formats/empad)."""
        with open(root + dataset.anchor, "rb", buffering=0) as f:
            header = ET.fromstring(f.read(HEADER_LIMIT))
        summary, subjects, values = [], [], {}
        # The navigation shape in RosettaSciIO 0.15.0's order: a series' count, the
        # scan's pix_x and pix_y, else the raw file's scan_x<n>_y<n> name
        raw = PurePosixPath(header.find("raw_file").attrib["filename"]).name
        series = header.findtext("scan_parameters/series_count")
        scan = re.fullmatch(r"scan_x(\d+)_y(\d+)\.raw", raw)
        if series is not None:
            values["frames"] = int(series)
            summary.append(f"series of {int(series)} frames")
        elif header.findtext("pix_x") is not None:
            values["scan"] = [
                int(header.findtext("pix_x")),
                int(header.findtext("pix_y")),
            ]
        elif scan is not None:
            values["scan"] = [int(scan[1]), int(scan[2])]
        if "scan" in values:
            summary.append("scan of {}×{} positions".format(*values["scan"]))
            subjects.append("4D-STEM")
        values["frame"] = list(FRAME)
        summary.append("{}×{} pixel frames".format(*FRAME))
        # TODO: the unit of exposure_time (1 in the headers seen, backgrounds named
        # img_exp_1); until a source says, the number goes out without one. Term:
        # "exposure time" as in ../../../GLOSSARY.md; the same for Merlin and DM.
        exposure = header.findtext("exposure_time")
        if exposure is not None:
            values["exposure_time"] = float(exposure)
            summary.append(f"exposure time {float(exposure):g} (unit unknown)")
        stamp = header.find("timestamp")
        if stamp is not None and "isoformat" in stamp.attrib:
            acquired = datetime.fromisoformat(stamp.attrib["isoformat"])
            values["acquired"] = acquired.isoformat()
            summary.append(acquired.strftime("%Y-%m-%d %H:%M"))
        return Extracted(summary=summary, subjects=subjects, values=values)


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [Empad()], mime_files=(HERE / "empad.xml",))
