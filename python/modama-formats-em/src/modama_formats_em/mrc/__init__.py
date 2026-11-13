"""MRC files (MRC2014: maps, tomograms, image stacks, movies; `.mrc`, `.mrcs`, `.map`), one file one dataset.

Recognition checks the map word at byte 208, as mrcfile does, since other
programs write `.map` files too. Extraction reads the 1024-byte main header
through mrcfile and, for an FEI extended header (EPU, Tomo, Velox), its first
record with mrcfile's description of it; nothing else (change em-mrc).
"""

import io
import logging
import math
import warnings
from collections.abc import Iterable
from pathlib import Path

import numpy as np
from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format
from modama_crawler.formats.values import credential, textual

log = logging.getLogger(__name__)
HERE = Path(__file__).parent
TYPE = "application/x.mrc"
# The main header, and its word nsymbt, the extended header's size in bytes
HEADER_BYTES = 1024
NSYMBT = slice(92, 96)
# The map word: mrcfile checks its first three bytes, "MAP"
MAP_WORD = (208, b"MAP")
# Extended headers whose first record is read: those mrcfile can interpret
FEI = (b"FEI1", b"FEI2")
# The skip lists (spec formats/mrc): unused space in the main header; unused
# space and reserved placeholders in an FEI record
SKIPPED = ("extra1", "extra2")
SKIPPED_FEI = (
    "Unused range",
    *(f"Camera param reserved {n}" for n in range(10)),
    *(f"STEM param reserved {n}" for n in range(5)),
)
# The summary line's entries, the only list of wanted entries: of the main
# header (0 is a value of each), then of an FEI record (0 or empty left out;
# text bare, a number after its name, without a unit: mrcfile gives none)
HEADLINE = ("nx", "ny", "nz", "mode")
HEADLINE_FEI = ("Microscope type", "HT", "Pixel size X", "Camera name")


def plain(v):
    """A header value as found, as a plain JSON value.

    Text ends at its first NUL (fixed-size C strings: EPU leaves bytes after it)
    and loses trailing spaces, read as Latin-1; numbers as the reader widens them
    to Python numbers (a 32-bit 11.4 as 11.399999618530273, TEMPLATE.md); the
    infinities and NaN, which JSON cannot hold, as Python writes them ("nan").
    """
    if isinstance(v, bytes):
        return v.split(b"\0", 1)[0].rstrip(b" ").decode("latin-1")
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return str(v)
    return v


def entries(header) -> dict:
    """Every field of mrcfile's header record under its name, flat, as found.

    Records (cella, cellb, origin) become `name.field`, the labels `label[n]`
    from 1; the machine stamp is printed as mrcfile prints it.
    """
    from mrcfile.utils import pretty_machine_stamp

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
            for n in range(len(field)):
                out[f"label[{n + 1}]"] = plain(field[n])
        elif field.dtype.names:
            for sub in field.dtype.names:
                out[f"{name}.{sub}"] = plain(field[sub][()])
        else:
            out[name] = plain(field[()])
    return out


def fei_record(header, nsymbt: int, f, anchor: str) -> dict:
    """The first record of an FEI extended header of `nsymbt` bytes, read from `f`
    (at its start), as `extended_header.<name>`, but the skip list; {} if it is
    not of its type."""
    from mrcfile.dtypes import get_ext_header_dtype

    exttyp = bytes(header.exttyp)
    dtype = get_ext_header_dtype(exttyp, header.mode.dtype.byteorder)
    blob = f.read(min(dtype.itemsize, nsymbt)) if nsymbt > 0 else b""
    record = np.frombuffer(blob, dtype)[0] if len(blob) == dtype.itemsize else None
    # mrcfile's test (MrcObject.indexed_extended_header): a whole record that
    # states its own size
    if record is None or record["Metadata size"] != dtype.itemsize:
        log.warning("%s: the extended header is not %s", anchor, exttyp.decode())
        return {}
    return {
        f"extended_header.{name}": plain(record[name])
        for name in dtype.names
        if name not in SKIPPED_FEI
    }


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


def summary(original: dict) -> list[str]:
    """The summary line (spec formats/mrc, "The MRC header is extracted")."""
    line = [f"{k} {original[k]}" for k in HEADLINE if k in original]
    for name in HEADLINE_FEI:
        v = original.get(f"extended_header.{name}")
        if isinstance(v, str) and v:
            line.append(v)
        elif isinstance(v, int | float) and v != 0:
            line.append(f"{name} {v} (unit unknown)")
    if original.get("label[1]"):
        line.append(original["label[1]"])
    return line


class Mrc(Format):
    type = TYPE
    display_name = "MRC"
    # A format that drops a type runs at 61 or more (TEMPLATE.md); one that
    # claims MRC files as members of a larger dataset (em/de) runs above it
    priority = 61
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
        """The main header's fields and an FEI record's as found, and what mrcfile
        computes from them (spec formats/mrc, "The MRC header is extracted")."""
        from mrcfile.mrcinterpreter import MrcInterpreter
        from mrcfile.utils import dtype_from_mode

        with open(root + dataset.anchor, "rb", buffering=0) as f:
            head = f.read(HEADER_BYTES)
            # mrcfile allocates the extended header's declared size even with
            # header_only (a bytearray of nsymbt, up to 2 GiB; a negative one
            # fails): it gets the header with nsymbt 0, the real one is ours
            blank = head[: NSYMBT.start] + bytes(4) + head[NSYMBT.stop :]
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                # Permissive: a header mrcfile finds odd is read with a warning
                m = MrcInterpreter(io.BytesIO(blank), permissive=True, header_only=True)
                # Cell over sampling; a sampling of 0 gives inf or nan, with a warning
                voxel_size = [plain(m.voxel_size[axis][()]) for axis in "xyz"]
            for w in caught:
                if issubclass(w.category, RuntimeWarning):
                    log.warning("%s: mrcfile: %s", dataset.anchor, w.message)
            nsymbt = int(np.frombuffer(head[NSYMBT], m.header.nsymbt.dtype)[0])
            found = entries(m.header) | {"nsymbt": nsymbt}
            if bytes(m.header.exttyp) in FEI:
                found |= fei_record(m.header, nsymbt, f, dataset.anchor)
        original, secrets = {}, 0
        for name, value in found.items():
            if not textual(value):
                continue
            if credential(name, value):
                secrets += 1
                continue
            original[name] = value
        mapped = {
            "data_type": str(dtype_from_mode(m.header.mode)),
            "voxel_size": voxel_size,
            "kind": kind(m.header),
        }
        if secrets:
            mapped["credentials_left_out"] = secrets
        return Extracted(
            summary=summary(original),
            subjects=[],
            values={
                "original_metadata": original,
                "mapped_metadata": mapped,
            },
        )


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [Mrc()], mime_files=(HERE / "mrc.xml",))
