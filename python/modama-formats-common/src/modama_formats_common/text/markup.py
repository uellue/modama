"""What a document's markup says about it, each with the field's established reader (spec formats/text).

Each function takes the decoded head of a file and returns its
`original_metadata` (what the file says, in the reader's names) and what goes
into `mapped_metadata` beside the encoding and the line count.
"""

import io
import itertools
import math
import re
from collections.abc import Iterator
from html.parser import HTMLParser

import yaml
from modama_crawler.formats.values import textual

# Characters of the decoded head parsed for Markdown, reStructuredText and
# LaTeX: their metadata is at the start, and docutils needs 28 s for 1 MiB
# (design D2)
PARSE = 1 << 16
# Entries of a YAML front matter at most: aliases can make a small block a
# huge tree (an alias bomb)
MAX_ENTRIES = 1000


def flat(value, name: str = "") -> Iterator[tuple[str, object]]:
    """(dotted name, value) of every leaf below a YAML value: a mapping's keys joined
    with dots, a list holding mappings or lists numbered (`author[0].name`), a list of
    values kept as one value; an empty mapping or list kept as it is."""
    if isinstance(value, dict) and value:
        for key, item in value.items():
            yield from flat(item, f"{name}.{key}" if name else str(key))
    elif isinstance(value, list) and any(isinstance(v, dict | list) for v in value):
        for i, item in enumerate(value):
            yield from flat(item, f"{name}[{i}]")
    else:
        yield name, value


class YamlLoader(yaml.SafeLoader):
    """PyYAML's safe loader, a date or time as written: no conversion to a time zone."""


YamlLoader.add_constructor(
    "tag:yaml.org,2002:timestamp",
    lambda loader, node: loader.construct_scalar(node),
)


def plain(value):
    """A YAML value as JSON holds it: an infinity or NaN as Python writes it (`inf`)."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def front_matter(source: str) -> dict:
    """Every entry of a YAML front matter but values not suitable for text, at most MAX_ENTRIES."""
    found = yaml.load(source, Loader=YamlLoader)  # a safe loader
    if found is None:
        return {}
    entries = itertools.islice(
        flat(found, "" if isinstance(found, dict) else "front matter"), MAX_ENTRIES
    )
    return {name: plain(value) for name, value in entries if textual(value)}


def markdown(text: str) -> tuple[dict, dict]:
    """A Markdown file's YAML front matter and first heading, by markdown-it-py (CommonMark)."""
    from markdown_it import MarkdownIt
    from mdit_py_plugins.front_matter import front_matter_plugin

    tokens = MarkdownIt("commonmark").use(front_matter_plugin).parse(text[:PARSE])
    original, mapped = {}, {}
    if tokens and tokens[0].type == "front_matter":
        try:
            original = front_matter(tokens[0].content)
        except yaml.YAMLError as error:
            mapped["front matter error"] = str(error)
    for opening, inline in itertools.pairwise(tokens):
        if opening.type == "heading_open":
            mapped["first heading"] = inline.content
            break
    return original, mapped


# docutils without the directives that read other files or take raw input, and
# without a configuration file from the working directory; its messages not
# reported (they become no nodes either)
DOCUTILS = {
    "file_insertion_enabled": False,
    "raw_enabled": False,
    "_disable_config": True,
    "report_level": 5,
    "halt_level": 5,
}


def rst(text: str) -> tuple[dict, dict]:
    """A reStructuredText document's title, subtitle and docinfo as docutils reads them."""
    from docutils import nodes
    from docutils.core import publish_doctree

    settings = DOCUTILS | {"warning_stream": io.StringIO()}
    document = publish_doctree(text[:PARSE], settings_overrides=settings)
    original = {}
    for node in document.children:
        if isinstance(node, nodes.title | nodes.subtitle):
            original[node.tagname] = node.astext()
        elif isinstance(node, nodes.docinfo):
            for field in node.children:
                if isinstance(field, nodes.authors):
                    original["authors"] = [a.astext() for a in field.children]
                elif isinstance(field, nodes.field):
                    name, body = field.children
                    original[name.astext()] = body.astext()
                else:  # a bibliographic element: author, date, revision, ...
                    original[field.tagname] = field.astext()
    return {k: v for k, v in original.items() if textual(v)}, {}


# The skip list of HTML heads: a display setting
HTML_SKIPPED = frozenset({"meta.viewport"})
# Characters fed to the parser at a time, until the head ends
HTML_PIECE = 1 << 16
# ASCII whitespace as the HTML standard defines it, for the document's title
HTML_SPACE = re.compile("[\t\n\f\r ]+")


