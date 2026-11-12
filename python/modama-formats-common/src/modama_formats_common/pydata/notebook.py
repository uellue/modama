"""Jupyter notebooks: the notebook's metadata as found, its cells counted by nbformat.

Outputs are not metadata: they are never kept (spec formats/pydata, "A
Jupyter notebook is described by its metadata and its cells").
"""

import json
import os
from collections import Counter

import nbformat
from modama_crawler.formats.values import textual

from .values import Walk, no_readahead

# A notebook is JSON and read whole to count its cells, up to this size; a
# larger one (131 of the October listing's 1,525 notebooks, up to 229 MB,
# mostly outputs) is read at its end only, where Jupyter writes the notebook's
# metadata after the cells (json.dumps with sort_keys)
MAX_WHOLE = 8 << 20
TAIL = 64 << 10
TRIES = 8  # "metadata" keys tried from the end of the tail
# The skip list: editor state, not about the notebook (spec formats/pydata,
# "Editor state"): ipywidgets' saved widget state, the Table of Contents and
# Variable Inspector extensions' settings, VS Code's interpreter
SKIPPED = ("widgets", "toc", "varInspector", "vscode")
# The summary line's entries, in its order (the one positive list)
HEADLINE = ("first_heading", "kernelspec.display_name")


def flat(node, prefix: str = ""):
    """(dotted name, value) of every leaf below the dict node; an empty dict below it is a leaf ({}) too."""
    for key, value in node.items():
        if isinstance(value, dict) and value:
            yield from flat(value, f"{prefix}{key}.")
        else:
            yield f"{prefix}{key}", value


def heading(nb) -> str | None:
    """The first Markdown heading of a notebook of version 4: its text after the #s."""
    for cell in nb.cells:
        if cell.cell_type != "markdown":
            continue
        for line in cell.source.splitlines():
            if line.startswith("#"):
                return line.lstrip("#").strip()
    return None


def from_tail(data: bytes) -> dict | None:
    """The notebook's top-level keys after its cells, from the end of the file, or None.

    Tries the last few `"metadata"` keys: only the notebook's own, the last
    at the top level, makes the rest of the file a JSON object that holds
    `nbformat` as well.
    """
    at = len(data)
    for _ in range(TRIES):
        at = data.rfind(b'"metadata"', 0, at)
        if at < 0:
            return None
        try:
            found = json.loads(b"{" + data[at:])
        except ValueError:
            continue
        if isinstance(found, dict) and "nbformat" in found:
            return found
    return None


def described(path: str) -> tuple[dict, dict, list[str]]:
    """original_metadata, mapped_metadata and the summary line of a notebook."""
    with open(path, "rb", buffering=0) as f:
        size = os.fstat(f.fileno()).st_size
        if size > MAX_WHOLE:
            no_readahead(f.fileno())
            f.seek(size - TAIL)
            raw, nb = from_tail(f.read(TAIL)) or {}, None
            mapped = {
                "read": f"the last {TAIL} bytes of {size}, over {MAX_WHOLE}: "
                "no cells counted"
            }
        else:
            text = f.read().decode("utf-8-sig")
            raw = json.loads(text)  # the metadata as found
            # nbformat's reading as version 4: version 3's worksheets and
            # heading cells as version 4's cells and Markdown, sources as one
            # string; an invalid notebook is read all the same, its
            # validation error kept here instead of logged
            nb = nbformat.reads(text, as_version=4, capture_validation_error={})
            mapped = {}
    walk = Walk()
    metadata = raw.get("metadata")
    for name, value in flat(metadata if isinstance(metadata, dict) else {}):
        if walk.over():
            break
        if name.split(".", 1)[0] not in SKIPPED:
            walk.add(name, value)
    for key in ("nbformat", "nbformat_minor"):
        if key in raw:
            walk.add(key, raw[key])
    original, cut = walk.result()
    mapped |= cut
    if nb is not None:
        counts = Counter(cell.cell_type for cell in nb.cells)
        mapped |= {f"cells.{kind}": n for kind, n in sorted(counts.items())}
        if (first := heading(nb)) is not None and textual(first):
            mapped["first_heading"] = first
    entries = {**mapped, **original}
    summary = [entries[k] for k in HEADLINE if isinstance(entries.get(k), str)]
    return original, mapped, [s for s in dict.fromkeys(summary) if s]
