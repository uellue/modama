"""An Office Open XML document's text, rendered as Markdown (change office-text, spec
formats/office): Word by mammoth and markdownify, PowerPoint by python-pptx.

The converters only see a proxy: a copy of the package in memory that holds its XML
parts and every other part empty, so that pictures, video, audio, embedded documents,
macros and fonts are never read (design D2). The rendering goes through the text
area's rule for what is shown (`written.shown`: the credential check, head and tail).
"""

import signal
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from io import BytesIO
from typing import BinaryIO
from zipfile import ZipFile, ZipInfo

from defusedxml import ElementTree

from .. import written
from .common import local, part

# Bytes read of the file past which a document is flagged (design D5): the per-file
# read limit's stop of decision 329
LARGE = 1 << 20
# Seconds a rendering may take before it is given up, its metadata kept (review S4);
# under the extraction's limit of 60 s, which fails the whole extraction
DEADLINE = 30.0
CONTENT_TYPES = "[Content_Types].xml"
# Media types whose parts are never read, whatever their subtype (Office writes SVG
# pictures as image/svg+xml)
MEDIA = ("image/", "audio/", "video/", "model/")
# Core properties that are the author's own text, shown at the text's head (review S6):
# with a text, the property lines leave the record
AUTHORED = ("core.subject", "core.keywords", "core.description", "core.category")
# mammoth's default style map has no entry for the style Title
STYLE_MAP = "p[style-name='Title'] => h1:fresh"


def is_xml(content_type: str) -> bool:
    """Whether a part of this content type is XML that is not a picture or other media."""
    t = content_type.split(";")[0].strip().lower()
    if t.startswith(MEDIA):
        return False
    return t in ("application/xml", "text/xml") or t.endswith("+xml")


def content_types(z: ZipFile) -> Callable[[str], str]:
    """A part's content type by its member name, as OPC looks it up: its Override first,
    then the Default of its extension, both case-insensitive; "" when neither."""
    overrides, defaults = {}, {}
    for e in part(z, CONTENT_TYPES):
        if local(e.tag) == "Override":
            overrides[e.get("PartName", "").lstrip("/").lower()] = e.get(
                "ContentType", ""
            )
        elif local(e.tag) == "Default":
            defaults[e.get("Extension", "").lower()] = e.get("ContentType", "")

    def typed(name: str) -> str:
        if name.lower() in overrides:
            return overrides[name.lower()]
        last = name.rsplit("/", 1)[-1]
        return defaults.get(last.rpartition(".")[2].lower(), "") if "." in last else ""

    return typed


class Unrendered(ValueError):
    """A package the converters are not given."""


def no_dtd(name: str, data: bytes) -> None:
    """Raise Unrendered when the XML part declares a DTD: OOXML never needs one, and the
    converters do not parse with defusedxml (design D2, review S1)."""
    try:
        for _ in ElementTree.iterparse(BytesIO(data), ("start",), forbid_dtd=True):
            break  # past the first start tag, no DOCTYPE can follow
    except ElementTree.DTDForbidden as error:
        raise Unrendered(f"{name}: a DOCTYPE") from error


def xml_parts(z: ZipFile) -> set[str]:
    """The member names of the package's XML parts, by the ZIP's directory and the
    content types alone, before any of them is read."""
    typed = content_types(z)
    return {
        info.filename
        for info in z.infolist()
        if info.filename == CONTENT_TYPES or is_xml(typed(info.filename))
    }


def proxy(z: ZipFile, kept: set[str]) -> BytesIO:
    """The package with the parts kept (xml_parts) as they are and every other part
    empty, uncompressed."""
    out = BytesIO()
    with ZipFile(out, "w") as w:
        for info in z.infolist():
            data = b""
            if info.filename in kept:
                data = z.read(info)
                no_dtd(info.filename, data)
            w.writestr(ZipInfo(info.filename, info.date_time), data)
    out.seek(0)
    return out


