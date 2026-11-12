"""Legacy Word, PowerPoint and Excel files (OLE2): the SummaryInformation and DocumentSummaryInformation property sets, by olefile.

Each property under olefile's name for it (`OleMetadata.SUMMARY_ATTRIBS`,
`DOCSUM_ATTRIBS`), one it has no name for as <stream>.<id>; strings decoded
with the code page the property set gives; a time as olefile gives it, with
`Z` (a FILETIME is UTC by the format's definition). Only the first section of
each property set: olefile's `get_userdefined_properties` pairs names and
values by position, not by property id (BACKLOG, "Sync with upstream").

Skip list (spec formats/office, "What is left out", `SKIPPED`): the binary
properties, which would otherwise be decoded as text; values not suitable for
text (common.kept).
"""

from datetime import datetime

from modama_crawler.formats import Extracted

from .common import headline, kept, opened

SUMMARY = "\x05SummaryInformation"
DOCUMENT_SUMMARY = "\x05DocumentSummaryInformation"
# The binary properties by olefile's names: a picture, a signature, hyperlinks
SKIPPED = frozenset({"thumbnail", "dig_sig", "hlinks"})
# SummaryInformation's total edit time is a duration: olefile gives seconds
EDIT_TIME = 10
# Code pages Python knows by another name than cp<n>
CODECS = {1200: "utf-16-le", 10000: "mac-roman", 65001: "utf-8"}
# The summary line's entries (the one positive list)
HEADLINE = (
    "title",
    "author",
    "create_time",
    "creating_application",
    "num_pages",
    "slides",
)


def plain(value, codepage):
    """A property value as a JSON value: bytes decoded with the code page (as bytes if they do not decode), a time as ISO text."""
    if isinstance(value, bytes):
        try:
            return value.decode(CODECS.get(codepage, f"cp{codepage}"))
        except (LookupError, UnicodeDecodeError):
            return value
    if isinstance(value, datetime):
        # A FILETIME is UTC by the format's definition: written with Z, as
        # Office Open XML writes its times, not converted
        return value.isoformat() + "Z"
    if isinstance(value, list):
        return [plain(v, codepage) for v in value]
    return value


def entries(ole, stream: str, names: list[str]):
    """The properties of a stream by olefile's names, but the skip list's binary ones."""
    properties = ole.getproperties(stream, convert_time=True, no_conversion=[EDIT_TIME])
    # The code page is an unsigned 16-bit number (MS-OLEPS; review of
    # common-office, finding 3), which olefile reads as a signed one (VT_I2):
    # 65001 (UTF-8) arrives as -535 (BACKLOG, "Sync with upstream")
    if isinstance(properties.get(1), int):
        properties[1] &= 0xFFFF
    codepage = properties.get(1)
    for pid, value in properties.items():
        name = names[pid - 1] if 0 < pid <= len(names) else f"{stream[1:]}.{pid}"
        if name not in SKIPPED:
            yield name, plain(value, codepage)


def extract(path: str) -> Extracted:
    import olefile

    pairs = []
    with opened(path) as f, olefile.OleFileIO(f) as ole:
        for stream, names in (
            (SUMMARY, olefile.OleMetadata.SUMMARY_ATTRIBS),
            (DOCUMENT_SUMMARY, olefile.OleMetadata.DOCSUM_ATTRIBS),
        ):
            if ole.exists(stream):
                pairs += entries(ole, stream, names)
    original = kept(pairs)
    return Extracted(
        summary=headline(original, HEADLINE),
        subjects=[],
        values={"original_metadata": original, "mapped_metadata": {}},
    )
