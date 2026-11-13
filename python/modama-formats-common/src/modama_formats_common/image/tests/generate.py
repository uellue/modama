"""Fixture generators: image files written at test time by the established writers, tifffile and Pillow.

Fixed contents and times, so that the recorded results do not change between runs.
"""

from pathlib import Path

# A tag that no reader names: an entry nobody has seen before (TEMPLATE, checklist)
UNSEEN_TIFF_TAG = 65500
UNSEEN_EXIF_TAG = 0xC6FF


def pattern(height: int, width: int, dtype="uint8"):
    import numpy as np

    return (np.arange(height * width) % 251).astype(dtype).reshape(height, width)


def tifffile_tiff(target: Path) -> None:
    """A three-page stack as tifffile writes it from Python: its shape in the description, a private tag."""
    import numpy as np
    import tifffile

    target.mkdir(parents=True)
    data = np.stack([pattern(48, 64, "uint16")] * 3)
    tifffile.imwrite(
        target / "stack.tif",
        data,
        datetime="2026:11:12 18:00:00",
        photometric="minisblack",
        resolution=(10, 10),
        extratags=[(UNSEEN_TIFF_TAG, "s", 0, "new value", True)],
    )


def png_text(target: Path) -> None:
    """A PNG with text chunks: plain, compressed, international and empty ones, and a resolution."""
    from PIL import Image, PngImagePlugin

    target.mkdir(parents=True)
    chunks = PngImagePlugin.PngInfo()
    chunks.add_text("Title", "A test pattern")
    chunks.add_text("Software", "Pillow")
    chunks.add_text("Comment", "")
    chunks.add_text("Description", "Written for the crawler's tests", zip=True)
    chunks.add_itxt("Author", "Jülich", lang="de", tkey="Autor")
    Image.fromarray(pattern(48, 64)).save(
        target / "pattern.png", pnginfo=chunks, dpi=(300, 300)
    )


def jpeg_exif(target: Path) -> None:
    """A JPEG with a comment and EXIF in IFD0, the Exif IFD and the GPS IFD, and a tag no reader names."""
    from PIL import ExifTags, Image
    from PIL.TiffImagePlugin import IFDRational as Fraction

    target.mkdir(parents=True)
    exif = Image.Exif()
    exif[0x010F] = "ER-C"  # Make
    exif[0x0110] = "Test Camera 1"  # Model
    exif[0x0131] = "Pillow"  # Software
    exif[0x0132] = "2026:11:12 18:00:00"  # DateTime
    exif[UNSEEN_EXIF_TAG] = "new value"
    exif.get_ifd(ExifTags.IFD.Exif).update(
        {0x9003: "2026:11:12 17:59:58", 0x829A: Fraction(1, 250)}
    )  # DateTimeOriginal, ExposureTime
    exif.get_ifd(ExifTags.IFD.GPSInfo).update(
        {1: "N", 2: (Fraction(50), Fraction(54), Fraction(36, 10))}
    )  # GPSLatitudeRef, GPSLatitude
    Image.fromarray(pattern(48, 64)).convert("RGB").save(
        target / "photo.jpg", exif=exif, comment=b"made for a test"
    )


def bmp(target: Path) -> None:
    """A BMP as Pillow writes it."""
    from PIL import Image

    target.mkdir(parents=True)
    Image.fromarray(pattern(48, 64)).convert("RGB").save(target / "pattern.bmp")


def gif_comment(target: Path) -> None:
    """A GIF with a comment."""
    from PIL import Image

    target.mkdir(parents=True)
    Image.fromarray(pattern(48, 64)).convert("P").save(
        target / "pattern.gif", comment=b"made for a test"
    )


def webp_exif(target: Path) -> None:
    """A WEBP with EXIF."""
    from PIL import Image

    target.mkdir(parents=True)
    exif = Image.Exif()
    exif[0x010F] = "ER-C"  # Make
    exif[0x0110] = "Test Camera 1"  # Model
    Image.fromarray(pattern(48, 64)).convert("RGB").save(
        target / "pattern.webp", exif=exif
    )


def eps(target: Path) -> None:
    """An EPS as Pillow writes it."""
    from PIL import Image

    target.mkdir(parents=True)
    Image.fromarray(pattern(48, 64)).convert("RGB").save(target / "figure.eps")


