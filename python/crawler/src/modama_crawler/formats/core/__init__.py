"""The core collection: common single-file types from the vendored shared-mime-info definitions, with ER-C curation in er-c.xml."""

from pathlib import Path

from .. import Collection

HERE = Path(__file__).parent

COLLECTION = Collection(
    "core", [], mime_files=(HERE / "freedesktop.org.xml", HERE / "er-c.xml")
)
