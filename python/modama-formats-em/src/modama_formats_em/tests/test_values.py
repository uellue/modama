"""Values not suitable for text (values.textual), one test per kind, from real fixtures where they have one."""

import os

import numpy as np

from modama_formats_em.dm import first_image, parsed
from modama_formats_em.values import MAX_CHARS, MAX_ITEMS, textual

HERE = os.path.dirname(os.path.dirname(__file__))
CL = os.path.join(HERE, "dm/tests/fixtures/cl_image_dm4/test-MonarcCL_mono-image.dm4")
GTG = os.path.join(HERE, "k2is/tests/fixtures/capture52/Capture52_.gtg")


def test_a_large_list():
    # GMS's printer settings, a Windows structure as 1,076 bytes, and a 60-byte one
    page = first_image(CL)["original_metadata"]["PageSetup"]
    assert len(page["Win32_DevModeW"]) == 1076 and not textual(page["Win32_DevModeW"])
    assert len(page["Win32"]) == 60 and not textual(page["Win32"])
    assert not textual([0.25] * (MAX_ITEMS + 1))


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


def test_a_long_string():
    # No fixture has one: the longest string in RosettaSciIO's 110 DM test files has 115 characters
    assert textual("x" * MAX_CHARS)
    assert not textual("x" * (MAX_CHARS + 1))


def test_control_characters():
    # No fixture has one; tab, line feed and carriage return are text
    assert textual("line 1\r\nline 2\tend")
    assert not textual("PK\x03\x04")
    assert not textual("a\x00b")


def test_bytes():
    assert not textual(b"\x00\x01")
    assert not textual(bytearray(b"ab"))


def test_numpy_arrays():
    # Numbers are text, objects and strings in an array are not; nor a large array
    assert textual(np.float64(2.0))
    assert textual(np.array([1, 2, 3]))
    assert not textual(np.array(["a", "b"]))
    assert not textual(np.array([object()]))
    assert not textual(np.zeros(MAX_ITEMS + 1))
