"""What the office families share: opening a file for small reads, XML parts of a ZIP package, the summary line."""

import os
from collections.abc import Iterable, Iterator
from contextlib import contextmanager, suppress
from typing import BinaryIO
from zipfile import ZipFile

from defusedxml import ElementTree
from modama_crawler.formats.values import textual

# Python sizes a file's buffer from st_blksize, 1 MiB on NFS; the readers here
# seek between small pieces (a ZIP's central directory and a few members, a
# PDF's cross-reference table and a few objects). 64 KiB is NFS's read size
# (modama-formats-em's DM reader, staging finding F14).
BUFFER = 64 * 1024
# The largest XML part read: property parts are a few kB, a presentation's
# slide list grows by about 40 bytes a slide. The size is the one the ZIP's
# directory gives, which the ZIP reader holds the member to.
MAX_PART = 16 * 1024 * 1024


@contextmanager
def opened(path: str) -> Iterator[BinaryIO]:
    """The file at path for reading in small pieces: a 64 KiB buffer, readahead off."""
    with open(path, "rb", buffering=BUFFER) as f:
        # The advice is an optimisation: a file system that refuses it, or a
        # platform without it, still reads the file (as mime.py)
        if hasattr(os, "posix_fadvise"):
            with suppress(OSError):
                os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_RANDOM)
        yield f


def part(z: ZipFile, name: str):
    """The root element of the XML member name of z, parsed by defusedxml; ValueError if larger than MAX_PART."""
    info = z.getinfo(name)
    if info.file_size > MAX_PART:
        raise ValueError(f"{name}: {info.file_size} bytes, more than {MAX_PART}")
    with z.open(info) as f:
        return ElementTree.parse(f).getroot()


def local(name: str) -> str:
    """An element's or attribute's name without its namespace."""
    return name.rpartition("}")[2]


def text(element) -> str | list[str]:
    """An element's text as written ("" if it has none), or the texts of its innermost elements when it has children (a vector)."""
    if len(element) == 0:
        return element.text or ""
    return [e.text or "" for e in element.iter() if len(e) == 0]


def kept(entries: Iterable[tuple[str, object]]) -> dict:
    """The entries as name -> value but those not suitable for text (values.textual), the skip list every family shares."""
    return {name: value for name, value in entries if textual(value)}


def headline(values: dict, chosen: Iterable[str | tuple[str, str]]) -> list[str]:
    """The summary line: the values of the chosen entries present and not empty, in their order.

    An entry given as a name alone is a text, as it is (`My Title`), or a
    number after its name (`num_pages 1`); an entry given as (name, label) is
    a count whose file writes it as text, after its label (`Pages 1`). A
    number of 0 is left out, as office files write 0 where they have no
    value. A phrase repeated is kept once (spec formats/office, "The summary
    line of an office document").
    """
    phrases = []
    for entry in chosen:
        name, label = (entry, None) if isinstance(entry, str) else entry
        value = values.get(name)
        if value is None or value == "" or isinstance(value, bool | list | dict):
            continue
        if label is None and isinstance(value, str):
            phrases.append(value)
        elif str(value) not in ("0", "0.0"):
            phrases.append(f"{label or name} {value}")
    return list(dict.fromkeys(phrases))
