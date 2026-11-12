"""Plain text and markup documents: one dataset per file of the types the core gives them (spec formats/text).

The core's MIME database types these files already (`freedesktop.org.xml`), so
this part has no rules of its own. Extraction reads the first 1 MiB of a file
(`head.HEAD`; 64 KiB of one typed by its content, `head.SNIFFED_HEAD`): the
encoding as its bytes say it and the line count for every text file, and what
the markup says about the document for Markdown,
reStructuredText, HTML, LaTeX and BibTeX (`markup`). Never the body.
"""

import re
from collections.abc import Iterable
from dataclasses import replace

from modama_crawler import mime
from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format

from . import head, markup


def phrases(name: str, value) -> list[str]:
    """A summary line's phrases for a value as found: text bare, a number after its name
    unless it is 0, a list item by item (decision 230; TEMPLATE.md, the summary line)."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, bool) or value is None or isinstance(value, dict):
        return []
    if isinstance(value, int | float):
        return [f"{name} {value}"] if value != 0 else []
    if isinstance(value, list):
        return [p for item in value for p in phrases(name, item)]
    return []


def headline_value(name: str, original: dict, mapped: dict):
    """The value of a summary line's entry: from original_metadata, then mapped_metadata;
    for a list of mappings (`author[0].name`, as Pandoc and Quarto write authors), their names."""
    if name in original:
        return original[name]
    if name in mapped:
        return mapped[name]
    names = re.compile(rf"{re.escape(name)}\[\d+\]\.name")
    return [v for k, v in original.items() if names.fullmatch(k)]


# The basis of a file typed by its content, not by its name: its head is
# head.SNIFFED_HEAD (design D2)
SNIFFED = "single file, typed by its content"


class Text(Format):
    """A plain text file, as one dataset: its encoding and line count."""

    type = "text/plain"
    reacts_to = frozenset({type})
    # After the formats that claim a text file as a member of their dataset, or
    # drop a file's type to a text type (design D4)
    priority = 20
    # The entries of the summary line, from original_metadata, then mapped_metadata
    HEADLINE: tuple[str, ...] = ()

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        for e in d.of_type(self.type):
            named = mime.by_name(e.name) == e.mime
            yield Dataset(anchor=e.rel, basis="single file" if named else SNIFFED)

    def decode(self, found: head.Head) -> head.Head:
        """The head as the markup says to decode it; as the bytes say for plain text."""
        return found

    def parse(self, found: head.Head) -> tuple[dict, dict]:
        """original_metadata and the mapped values of the markup; none for plain text."""
        return {}, {}

    def extract(self, dataset: Dataset, root: str) -> Extracted | None:
        """What the file says about itself, the encoding and the line count (spec formats/text)."""
        bound = head.SNIFFED_HEAD if SNIFFED in dataset.basis else head.HEAD
        found = head.read(root + dataset.anchor, bound)
        if not found.data:
            return None
        if found.encoding is None:
            # Not text: nothing to parse or count
            values = {"original_metadata": {}, "mapped_metadata": {"encoding": None}}
            return Extracted(summary=[], subjects=[], values=values)
        found = self.decode(found)
        original, mapped = self.parse(found)
        mapped = {"encoding": found.encoding, **head.lines(found), **mapped}
        summary = [
            p
            for name in self.HEADLINE
            for p in phrases(name, headline_value(name, original, mapped))
        ]
        summary.append(found.encoding)
        summary += [f"{k} {v}" for k, v in head.lines(found).items()]
        return Extracted(
            summary=list(dict.fromkeys(summary)),
            subjects=[],
            values={"original_metadata": original, "mapped_metadata": mapped},
        )


class Log(Text):
    type = "text/x-log"
    reacts_to = frozenset({type})


class Readme(Text):
    type = "text/x-readme"
    reacts_to = frozenset({type})


class Markdown(Text):
    type = "text/markdown"
    reacts_to = frozenset({type})
    HEADLINE = ("title", "author", "date", "first heading")

    def parse(self, found):
        return markup.markdown(found.text)


class Rst(Text):
    type = "text/x-rst"
    reacts_to = frozenset({type})
    HEADLINE = ("title", "subtitle", "author", "authors", "date")

    def parse(self, found):
        return markup.rst(found.text)


class Html(Text):
    type = "text/html"
    reacts_to = frozenset({type})
    HEADLINE = ("title", "meta.author", "meta.generator")

    def decode(self, found):
        """As the head's `<meta charset>` declares, where the bytes are not UTF-8 (the
        HTML standard's order: a BOM, then the declaration, then the default)."""
        if found.encoding != head.FALLBACK:
            return found
        label = markup.declared(markup.html(found.text)[0])
        if label is None:
            return found
        text = head.decoded(found.data, label, found.complete)
        return replace(found, encoding=label, text=text)

    def parse(self, found):
        return markup.html(found.text)


class Tex(Text):
    type = "text/x-tex"
    reacts_to = frozenset({type})
    HEADLINE = ("title", "author", "date", "documentclass")

    def parse(self, found):
        return markup.tex(found.text)


class Bibtex(Text):
    type = "text/x-bibtex"
    reacts_to = frozenset({type})
    HEADLINE = ("entries", "entries at least")

    def parse(self, found):
        return markup.bibtex(found.text, found.complete)


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection(
    "common",
    [Text(), Log(), Readme(), Markdown(), Rst(), Html(), Tex(), Bibtex()],
)
