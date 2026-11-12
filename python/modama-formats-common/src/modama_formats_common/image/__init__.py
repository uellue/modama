"""Common image files: TIFF, PNG, JPEG, BMP, GIF, WEBP and SVG as single-file datasets with their metadata (spec formats/image).

The core types them by name (freedesktop.org.xml); each format claims the
files of its type and reads their metadata with the field's reader: tifffile
for TIFF (tiff.py), Pillow for the others but SVG (pil.py), defusedxml for
SVG (svg.py). Recognition reads nothing (proposal common-image, lean 1);
extraction reads headers only. EPS files keep the core's type, without a
format: no light reader gives their header comments (lean 4).
"""

import os
from collections.abc import Iterable

from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format

from . import pil, svg, tiff

# Pillow's WEBP plugin hands the whole file to libwebp (proposal, lean 5)
WEBP_LIMIT = 16 << 20


class Single(Format):
    """The files of the core's type `type`, each a dataset of one file."""

    # The XDG default: a format that groups image files (a series) goes above
    priority = 50

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        for e in d.of_type(self.type):
            yield Dataset(anchor=e.rel, basis="single file")


class Tiff(Single):
    type = "image/tiff"
    reacts_to = frozenset({type})

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        return tiff.extract(root + dataset.anchor)


class Pillow(Single):
    """A format Pillow reads, with the name of Pillow's plugin for it."""

    plugin = ""

    def extract(self, dataset: Dataset, root: str) -> Extracted | None:
        return pil.extract(root + dataset.anchor, self.plugin)


class Png(Pillow):
    type = "image/png"
    reacts_to = frozenset({type})
    plugin = "PNG"


class Jpeg(Pillow):
    type = "image/jpeg"
    reacts_to = frozenset({type})
    plugin = "JPEG"


class Bmp(Pillow):
    type = "image/bmp"
    reacts_to = frozenset({type})
    plugin = "BMP"


class Gif(Pillow):
    type = "image/gif"
    reacts_to = frozenset({type})
    plugin = "GIF"


class Webp(Pillow):
    type = "image/webp"
    reacts_to = frozenset({type})
    plugin = "WEBP"

    def extract(self, dataset: Dataset, root: str) -> Extracted | None:
        if os.stat(root + dataset.anchor).st_size > WEBP_LIMIT:
            return None
        return super().extract(dataset, root)


class Svg(Single):
    type = "image/svg+xml"
    reacts_to = frozenset({type})

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        return svg.extract(root + dataset.anchor)


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("image", [Tiff(), Png(), Jpeg(), Bmp(), Gif(), Webp(), Svg()])
