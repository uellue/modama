"""Gatan Digital Micrograph files (DM3, DM4): single-file datasets, recognised by their header (dm.xml)."""

from pathlib import Path

from modama_crawler.formats import Collection

HERE = Path(__file__).parent

# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [], mime_files=(HERE / "dm.xml",))
