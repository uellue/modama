"""What the formats of this part share: values as JSON holds them, limits, the summary line."""

import json
import math
import os
import time
from contextlib import suppress
from fnmatch import fnmatchcase

from modama_crawler import extraction
from modama_crawler.formats import Directory, Entry
from modama_crawler.formats.values import MAX_ITEMS, textual

# A walk over a file's entries (HDF5 objects, .npz members) stops at the
# storage's limit of entries per dict, which would cut the rest anyway; after
# a number of objects, as most add no entry (200,000 empty groups: 11 s and
# 335 MB in the review of change common-pydata); or after a third of the
# extractor's time limit, so that a file of hundreds of thousands of objects
# on a slow NFS ends with what was found (spec formats/pydata, "The walk of an
# HDF5 file is bounded")
MAX_ENTRIES = extraction.MAX_ITEMS
MAX_OBJECTS = 5000
SECONDS = extraction.TIME_LIMIT / 3
ENTRY_LIMIT = f"cut at the entry limit of {MAX_ENTRIES}"


class Walk:
    """The entries found so far, and why the walk stopped early (None while it goes on)."""

    def __init__(self):
        self.values: dict = {}
        self.objects = 0  # counted by the walker
        self.cut: str | None = None
        self._start = time.monotonic()

    def over(self) -> bool:
        """Whether a limit is reached before the next entry or object; notes which one."""
        if len(self.values) >= MAX_ENTRIES:
            self.cut = ENTRY_LIMIT
        elif self.objects >= MAX_OBJECTS:
            self.cut = f"cut at the object limit of {MAX_OBJECTS}"
        elif time.monotonic() - self._start > SECONDS:
            self.cut = f"cut at the time limit of {SECONDS:g} s"
        return self.cut is not None

    def add(self, name: str, value) -> None:
        """value under name if it is suitable for text, as JSON holds it."""
        value = plain(value)
        if textual(value) and jsonable(value):
            self.values[name] = value

    def result(self) -> tuple[dict, dict]:
        """original_metadata, cut to the entry limit, and the mapped note of a cut."""
        if len(self.values) > MAX_ENTRIES:  # the last object brought more
            self.cut = ENTRY_LIMIT
        values = dict(list(self.values.items())[:MAX_ENTRIES])
        return values, ({"walk": self.cut} if self.cut else {})


def jsonable(value) -> bool:
    """Whether JSON can hold value (not an HDF5 reference, a set, a complex number …)."""
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        return False
    return True


def plain(value):
    """A value read from a file as JSON holds it: NumPy scalars and arrays of numbers or
    text as Python values, bytes of text decoded as UTF-8; the infinities and NaN as
    Python writes them ("inf"), as modama_formats_em.dm.kept does. Anything else (bytes
    that are not UTF-8, opaque or complex values) is returned as it is, for textual to refuse.
    """
    dtype = getattr(value, "dtype", None)
    if dtype is not None and dtype.kind in "biufSUO":
        if getattr(value, "size", 1) > MAX_ITEMS:  # textual refuses it; don't convert
            return value
        value = value.tolist() if hasattr(value, "tolist") else value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, list | tuple):
        return [plain(v) for v in value]
    return value


def matches(pattern: str, name: str) -> bool:
    """Whether a dotted name matches a dotted pattern part by part (`*` stands for one part)."""
    parts, names = pattern.split("."), name.split(".")
    return len(parts) == len(names) and all(map(fnmatchcase, names, parts))


def headline(values: dict, patterns) -> list[str]:
    """The summary line: for each pattern, the first entry matching it, as found.

    A text as it is; any other value after the last part of its name
    (`shape [16, 16]`), and not at all when it is 0, False or empty, which
    files write where they have no value (TEMPLATE.md, the summary line).
    """
    phrases = []
    for pattern in patterns:
        found = (v for k, v in values.items() if matches(pattern, k))
        value = next(found, None)
        if value in (None, "", [], 0, False):
            continue
        if isinstance(value, str):
            phrases.append(value)
        else:
            phrases.append(f"{pattern.rsplit('.', 1)[-1]} {value}")
    return list(dict.fromkeys(phrases))


def start(d: Directory, e: Entry, n: int) -> bytes | None:
    """The first n bytes of e, or None if it cannot be read: then it keeps its type and the
    crawl warns at it (Directory.cannot_read), as modama_formats_em.dm.header does."""
    try:
        return d.read(e, n)
    except OSError as error:
        d.cannot_read(e, error)
        return None


def no_readahead(fd: int) -> None:
    """Readahead off for a reader that seeks between small pieces (crawler README,
    "Pitfalls", F14); a file system that refuses the advice is still read."""
    if hasattr(os, "posix_fadvise"):
        with suppress(OSError):
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_RANDOM)
