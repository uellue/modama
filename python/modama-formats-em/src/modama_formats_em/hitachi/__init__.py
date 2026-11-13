"""Hitachi electron microscope images: a TIFF and its `[SemImageFile]` header of the same stem, one dataset anchored at the TIFF (hitachi.xml; spec formats/hitachi).

The instrument writes each image as a TIFF and a `.txt` of the same name. The
`.txt` is an INI-like header (`[SemImageFile]`, then `key=value` lines); the
TIFF carries the same block in its description, which the image area of
modama-formats-common parses with its private tag 65500. So the pair's values
are the TIFF's, as the image area gives them, and its `.txt` is shown as written
(change em-hitachi, design D5, D7). Recognition reads the first 14 bytes of the
`.txt` only.
"""

from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format

HERE = Path(__file__).parent
TYPE = "application/x-hitachi-sem"
TIFF = "image/tiff"
# The header's first line, as Gwyddion (hitachi-sem.c) and Bio-Formats (HitachiReader) detect it
SIGNATURE = b"[SemImageFile]"


def header_name(tiff_name: str) -> str:
    """The name of a TIFF's header: its last suffix replaced by .txt (names hold dots: `a_x50.0k_0007.tif`)."""
    return f"{PurePosixPath(tiff_name).stem}.txt"


class Hitachi(Format):
    type = TYPE
    priority = 60
    reacts_to = frozenset({TIFF})

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        for tif in d.of_type(TIFF):
            name = header_name(tif.name)
            if name in d.claimed:
                # A format before this one took the header: flagged for review,
                # the TIFF left to the formats after this one (decision 344)
                d.claimed_elsewhere(tif.rel, name)
                continue
            header = d.entry(name)
            if header is None:
                continue
            try:
                if d.read(header, len(SIGNATURE)) != SIGNATURE:
                    continue
            except OSError as e:
                d.cannot_read(header, e)
                continue
            yield Dataset(
                anchor=tif.rel,
                members=(tif.rel, header.rel),
                basis=f"header {name}",
            )

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """The TIFF's values as the image area gives them (spec formats/hitachi, "The pair's values are its TIFF's")."""
        from modama_formats_common.image import tiff

        return tiff.extract(root + dataset.anchor)


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [Hitachi()], mime_files=(HERE / "hitachi.xml",))
