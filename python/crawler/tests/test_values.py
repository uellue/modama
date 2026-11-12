"""Values not suitable for text (formats.values.textual), one test per kind; the
cases from real EM fixtures are in modama_formats_em/tests/test_values.py."""

import numpy as np
from modama_crawler.formats.values import MAX_CHARS, MAX_ITEMS, textual


def test_a_large_list():
    assert textual([0.25] * MAX_ITEMS)
    assert not textual([0.25] * (MAX_ITEMS + 1))


def test_an_array_not_read():
    # RosettaSciIO's marker where it skips the image data: where it is, not what it holds
    assert not textual({"size": 1, "size_bytes": 4, "offset": 0, "endian": "<"})
    assert textual({"size": 1})


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
