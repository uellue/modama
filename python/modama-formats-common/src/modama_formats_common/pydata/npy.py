"""NumPy's `.npy` files and `.npz` archives: the arrays' headers, never the arrays.

The header is NumPy's own reading of it (`numpy.lib.format`), the private
`_read_array_header` because only it reads all three versions (the public
read_array_header_1_0 and _2_0 decode version 3.0's UTF-8 as Latin-1); NumPy
is pinned exactly for it (pyproject.toml).
"""

import zipfile
from typing import BinaryIO

from modama_crawler.formats.values import textual
from numpy.lib import format as npformat
from numpy.lib._format_impl import _read_array_header

from .values import MAX_ITEMS, Walk

ZIP = b"PK\x03\x04"  # a ZIP's local file header (APPNOTE 4.3.7)
MAX_HEADER = 1 << 20


def header(f: BinaryIO) -> tuple[dict, str]:
    """The header of the array file f at its start, as the file says it, and NumPy's dtype."""
    version = npformat.read_magic(f)
    # NumPy refuses headers over 10,000 bytes by default (a structured dtype of
    # 600 fields has more); the header is a dict literal, parsed with
    # ast.literal_eval, never unpickled, so a larger one is safe to read
    shape, fortran_order, dtype = _read_array_header(
        f, version, max_header_size=MAX_HEADER
    )
    descr = npformat.dtype_to_descr(dtype)
    found = {
        "descr": descr,
        "fortran_order": fortran_order,
        "shape": list(shape),
        "version": ".".join(map(str, version)),
    }
    return found, str(dtype)


def npy(path: str) -> tuple[dict, dict, list[str]]:
    """original_metadata, mapped_metadata and the summary line of an .npy file."""
    # Unbuffered: the magic, the header's length and the header, three reads
    with open(path, "rb", buffering=0) as f:
        found, dtype = header(f)
    walk = Walk()
    for name, value in found.items():
        walk.add(name, value)  # a structured descr's tuples as lists
    # NumPy's name of a structured dtype of many fields is too long for text
    named = [dtype] if textual(dtype) else []
    summary = [f"shape {found['shape']}", *named]
    if found["fortran_order"]:
        summary.append("fortran_order True")
    return walk.values, {"dtype": dtype} if named else {}, summary


def npz(path: str) -> tuple[dict, dict, list[str]]:
    """original_metadata, mapped_metadata and the summary line of an .npz archive.

    Each `.npy` member's header under NumPy's key for it (the name without
    `.npy`, as `numpy.load` gives it); other members are not arrays and are
    left out. zipfile on an unbuffered file reads the directory at the end and,
    per member, its local header and the first block of its data.
    """
    walk = Walk()
    summary = []
    with open(path, "rb", buffering=0) as raw, zipfile.ZipFile(raw) as z:
        for info in z.infolist():
            if walk.over():
                break
            if not info.filename.endswith(".npy"):
                continue
            key = info.filename.removesuffix(".npy")
            with z.open(info) as member:
                found, _ = header(member)
            for name, value in found.items():
                walk.add(f"{key}.{name}", value)
            if len(summary) < MAX_ITEMS:
                summary.append(f"{key}.shape {found['shape']}")
    original, mapped = walk.result()
    return original, mapped, summary