@contextmanager
def deadline(seconds: float) -> Iterator[None]:
    """TimeoutError in the block after seconds; only in the main thread, where signals
    arrive (the extraction worker's, and a test's)."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def expired(signum, frame):
        raise TimeoutError(f"rendering took more than {seconds:g} s")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def word(doc: BinaryIO) -> str:
    """A Word document's text: mammoth to HTML, pictures left out, markdownify to Markdown."""
    import mammoth
    from markdownify import MarkdownConverter

    class Markdown(MarkdownConverter):
        def convert_a(self, el, text, parent_tags):
            # A link within the document (a footnote's number and its way back) as its text
            if (el.get("href") or "").startswith("#"):
                return "" if text.strip() == "↑" else text
            return super().convert_a(el, text, parent_tags)

    html = mammoth.convert_to_html(
        doc,
        style_map=STYLE_MAP,
        convert_image=lambda image: [],
        external_file_access=False,
    ).value
    return Markdown(
        heading_style="ATX",
        escape_underscores=False,
        escape_asterisks=False,
        table_infer_header=True,
    ).convert(html)


def _runs(paragraph) -> str:
    out = []
    for run in paragraph.runs:
        text = run.text
        if text.strip() and run.font.bold:
            text = f"**{text}**"
        elif text.strip() and run.font.italic:
            text = f"*{text}*"
        out.append(text)
    return "".join(out).strip()


def _table(table) -> list[str]:
    rows = [
        [" ".join(c.text.split()).replace("|", "\\|") for c in row.cells]
        for row in table.rows
    ]
    if not rows:
        return []
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * len(rows[0])]
    return lines + ["| " + " | ".join(r) + " |" for r in rows[1:]]


def _shapes(shapes) -> Iterator:
    from pptx.shapes.group import GroupShape

    for shape in shapes:
        if isinstance(shape, GroupShape):
            yield from _shapes(shape.shapes)
        else:
            yield shape


def slides(doc: BinaryIO) -> str:
    """A deck's text: per slide its title as a heading (`---` for a slide without one),
    its text shapes' paragraphs as lines, its tables, then its speaker notes."""
    from pptx import Presentation

    out = []
    for slide in Presentation(doc).slides:
        title = slide.shapes.title
        heading = " ".join(title.text_frame.text.split()) if title is not None else ""
        out.append(f"# {heading}" if heading else "---")
        for shape in _shapes(slide.shapes):
            if title is not None and shape.shape_id == title.shape_id:
                continue
            if shape.has_text_frame:
                out += [line for p in shape.text_frame.paragraphs if (line := _runs(p))]
            elif getattr(shape, "has_table", False):
                out += _table(shape.table)
        if slide.has_notes_slide:
            frame = slide.notes_slide.notes_text_frame
            notes = frame.text.strip() if frame is not None else ""
            if notes:
                out += ["### Notes:", notes]
        out.append("")
    return "\n".join(out)


def rendered(
    z: ZipFile, f: BinaryIO, render: Callable[[BinaryIO], str], original: dict
) -> tuple[str | None, dict]:
    """The text for values["text"] (None: none) and the entries for mapped_metadata: the
    bytes read of the file and the XML parts' size (design D5), lines left out as may
    holding a credential, why the text was not rendered. The sizes are set before a
    failure of the copy can stop it (a DTD, a broken part, memory), so it carries them."""
    mapped = {}
    try:
        with deadline(DEADLINE):
            kept = xml_parts(z)
            mapped["xml bytes"] = sum(z.getinfo(name).file_size for name in kept)
            try:
                doc = proxy(z, kept)
            finally:
                read = f.raw.read_so_far
                mapped["bytes read"] = read
                mapped["large document text"] = read > LARGE
            body = render(doc).strip()
    except Exception as error:  # noqa: BLE001 - any converter's failure keeps the metadata (D6)
        mapped["text not rendered"] = f"{type(error).__name__}: {error}"
        return None, mapped
    head = [
        f"{k}: {original[k]}"
        for k in AUTHORED
        if isinstance(original.get(k), str) and original[k].strip()
    ]
    text = "\n".join(head + [""] + [body]).strip()
    if not text:
        return None, mapped
    data = text.encode("utf-8")
    shown = written.shown(data, "utf-8", len(data))
    if shown.credentials:
        mapped["credentials_left_out"] = shown.credentials
    return shown.text, mapped
