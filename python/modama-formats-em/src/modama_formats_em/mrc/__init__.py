"""MRC files (MRC2014: maps, tomograms, image stacks; `.mrc`, `.mrcs`, `.map`), one file one dataset.

Recognition checks the map word at byte 208, as mrcfile does, since other
programs write `.map` files too. Extraction reads the 1024-byte main header
only, through mrcfile; the extended header is not read (change em-mrc).
"""

import io
import logging
import warnings
from collections.abc import Iterable
from pathlib import Path

from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format
from modama_crawler.formats.values import credential, textual

log = logging.getLogger(__name__)
HERE = Path(__file__).parent
TYPE = "application/x.mrc"
# The main header; the extended header that may follow is not read
HEADER_BYTES = 1024
# The map word: mrcfile checks its first three bytes, "MAP"
MAP_WORD = (208, b"MAP")
# The skip list: unused space in the header (spec formats/mrc)
SKIPPED = ("extra1", "extra2")
# The summary line's entries, the only list of wanted entries; a cell length or
# sampling of 0 is a placeholder, a mode or space group of 0 a value
HEADLINE = ("nx", "ny", "nz", "mode", "ispg")
PLACEHOLDER_0 = ("cella.x", "cella.y", "cella.z", "mx", "my", "mz")


def entries(header) -> dict:
    """Every field of mrcfile's header record under its name, flat, as found.

    Records (cella, cellb, origin) become `name.field`, the labels `label[n]`
    from 1; byte strings lose their padding (trailing spaces and NULs) and read
    as Latin-1; the machine stamp is printed as mrcfile prints it.
    """
    from mrcfile.utils import pretty_machine_stamp

    def plain(v):
        if isinstance(v, bytes):
            return v.rstrip(b" \x00").decode("latin-1")
        return v

    out = {}
    for name in header.dtype.names:
        if name in SKIPPED:
            continue
        field = header[name]
        if name == "machst":
            out[name] = pretty_machine_stamp(field)
        elif name == "map":
            # The map word as written, "MAP " with its space
            out[name] = bytes(field).rstrip(b"\x00").decode("latin-1")
        elif name == "label":
            for n, label in enumerate(field.tolist(), 1):
                out[f"label[{n}]"] = plain(label)
        elif field.dtype.names:
            for sub, v in zip(field.dtype.names, field.tolist()):
                out[f"{name}.{sub}"] = plain(v)
        else:
            out[name] = plain(field.item())
    return out


def kind(header) -> str:
    """What the data block holds, by the shape mrcfile would read it in and
    mrcfile's rule (MrcObject.is_image_stack and the like), without the data."""
    from mrcfile.constants import IMAGE_STACK_SPACEGROUP
    from mrcfile.utils import data_shape_from_header

    ndim = len(data_shape_from_header(header))
    if ndim == 2:
        return "image"
    if ndim == 4:
        return "volume stack"
    return "image stack" if header.ispg == IMAGE_STACK_SPACEGROUP else "volume"


class Mrc(Format):
    type = TYPE
    display_name = "MRC"
    priority = 60
    reacts_to = frozenset({TYPE})

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        offset, word = MAP_WORD
        for e in d.of_type(TYPE):
            # The signature only, as the magic rule tests it
            if d.read(e, offset + len(word))[offset:] != word:
                d.not_of_type(e, f"no {word.decode()} at byte {offset}")
                continue
            yield Dataset(anchor=e.rel, basis=f"{word.decode()} at byte {offset}")

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """The main header's fields as found, and what mrcfile computes from them
        (spec formats/mrc, "The MRC header is extracted")."""
        from mrcfile.mrcinterpreter import MrcInterpreter
        from mrcfile.utils import dtype_from_mode

        with open(root + dataset.anchor, "rb", buffering=0) as f:
            head = f.read(HEADER_BYTES)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            # Permissive: a header mrcfile finds odd is read with a warning.
            # The extended header is not in `head`, so its warning is ours.
            m = MrcInterpreter(io.BytesIO(head), permissive=True, header_only=True)
        for w in caught:
            if issubclass(w.category, RuntimeWarning) and not str(w.message).startswith(
                "Expected"
            ):
                log.warning("%s: mrcfile: %s", dataset.anchor, w.message)
        original, secrets = {}, 0
        for name, value in entries(m.header).items():
            if not textual(value):
                continue
            if credential(name, value):
                secrets += 1
                continue
            original[name] = value
        mapped = {
            "data_type": str(dtype_from_mode(m.header.mode)),
            # float32 values as Python floats, unrounded, as for every field
            "voxel_size": list(m.voxel_size.tolist()),
            "kind": kind(m.header),
        }
        if secrets:
            mapped["credentials_left_out"] = secrets
        summary = [f"{k} {original[k]}" for k in HEADLINE if k in original]
        summary += [
            f"{k} {original[k]}" for k in PLACEHOLDER_0 if original.get(k, 0) != 0
        ]
        if original.get("label[1]"):
            summary.append(original["label[1]"])
        return Extracted(
            summary=summary,
            subjects=[],
            values={
                "original_metadata": original,
                "mapped_metadata": mapped,
            },
        )


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [Mrc()], mime_files=(HERE / "mrc.xml",))
