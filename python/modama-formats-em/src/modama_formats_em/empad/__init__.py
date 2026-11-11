"""EMPAD acquisitions: an XML header and the raw frame file it names, as one dataset anchored at the header."""

from collections.abc import Iterable
from pathlib import Path, PurePosixPath

import defusedxml.ElementTree as ET
from modama_crawler.formats import Collection, Dataset, Directory, Format

HERE = Path(__file__).parent
HEADER = "application/x.empad+xml"


class Empad(Format):
    type = HEADER
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


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [Empad()], mime_files=(HERE / "empad.xml",))
