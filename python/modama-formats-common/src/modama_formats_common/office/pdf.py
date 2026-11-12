"""PDF: the document information dictionary and the XMP metadata, by pypdf.

pypdf reads the cross-reference table, the trailer, the catalog, the page
tree's root and these two objects; never the pages' content. A file without
`%%EOF` at its end is not given to pypdf, and pypdf reads at most `BUDGET`
bytes (BACKLOG, "Sync with upstream"). An encrypted file is opened with the
empty user password, as viewers open it; one that needs a password keeps its
header and `encrypted` only, and its summary line says `(encrypted)`. pypdf's `XmpInformation` gives named properties
only, so the XMP packet is flattened here, every property it holds.

Skip list (spec formats/office, "What is left out"): the RDF syntax of XMP
(`rdf:about`, `xml:lang`, `rdf:parseType`, the containers `rdf:Alt`,
`rdf:Seq`, `rdf:Bag` as such: their items are kept); values not suitable for
text (common.kept: a byte string, an XMP thumbnail, a list of more than 16).
"""

import io
import os
import re
from collections.abc import Iterator

from defusedxml import ElementTree
from modama_crawler.formats import Extracted
from modama_crawler.formats.values import textual

from .common import ENCRYPTED, OverBudget, headline, kept, opened

# The core's magic: %PDF- within the first 1,024 bytes; %%EOF is to be within
# the last 1,024 (ISO 32000-1, 7.5.5; pypdf accepts it there too)
WINDOW = 1024
HEADER = re.compile(rb"%PDF-[^\s%]*")
# The most pypdf may read of a file: its recovery paths (a bad startxref, junk
# before the header) read and hold the whole file, which on staging is up to
# 642 MB; an intact file costs about 1 MB (spec formats/office). Over it, the
# extraction fails (common.OverBudget)
BUDGET = 32 * 1024 * 1024
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
XML = "{http://www.w3.org/XML/1998/namespace}"
CONTAINERS = {f"{RDF}Alt", f"{RDF}Seq", f"{RDF}Bag"}
# The summary line's entries (the one positive list); pages from mapped_metadata
HEADLINE = (
    "Info.Title",
    "Info.Author",
    "Info.CreationDate",
    "Info.Creator",
    "Info.Producer",
    "pages",
)


def plain(value):
    """A pypdf object as a JSON value: a text string as text, a byte string as bytes (left out later), a name as written (`/Foo`).

    A reference inside it as the file writes it (`12 0 R`), not followed: a
    reference may lead back to where it is (a cycle), or into the document's
    page tree (review of common-office, finding 4).
    """
    from pypdf.generic import BooleanObject, IndirectObject, NullObject

    if isinstance(value, IndirectObject):
        return f"{value.idnum} {value.generation} R"
    if isinstance(value, BooleanObject):
        return bool(value)
    if value is None or isinstance(value, NullObject):
        return None
    if isinstance(value, bytes):
        return bytes(value)
    if isinstance(value, str):
        return str(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, list):
        return [plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    return str(value)


def xmp(data: bytes) -> Iterator[tuple[str, object]]:
    """Every property of an XMP packet as XMP.<prefix>:<name>, the prefixes as the packet declares them."""
    prefixes: dict[str, str] = {}
    events = ElementTree.iterparse(io.BytesIO(data), events=("start-ns",))
    for _, (prefix, uri) in events:
        prefixes.setdefault(uri, prefix)

    def name(tag: str) -> str:
        uri, _, rest = tag[1:].partition("}") if tag.startswith("{") else ("", "", tag)
        return f"{prefixes[uri]}:{rest}" if prefixes.get(uri) else rest

    def properties(description) -> Iterator[tuple[str, object]]:
        for key, value in description.attrib.items():
            if not key.startswith((RDF, XML)):
                yield name(key), value
        for element in description:
            yield name(element.tag), node(element)

    def node(element):
        if (resource := element.get(f"{RDF}resource")) is not None:
            return resource
        if element.get(f"{RDF}parseType") == "Resource":
            return dict(properties(element))
        if len(element) == 0:
            return element.text or ""
        inner = element[0]
        if inner.tag in CONTAINERS:
            return [node(item) for item in inner]
        if inner.tag == f"{RDF}Description":
            return dict(properties(inner))
        return dict(properties(element))

    root = events.root
    for rdf in root.iter(f"{RDF}RDF"):
        for description in rdf:
            if description.tag == f"{RDF}Description":
                for key, value in properties(description):
                    yield from flat(f"XMP.{key}", value)


def flat(name: str, value) -> Iterator[tuple[str, object]]:
    """A structure as name.<field>, a list of structures as name[i]; a list or structure not suitable for text as it is (left out later)."""
    if isinstance(value, dict) and textual(value):
        for key, inner in value.items():
            yield from flat(f"{name}.{key}", inner)
    elif (
        isinstance(value, list)
        and textual(value)
        and any(isinstance(v, dict) for v in value)
    ):
        for i, inner in enumerate(value):
            yield from flat(f"{name}[{i}]", inner)
    else:
        yield name, value


def ends(f) -> bytes:
    """The first bytes of f's header (from `%PDF-` in its first 1,024 bytes) after checking that `%%EOF` is in its last 1,024.

    A file without it is cut off (or still being written); pypdf would then
    rebuild the cross-reference table from the whole file, a read of all of
    it, every crawl (review of common-office, finding 1).
    """
    header = HEADER.search(f.read(WINDOW))
    if header is None:
        raise ValueError("no %PDF- in the first 1,024 bytes")
    size = f.seek(0, os.SEEK_END)
    f.seek(max(size - WINDOW, 0))
    if b"%%EOF" not in f.read():
        raise ValueError(
            "no %%EOF in the last 1,024 bytes: the file is cut off or still being written"
        )
    f.seek(0)
    return header.group()


def extract(path: str) -> Extracted:
    with opened(path, BUDGET) as f:
        try:
            return described(f)
        except Exception as error:
            # pypdf catches the budget's exception in places and fails
            # later, as if the file lacked a part: say why
            if f.raw.exceeded:
                raise OverBudget(f.raw.exceeded) from error
            raise


def described(f) -> Extracted:
    from pypdf import PasswordType, PdfReader

    header = ends(f).decode("latin-1")
    reader = PdfReader(f)
    mapped = {"header": header, "encrypted": reader.is_encrypted}
    if reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED:
        return Extracted(
            summary=[ENCRYPTED],
            subjects=[],
            values={"original_metadata": {}, "mapped_metadata": mapped},
        )
    catalog = reader.trailer["/Root"]
    if "/Version" in catalog:
        mapped["version"] = str(catalog["/Version"]).lstrip("/")
    pages = catalog["/Pages"]
    mapped["pages"] = plain(pages["/Count"]) if "/Count" in pages else None
    pairs = []
    if (info := reader.trailer.get("/Info")) is not None:
        info = info.get_object()
        # info[key] follows the value's own reference, plain no other
        pairs += [(f"Info.{key.lstrip('/')}", plain(info[key])) for key in info]
    if (metadata := catalog.get("/Metadata")) is not None:
        pairs += xmp(metadata.get_object().get_data())
    original = kept(pairs)
    return Extracted(
        summary=headline({**original, **mapped}, HEADLINE),
        subjects=[],
        values={"original_metadata": original, "mapped_metadata": mapped},
    )
