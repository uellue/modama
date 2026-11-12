"""EMPAD acquisitions: an XML header and the raw frame file it names, as one dataset anchored at the header."""

import re
from collections import Counter
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
        """Every element and attribute of the header as found, then scan size or frame
        count, frame size, exposure and time (spec formats/empad)."""
        with open(root + dataset.anchor, "rb", buffering=0) as f:
            header = ET.fromstring(f.read(HEADER_LIMIT))
        # The summary line: chosen values as the header writes them, after the
        # element's or attribute's name, or after their name in mapped_metadata
        # where computed (decision 230)
        summary, subjects, mapped = [], [], {}
        # The navigation shape in RosettaSciIO 0.15.0's order: a series' count, the
        # scan's pix_x and pix_y, else the raw file's scan_x<n>_y<n> name
        raw = PurePosixPath(header.find("raw_file").attrib["filename"]).name
        series = header.findtext("scan_parameters/series_count")
        pix = header.findtext("pix_x"), header.findtext("pix_y")
        scan = re.fullmatch(r"scan_x(\d+)_y(\d+)\.raw", raw)
        if series is not None:
            mapped["frames"] = int(series)
            summary.append(f"series_count {series}")
        elif pix[0] is not None:
            mapped["scan"] = [int(pix[0]), int(pix[1])]
            summary += [f"pix_x {pix[0]}", f"pix_y {pix[1]}"]
        elif scan is not None:
            mapped["scan"] = [int(scan[1]), int(scan[2])]
            summary.append("scan {}×{}".format(*mapped["scan"]))
        if "scan" in mapped:
            subjects.append("4D-STEM")
        # Not in the header: the detector's, as RosettaSciIO reads it; so not in
        # the summary line, which says what the file says
        mapped["frame"] = list(FRAME)
        # TODO: the unit of exposure_time (1 in the headers seen, backgrounds named
        # img_exp_1); until a source says, the number goes out without one. Term:
        # "exposure time" as in ../../../GLOSSARY.md; the same for Merlin and DM.
        exposure = header.findtext("exposure_time")
        if exposure is not None:
            mapped["exposure_time"] = float(exposure)
            summary.append(f"exposure_time {exposure} (unit unknown)")
        stamp = header.find("timestamp")
        if stamp is not None and "isoformat" in stamp.attrib:
            acquired = datetime.fromisoformat(stamp.attrib["isoformat"])
            mapped["acquired"] = acquired.isoformat()
            summary.append(stamp.attrib["isoformat"])
        values = {"original_metadata": entries(header), "mapped_metadata": mapped}
        return Extracted(summary=summary, subjects=subjects, values=values)


def entries(root) -> dict[str, str]:
    """Every attribute and text of an XML tree below its root element, as found: dotted
    path -> text (spec formats/empad, "Every element and attribute is kept").

    As in XPath, an attribute is `@name` (`timestamp.@isoformat`) and an element
    that has siblings of its name is numbered from 1 (`scan_parameters[2].scan_size`).
    An element without children and attributes keeps its text, empty or not
    (decision 161); the skip list: whitespace around child elements, and the empty
    text of an element whose attributes carry its content (`<raw_file
    filename="…"/>`: `raw_file.@filename`, no `raw_file`).
    """
    found = {}

    # TODO: the shared check of modama_formats_em for content not suitable for text
    # display (too large, binary; TEMPLATE.md, "Extracting metadata"), one call per
    # value before it goes into found, once it is merged (DM change)
    def visit(element, path: str) -> None:
        for name, value in element.attrib.items():
            found[f"{path}@{name}"] = value
        children = list(element)
        text = element.text or ""
        if path and (text.strip() or not (children or element.attrib)):
            found[path[:-1]] = text
        counts = Counter(child.tag for child in children)
        seen = Counter()
        for child in children:
            seen[child.tag] += 1
            if counts[child.tag] > 1:
                visit(child, f"{path}{child.tag}[{seen[child.tag]}].")
            else:
                visit(child, f"{path}{child.tag}.")

    visit(root, "")
    return found


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [Empad()], mime_files=(HERE / "empad.xml",))
