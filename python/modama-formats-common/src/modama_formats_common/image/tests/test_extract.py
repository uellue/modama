"""Common image files: recognition and extraction (spec formats/image), one test per scenario.

Run with -s to see the bytes each extraction of a large file read.
"""

import time
from pathlib import Path
from xml.etree.ElementTree import ParseError

import numpy as np
import pytest
import tifffile
from modama_crawler import extraction
from modama_crawler.testing import recognise
from modama_crawler.walk import walk
from PIL import Image

from modama_formats_common import image
from modama_formats_common.image import tiff
from modama_formats_common.image.tests import generate

FORMATS = {f.id: f for f in image.COLLECTION.formats}


@pytest.fixture(autouse=True)
def mime_types(collection_tests):
    """This part's MIME database, for the tests on files of their own too."""


def rchar() -> int:
    """Bytes this process has read so far, from /proc/self/io (Linux)."""
    for line in Path("/proc/self/io").read_text().splitlines():
        key, _, value = line.partition(":")
        if key == "rchar":
            return int(value)
    raise RuntimeError("no rchar in /proc/self/io")


def extracted(ct, fixture: str, tmp_path: Path):
    """The extraction of a fixture's one dataset, run in this process."""
    tree = ct.materialise(fixture, tmp_path)
    (d,) = walk(tree, ct.collection.formats).datasets
    return FORMATS[d.format].extract(d, str(tree))


def original(ct, fixture: str, tmp_path: Path) -> dict:
    """The original_metadata of a fixture's one dataset."""
    return extracted(ct, fixture, tmp_path).values["original_metadata"]


def of_file(path: Path):
    """The extraction of one file by the format of its type, as a single-file dataset."""
    (d,) = [
        d
        for d in walk(path.parent, image.COLLECTION.formats).datasets
        if d.anchor == f"/{path.name}"
    ]
    return FORMATS[d.format].extract(d, str(path.parent))


def read_by(path: Path) -> tuple[object, int]:
    """The extraction of a file and the bytes it read (the second of two runs: imports are read in the first)."""
    of_file(path)
    before = rchar()
    result = of_file(path)
    return result, rchar() - before


# Image files are datasets of their format


def test_an_sem_image_from_an_fei_instrument(collection_tests, tmp_path):
    (d,) = recognise(collection_tests, "fei_sem", tmp_path).datasets
    assert (d.type, d.format, d.basis, d.members) == (
        "image/tiff",
        "common/tiff",
        "single file",
        ("/FEI-Helios-Ebeam-8bits.tif",),
    )


@pytest.mark.parametrize(
    "fixture, form",
    [
        ("png_text", "common/png"),
        ("jpeg_exif", "common/jpeg"),
        ("bmp", "common/bmp"),
        ("gif_comment", "common/gif"),
        ("webp_exif", "common/webp"),
        ("matplotlib_svg", "common/svg"),
    ],
)
def test_an_image_of_each_other_kind(collection_tests, tmp_path, fixture, form):
    (d,) = recognise(collection_tests, fixture, tmp_path).datasets
    assert (d.format, d.basis) == (form, "single file")


def test_an_eps_file(collection_tests, tmp_path):
    (d,) = recognise(collection_tests, "eps", tmp_path).datasets
    assert (d.type, d.format) == ("image/x-eps", "")


def test_a_text_file_named_like_an_image(collection_tests, tmp_path):
    tree = collection_tests.materialise("text_named_tif", tmp_path)
    result = walk(tree, collection_tests.collection.formats)
    (d,) = result.datasets
    assert (d.type, d.format) == ("image/tiff", "common/tiff")
    with pytest.raises(tifffile.TiffFileError):
        FORMATS[d.format].extract(d, str(tree))
    # As a crawl runs it: a warning, the dataset stays
    extraction.extract(
        result, collection_tests.collection.formats, str(tree), identity="t", workers=1
    )
    (warning,) = result.all_warnings()
    assert "TiffFileError" in str(warning)


# TIFF metadata is every tag of the first page


