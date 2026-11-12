"""PNG, JPEG, BMP, GIF and WEBP files through Pillow: what Image.open reads before the image data (spec formats/image)."""

from contextlib import contextmanager

from modama_crawler.formats import Extracted

from .flat import entries, headline, opened, plain

# The one skip list of Pillow's formats (`skipped`; spec formats/image, "What
# Pillow's formats' values leave out"):
# 1. EXIF's pointers to its sub-IFDs (ExifOffset, GPSInfo, ExifInteroperabilityOffset):
#    offsets in the file, where the IFDs they point to are kept
POINTERS = frozenset(
    {"exif.ExifOffset", "exif.GPSInfo", "exif.Exif.ExifInteroperabilityOffset"}
)
# 2. IFD1, the thumbnail's: not read (exif_tags)
# 3. after Pillow refused an oversize compressed text chunk, every empty text
#    (extract): Pillow keeps that chunk's keyword with an empty text
# 4. a value not suitable for text (values.textual, in flat.entries); the
#    EXIF block's bytes are kept parsed instead (exif_tags)

# Keys whose bytes the formats define as text (a JPEG's COM segment, a GIF's
# comment extension): as text where they are valid UTF-8
TEXT = frozenset({"comment"})
# Pillow's conversion, not the file's entry: a resolution in dots per inch
# from a PNG's pHYs (pixels per metre), a BMP's header or JFIF (mapped_metadata)
CONVERTED = frozenset({"dpi"})

# The summary line (spec formats/image, "The summary line of an image file")
HEADLINE = (
    ("exif.Make",),
    ("exif.Model",),
    ("Title",),
    ("width",),
    ("height",),
    ("Software", "exif.Software"),
    ("exif.Exif.DateTimeOriginal", "exif.DateTime", "Creation Time"),
)


def skipped(name: str, value) -> bool:
    """Whether a flat name is on the skip list's first part: a pointer as an offset, not as its IFD."""
    return name in POINTERS and not isinstance(value, dict)


def as_text(value):
    """Bytes as UTF-8 text where they are valid UTF-8, else as they are (left out as binary)."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value
    return value


def exif_tags(data: bytes) -> dict:
    """An EXIF block parsed by Pillow: IFD0's tags by name, its Exif, GPS and Interop IFDs under their names.

    Pillow's Image.getexif() would decode a PNG's pixels when its eXIf chunk
    is not before the image data (proposal, lean 6); Image.Exif.load parses
    the block that open found. IFD1, the thumbnail's, is not read. A field of
    EXIF's type UNDEFINED, which Pillow gives as bytes, as text where it is
    UTF-8 (`ExifVersion` 0220); binary ones are then left out by textual.
    """
    from PIL import ExifTags, Image

    exif = Image.Exif()
    exif.load(data)

    def named(ifd, names) -> dict:
        return {names.get(k, str(k)): as_text(v) for k, v in ifd.items()}

    tree = named(exif, ExifTags.TAGS)
    for ifd, names in (
        (ExifTags.IFD.Exif, ExifTags.TAGS),
        (ExifTags.IFD.GPSInfo, ExifTags.GPSTAGS),
        (ExifTags.IFD.Interop, ExifTags.TAGS),
    ):
        if sub := exif.get_ifd(ifd):
            tree[ifd.name] = named(sub, names)
    return tree


@contextmanager
def lenient(truncated: bool):
    """Pillow's settings for reading headers: no decompression-bomb check, optionally lenient text chunks.

    The check guards decoding, which never happens here (`load()` is not
    called); with it, a header of more than 179 Mpixel fails the extraction.
    Pillow's settings are global: restored afterwards.
    """
    from PIL import Image, ImageFile

    saved = Image.MAX_IMAGE_PIXELS, ImageFile.LOAD_TRUNCATED_IMAGES
    Image.MAX_IMAGE_PIXELS = None
    ImageFile.LOAD_TRUNCATED_IMAGES = truncated
    try:
        yield
    finally:
        Image.MAX_IMAGE_PIXELS, ImageFile.LOAD_TRUNCATED_IMAGES = saved


def header(path: str, plugin: str, truncated: bool) -> tuple[dict, dict]:
    """Pillow's info and the image's width, height and mode, from the header."""
    from PIL import Image

    # Only the format's own plugin: open reads the header and stops before the
    # image data; load(), which decodes it, is never called
    with lenient(truncated), opened(path) as f, Image.open(f, formats=[plugin]) as im:
        return dict(im.info), {"width": im.width, "height": im.height, "mode": im.mode}


def extract(path: str, plugin: str) -> Extracted:
    """Pillow's info but the skip list, the EXIF block parsed, width, height and mode; no pixel is decoded."""
    said = []
    try:
        info, mapped = header(path, plugin, truncated=False)
    except ValueError as error:
        # A compressed text chunk that decompresses to more than Pillow's
        # MAX_TEXT_CHUNK (1 MiB): read again with Pillow's leniency, which
        # keeps that chunk's keyword with an empty text; the others stay
        if "MAX_TEXT_CHUNK" not in str(error):
            raise
        said.append(str(error))
        info, mapped = header(path, plugin, truncated=True)
        info = {k: v for k, v in info.items() if v != ""}
    mapped |= {k: plain(info.pop(k)) for k in CONVERTED if k in info}
    block = info.pop("exif", None)
    items = [(k, as_text(v) if k in TEXT else v) for k, v in info.items()]
    if isinstance(block, bytes):
        items.append(("exif", exif_tags(block)))
    original = dict(entries(items, skipped))
    values = {"original_metadata": original, "mapped_metadata": mapped}
    summary = headline({**original, **mapped}, HEADLINE)
    if said:
        # As modama_formats_em.blockfile: the reader's warnings into the record
        summary += [f"reader warning: {text}" for text in said]
        values["reader_warnings"] = said
    return Extracted(summary=summary, subjects=[], values=values)
