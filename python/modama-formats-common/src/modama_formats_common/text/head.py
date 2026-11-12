"""The head of a text file: its first bytes, their encoding as detected, the text and its line count (spec formats/text; design D1, D2)."""

import codecs
from dataclasses import dataclass

# The bytes read of a file (design D2; the brief: "read at most the first 1 MB")
HEAD = 1 << 20
# The encoding of text that is not UTF-8 (design D1)
FALLBACK = "Windows-1252"
# Byte order marks and names for them that Python's codecs read without the
# mark (chardet's); UTF-32's before UTF-16's, which they start with
BOMS = (
    (codecs.BOM_UTF32_LE, "UTF-32"),
    (codecs.BOM_UTF32_BE, "UTF-32"),
    (codecs.BOM_UTF8, "UTF-8-SIG"),
    (codecs.BOM_UTF16_LE, "UTF-16"),
    (codecs.BOM_UTF16_BE, "UTF-16"),
)


@dataclass(frozen=True)
class Head:
    data: bytes  # at most HEAD bytes
    complete: bool  # data is the whole file
    encoding: str | None  # None: not text
    text: str  # data decoded, "" when encoding is None


def decodes(data: bytes, encoding: str, complete: bool) -> bool:
    """Whether data is valid in encoding; a sequence cut at the end allowed unless data is the whole file."""
    try:
        codecs.getincrementaldecoder(encoding)().decode(data, final=complete)
    except UnicodeDecodeError:
        return False
    return True


def encoding(data: bytes, complete: bool) -> str | None:
    """The encoding of data as its bytes say it (design D1): its BOM's; none for a NUL
    byte (not text); ascii or utf-8 if they decode so; else Windows-1252."""
    for bom, name in BOMS:
        if data.startswith(bom):
            return name
    if b"\0" in data:
        return None
    for name in ("ascii", "utf-8"):
        if decodes(data, name, complete):
            return name
    # Not UTF-8: the default the HTML standard suggests for legacy content in
    # German and English locales (13.2.3.2); detectors named one in nine
    # short German notes wrongly (design D1)
    return FALLBACK


def read(path: str) -> Head:
    """The first HEAD bytes of the file at path, read once, with their encoding and text."""
    with open(path, "rb", buffering=0) as f:
        data = b""
        # One more byte than HEAD: whether the head is the whole file
        while len(data) <= HEAD and (chunk := f.read(HEAD + 1 - len(data))):
            data += chunk
    complete = len(data) <= HEAD
    data = data[:HEAD]
    found = encoding(data, complete)
    text = (
        ""
        if found is None
        else codecs.getincrementaldecoder(found)("replace").decode(data, final=complete)
    )
    return Head(data, complete, found, text)


def lines(head: Head) -> dict:
    """The line count: `lines` for a whole file (a last line without a line feed counts), `lines at least` for a head."""
    n = head.text.count("\n")
    if not head.complete:
        return {"lines at least": n}
    return {"lines": n + (1 if head.text and not head.text.endswith("\n") else 0)}
