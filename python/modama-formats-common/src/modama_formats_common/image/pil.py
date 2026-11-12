"""PNG, JPEG, BMP, GIF and WEBP files through Pillow: what Image.open reads before the image data (spec formats/image)."""

from modama_crawler.formats import Extracted

from .flat import entries, headline, opened

# EXIF's pointers to its sub-IFDs (ExifOffset, GPSInfo, ExifInteroperabilityOffset):
# offsets in the file, replaced by the IFDs they point to (spec formats/image,
# "What Pillow's formats' values leave out")
POINTERS = frozenset({0x8769, 0x8825, 0xA005})
# Keys whose bytes the formats define as text (a JPEG's COM segment, a GIF's
# comment extension): as text where they are valid UTF-8
TEXT = frozenset({"comment"})

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


def exif_tags(data: bytes) -> dict:
    """An EXIF block parsed by Pillow: IFD0's tags by name, its Exif, GPS and Interop IFDs under their names.

    Pillow's Image.getexif() would decode a PNG's pixels when its eXIf chunk
    is not before the image data (proposal, lean 6); Image.Exif.load parses
    the block that open found. IFD1, the thumbnail's, is not read.
    """
    from PIL import ExifTags, Image

    exif = Image.Exif()
    exif.load(data)

    def named(ifd, names) -> dict:
        return {names.get(k, str(k)): v for k, v in ifd.items() if k not in POINTERS}

    tree = named(exif, ExifTags.TAGS)
    for ifd, names in (
        (ExifTags.IFD.Exif, ExifTags.TAGS),
        (ExifTags.IFD.GPSInfo, ExifTags.GPSTAGS),
        (ExifTags.IFD.Interop, ExifTags.TAGS),
    ):
        if sub := exif.get_ifd(ifd):
            tree[ifd.name] = named(sub, names)
    return tree


def as_text(value):
    """Bytes as UTF-8 text where they are valid UTF-8, else as they are (left out as binary)."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value
    return value


def extract(path: str, plugin: str) -> Extracted:
    """Pillow's info but the skip list, the EXIF block parsed, width, height and mode; no pixel is decoded."""
    from PIL import Image

    # Only the format's own plugin: open reads the header and stops before the
    # image data; load(), which decodes it, is never called
    with opened(path) as f, Image.open(f, formats=[plugin]) as im:
        info = dict(im.info)
        mapped = {"width": im.width, "height": im.height, "mode": im.mode}
    block = info.pop("exif", None)
    items = [(k, as_text(v) if k in TEXT else v) for k, v in info.items()]
    if isinstance(block, bytes):
        items.append(("exif", exif_tags(block)))
    original = dict(entries(items))
    return Extracted(
        summary=headline({**original, **mapped}, HEADLINE),
        subjects=[],
        values={"original_metadata": original, "mapped_metadata": mapped},
    )
