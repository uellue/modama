"""SVG files through defusedxml: the root's attributes and its title, desc and metadata elements (spec formats/image)."""

from collections import Counter

from modama_crawler.formats import Extracted
from modama_crawler.formats.values import textual

# At most this much of a file is read (spec formats/image, "SVG metadata is the
# root's attributes and its descriptive elements"); the descriptive elements
# come first in the files seen (Matplotlib, Inkscape)
SVG_LIMIT = 1 << 20
# The root's children that describe the drawing (SVG 1.1, 5.4 and 21); the
# skip list: every other element (the drawing), text between child elements,
# what follows SVG_LIMIT, values not suitable for text
KEPT = frozenset({"title", "desc", "metadata"})
# The one prefix XML binds without a declaration (xml:space, xml:lang)
XML = "http://www.w3.org/XML/1998/namespace"


def extract(path: str) -> Extracted:
    """The root's attributes as `@name`, its title, desc and metadata under dotted paths."""
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
    # Unbuffered: iterparse reads 16 KiB at a time, and tell() is what was read
    with open(path, "rb", buffering=0) as f:
        for event, item in ET.iterparse(f, events=("start-ns", "start", "end")):
            if event == "start-ns":
                prefix, uri = item
                prefixes.setdefault(uri, prefix)
            elif event == "start":
                depth += 1
                if depth == 1:
                    for key, value in item.attrib.items():
                        add(f"@{named(key)}", value)
            else:
                if depth == 2 and (name := named(item.tag)) in KEPT:
                    kept[name] += 1
                    visit(item, name if kept[name] == 1 else f"{name}[{kept[name]}]")
                if depth == 2:
                    item.clear()
                depth -= 1
            if f.tell() > SVG_LIMIT:
                break
    summary = [found["title"]] if found.get("title") else []
    summary += [
        f"{n} {found[f'@{n}']}" for n in ("width", "height") if found.get(f"@{n}")
    ]
    return Extracted(summary=summary, subjects=[], values={"original_metadata": found})
