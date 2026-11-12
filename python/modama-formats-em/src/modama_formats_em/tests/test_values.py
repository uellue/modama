"""Values not suitable for text (the crawler's formats.values.textual) on real
EM fixtures; one test per kind, with made-up values, in the crawler's tests/test_values.py."""

import os

from modama_crawler.formats.values import textual

from modama_formats_em.dm import first_image, parsed

HERE = os.path.dirname(os.path.dirname(__file__))
CL = os.path.join(HERE, "dm/tests/fixtures/cl_image_dm4/test-MonarcCL_mono-image.dm4")
GTG = os.path.join(HERE, "k2is/tests/fixtures/capture52/Capture52_.gtg")


def test_a_large_list():
    # GMS's printer settings, a Windows structure as 1,076 bytes, and a 60-byte one
    page = first_image(CL)["original_metadata"]["PageSetup"]
    assert len(page["Win32_DevModeW"]) == 1076 and not textual(page["Win32_DevModeW"])
    assert len(page["Win32"]) == 60 and not textual(page["Win32"])


def test_a_short_list_of_values():
    # The camera's active size in Capture52
    size = parsed(GTG).tags_dict["Acquisition"]["Device"]["Active Size (pixels)"]
    assert size == (1920, 1792) and textual(size)


def test_an_array_not_read():
    # RosettaSciIO's marker where it skips the image data: where it is, not what it holds
    data = first_image(CL)["original_metadata"]["ImageList"]["TagGroup0"]["ImageData"]
    assert set(data["Data"]) == {"size", "size_bytes", "offset", "endian"}
    assert not textual(data["Data"])
    assert textual(data["Calibrations"])
