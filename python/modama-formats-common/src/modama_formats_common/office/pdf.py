"""PDF: the document information dictionary and the XMP metadata, by pypdf.

pypdf reads the cross-reference table, the trailer, the catalog, the page
tree's root and these two objects; never the pages' content. An encrypted
file is opened with the empty user password, as viewers open it; one that
needs a password keeps its header and `encrypted` only.

Skip list (spec formats/office, "What is left out"): the RDF syntax of XMP
(`rdf:about`, `xml:lang`, `rdf:parseType`, the containers `rdf:Alt`,
`rdf:Seq`, `rdf:Bag` as such: their items are kept); values not suitable for
text (common.kept: a byte string, an XMP thumbnail, a list of more than 16).
"""

import io
from collections.abc import Iterator

from defusedxml import ElementTree
from modama_crawler.formats import Extracted
from modama_crawler.formats.values import textual

from .common import headline, kept, opened

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
    """A pypdf object as a JSON value: a text string as text, a byte string as bytes (left out later), a name as written (`/Foo`)."""
    from pypdf.generic import BooleanObject, IndirectObject, NullObject

    if isinstance(value, IndirectObject):
        value = value.get_object()
    if isinstance(value, BooleanObject):
        return bool(value)
    if isinstance(value, NullObject):
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


def extract(path: str) -> Extracted:
    from pypdf import PasswordType, PdfReader

    with opened(path) as f:
        reader = PdfReader(f)
        mapped = {"header": reader.pdf_header, "encrypted": reader.is_encrypted}
        if reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED:
            return Extracted(
                summary=[],
                subjects=[],
                values={"original_metadata": {}, "mapped_metadata": mapped},
            )
        catalog = reader.trailer["/Root"]
        if "/Version" in catalog:
            mapped["version"] = str(catalog["/Version"]).lstrip("/")
        mapped["pages"] = plain(catalog["/Pages"].get("/Count"))
        pairs = []
        if (info := reader.trailer.get("/Info")) is not None:
            info = info.get_object()
            pairs += [(f"Info.{key.lstrip('/')}", plain(info[key])) for key in info]
        if (metadata := catalog.get("/Metadata")) is not None:
            pairs += xmp(metadata.get_object().get_data())
        original = kept(pairs)
    return Extracted(
        summary=headline({**original, **mapped}, HEADLINE),
        subjects=[],
        values={"original_metadata": original, "mapped_metadata": mapped},
    )
