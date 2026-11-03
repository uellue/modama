"""Rendering records as OAI-PMH oai_dc XML, shared by the server and the records command."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime

from lxml import etree

OAI_NS = "http://www.openarchives.org/OAI/2.0/"
OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DC_NS = "http://purl.org/dc/elements/1.1/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
XSI_SCHEMA_LOCATION = f"{{{XSI_NS}}}schemaLocation"
OAI_DC_SCHEMA = "http://www.openarchives.org/OAI/2.0/oai_dc.xsd"

# The elements of unqualified Dublin Core, in the order we render them
DC_ELEMENTS = (
    "title", "creator", "subject", "description", "publisher", "contributor",
    "date", "type", "format", "identifier", "source", "language", "relation",
    "coverage", "rights",
)  # fmt: skip


def format_datestamp(timestamp: datetime) -> str:
    return timestamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# Characters that XML 1.0 can't represent
INVALID_XML_RE = re.compile("[^\t\n\r\x20-퟿-�\U00010000-\U0010ffff]")


def xml_text(text: str) -> str:
    return INVALID_XML_RE.sub("�", text)


def element(tag: str) -> etree._Element:
    return etree.Element(f"{{{OAI_NS}}}{tag}", nsmap={None: OAI_NS})


def sub(parent, tag: str, text: str | None = None) -> etree._Element:
    e = etree.SubElement(parent, f"{{{OAI_NS}}}{tag}")
    if text is not None:
        e.text = xml_text(text)
    return e


def header(parent, identifier: str, datestamp: datetime):
    h = sub(parent, "header")
    sub(h, "identifier", identifier)
    sub(h, "datestamp", format_datestamp(datestamp))


def record(parent, identifier: str, datestamp: datetime, metadata: dict):
    r = sub(parent, "record")
    header(r, identifier, datestamp)
    dc = etree.SubElement(
        sub(r, "metadata"),
        f"{{{OAI_DC_NS}}}dc",
        nsmap={"oai_dc": OAI_DC_NS, "dc": DC_NS, "xsi": XSI_NS},
    )
    dc.set(XSI_SCHEMA_LOCATION, f"{OAI_DC_NS} {OAI_DC_SCHEMA}")
    for name in DC_ELEMENTS:
        for value in metadata.get(name, ()):
            etree.SubElement(dc, f"{{{DC_NS}}}{name}").text = xml_text(value)


def document(
    base_url: str, verb: str | None, args: dict[str, str]
) -> tuple[etree._Element, etree._Element]:
    """An OAI-PMH response skeleton: the root and its request element."""
    root = etree.Element(f"{{{OAI_NS}}}OAI-PMH", nsmap={None: OAI_NS, "xsi": XSI_NS})
    root.set(
        XSI_SCHEMA_LOCATION, f"{OAI_NS} http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd"
    )
    sub(root, "responseDate", format_datestamp(datetime.now(UTC)))
    request = sub(root, "request", base_url)
    if verb:
        request.set("verb", verb)
    for key, value in args.items():
        request.set(key, xml_text(value))
    return root, request


def comment(parent, text: str) -> None:
    """An XML comment; a comment cannot contain "--", so every dash followed by a dash gets a space."""
    parent.append(etree.Comment(f" {re.sub(r'-(?=-)', '- ', xml_text(text))} "))


def list_records(
    base_url: str, items: Iterable[str | tuple[str, datetime, dict]]
) -> bytes:
    """A complete ListRecords response without pagination, for the records command.

    An item is a record (identifier, datestamp, metadata) or a string, which
    becomes an XML comment at that place: diagnostics next to the records they
    concern, in a document that stays valid.
    """
    root, _ = document(base_url, "ListRecords", {"metadataPrefix": "oai_dc"})
    container = element("ListRecords")
    root.append(container)
    for item in items:
        if isinstance(item, str):
            comment(container, item)
        else:
            record(container, *item)
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=True
    )
