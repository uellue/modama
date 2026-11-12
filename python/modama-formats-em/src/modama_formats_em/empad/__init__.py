"""EMPAD acquisitions: an XML header and the raw frame file it names, as one dataset anchored at the header."""

import logging
import re
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path, PurePosixPath

import defusedxml.ElementTree as ET
from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format
from modama_crawler.formats.values import textual

log = logging.getLogger(__name__)
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
        series = given(header.findtext("scan_parameters/series_count"))
        pix = given(header.findtext("pix_x")), given(header.findtext("pix_y"))
        scan = re.fullmatch(r"scan_x(\d+)_y(\d+)\.raw", raw)
        if series is not None:
            mapped["frames"] = int(series)
        elif None not in pix:
            mapped["scan"] = [int(pix[0]), int(pix[1])]
        elif scan is not None:
            mapped["scan"] = [int(scan[1]), int(scan[2])]
        if "scan" in mapped:
            subjects.append("4D-STEM")
        # In the summary line the header's own words where it has them: the
        # acquisition's scan_resolution_x and _y before RosettaSciIO's sources
        acquire = header.find("scan_parameters[@mode='acquire']")
        resolution = {
            name: given(acquire.findtext(name)) if acquire is not None else None
            for name in ("scan_resolution_x", "scan_resolution_y")
        }
        if series is not None:
            summary.append(f"series_count {series}")
        elif None not in resolution.values():
            summary += [f"{name} {value}" for name, value in resolution.items()]
        elif None not in pix:
            summary += [f"pix_x {pix[0]}", f"pix_y {pix[1]}"]
        elif "scan" in mapped:
            summary.append("scan {}, {}".format(*mapped["scan"]))
        # Not in the header: the detector's, as RosettaSciIO reads it; so not in
        # the summary line, which says what the file says
        mapped["frame"] = list(FRAME)
        # TODO: the unit of exposure_time (1 in the headers seen, backgrounds named
        # img_exp_1); until a source says, the number goes out without one. Term:
        # "exposure time" as in ../../../GLOSSARY.md; the same for Merlin and DM.
        exposure = given(header.findtext("exposure_time"))
        if exposure is not None:
            mapped["exposure_time"] = float(exposure)
            summary.append(f"exposure_time {exposure} (unit unknown)")
        stamp = header.find("timestamp")
        isoformat = given(stamp.get("isoformat") if stamp is not None else None)
        if isoformat is not None:
            summary.append(isoformat)
            try:
                mapped["acquired"] = datetime.fromisoformat(isoformat).isoformat()
            except ValueError:
                log.warning(
                    "%s: timestamp.@isoformat %r is not ISO 8601; no acquisition time",
                    dataset.anchor,
                    isoformat,
                )
        values = {
            "original_metadata": entries(header, dataset.anchor),
            "mapped_metadata": mapped,
        }
        return Extracted(summary=summary, subjects=subjects, values=values)


def given(text: str | None) -> str | None:
    """A header's text for the mapped values: None where it is missing or blank."""
    return text if text is not None and text.strip() else None


def unindented(text: str) -> str:
    """An XML text as kept: without its leading and trailing whitespace where it
    has a line break (pretty-printing is not content, decision 243b), else as written."""
    return text.strip() if "\n" in text else text


def entries(root, where: str) -> dict[str, str]:
    """Every attribute and text of an XML tree, as found: dotted path below the root
    element -> text (spec formats/empad, "Every element and attribute is kept").

    As in XPath, an attribute is `@name` (`timestamp.@isoformat`) and an element
    that has siblings of its name is numbered from 1 (`scan_parameters[2].scan_size`);
    one without such siblings has no number. An element without children and
    attributes keeps its text, empty or not (decision 161). Text that is not
    whitespace is kept where XML allows it besides: the root's as `#text`, an
    element's beside its children under its path, the text after an element (its
    tail) as `<path>#tail`. A text or tail with a line break is kept without its
    leading and trailing whitespace: pretty-printing is not content (decision
    243b); inner whitespace, and text without a line break, stay as written.
    A path met twice (a tag name with a dot) keeps both,
    the second as `<path>#2`, with a warning naming where. The skip list:
    whitespace around elements, the empty text of an element whose attributes or
    children carry its content (`<raw_file filename="…"/>`: `raw_file.@filename`,
    no `raw_file`), and a value not suitable for text (`values.textual`).
    """
    found = {}

    def add(key: str, value: str) -> None:
        if not textual(value):
            return
        if key in found:
            n = 2
            while f"{key}#{n}" in found:
                n += 1
            log.warning("%s: %s twice, the second kept as %s#%d", where, key, key, n)
            key = f"{key}#{n}"
        found[key] = value

    def visit(element, path: str) -> None:
        for name, value in element.attrib.items():
            add(f"{path}@{name}", value)
        children = list(element)
        text = element.text or ""
        if text.strip() or (path and not (children or element.attrib)):
            add(path[:-1] or "#text", unindented(text))
        counts = Counter(child.tag for child in children)
        seen = Counter()
        for child in children:
            seen[child.tag] += 1
            if counts[child.tag] > 1:
                inner = f"{path}{child.tag}[{seen[child.tag]}]"
            else:
                inner = f"{path}{child.tag}"
            visit(child, f"{inner}.")
            if child.tail and child.tail.strip():
                add(f"{inner}#tail", unindented(child.tail))

    visit(root, "")
    return found


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [Empad()], mime_files=(HERE / "empad.xml",))