def test_the_fei_metadata_of_an_sem_image(collection_tests, tmp_path):
    values = extracted(collection_tests, "fei_sem", tmp_path).values
    found = values["original_metadata"]
    assert found["FEI_HELIOS.Beam.HV"] == 5000
    assert found["FEI_HELIOS.System.SystemType"] == 'Helios NanoLab" 660'
    assert found["FEI_HELIOS.User.Date"] == "06/13/2016"
    assert found["FEI_HELIOS.EBeam.EmissionCurrent"] == ""
    assert found["ExifTag.ImageUniqueID"] == "CC3C07AED2A9E3AD28367BD8FCA4DDA"
    assert found["Compression"] == "NONE"
    assert found["XResolution"] == [64, 1]
    assert values["mapped_metadata"] == {
        "first_page_shape": [471, 512],
        "dtype": "uint8",
        "axes": "YX",
    }


def test_the_zeiss_metadata_of_an_sem_image(collection_tests, tmp_path):
    found = original(collection_tests, "zeiss_sem", tmp_path)
    assert found["CZ_SEM.ap_actualkv"] == ["EHT", 5.0, "kV"]
    assert found["CZ_SEM.dp_detector_channel"] == ["Signal A", "InLens"]


def test_an_image_saved_by_imagej(collection_tests, tmp_path):
    found = original(collection_tests, "imagej", tmp_path)
    assert found["imagej_metadata.ImageJ"] == "1.51a"
    assert found["imagej_metadata.unit"] == "micron"
    assert not [n for n in found if n.startswith(("ImageDescription", "IJMetadata"))]


def test_imagejs_info_line_by_line(collection_tests, tmp_path):
    # The fixture's Info: a DM file's 274 tags as `root.X = value` lines
    values = extracted(collection_tests, "imagej", tmp_path).values
    found = values["original_metadata"]
    assert found["imagej_metadata.Info.root.ApplicationBounds"] == "{0,0,701,1276}"
    assert len([n for n in found if n.startswith("imagej_metadata.Info.")]) == 274
    assert "imagej_metadata.Info" not in found
    assert "imagej_info_lines_left_out" not in values["mapped_metadata"]


def test_imagejs_info_with_lines_of_another_form(tmp_path):
    path = tmp_path / "info.tif"
    text = "Exposure = 0.5\nfree text\n[a section]\nGain = 2"
    tifffile.imwrite(path, generate.pattern(8, 8), imagej=True, metadata={"Info": text})
    values = of_file(path).values
    found = values["original_metadata"]
    assert found["imagej_metadata.Info.Exposure"] == "0.5"
    assert found["imagej_metadata.Info.Gain"] == "2"
    assert values["mapped_metadata"]["imagej_info_lines_left_out"] == 2


def test_a_tag_nobody_has_seen_before(collection_tests, tmp_path):
    found = original(collection_tests, "tifffile_tiff", tmp_path)
    assert found[str(generate.UNSEEN_TIFF_TAG)] == "new value"


# What a TIFF's values leave out


def test_layout_settings_and_arrays_are_left_out(collection_tests, tmp_path):
    fei = original(collection_tests, "fei_sem", tmp_path / "fei")
    zeiss = original(collection_tests, "zeiss_sem", tmp_path / "zeiss")
    for found in (fei, zeiss):
        assert not {"StripOffsets", "StripByteCounts", "ColorMap", "CZ_SEM."} & set(
            found
        )
    assert "FEI_HELIOS.PrivateFei.DataBarAvailable" not in fei
    assert "FEI_HELIOS.PrivateFei.DataBarSelected" not in fei
    assert fei["FEI_HELIOS.PrivateFei.DatabarHeight"] == 29


def test_a_large_tag_value_is_not_read(tmp_path):
    path = tmp_path / "large_tag.tif"
    tifffile.imwrite(
        path,
        generate.pattern(48, 64),
        extratags=[
            (65000, "B", tiff.MAX_TAG_BYTES + 1, bytes(tiff.MAX_TAG_BYTES + 1), True)
        ],
    )
    result, read = read_by(path)
    print(f"{path.name}: {read} bytes read of {path.stat().st_size}")
    assert "65000" not in result.values["original_metadata"]
    assert read < 256_000


