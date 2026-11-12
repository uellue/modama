"""Office Open XML packages (.docx, .pptx, .xlsx and their macro-enabled variants): the property parts.

The package's relationships (`_rels/.rels`) name the core, extended and
custom properties and the main document; only these parts are read, never
the document's other parts. For a workbook, openpyxl's read-only mode also
reads the styles, the shared strings (the cells' texts) and each worksheet up
to its <dimension>, when none of these parts of cell data is larger than
MAX_PART. python-docx and python-pptx are not used: they load every part of the
package on open, the pictures too (BACKLOG, "Sync with upstream").

Skip list (spec formats/office, "What is left out"): the attributes of the
property elements, which are type annotations (`xsi:type="dcterms:W3CDTF"`)
and a vector's size and base type; values not suitable for text
(common.kept).
"""

from collections.abc import Callable, Iterator
from zipfile import ZipFile

from modama_crawler.formats import Extracted

from .common import MAX_PART, headline, kept, local, opened, part, text

RELS = "_rels/.rels"
# Relationship types by the last segment of their URI, in the transitional
# (schemas.openxmlformats.org) and the strict (purl.oclc.org) form
KINDS = {
    "core-properties": "core",
    "extended-properties": "app",
    "extendedProperties": "app",
    "custom-properties": "custom",
    "customProperties": "custom",
    "officeDocument": "main",
}
# The summary line's entries (the one positive list)
HEADLINE = (
    "core.title",
    "core.creator",
    "core.created",
    "app.Application",
    ("app.Pages", "Pages"),
    ("app.Slides", "Slides"),
)


def targets(z: ZipFile) -> dict[str, str]:
    """The member names of the package's property parts and main document, by kind (core, app, custom, main)."""
    found = {}
    for rel in part(z, RELS):
        kind = KINDS.get(rel.get("Type", "").rsplit("/", 1)[-1])
        if kind and rel.get("TargetMode") != "External":
            found.setdefault(kind, rel.get("Target", "").lstrip("/"))
    return found


def entries(z: ZipFile, parts: dict[str, str]) -> Iterator[tuple[str, object]]:
    """Every entry of the property parts: core.<element>, app.<element>, custom.<property name>."""
    for kind in ("core", "app"):
        if kind in parts:
            for element in part(z, parts[kind]):
                yield f"{kind}.{local(element.tag)}", text(element)
    if "custom" in parts:
        for prop in part(z, parts["custom"]):
            yield f"custom.{prop.get('name', '')}", text(prop[0]) if len(prop) else ""


def slides(z: ZipFile, main: str, f) -> dict:
    """The number of slides a presentation lists (`p:sldIdLst`)."""
    listed = [e for e in part(z, main).iter() if local(e.tag) == "sldId"]
    return {"slides": len(listed)}


def too_large(z: ZipFile, main: str) -> str | None:
    """Why openpyxl is not to read a workbook, or None: a part of cell data larger than MAX_PART.

    Its read-only mode reads the shared strings (the cells' texts) whole, and
    a worksheet up to its <dimension>, to its end without one (review of
    common-office, finding 2; BACKLOG, "Sync with upstream").
    """
    folder = main.rpartition("/")[0] + "/"
    for info in z.infolist():
        name = info.filename
        cells = name == f"{folder}sharedStrings.xml" or (
            name.startswith(f"{folder}worksheets/") and name.endswith(".xml")
        )
        if cells and info.file_size > MAX_PART:
            return f"{name}: {info.file_size} bytes, more than {MAX_PART}"
    return None


def sheets(z: ZipFile, main: str, f) -> dict:
    """A workbook's sheets with the dimension each worksheet gives (None if it gives none, or for a chart sheet), by openpyxl in read-only mode.

    Not read when a part of cell data is larger than MAX_PART: then
    `sheets not read` says which.
    """
    from openpyxl import load_workbook

    if (reason := too_large(z, main)) is not None:
        return {"sheets not read": reason}
    f.seek(0)
    workbook = load_workbook(f, read_only=True, keep_links=False)
    try:
        found = {}
        for name in workbook.sheetnames:
            # A chart sheet has no cells
            dimension = getattr(workbook[name], "calculate_dimension", None)
            try:
                found[name] = dimension() if dimension else None
            except ValueError:
                # A worksheet without a <dimension> (writers put it before
                # the cells) is unsized; openpyxl then parses its cells to
                # their end, keeping none, and we do not size it from them
                found[name] = None
        return {"sheets": found}
    finally:
        workbook.close()


def extract(path: str, computed: Callable | None = None) -> Extracted:
    """The property parts' entries but the skip list as original_metadata, what computed(z, main part, file) gives as mapped_metadata."""
    with opened(path) as f, ZipFile(f) as z:
        parts = targets(z)
        original = kept(entries(z, parts))
        mapped = computed(z, parts["main"], f) if computed and "main" in parts else {}
    return Extracted(
        summary=headline(original, HEADLINE),
        subjects=[],
        values={"original_metadata": original, "mapped_metadata": mapped},
    )
