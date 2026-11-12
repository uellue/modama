"""HDF5 files, NeXus and HyperSpy files among them: a bounded walk of the objects with h5py.

Every attribute of the file, its groups and datasets, each dataset's shape and
dtype, and the value of each scalar dataset, as dotted names, minus a skip
list per format (spec formats/pydata, "An HDF5 file is described by a walk of
its objects"). No array is read, no external link followed.
"""

from collections.abc import Callable

import h5py
import numpy

from .values import MAX_ITEMS, Walk, headline, matches, no_readahead, plain

SIGNATURE = b"\x89HDF\r\n\x1a\n"

# skip(dotted name, value): whether an object (with everything below it) or a
# value is on a format's skip list; value is None when an object is asked
Skip = Callable[[str, object], bool]


def nothing(name: str, value) -> bool:
    """The skip list of plain HDF5 and NeXus files: only what values.textual refuses."""
    return False


def hyperspy(name: str, value) -> bool:
    """HyperSpy's skip list (spec formats/pydata, "A HyperSpy file is described as
    HyperSpy stores it"): its internal state (`metadata._HyperSpy`: folding) and its
    placeholder for None, `_None_`."""
    return "._HyperSpy." in f".{name}." or (
        isinstance(value, str) and value == "_None_"
    )


def matlab(name: str, value) -> bool:
    """MATLAB 7.3's skip list: its internal groups `#refs#` (the contents of cell arrays
    and structures, which the variables reference) and `#subsystem#` (objects)."""
    return name.split(".", 1)[0] in ("#refs#", "#subsystem#")


def opened(path: str) -> h5py.File:
    """The file opened for reading with HDF5's own driver, which reads what the library
    asks for (no Python buffer), readahead off, and without HDF5's file lock: on NFS a
    lock can fail or wait, and a crawler must not get in a writer's way."""
    f = h5py.File(path, "r", locking=False)
    no_readahead(f.id.get_vfd_handle())
    return f


def dtype_name(dt: numpy.dtype) -> str:
    """A dataset's dtype as NumPy names it; h5py's variable-length types, which NumPy
    calls object, as h5py spells them (`vlen str`, `vlen int32`)."""
    if (info := h5py.check_string_dtype(dt)) is not None and info.length is None:
        return "vlen str" if info.encoding == "utf-8" else "vlen bytes"
    if (base := h5py.check_vlen_dtype(dt)) is not None:
        return f"vlen {base.__name__ if isinstance(base, type) else numpy.dtype(base)}"
    return str(dt)


def walked(f: h5py.File, skip: Skip = nothing) -> tuple[dict, dict]:
    """original_metadata and the mapped note of a cut, from the file's objects in name order.

    Names are joined with dots as found (a name holding a dot is not escaped).
    """
    walk = Walk()

    def add(name: str, value) -> None:
        value = plain(value)
        if not skip(name, value):
            walk.add(name, value)

    def attributes(obj, prefix: str) -> None:
        # One of more than MAX_ITEMS elements is not read: textual would refuse it
        for name in obj.attrs:
            try:
                shape = obj.attrs.get_id(name).shape
                if shape is not None and numpy.prod(shape) > MAX_ITEMS:
                    continue
                value = obj.attrs[name]
            except (OSError, TypeError, ValueError, KeyError):
                continue  # a type h5py cannot convert (a region reference, …)
            add(f"{prefix}{name}", "" if isinstance(value, h5py.Empty) else value)

    skipped: list[str] = []

    def visit(name: str, obj) -> bool | None:
        if walk.over():
            return True  # stops visititems
        dotted = name.replace("/", ".")
        if any(dotted.startswith(f"{s}.") for s in skipped):
            return None
        if skip(dotted, None):
            skipped.append(dotted)
            return None
        if isinstance(obj, h5py.Dataset):
            if obj.shape == ():
                try:
                    add(dotted, obj[()])
                except (OSError, TypeError, ValueError):
                    pass  # a type h5py cannot convert
            else:
                add(f"{dotted}.shape", list(obj.shape or ()))
                add(f"{dotted}.dtype", dtype_name(obj.dtype))
        attributes(obj, f"{dotted}.")
        return None

    attributes(f, "")
    # visititems follows hard links only: an external link (another file) and
    # a soft link (another name for an object) are not visited
    f.visititems(visit)
    return walk.result()


def described(path: str, skip: Skip | None = None) -> tuple[dict, dict]:
    """original_metadata and the mapped note of a cut; without a skip list, HyperSpy's
    for a file that says it is HyperSpy's (older HyperSpy wrote .hdf5), else none."""
    with opened(path) as f:
        if skip is None:
            said = f.attrs.get("file_format")
            skip = hyperspy if said in ("HyperSpy", b"HyperSpy") else nothing
        return walked(f, skip)


# The summary line, the one positive list (TEMPLATE.md): a NeXus entry's title,
# start time and application definition (scalar datasets of an NXentry, NeXus
# manual), a HyperSpy signal's title, signal type and data shape (RosettaSciIO's
# hspy specification)
HEADLINE = (
    "*.title",
    "*.start_time",
    "*.definition",
    "Experiments.*.metadata.General.title",
    "Experiments.*.metadata.Signal.signal_type",
    "Experiments.*.data.shape",
)
# Subjects: what names a technique, as found
TERMS = ("*.definition", "Experiments.*.metadata.Signal.signal_type")


def summary(values: dict) -> list[str]:
    return headline(values, HEADLINE)


def terms(values: dict) -> list[str]:
    found = (
        v
        for k, v in values.items()
        if isinstance(v, str) and v and any(matches(p, k) for p in TERMS)
    )
    return list(dict.fromkeys(found))
