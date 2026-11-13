"""TIFF files through tifffile: every tag of the first page, the vendor blocks tifffile parses in them (spec formats/image)."""

import re

from modama_crawler.formats import Extracted

from .flat import entries, headline, opened, phrase

# The one skip list of TIFF files (spec formats/image, "What a TIFF's values
# leave out"; @weber 2026-11-12: "a negative 'skip these' list"):
# 1. where the image data is, not what it holds: one offset and one byte
#    count per strip or tile, ImageJ's byte counts of its IJMetadata entries
LAYOUT = frozenset(
    {
        "StripOffsets",
        "StripByteCounts",
        "TileOffsets",
        "TileByteCounts",
        "IJMetadataByteCounts",
    }
)
# 2. user-interface settings: the fields FEI's software offers and shows in
#    the data bar it draws below the image (DatabarHeight stays: the bar is in
#    the image's rows)
SETTINGS = frozenset(
    f"{block}.PrivateFei.{name}"
    for block in ("FEI_HELIOS", "FEI_SFEG")
    for name in ("DataBarAvailable", "DataBarSelected")
)
# 3. a tag value of more than this, of the tags tifffile reads on demand, is
#    not read (proposal, lean 3): it could not pass values.textual. tifffile
#    reads some tags whatever their size when it opens the page
#    (ImageDescription, Software, IJMetadata, the offsets: TIFF.TAG_LOAD)
MAX_TAG_BYTES = 1 << 20
# 4. lines of ImageJ's Info that are not `key = value` (info): counted only
# 5. a value not suitable for text: values.textual, in flat.entries

IMAGEJ_SOURCES = frozenset({270, 50839})  # ImageDescription, IJMetadata
# A line of ImageJ's Info, as written by ImageJ for the tags of a DM file or
# Bio-Formats' original metadata: `root.ImageList.1.Name = h1` (the first " = ")
INFO_LINE = re.compile(r"(.+?) = (.*)")


def skipped(name: str, value) -> bool:
    """Whether a flat name is on the skip list's first two parts."""
    return name in LAYOUT or name in SETTINGS


def info(text: str) -> tuple[dict, int] | None:
    """ImageJ's Info as `key -> value` from its `key = value` lines, and the number of
    lines that are not; None if no line is (spec formats/image, ImageJ's Info).

    tifffile gives Info as one text; ImageJ writes there whatever the image
    brought (a DM file's tags, 18,996 characters in the fixture imagej), more
    than values.textual lets through as one value. Our own small parser: no
    reader splits it.
    """
    lines = text.splitlines()
    found = [m for line in lines if (m := INFO_LINE.fullmatch(line))]
    if not found:
        return None
    return {m[1]: m[2] for m in found}, len(lines) - len(found)


# Hitachi's header, the .txt sidecar's block, in a TIFF's description (spec
# formats/image, "Hitachi's header in a TIFF's description"; change em-hitachi)
HITACHI = "[SemImageFile]"
HITACHI_TAGS = frozenset({270, 65500})  # ImageDescription, Hitachi's private tag
# An item of Hitachi's tag 65500: "@<group>"<key>=<value>, the value up to the
# next item or line end (one item is glued to the one before it in real files)
HITACHI_ITEM = re.compile(r'"@([^"]+)"([^="\r\n]+)=([^"\r\n]*)')


def sections(text: str) -> dict[str, dict[str, str]]:
    """An INI-like header as {section: {key: value}}: each line split at its first `=`,
    keys and values as written, a key met twice keeping its last value.

    Our own few lines: configparser strips values and refuses a whole header for
    one indented line (change em-hitachi, design D2).
    """
    found: dict[str, dict[str, str]] = {}
    section = found.setdefault("", {})
    for line in text.splitlines():
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = found.setdefault(line[1:-1], {})
            continue
        key, _, value = line.partition("=")
        section[key] = value
    return {name: keys for name, keys in found.items() if keys}


def tag_items(text: str) -> dict[str, dict[str, str]] | None:
    """Hitachi's tag 65500 as {"@group": {key: value}}, a key met twice keeping its last value; None if no item."""
    found: dict[str, dict[str, str]] = {}
    for group, key, value in HITACHI_ITEM.findall(text):
        found.setdefault(f"@{group}", {})[key] = value
    return found or None


