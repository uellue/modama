"""SVG files through defusedxml: the root's attributes and the elements at the root that are not the drawing (spec formats/image)."""

from collections import Counter

from modama_crawler.formats import Extracted
from modama_crawler.formats.values import textual

# At most this much of a file is read (spec formats/image, "SVG metadata is the
# root's attributes and what is not the drawing"); the descriptive elements
# come first in the files seen (Matplotlib, Inkscape). A larger file is parsed
# up to here: what was found by then is kept
SVG_LIMIT = 1 << 20
SVG = "http://www.w3.org/2000/svg"
# The SVG elements that describe the drawing rather than draw it (SVG 1.1,
# 5.4 and 21): kept, as every element of another namespace (foreign metadata)
DESCRIPTIVE = frozenset({"title", "desc", "metadata"})
# The one skip list of SVG files (`skipped`): at the root, the drawing (every
# other element of the SVG namespace, or of none: g, defs, path, image, style,
# …) and Inkscape's user-interface settings (sodipodi:namedview: zoom, window,
# guides); text between child elements; what follows SVG_LIMIT; values not
# suitable for text (values.textual)
SETTINGS = frozenset({"{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}namedview"})
# The one prefix XML binds without a declaration (xml:space, xml:lang)
XML = "http://www.w3.org/XML/1998/namespace"


def skipped(tag: str) -> bool:
    """Whether an element at the root (its tag as ElementTree gives it, `{namespace}name`) is on the skip list."""
    if tag in SETTINGS:
        return True
    uri, _, local = tag[1:].partition("}") if tag.startswith("{") else ("", "", tag)
    return uri in (SVG, "") and local not in DESCRIPTIVE


class Head:
    """The first `limit` bytes of a binary file, then its end, for a parser that reads in pieces."""

    def __init__(self, f, limit: int):
        self.f, self.left = f, limit

    def read(self, n: int = -1) -> bytes:
        data = self.f.read(self.left if n < 0 else min(n, self.left))
        self.left -= len(data)
        return data


def extract(path: str) -> Extracted:
    """The root's attributes as `@name`, the elements at the root but the skip list under dotted paths."""
    import defusedxml.ElementTree as ET

    prefixes = {XML: "xml"}  # namespace -> the prefix the file declares for it

    def named(tag: str) -> str:
        if not tag.startswith("{"):
            return tag
        uri, local = tag[1:].split("}", 1)
        prefix = prefixes.get(uri)
        if prefix is None:
            return tag
        return f"{prefix}:{local}" if prefix else local

    found = {}

    def add(name: str, value: str) -> None:
        if textual(value):
            found[name] = value

    def visit(element, path: str) -> None:
        """Every attribute and text of element as found, as formats/empad's entries."""
        for key, value in element.attrib.items():
            add(f"{path}.@{named(key)}", value)
        children = list(element)
        text = element.text or ""
        if text.strip() or not (children or element.attrib):
            add(path, text)
        counts = Counter(named(c.tag) for c in children)
        seen = Counter()
        for child in children:
            name = named(child.tag)
            seen[name] += 1
            number = f"[{seen[name]}]" if counts[name] > 1 else ""
            visit(child, f"{path}.{name}{number}")

    kept = Counter()
    depth = 0
    # Unbuffered: iterparse reads 16 KiB at a time, Head stops it at SVG_LIMIT
    with open(path, "rb", buffering=0) as f:
        head = Head(f, SVG_LIMIT)
        try:
            for event, item in ET.iterparse(head, events=("start-ns", "start", "end")):
                if event == "start-ns":
                    prefix, uri = item
                    prefixes.setdefault(uri, prefix)
                elif event == "start":
                    depth += 1
                    if depth == 1:
                        for key, value in item.attrib.items():
                            add(f"@{named(key)}", value)
                else:
                    if depth == 2 and not skipped(item.tag):
                        name = named(item.tag)
                        kept[name] += 1
                        number = f"[{kept[name]}]" if kept[name] > 1 else ""
                        visit(item, f"{name}{number}")
                    if depth == 2:
                        item.clear()
                    depth -= 1
        except ET.ParseError:
            # The file goes on past SVG_LIMIT: the XML ends in the middle
            if head.left > 0:
                raise
    summary = [found["title"]] if found.get("title") else []
    summary += [
        f"{n} {found[f'@{n}']}" for n in ("width", "height") if found.get(f"@{n}")
    ]
    return Extracted(summary=summary, subjects=[], values={"original_metadata": found})