# Pillow's formats' metadata is what Pillow reads before the image data


def test_the_exif_of_a_camera_jpeg(collection_tests, tmp_path):
    values = extracted(collection_tests, "camera_jpeg", tmp_path).values
    found = values["original_metadata"]
    assert found["exif.Make"] == "Canon"
    assert found["exif.Model"] == "Canon PowerShot S40"
    assert found["exif.Exif.DateTimeOriginal"] == "2003:12:14 12:01:44"
    assert found["exif.Exif.ExposureTime"] == 0.002
    assert found["exif.Interop.InteropIndex"] == "R98"
    assert found["jfif_version"] == [1, 1]
    assert found["jfif_density"] == [72, 72]
    assert values["mapped_metadata"] == {
        "width": 480,
        "height": 360,
        "mode": "RGB",
        "dpi": [72, 72],
    }


def test_exif_fields_of_type_undefined_as_text(collection_tests, tmp_path):
    found = original(collection_tests, "camera_jpeg", tmp_path)
    assert found["exif.Exif.ExifVersion"] == "0220"
    assert found["exif.Exif.FlashPixVersion"] == "0100"
    # b"\x01\x02\x03\x00": control characters as text, left out
    assert "exif.Exif.ComponentsConfiguration" not in found


def test_the_text_chunks_of_a_png_file(collection_tests, tmp_path):
    values = extracted(collection_tests, "png_text", tmp_path).values
    found = values["original_metadata"]
    assert found["Title"] == "A test pattern"
    assert found["Software"] == "Pillow"
    assert found["Comment"] == ""
    assert found["Description"] == "Written for the crawler's tests"  # zTXt
    assert found["Author"] == "Jülich"  # iTXt
    # Pillow's conversion of pHYs (pixels per metre), not an entry of the file
    assert "dpi" not in found
    assert values["mapped_metadata"]["dpi"] == [299.9994, 299.9994]


def png(path: Path, ihdr: tuple[int, int] | None = None, **chunks) -> Path:
    """A small PNG written by Pillow, its IHDR's size changed to ihdr (CRC fixed): a header as a large image has it."""
    import struct
    import zlib

    from PIL import PngImagePlugin

    info = PngImagePlugin.PngInfo()
    for key, (text, zip_) in chunks.items():
        info.add_text(key, text, zip=zip_)
    Image.fromarray(generate.pattern(8, 8)).save(path, pnginfo=info)
    if ihdr is not None:
        data = bytearray(path.read_bytes())
        header = struct.pack(">II", *ihdr) + bytes(data[24:29])
        data[16:29] = header
        data[29:33] = struct.pack(">I", zlib.crc32(b"IHDR" + header))
        path.write_bytes(bytes(data))
    return path


def test_a_header_of_more_than_pillows_pixel_limit(tmp_path):
    # 400 Mpixel: Pillow's decompression-bomb check would refuse the open
    path = png(tmp_path / "montage.png", ihdr=(20_000, 20_000), Title=("t", False))
    values = of_file(path).values
    assert values["mapped_metadata"]["width"] == 20_000
    assert values["original_metadata"]["Title"] == "t"
    assert Image.MAX_IMAGE_PIXELS is not None  # Pillow's setting restored


def test_an_oversize_compressed_text_chunk(tmp_path):
    path = png(
        tmp_path / "text.png",
        Title=("kept", False),
        Big=("x" * (2 << 20), True),  # 2 MiB as text, a few kB compressed
        Comment=("", False),
    )
    result = of_file(path)
    found = result.values["original_metadata"]
    assert found["Title"] == "kept"
    assert "Big" not in found and "Comment" not in found
    (warning,) = result.values["reader_warnings"]
    assert "MAX_TEXT_CHUNK" in warning
    assert result.summary[-1] == f"reader warning: {warning}"


