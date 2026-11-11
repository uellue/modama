"""Electron microscopy formats for the modama crawler, as the collection `em`.

Each format lives in a subpackage with its MIME rules, fixtures and tests, and
defines the part of the collection it contributes; the crawler's pytest plugin
tests each part on its own (formats/TEMPLATE.md).
"""

from modama_crawler.formats import Collection

from . import dm, empad, merlin

PARTS = (empad.COLLECTION, dm.COLLECTION, merlin.COLLECTION)

COLLECTION = Collection(
    "em",
    [f for part in PARTS for f in part.formats],
    mime_files=tuple(xml for part in PARTS for xml in part.mime_files),
)
