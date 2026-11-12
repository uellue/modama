"""Common file formats for the modama crawler, as the collection `common`.

Each area lives in a subpackage with its MIME rules, fixtures and tests, and
defines the part of the collection it contributes; the crawler's pytest plugin
tests each part on its own (formats/TEMPLATE.md).
"""

from modama_crawler.formats import Collection

from . import pydata

# The subpackages image, pydata, office, text and structured are added by
# other changes, each with one import above and one entry here
PARTS = (pydata.COLLECTION,)

COLLECTION = Collection(
    "common",
    [f for part in PARTS for f in part.formats],
    mime_files=tuple(xml for part in PARTS for xml in part.mime_files),
)
