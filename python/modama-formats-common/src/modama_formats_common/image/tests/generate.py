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


def text_named_tif(target: Path) -> None:
    """A text file named like a TIFF."""
    target.mkdir(parents=True)
    (target / "notes.tif").write_text("hello\n")
