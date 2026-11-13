"""Direct Electron acquisitions (de.xml): the files DE-Server writes under one Dataset Name, as one dataset anchored at the `_info.txt`.

DE-Server names every file of an acquisition with its Dataset Name,
`YYYYMMDD_NNNNN`, and a user-set suffix if any (`_info.txt`, `_movie.mrc`,
`_final.mrc`, detector images, `_scan_coordinates.csv`;
/docs/research/direct-electron-files.md). An info file is recognised by its
name (de.xml) and its first line; its stem, the name without `info.txt`, takes
every file of the directory that starts with it (change em-de, D3). Extraction
reads the info file only: its `key = value` lines as found, and RosettaSciIO's
mapping of it second (D4); no other member is read.
"""

import logging
import os
from collections.abc import Iterable
from pathlib import Path

import numpy as np
from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format
from modama_crawler.formats.values import credential, textual

from ..dm import tag_paths

log = logging.getLogger(__name__)
HERE = Path(__file__).parent
ACQUISITION = "application/x.de-acquisition"
INFO = "application/x.de-info"
# The first key of every info file seen, DE-Server 2.7.2 to 2.7.5 (D3, Q1)
FIRST = b"Server Software Version"
# The info files seen are 2.8 to 40 kB (D4)
MAX_INFO = 1 << 20
# The skip list (D4, Q6): option lists of the user interface, not the
# acquisition (`Instrument Accelerating Voltage (V) Allowed Values =
# 300000,200000,…`, `Preset - List`, `Scan - Preset List`); then the shared
# checks, values not suitable for text and credentials
SKIPPED_ENDINGS = (" Allowed Values", " Preset List")
SKIPPED = frozenset({"Preset - List"})
# The summary line's entries, the only positive list (D4): (key, the value after
# the key's name); the scan's only when it is enabled; the date as written (Q7)
HEADLINE = (
    ("Camera Model", False),
    ("Image Processing - Mode", False),
    ("Instrument Accelerating Voltage (V)", True),
    ("Exposure Time (seconds)", True),
    ("Frames Per Second", True),
)
SCAN = (("Scan - Type", False), ("Scan - Size X", True), ("Scan - Size Y", True))
DATE = (("Local time", False),)


def read_info(path: str) -> dict[str, str]:
    """The info file's `key = value` lines: key and value without the padding, in the file's order.

    Split at the first `=`; a line without one is a key with an empty value; a
    blank line is skipped. UTF-8 (ASCII in every file seen), else Windows-1252
    (the rule of common/text).
    """
    size = os.stat(path).st_size
    if size > MAX_INFO:
        raise ValueError(f"info file of {size:,} bytes, over {MAX_INFO:,}")
    with open(path, "rb", buffering=0) as f:
        data = f.read()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    entries = {}
    for line in text.splitlines():
        if line.strip():
            key, _, value = line.partition("=")
            entries[key.strip()] = value.strip()
    return entries


def skipped(key: str) -> bool:
    return key in SKIPPED or key.endswith(SKIPPED_ENDINGS)


def headline(entries: dict[str, str]) -> list[str]:
    """The summary line: a text bare, a number after its key, as written; a missing or empty entry left out."""
    chosen = (
        HEADLINE + (SCAN if entries.get("Scan - Enable") == "Enable" else ()) + DATE
    )
    return [
        f"{key} {entries[key]}" if named else entries[key]
        for key, named in chosen
        if entries.get(key)
    ]


def plain(value):
    """A value of RosettaSciIO's mapping as JSON holds it (its scales are NumPy floats)."""
    if isinstance(value, np.generic):
        return value.item()
    return value


def mapping(path: str, anchor: str) -> tuple[dict, list] | None:
    """RosettaSciIO's mapping of the info file, its metadata flat under dotted names and its axes; None, with a warning, where it has none (D4, Q3).

    read_de_metadata_file opens the file itself (a text file under MAX_INFO,
    checked by read_info first). It is not handed the scan coordinate file: for
    a scan that is not a raster it raises a ValueError.
    """
    from rsciio.mrc._api import read_de_metadata_file

    try:
        _, metadata, axes, _, _ = read_de_metadata_file(path)
    except ValueError as e:
        log.warning("%s: no mapping by RosettaSciIO: %s", anchor, e)
        return None
    flat = {k: plain(v) for k, v in tag_paths(metadata) if textual(plain(v))}
    kept = [
        {k: plain(a[k]) for k in ("name", "size", "scale", "units") if k in a}
        for a in axes
    ]
    return flat, kept


class De(Format):
    type = ACQUISITION
    display_name = "Direct Electron acquisition"
    # Before em/mrc (61) and common/pydata's formats at 61, which sort before
    # em/de by id and would claim a _movie.hspy first (D5)
    priority = 62
    reacts_to = frozenset({INFO})

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        infos = []
        for e in d.of_type(INFO):
            try:
                first = d.read(e, len(FIRST))
            except OSError as error:
                d.cannot_read(e, error)
                continue
            if first == FIRST:
                infos.append(e)
            else:
                d.not_of_type(e, "no DE-Server first line")
        files = [e for e in d.entries if e.kind == "file"]
        taken = set()
        # The longest stem first, so that 20241021_00405_x_info.txt keeps
        # 20241021_00405_x_movie.mrc from 20241021_00405_info.txt (D3)
        for info in sorted(infos, key=lambda e: -len(e.name)):
            stem = info.name[: -len("info.txt")]
            mine = [
                f.rel for f in files if f.rel not in taken and f.name.startswith(stem)
            ]
            taken.update(mine)
            # Files of the stem a format before this one claimed: named for
            # review, the acquisition built of the others (decision 344)
            for name in sorted(n for n in d.claimed if n.startswith(stem)):
                d.claimed_elsewhere(info.rel, name)
            yield Dataset(
                anchor=info.rel,
                members=tuple(mine),
                basis=f"DE-Server info, {len(mine)} file(s) {stem}*",
            )

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """Every entry of the info file but the skip list, RosettaSciIO's mapping second (spec formats/de)."""
        path = root + dataset.anchor
        entries = read_info(path)
        name = os.path.basename(dataset.anchor)
        dataset_name = entries.get("Dataset Name", "")
        if not name.startswith(f"{dataset_name}_"):
            log.warning(
                "%s: Dataset Name %s differs from the file name %s",
                dataset.anchor,
                dataset_name,
                name,
            )
        original = {}
        secrets = 0
        for key, value in entries.items():
            if skipped(key) or not textual(value):
                continue
            if credential(key, value):
                secrets += 1
                continue
            original[key] = value
        values = {"original_metadata": original}
        mapped = mapping(path, dataset.anchor)
        if mapped is not None or secrets:
            flat, axes = mapped if mapped is not None else ({}, None)
            if secrets:
                flat["credentials_left_out"] = secrets
            values["mapped_metadata"] = flat
            if axes is not None:
                values["axes"] = axes
        camera = original.get("Camera Model")
        return Extracted(
            summary=headline(original),
            subjects=[camera] if camera else [],
            values=values,
        )


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [De()], mime_files=(HERE / "de.xml",))
