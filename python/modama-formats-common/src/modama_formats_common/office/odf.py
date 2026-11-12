"""OpenDocument files (.odt, .odp, .ods): meta.xml.

Only `meta.xml` and the manifest are read. odfpy is not used: its `load()`
reads every part of the package, the pictures too (BACKLOG, "Sync with
upstream"). An encrypted document's meta.xml (encryption data in the
manifest) is not read; its summary line says `(encrypted)`.

Skip list (spec formats/office, "What is left out"): the value type of a
user-defined field (`meta:value-type`); values not suitable for text
(common.kept).
"""

from collections.abc import Iterator
from zipfile import ZipFile

from modama_crawler.formats import Extracted

from .common import ENCRYPTED, headline, kept, local, opened, part, text

META = "meta.xml"
MANIFEST = "META-INF/manifest.xml"
NS_META = "{urn:oasis:names:tc:opendocument:xmlns:meta:1.0}"
NS_MANIFEST = "{urn:oasis:names:tc:opendocument:xmlns:manifest:1.0}"
# The summary line's entries (the one positive list)
HEADLINE = (
    "title",
    "initial-creator",
    "creation-date",
    "generator",
    ("document-statistic.@page-count", "page-count"),
)


def encrypted(z: ZipFile) -> bool:
    """Whether the manifest gives encryption data for meta.xml."""
    if MANIFEST not in z.namelist():
        return False
    for entry in part(z, MANIFEST):
        if entry.get(f"{NS_MANIFEST}full-path") == META:
            return any(local(e.tag) == "encryption-data" for e in entry)
    return False


def entries(meta) -> Iterator[tuple[str, object]]:
    """Every child of office:meta by its local name: its text, its attributes as <name>.@<attribute>, a user-defined field as user-defined.<its name>."""
    for element in meta:
        name = local(element.tag)
        if name == "user-defined":
            yield f"user-defined.{element.get(f'{NS_META}name', '')}", text(element)
            continue
        attributes = {local(k): v for k, v in element.attrib.items()}
        # An element of attributes only (document-statistic) has no text entry
        if element.text is not None or len(element) or not attributes:
            yield name, text(element)
        for attribute, value in attributes.items():
            yield f"{name}.@{attribute}", value


def gathered(pairs: Iterator[tuple[str, object]]) -> Iterator[tuple[str, object]]:
    """The entries, an entry that repeats (keyword) as the list of its values."""
    found: dict[str, list] = {}
    for name, value in pairs:
        found.setdefault(name, []).append(value)
    for name, values in found.items():
        yield name, values[0] if len(values) == 1 else values


def extract(path: str) -> Extracted:
    with opened(path) as f, ZipFile(f) as z:
        locked = encrypted(z)
        original = {}
        if not locked and META in z.namelist():
            for meta in part(z, META):  # office:document-meta holds office:meta
                original.update(kept(gathered(entries(meta))))
    return Extracted(
        summary=[ENCRYPTED] if locked else headline(original, HEADLINE),
        subjects=[],
        values={
            "original_metadata": original,
            "mapped_metadata": {"encrypted": locked},
        },
    )