def test_an_exif_tag_nobody_has_seen_before(collection_tests, tmp_path):
    found = original(collection_tests, "jpeg_exif", tmp_path)
    assert found[f"exif.{generate.UNSEEN_EXIF_TAG}"] == "new value"
    assert found["exif.GPSInfo.GPSLatitude"] == [50.0, 54.0, 3.6]
    assert found["comment"] == "made for a test"


def test_the_comment_of_a_gif_file(collection_tests, tmp_path):
    values = extracted(collection_tests, "gif_comment", tmp_path).values
    assert values["original_metadata"]["comment"] == "made for a test"
    assert {"width", "height", "mode"} == set(values["mapped_metadata"])


# What Pillow's formats' values leave out


def test_binary_exif_fields_are_left_out(collection_tests, tmp_path):
    found = original(collection_tests, "camera_jpeg", tmp_path)
    for name in (
        "exif",
        "exif.Exif.MakerNote",
        "exif.Exif.UserComment",
        "exif.ExifOffset",
        "exif.Exif.ExifInteroperabilityOffset",
    ):
        assert name not in found
    # IFD1, the thumbnail's: JpegIFOffset is its tag only
    assert not [n for n in found if "IFD1" in n or "JpegIF" in n]


# SVG metadata is the root's attributes and its descriptive elements


def test_an_svg_file_written_by_matplotlib(collection_tests, tmp_path):
    found = original(collection_tests, "matplotlib_svg", tmp_path)
    assert found["@width"] == "576pt"
    assert found["@height"] == "432pt"
    assert found["@viewBox"] == "0 0 576 432"
    assert found["metadata.rdf:RDF.cc:Work.dc:format"] == "image/svg+xml"
    assert "metadata.rdf:RDF.cc:Work.dc:type.@rdf:resource" in found
    assert not [v for v in found.values() if "汉字" in str(v)]


SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
     xmlns:lab="https://example.org/lab"
     width="210mm" height="297mm" viewBox="0 0 210 297" version="1.1"
     inkscape:version="1.2 (dc2aedaf03, 2022-05-15)" data-new="never seen">
  <title>A test drawing</title>
  <desc>Made for the crawler's tests</desc>
  <sodipodi:namedview id="namedview1" inkscape:zoom="0.5"/>
  <lab:sample>S-17</lab:sample>
  {padding}
  <rect width="10" height="10"><title>not the document's</title></rect>
