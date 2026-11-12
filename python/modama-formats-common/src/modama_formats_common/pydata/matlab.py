"""MATLAB MAT-files: the header text and the variables' shapes and classes, never their data.

Versions 4 and 5 through SciPy (`matfile_version`, `whosmat`), version 7.3
(HDF5 after a user block of 512 bytes) through the HDF5 walk without MATLAB's
internal groups (spec formats/pydata, "A MATLAB file is described by its
header and its variables").
"""

import scipy.io
from modama_crawler.formats.values import textual

from . import hdf5
from .values import MAX_ENTRIES, Walk, no_readahead

BUFFER = 64 * 1024  # SciPy reads tags of 8 bytes and seeks between variables (F14)
HEADER = 116  # the descriptive text at the start of versions 5 and 7.3
# What SciPy strips from the header text (MatFile5Reader.read_file_header)
PADDING = b" \t\n\x00"


def described(path: str) -> tuple[dict, dict, list[str]]:
    """original_metadata, mapped_metadata and the summary line of a MAT-file."""
    with open(path, "rb", buffering=BUFFER) as f:
        no_readahead(f.fileno())
        major, _ = scipy.io.matlab.matfile_version(f)
        f.seek(0)
        # The text as written, in Latin-1 as SciPy decodes MATLAB's names; its
        # date as written, in no time zone of ours (TEMPLATE.md)
        text = f.read(HEADER).rstrip(PADDING).decode("latin-1")
        if major != 2:
            f.seek(0)
            # Without the integrity check, which reads a compressed variable
            # to its end
            variables = scipy.io.whosmat(f, verify_compressed_data_integrity=False)
    # Version 4 has no header text
    header = {"header": text} if major != 0 and textual(text) else {}
    if major == 2:
        found, mapped = hdf5.described(path, hdf5.matlab)
        original = dict(list({**header, **found}.items())[:MAX_ENTRIES])
    else:
        walk = Walk()
        walk.values.update(header)
        for name, shape, cls in variables:
            if walk.over():
                break
            walk.add(f"{name}.shape", list(shape))
            walk.add(f"{name}.class", cls)
        original, mapped = walk.result()
    return original, mapped, [text] if header and text else []