class _Head(HTMLParser):
    """The title, the html element's lang and the meta elements of a document's head."""

    def __init__(self):
        super().__init__()
        self.found: dict = {}
        self.title: list[str] | None = None  # the first title's text while it is read
        self.done = False

    def handle_starttag(self, tag, attrs):
        # A piece fed goes on after the head's end: what follows is the body's
        if self.done:
            return
        attrs = dict(attrs)
        if tag == "html" and "lang" in attrs:
            self.found.setdefault("lang", attrs["lang"])
        elif tag == "title" and "title" not in self.found and self.title is None:
            self.title = []
        elif tag == "meta":
            if "charset" in attrs:
                self.add("meta.charset", attrs["charset"])
            key = next(
                (
                    attrs[a]
                    for a in ("name", "http-equiv", "property", "itemprop")
                    if attrs.get(a)
                ),
                None,
            )
            if key is not None and attrs.get("content") is not None:
                self.add(f"meta.{key}", attrs["content"])
        elif tag == "body":
            self.done = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.done:
            return
        if tag == "title" and self.title is not None:
            self.found["title"] = HTML_SPACE.sub(" ", "".join(self.title)).strip(
                "\t\n\f\r "
            )
            self.title = None
        elif tag == "head":
            self.done = True

    def handle_data(self, data):
        if self.title is not None:
            self.title.append(data)

    def add(self, name: str, value: str):
        """A value; a name met twice keeps all its values, as a list in order."""
        if name not in self.found:
            self.found[name] = value
        elif isinstance(self.found[name], list):
            self.found[name].append(value)
        else:
            self.found[name] = [self.found[name], value]


def html(text: str) -> tuple[dict, dict]:
    """An HTML document's title, lang and meta elements, from its head (Python's html.parser)."""
    parser = _Head()
    for start in range(0, len(text), HTML_PIECE):
        parser.feed(text[start : start + HTML_PIECE])
        if parser.done:
            break
    found = {
        k: v for k, v in parser.found.items() if k not in HTML_SKIPPED and textual(v)
    }
    return found, {}


# The macros of a LaTeX document's title, and its class
LATEX_MACROS = ("documentclass", "title", "author", "date")


def tex(text: str) -> tuple[dict, dict]:
    """The mandatory argument of the first \\documentclass, \\title, \\author and \\date, as raw LaTeX (pylatexenc)."""
    from pylatexenc.latexwalker import (
        LatexGroupNode,
        LatexMacroNode,
        LatexWalker,
        get_default_latex_context_db,
    )
    from pylatexenc.macrospec import MacroSpec

    def walk(nodelist) -> Iterator:
        for node in nodelist or ():
            yield node
            yield from walk(getattr(node, "nodelist", None))

    # The title fields with beamer's optional short form (\title[Short]{Long});
    # pylatexenc's default knows the mandatory argument only
    context = get_default_latex_context_db()
    context.add_context_category(
        "title fields",
        macros=[MacroSpec(m, "[{") for m in LATEX_MACROS[1:]],
        prepend=True,
    )
    walker = LatexWalker(text[:PARSE], latex_context=context, tolerant_parsing=True)
    nodelist, _, _ = walker.get_latex_nodes()
    original = {}
    for node in walk(nodelist):
        if not isinstance(node, LatexMacroNode) or node.macroname not in LATEX_MACROS:
            continue
        if node.macroname in original or node.nodeargd is None:
            continue
        # The last argument is the mandatory one, after the optional [...]
        argument = node.nodeargd.argnlist[-1] if node.nodeargd.argnlist else None
        if isinstance(argument, LatexGroupNode):
            original[node.macroname] = "".join(
                n.latex_verbatim() for n in argument.nodelist
            )
    return {k: v for k, v in original.items() if textual(v)}, {}


def bibtex(text: str, complete: bool) -> tuple[dict, dict]:
    """The number of entries of a BibTeX file and their keys (bibtexparser); of a head, the entries before its last one."""
    import bibtexparser

    if not complete:
        # The last entry may be cut in two: neither counted nor reported as broken
        text = text[: max(text.rfind("\n@"), 0)]
    keys = [entry.key for entry in bibtexparser.parse_string(text).entries]
    mapped = {"entries" if complete else "entries at least": len(keys), "keys": keys}
    return {}, {k: v for k, v in mapped.items() if textual(v)}
