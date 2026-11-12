"""The collection is installed under its name and holds the formats of its parts."""

from modama_crawler.selection import discover

import modama_formats_common


def test_registered_as_common():
    collection = discover()["common"]
    assert collection is modama_formats_common.COLLECTION
    parts = modama_formats_common.PARTS
    assert collection.formats == [f for p in parts for f in p.formats]
