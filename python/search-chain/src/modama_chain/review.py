"""`modama-chain review`: the files a crawl flagged, as Markdown links into the browser (spec chain-browse; design D17)."""

from __future__ import annotations

import re
from collections import defaultdict
from urllib.parse import quote

EXTRACTION_FAILED = "extraction failed"
# The crawler's fixed markers: formats.WANTED_TWICE (decision 344) and NOT_INSPECTED (340, hdf5-links)
MARKERS = ("two formats want it", "not inspected")
# READ_MUCH and OVER_LIMIT: what recognition read of one file (change read-limit-per-file).
# As text, not imported: review needs no crawler installed (psycopg only);
# tests/test_review.py compares them with the crawler's
MARKERS += ("read more than 64 KiB", "over its read limit")
OTHER = "other warnings"
KINDS = (EXTRACTION_FAILED, *MARKERS, OTHER)
NO_FORMAT = "no format named"
LIMIT = 20
# The format id a warning starts with, as the crawler's formats write it: "em/merlin: …", "em/k2is failed: …"
FORMAT = re.compile(r"([\w.-]+/[\w.-]+)[: ]")

# (kind, format) -> [(path, text)]
Groups = dict[tuple[str, str], list[tuple[str, str]]]


def link(browse: str, path: str) -> str:
    """The browser's address of path: the page's `?path=` (browse.html), with brackets encoded too (finding F19)."""
    return f"{browse}?path={quote(path, safe='')}"


def groups(
    warnings: list[tuple[str, str]], failures: list[tuple[str, str, str]]
) -> Groups:
    """The entries by kind and format, in the order of KINDS, then by format id with NO_FORMAT last; each by path."""
    found = defaultdict(list)
    for anchor, fmt, error in failures:
        found[EXTRACTION_FAILED, fmt].append((anchor, error))
    for path, text in warnings:
        kind = next((m for m in MARKERS if m in text), OTHER)
        named = FORMAT.match(text)
        found[kind, named[1] if named else NO_FORMAT].append((path, text))
    order = sorted(found, key=lambda k: (KINDS.index(k[0]), k[1] == NO_FORMAT, k[1]))
    return {k: sorted(found[k]) for k in order}


def markdown(found: Groups, browse: str, limit: int | None) -> list[str]:
    """The list as Markdown lines: a heading per kind, one per format with its count, then up to `limit` entries."""
    lines = [
        "# Flagged files",
        "",
        (
            "Stored warnings and failed extractions of the crawler's index, by kind and format. "
            f"Each link opens the file or folder in `modama-chain browse` at {browse}."
        ),
        "",
    ]
    if not found:
        return [*lines, "Nothing flagged."]
    kind = None
    for (k, fmt), entries in found.items():
        if k != kind:
            lines += [f"## {k}", ""]
            kind = k
        shown = entries[:limit] if limit is not None else entries
        lines += [f"### {fmt} ({len(entries)})", ""]
        # one entry per line: a text's own line breaks would end the list item
        lines += [
            f"- [`{path}`]({link(browse, path)}): {' '.join(text.split())}"
            for path, text in shown
        ]
        if len(entries) > len(shown):
            lines.append(f"- {len(entries) - len(shown)} more: --all lists them")
        lines.append("")
    return lines


def summary(found: Groups) -> list[str]:
    """One line per group, for stderr."""
    return [f"{k}, {fmt}: {len(e)}" for (k, fmt), e in found.items()] or [
        "nothing flagged"
    ]