def hitachi(page) -> list[tuple[str, object]] | None:
    """Hitachi's header and tag 65500 as entries, if the description is Hitachi's."""
    description = page.tags.get(270)
    if description is None or not str(description.value).startswith(HITACHI):
        return None
    found: list[tuple[str, object]] = list(sections(description.value).items())
    private = page.tags.get(65500)
    if private is not None:
        parsed = tag_items(str(private.value))
        found.append(("65500", parsed if parsed is not None else private.value))
    return found


def fei(path: str) -> tuple[str, ...]:
    """A name in FEI's metadata block, under either of its tags."""
    return (f"FEI_HELIOS.{path}", f"FEI_SFEG.{path}")


# The summary line (spec formats/image, "The summary line of an image file"):
# the one positive list. FEI's numbers come without units
HEADLINE = (
    ("Make",),
    ("Model",),
    fei("System.SystemType"),
    fei("Detectors.Name"),
    fei("Detectors.Mode"),
    fei("Beam.HV"),
    ("CZ_SEM.sv_serial_number",),
    ("CZ_SEM.dp_detector_channel",),
    ("CZ_SEM.ap_actualkv",),
    ("CZ_SEM.ap_mag",),
    ("CZ_SEM.ap_pixel_size",),
    ("SemImageFile.Instrument name",),
    ("SemImageFile.Signal name",),
    ("SemImageFile.Operation mode",),
    ("SemImageFile.Accelerating voltage",),
    ("SemImageFile.Magnification",),
    ("SemImageFile.PixelSize",),
    ("SemImageFile.SampleName",),
    ("ImageWidth",),
    ("ImageLength",),
    ("BitsPerSample",),
    ("Software",),
    ("DateTime",),
    fei("User.Date"),
    fei("User.Time"),
    ("CZ_SEM.ap_date",),
    ("CZ_SEM.ap_time",),
    ("SemImageFile.Date",),
    ("SemImageFile.Time",),
)
UNIT_UNKNOWN = frozenset(
    (*fei("Beam.HV"), "SemImageFile.Accelerating voltage", "SemImageFile.PixelSize")
)
# A number as Hitachi's header writes one, as text (spec formats/image, "A
# number written as text in a Hitachi summary phrase")
NUMBER = re.compile(r"[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?")


def say(name: str, value) -> str | None:
    """A summary phrase; a Zeiss entry [label, value, unit] as `label value unit`, or its value if that is text;
    a Hitachi number written as text after its key."""
    if name.startswith("SemImageFile.") and NUMBER.fullmatch(value):
        if float(value) == 0:
            return None
        text = f"{name.partition('.')[2]} {value}"
        return f"{text} (unit unknown)" if name in UNIT_UNKNOWN else text
    if name.startswith("CZ_SEM.") and isinstance(value, list) and len(value) >= 2:
        label, number, *unit = value
        if isinstance(number, str):
            return number or None
        if number == 0:
            return None
        return " ".join(str(v) for v in (label, number, *unit))
    return phrase(name, value, name in UNIT_UNKNOWN)


def extract(path: str) -> Extracted:
    """The first page's tags but the skip list, its shape, data type and axes."""
    import tifffile  # imports NumPy: in the worker only

    # LSM, ScanImage and NDPI files make TiffFile read every page on open; the
    # first page's tags are all this reads (proposal, lean 2)
    with (
        opened(path) as f,
        tifffile.TiffFile(f, is_lsm=False, is_scanimage=False, is_ndpi=False) as tif,
    ):
        page = tif.pages.first
        # ImageJ's description and IJMetadata as tifffile parses them, from the first page
        imagej = tif.imagej_metadata if page.is_imagej else None
        # Hitachi's header and tag 65500 as entries, in place of the two texts
        vendor = hitachi(page)
        items = [
            (tag.name, tag.value)
            for tag in page.tags
            if tag.valuebytecount <= MAX_TAG_BYTES
            and not (imagej is not None and tag.code in IMAGEJ_SOURCES)
            and not (vendor is not None and tag.code in HITACHI_TAGS)
        ]
        items.extend(vendor or ())
        mapped = {
            "first_page_shape": list(page.shape),
            "dtype": None if page.dtype is None else str(page.dtype),
            "axes": page.axes,
        }
        if imagej is not None:
            if isinstance(imagej.get("Info"), str) and (lines := info(imagej["Info"])):
                imagej = {**imagej, "Info": lines[0]}
                if lines[1]:
                    mapped["imagej_info_lines_left_out"] = lines[1]
            items.append(("imagej_metadata", imagej))
    original = dict(entries(items, skipped))
    return Extracted(
        summary=headline(original, HEADLINE, say),
        subjects=[],
        values={"original_metadata": original, "mapped_metadata": mapped},
    )
