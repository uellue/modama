"""Flat entries of a parsed document, as found: dotted path -> value, bounded; and the summary line from them.

Spec formats/structured: "Every entry of a JSON, YAML or TOML document is kept",
"Every element and attribute of an XML document is kept", "Bounded reading",
"The summary line", "What is left out".
"""

import json
import logging
import math
import re
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from datetime import date, time

from modama_crawler.formats.values import credential, textual

log = logging.getLogger(__name__)

# The crawler cuts a stored object at 1,000 entries (extraction.MAX_ITEMS):
# cut here first, in the file's order, and say so
MAX_ENTRIES = 1000
# Values walked, kept or skipped: a document of shared references (a YAML
# alias bomb) is a tree of exponential size for a walk. About 10 µs each
# (a bomb's 100,000 took 0.85 s on the VM, 2026-11-12)
MAX_VISITS = 10 * MAX_ENTRIES
# "A few chosen entries" for the summary line (TEMPLATE.md, checklist)
SUMMARY = 8
# The path of a document that is a plain value, JSONPath's root (RFC 9535)
ROOT = "$"

Pairs = Iterable[tuple[str, object]]


def plain(value):
    """A reader's value as JSON can hold it: a date or time as ISO 8601 text with
    its offset as parsed, an infinite or not-a-number float as Python writes it."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, date | time):  # datetime is a date
        return value.isoformat()
    return value


def of_data(node, path: str = "") -> Iterator[tuple[str, object]]:
    """(path, value) of every value of a JSON, YAML or TOML document in its order.

    Keys joined with dots; a list of plain values is one value; a list that
    holds an object or a list numbers its items from 1, `a[2].b`; an empty
    object as {}; a document that is a plain value under ROOT.
    """
    if isinstance(node, dict):
        if not node:
            yield path or ROOT, {}
        for key, value in node.items():
            yield from of_data(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list) and any(isinstance(v, dict | list) for v in node):
        for i, value in enumerate(node, 1):
            yield from of_data(value, f"{path}[{i}]")
    elif isinstance(node, list):
        yield path or ROOT, [plain(v) for v in node]
    else:
        yield path or ROOT, plain(node)


def of_documents(documents: list) -> Iterator[tuple[str, object]]:
    """(path, value) of a file's documents: one document as itself, several numbered from 1, `[2].a`."""
    if len(documents) == 1:
        yield from of_data(documents[0])
        return
    for i, document in enumerate(documents, 1):
        yield from of_data(document, f"[{i}]")


def of_xml(root) -> Iterator[tuple[str, str]]:
    """(path, text) of every attribute and text of an XML tree below its root, in document order.

    The rules of modama_formats_em.empad.entries (spec formats/empad, "Every
    element and attribute is kept"): `@name` for an attribute, `[n]` from 1
    for siblings of one name only, an element without children and attributes
    with its text (empty too), other text that is not whitespace as `#text`
    (the root's) or beside the children, the text after an element as
    `#tail`. Names as the tree holds them (structured.parse_xml qualifies them).
    """

    def visit(element, path: str) -> Iterator[tuple[str, str]]:
        for name, value in element.attrib.items():
            yield f"{path}@{name}", value
        children = list(element)
        text = element.text or ""
        if text.strip() or (path and not (children or element.attrib)):
            yield path[:-1] or "#text", text
        counts = Counter(child.tag for child in children)
        seen = Counter()
        for child in children:
            seen[child.tag] += 1
            if counts[child.tag] > 1:
                inner = f"{path}{child.tag}[{seen[child.tag]}]"
            else:
                inner = f"{path}{child.tag}"
            yield from visit(child, f"{inner}.")
            if child.tail and child.tail.strip():
                yield f"{inner}#tail", child.tail

    yield from visit(root, "")


def kept(pairs: Pairs, where: str) -> tuple[dict, bool, int]:
    """The pairs but the skip list, as a dict; whether the bounds cut it; how many credentials were left out.

    The skip list: a value not suitable for text (values.textual); a value
    that may be a credential (values.credential); entries after MAX_ENTRIES
    kept or MAX_VISITS walked. A path met twice keeps both, the second as
    `<path>#2`, with a warning naming where.
    """
    found = {}
    secrets = 0
    for n, (key, value) in enumerate(pairs):
        if n == MAX_VISITS:
            return found, True, secrets
        if not textual(value):
            continue
        if credential(key, value):
            secrets += 1
            continue
        if len(found) == MAX_ENTRIES:
            return found, True, secrets
        if key in found:
            i = 2
            while f"{key}#{i}" in found:
                i += 1
            log.warning("%s: %s twice, the second kept as %s#%d", where, key, key, i)
            key = f"{key}#{i}"
        found[key] = value
    return found, False, secrets


def _is_number_or_boolean(text: str) -> bool:
    if text.lower() in ("true", "false"):
        return True
    try:
        float(text)
    except ValueError:
        return False
    return True


def _name(path: str) -> str:
    """The last part of a path, without `@` and `[n]`: what a number goes after."""
    last = path.rsplit(".", 1)[-1]
    return re.sub(r"(\[\d+\])+$", "", last).lstrip("@")


def phrase(path: str, value) -> str | None:
    """A value for the summary line: text bare, a number or a boolean after its name, None if empty or not plain.

    A text's whitespace, line breaks too, as single spaces: the line is one line.
    """
    if isinstance(value, bool):
        return f"{_name(path)} {json.dumps(value)}"
    if isinstance(value, int | float):
        return f"{_name(path)} {value}"
    if not isinstance(value, str) or not value.strip():
        return None
    text = " ".join(value.split())
    return f"{_name(path)} {text}" if _is_number_or_boolean(text) else text


def headline(
    entries: dict, skip: Callable[[str], bool] = lambda path: False
) -> list[str]:
    """The summary line: the first SUMMARY phrases of the entries in their order, a value repeated once."""
    phrases = []
    for path, value in entries.items():
        if skip(path) or (p := phrase(path, value)) is None or p in phrases:
            continue
        phrases.append(p)
        if len(phrases) == SUMMARY:
            break
    return phrases
