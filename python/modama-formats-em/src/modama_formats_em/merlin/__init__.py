"""Merlin acquisitions: the text header, recognised by its content (merlin.xml); its frames follow in task 2.5."""

from pathlib import Path

from modama_crawler.formats import Collection

HERE = Path(__file__).parent

# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [], mime_files=(HERE / "merlin.xml",))
