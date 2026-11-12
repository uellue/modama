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
    ("ImageWidth",),
    ("ImageLength",),
    ("BitsPerSample",),
    ("Software",),
    ("DateTime",),
    fei("User.Date"),
    fei("User.Time"),
    ("CZ_SEM.ap_date",),
    ("CZ_SEM.ap_time",),
)
UNIT_UNKNOWN = frozenset(fei("Beam.HV"))


def say(name: str, value) -> str | None:
    """A summary phrase; a Zeiss entry [label, value, unit] as `label value unit`, or its value if that is text."""
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
        items = [
            (tag.name, tag.value)
            for tag in page.tags
            if tag.valuebytecount <= MAX_TAG_BYTES
            and not (imagej is not None and tag.code in IMAGEJ_SOURCES)
        ]
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