</svg>
"""


def test_an_svg_files_title_description_and_an_attribute_nobody_has_seen(tmp_path):
    path = tmp_path / "drawing.svg"
    path.write_text(SVG.format(padding=""))
    result = of_file(path)
    found = result.values["original_metadata"]
    assert found["title"] == "A test drawing"
    assert found["desc"] == "Made for the crawler's tests"
    assert found["@inkscape:version"] == "1.2 (dc2aedaf03, 2022-05-15)"
    assert found["@data-new"] == "never seen"
    assert result.summary == ["A test drawing", "width 210mm", "height 297mm"]


def test_what_an_svg_files_values_leave_out(tmp_path):
    path = tmp_path / "drawing.svg"
    path.write_text(SVG.format(padding=""))
    found = of_file(path).values["original_metadata"]
    # An element of another namespace at the root is kept; Inkscape's
    # settings and the drawing are not
    assert found["lab:sample"] == "S-17"
    assert not [n for n in found if n.startswith(("sodipodi:", "rect"))]
    assert "not the document's" not in found.values()


# The summary line of an image file


def test_the_summary_line_of_an_fei_sem_image(collection_tests, tmp_path):
    summary = extracted(collection_tests, "fei_sem", tmp_path).summary
    assert ", ".join(summary) == (
        'Helios NanoLab" 660, ETD, SE, HV 5000 (unit unknown), ImageWidth 512, '
        "ImageLength 471, BitsPerSample 8, 06/13/2016, 05:06:40 PM"
    )


def test_the_summary_line_of_a_zeiss_sem_image(collection_tests, tmp_path):
    summary = extracted(collection_tests, "zeiss_sem", tmp_path).summary
    assert ", ".join(summary).startswith(
        "ULTRA 55-36-06, InLens, EHT 5.0 kV, 50.00 K X, Pixel Size 5.825 nm, "
        "ImageWidth 512, ImageLength 384"
    )


def test_the_summary_line_of_a_camera_jpeg(collection_tests, tmp_path):
    summary = extracted(collection_tests, "camera_jpeg", tmp_path).summary
    assert ", ".join(summary) == (
        "Canon, Canon PowerShot S40, width 480, height 360, 2003:12:14 12:01:44"
    )


# Only the header is read


def large(kind: str, target: Path) -> Path:
    """A file of several MB written by tifffile or Pillow."""
    noise = np.random.default_rng(0).integers(0, 256, (2048, 2048, 3), dtype=np.uint8)
    match kind:
        case "tiff" | "bigtiff":
            path = target / f"{kind}.tif"
            tifffile.imwrite(
                path, np.stack([noise[..., 0]] * 4), bigtiff=kind == "bigtiff",
                photometric="minisblack",
            )  # fmt: skip
        case "imagej":  # a hyperstack: ImageJ's description says 4 slices
            path = target / "imagej.tif"
            tifffile.imwrite(path, np.stack([noise[..., 0]] * 4), imagej=True)
        case "png":
            path = target / "large.png"
            Image.fromarray(noise).save(path, compress_level=0)
        case "jpeg":
            path = target / "large.jpg"
            Image.fromarray(noise).save(path, quality=95)
        case "bmp":
            path = target / "large.bmp"
            Image.fromarray(noise).save(path)
        case "gif":
            path = target / "large.gif"
            Image.fromarray(noise[..., 0]).save(path)
    return path


@pytest.mark.parametrize(
    "kind", ["tiff", "bigtiff", "imagej", "png", "jpeg", "bmp", "gif"]
)
def test_a_large_image_file(tmp_path, kind):
    path = large(kind, tmp_path)
    size = path.stat().st_size
    result, read = read_by(path)
    print(f"{path.name}: {read} bytes read of {size}")
    assert size > 3_000_000
    assert read < 256_000
    assert any(p.endswith(" 2048") for p in result.summary)  # the width


def test_a_large_svg_file(tmp_path):
    path = tmp_path / "large.svg"
    path.write_text(SVG.format(padding='<rect width="1" height="1"/>\n' * 140_000))
    size = path.stat().st_size
    result, read = read_by(path)
    print(f"{path.name}: {read} bytes read of {size}")
    assert size > 4_000_000
    assert read < 1_100_000
    assert result.values["original_metadata"]["@width"] == "210mm"


def test_an_svg_file_with_one_large_element(tmp_path):
    # Matplotlib embeds a raster as a data URI in one <image> element
    path = tmp_path / "embedded.svg"
    uri = "data:image/png;base64," + "A" * 8_000_000
    path.write_text(SVG.format(padding=f'<image href="{uri}"/>'))
    result, read = read_by(path)
    print(f"{path.name}: {read} bytes read of {path.stat().st_size}")
    assert read < 1_100_000
    assert result.values["original_metadata"]["title"] == "A test drawing"


def test_a_broken_small_svg_file(tmp_path):
    # Read to its end: a parse error is the file's, and the extraction fails
    path = tmp_path / "broken.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg"><title>t</title>')
    with pytest.raises(ParseError):
        of_file(path)


def test_a_large_webp_file(tmp_path):
    path = tmp_path / "large.webp"
    Image.fromarray(generate.pattern(48, 64)).save(path)
    with open(path, "r+b") as f:
        f.truncate(image.WEBP_LIMIT + 1)  # sparse: nothing written
    result, read = read_by(path)
    assert result is None
    assert read < 4096


def test_dates_in_another_time_zone(collection_tests, tmp_path, monkeypatch):
    found = []
    for zone in ("Europe/Berlin", "UTC"):
        monkeypatch.setenv("TZ", zone)
        time.tzset()
        found.append(extracted(collection_tests, "camera_jpeg", tmp_path / zone).values)
    monkeypatch.undo()
    time.tzset()
    assert found[0] == found[1]
    assert found[0]["original_metadata"]["exif.DateTime"] == "2003:12:14 12:01:44"
