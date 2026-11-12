"""What the image formats share: opening a file for a header reader, flat names, the summary line."""

import enum
import math
import numbers
import os
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager, suppress

from modama_crawler.formats.values import textual

# A buffer of NFS's read size, readahead off: the readers read headers in small
# pieces and seek, and Python's default buffer on NFS is 1 MiB, refilled at
# every seek (crawler README, "Pitfalls"; modama_formats_em.dm, F14)
BUFFER = 64 * 1024


@contextmanager
def opened(path: str):
    """The file at path for a reader that reads in small pieces: a 64 KiB buffer, readahead off."""
    with open(path, "rb", buffering=BUFFER) as f:
        # An optimisation: a file system that refuses it still reads the file
        if hasattr(os, "posix_fadvise"):
            with suppress(OSError):
                os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_RANDOM)
        yield f


def plain(value):
    """A value as JSON holds it, as the reader gives it: a code the reader names
    (an enum) by its name, a tuple as a list, a NumPy value as Python's, a
    rational as its number, an infinity or NaN as its text."""
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, list | tuple):
        return [plain(v) for v in value]
    if hasattr(value, "tolist"):  # NumPy arrays and scalars
        return plain(value.tolist())
    if isinstance(value, numbers.Rational) and not isinstance(value, int):
        value = float(value)  # Pillow's IFDRational; 0/0 gives NaN
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, str):
        return str(value)  # a subclass (Pillow's iTXt) as plain text
    if value is None or isinstance(value, bool | int | float):
        return value
    return str(value)


def entries(
    items: Iterable[tuple[str, object]],
    skipped: Callable[[str, object], bool] = lambda name, value: False,
    prefix: str = "",
) -> Iterator[tuple[str, object]]:
    """(dotted name, value) of each item and of everything in its dicts, as found,
    but those skipped(name, value) names and values not suitable for text (values.textual).

    A dict's entries go under `<name>.<key>`; a list that holds dicts under
    `<name>[<index>]`. An empty value is kept (decision 161).
    """
    for key, value in items:
        name = f"{prefix}{key}"
        if skipped(name, value):
            continue
        if isinstance(value, dict):
            yield from entries(value.items(), skipped, f"{name}.")
        elif isinstance(value, list | tuple) and any(
            isinstance(v, dict) for v in value
        ):
            yield from entries(
                ((f"[{i}]", v) for i, v in enumerate(value)), skipped, name
            )
        elif textual(value):
            yield name, plain(value)


def phrase(name: str, value, unit_unknown: bool = False) -> str | None:
    """A text as it is, a number (or a list) after the last part of its name, 0 left out."""
    if isinstance(value, str):
        return value or None
    if value == 0:
        return None
    text = f"{name.rsplit('.', 1)[-1]} {value}"
    return f"{text} (unit unknown)" if unit_unknown else text


def headline(
    values: dict,
    groups: Iterable[tuple[str, ...]],
    say: Callable[[str, object], str | None] = phrase,
) -> list[str]:
    """The summary line: for each group the first of its names present, said by say(), a phrase repeated once."""
    phrases = []
    for group in groups:
        found = ((n, values[n]) for n in group if values.get(n) not in (None, "", []))
        if (hit := next(found, None)) is not None and (text := say(*hit)):
            phrases.append(text)
    return list(dict.fromkeys(phrases))
