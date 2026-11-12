"""What a document's markup says about it, each with the field's established reader (spec formats/text).

Each function takes the decoded head of a file and returns its
`original_metadata` (what the file says, in the reader's names) and what goes
into `mapped_metadata` beside the encoding and the line count.
"""

import codecs
import email.message
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


def flat(
    value, name: str = "", within: frozenset[int] = frozenset()
) -> Iterator[tuple[str, object]]:
    """(dotted name, value) of every leaf below a YAML value: a mapping's keys joined
    with dots, a list holding mappings or lists numbered (`author[0].name`), a list of
    values kept as one value; an empty mapping or list kept as it is. A mapping or
    list that holds itself (`x: &a [1, *a]`) ends there: `within` are the
    containers on the way down."""
    if isinstance(value, dict | list):
        if id(value) in within:
            return
        within = within | {id(value)}
    if isinstance(value, dict) and value:
        for key, item in value.items():
            yield from flat(item, f"{name}.{key}" if name else str(key), within)
    elif isinstance(value, list) and any(isinstance(v, dict | list) for v in value):
        for i, item in enumerate(value):
            yield from flat(item, f"{name}[{i}]", within)
    else:
        yield name, value


class YamlLoader(yaml.SafeLoader):
    """PyYAML's safe loader, a date or time as written: no conversion to a time zone.

    TODO (main's decision 3, review of common-text): use the package's one YAML
    loader of the area `structured` once it is merged (keys and scalars as
    written: `10:30`, `1.10`, `012`, `NO`; unknown tags as text).
    """


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


def declared(original: dict) -> str | None:
    """The encoding an HTML head declares, as written: `<meta charset>`, else the
    charset of `<meta http-equiv="Content-Type">`, the first of each; None if none
    or one Python's codecs do not know."""
    first = {k.lower(): v[0] if isinstance(v, list) else v for k, v in original.items()}
    label = first.get("meta.charset")
    if label is None and "meta.content-type" in first:
        message = email.message.Message()
        message["Content-Type"] = first["meta.content-type"]
        label = message.get_param("charset")
    if not isinstance(label, str):
        return None
    try:
        codecs.lookup(label)
    except LookupError:
        return None
    return label


# The macros of a LaTeX document's title, and its class: taken wherever they
# are first, in the document too
LATEX_MACROS = ("documentclass", "title", "author", "date")
# The skip list of a LaTeX preamble (spec formats/text, "LaTeX preamble"):
# definitions, packages and files the document reads, and layout and style
LATEX_SKIPPED = frozenset(
    {
        # definitions
        "newcommand",
        "renewcommand",
        "providecommand",
        "newenvironment",
        "renewenvironment",
        "newtheorem",
        "newcounter",
        "newlength",
        "newbox",
        "newsavebox",
        "newif",
        "DeclareMathOperator",
        "def",
        "edef",
        "gdef",
        "xdef",
        "let",
        # packages and files
        "usepackage",
        "RequirePackage",
        "input",
        "include",
        "includeonly",
        "graphicspath",
        "addbibresource",
        # layout and style
        "setlength",
        "addtolength",
        "setcounter",
        "addtocounter",
        "pagestyle",
        "thispagestyle",
        "geometry",
        "bibliographystyle",
        "theoremstyle",
        "numberwithin",
        "urlstyle",
    }
)
# Definitions whose next macro is the name they define, not a macro used
LATEX_DEFINING = frozenset({"def", "edef", "gdef", "xdef", "let"})
# The end of the preamble: \begin{document} at the start of a line, so not
# in a comment
LATEX_PREAMBLE_END = re.compile(r"^[ \t]*\\begin\{document\}", re.MULTILINE)


def tex(text: str) -> tuple[dict, dict]:
    """The first mandatory argument of the first occurrence of each macro of the preamble
    (before \\begin{document}) but the skip list, and of \\documentclass, \\title,
    \\author and \\date wherever they are first, as raw LaTeX (pylatexenc)."""
    from pylatexenc.latexwalker import (
        LatexCharsNode,
        LatexCommentNode,
        LatexEnvironmentNode,
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

    def content(group) -> str:
        return "".join(n.latex_verbatim() for n in group.nodelist)

    def mandatory(node) -> str | None:
        """The first mandatory argument of a macro pylatexenc knows the arguments of."""
        if node.nodeargd is None:
            return None
        for spec, argument in zip(
            node.nodeargd.argspec, node.nodeargd.argnlist, strict=False
        ):
            if spec == "{":
                return (
                    content(argument) if isinstance(argument, LatexGroupNode) else None
                )
        return None

    # The title fields with beamer's optional short form (\title[Short]{Long});
    # pylatexenc's default knows the mandatory argument only
    context = get_default_latex_context_db()
    context.add_context_category(
        "title fields",
        macros=[MacroSpec(m, "[{") for m in LATEX_MACROS[1:]],
        prepend=True,
    )

    def parsed(source: str) -> list:
        walker = LatexWalker(source, latex_context=context, tolerant_parsing=True)
        return walker.get_latex_nodes()[0]

    nodelist = parsed(text[:PARSE])
    original = {}
    # The preamble parsed on its own: pylatexenc pairs \begin and \end across
    # groups, so a definition such as docutils' \newenvironment{DUadmonition}
    # {\begin{center}…}{…\end{center}} swallows the rest of the file, the
    # document environment included (BACKLOG, "Sync with upstream")
    if (end := LATEX_PREAMBLE_END.search(text[:PARSE])) is not None:
        # A macro pylatexenc does not know (\affiliation) is followed by its
        # argument as a group of its own; `waiting` is such a macro's name
        waiting, defining = None, False
        for node in parsed(text[: end.start()]):
            if isinstance(node, LatexEnvironmentNode):
                waiting, defining = None, False
                continue
            if isinstance(node, LatexCommentNode) or (
                isinstance(node, LatexCharsNode) and not node.chars.strip()
            ):
                continue
            if isinstance(node, LatexGroupNode) and waiting is not None:
                original.setdefault(waiting, content(node))
            waiting = None
            if not isinstance(node, LatexMacroNode):
                defining = False
                continue
            name, skip = node.macroname, defining or node.macroname in LATEX_SKIPPED
            defining = name in LATEX_DEFINING
            if skip:
                continue
            if node.nodeargd is not None and "{" in node.nodeargd.argspec:
                if (value := mandatory(node)) is not None:
                    original.setdefault(name, value)
            else:
                waiting = name
    for node in walk(nodelist):
        if (
            isinstance(node, LatexMacroNode)
            and node.macroname in LATEX_MACROS
            and node.macroname not in original
            and (value := mandatory(node)) is not None
        ):
            original[node.macroname] = value
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