# A Hitachi electron microscope's header (change em-hitachi, design D1): the
# keys of a real S/TEM's header in their order, every value made up; the
# instrument writes `InstrumentName` in the .txt and `Instrument name` in the
# TIFF's description
HITACHI_HEADER = (
    ("Instrument name", "HF3300"),
    ("Date", "2024/01/15"),
    ("Time", "09:30:00"),
    ("Image comment", "Test pattern"),
    ("Keyword1", "300 kV"),
    ("Keyword2", "500"),
    ("SampleName", "Au on C"),
    ("Magnification", "50000"),
    ("Operation mode", "Analysis"),
    ("Sub mode", "Normal"),
    ("Signal name", "HAADF"),
    ("STEM camera length", "40"),
    ("Accelerating voltage", "300000"),
    ("Emission", "10"),
    ("File name", None),  # the TIFF's name
    ("Image number", "0007"),
    ("Data size", "64x64"),
    ("Screen mode", "320"),
    ("Data display combine", "off"),
    ("Add embed of property", "off"),
    ("Scan speed", "Fast"),
    ("Capture speed", "10s"),
    ("StagePositionX", "100"),
    ("StagePositionY", "-20"),
    ("StagePositionZ", "5"),
    ("StagePositionT", "1.5"),
    ("StagePositionA", "0"),
    ("Stage position R", "0"),
    ("Stage type", "2"),
    ("Raster rotation angle", "0.0"),
    ("Calibration", "1.0"),
    ("Calibration factor X", "1"),
    ("Calibration factor Y", "1"),
    ("PixelSize", "0.5"),
    ("Brightness", "1000"),
    ("Contrast", "2000"),
    ("TEM condenser aperture", "1"),
    ("STEM condenser aperture", "2"),
    ("OBJ aperture", "0"),
    ("SA aperture", "0"),
)
# Tag 65500 as the instrument writes it: `"@<group>"<key>=<value>` items
# separated by \r, the last ones repeated once, the first repeat glued to the
# item before it; values made up
HITACHI_TAG_65500 = (
    '"@Fld"FldImgPropReserveDbl1=-1\r"@Fld"FldImgPropReserveDbl2=2\r'
    '"@Fld"FldImgPropModeID=7\r"@Fld"FldImgPropSubmodeID=3\r'
    '"@Confidential"ScanTimeX=0.02\r"@Confidential"ScanTimeY=12.5\r'
    '"@Confidential"Stage tilt axis=Y"@Confidential"ScanTimeX=0.02\r'
    '"@Confidential"ScanTimeY=12.5\r"@Confidential"Stage tilt axis=Y'
)
# Tag 65501: 15,156 hexadecimal characters, as in the real file; what they hold is unknown
HITACHI_TAG_65501 = ("0123456789ABCDEF" * 948)[:15156]


def hitachi_lines(tif_name: str, instrument_key: str = "Instrument name", **changed):
    """The header's lines, `[SemImageFile]` first, with values changed or added by key."""
    header = dict(HITACHI_HEADER)
    header["File name"] = tif_name
    header.update(changed)
    lines = ["[SemImageFile]"]
    for key, value in header.items():
        key = instrument_key if key == "Instrument name" else key
        lines.append(key if value is None else f"{key}={value}")
    return lines


def hitachi_tif(
    path: Path, description: str | None = None, tag_65500: str = HITACHI_TAG_65500
) -> None:
    """A TIFF as a Hitachi microscope writes it: 64 x 96 pixels (a 64 x 64 image and 32 rows more),
    the header in its description with \\r line ends, the private tags 65500 and 65501."""
    import tifffile

    if description is None:
        description = "\r".join(hitachi_lines(path.name))
    tifffile.imwrite(
        path,
        pattern(96, 64),
        description=description,
        metadata=None,
        software=False,  # the instrument writes none
        photometric="minisblack",
        resolution=(96, 96),
        resolutionunit="INCH",
        extratags=[
            (65500, "s", 0, tag_65500, True),
            (65501, "s", 0, HITACHI_TAG_65501, True),
        ],
    )


def lone_hitachi_tif(target: Path) -> None:
    """A Hitachi TIFF without its .txt header."""
    target.mkdir(parents=True)
    hitachi_tif(target / "grid2_x50.0k_HAADF_0007.tif")


def text_named_tif(target: Path) -> None:
    """A text file named like a TIFF."""
    target.mkdir(parents=True)
    (target / "notes.tif").write_text("hello\n")
