"""HDF5 files, NeXus and HyperSpy files among them: a bounded walk of the objects with h5py.

Every attribute of the file, its groups and datasets, each dataset's shape and
dtype, and the value of each scalar dataset, as dotted names, minus a skip
list per format (spec formats/pydata, "An HDF5 file is described by a walk of
its objects"). No array is read, no link to another file followed, nothing
read from outside the file.
"""

import warnings
from collections.abc import Callable

import h5py
import numpy
from modama_crawler.formats.values import MAX_CHARS
from numpy.lib.format import dtype_to_descr

from .values import (
    MAX_ENTRIES,
    MAX_ITEMS,
    MAX_OBJECTS,
    Walk,
    headline,
    matches,
    no_readahead,
    plain,
)

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


def dtype_name(dt: numpy.dtype):
    """A dtype as the file spells it, NumPy's descr as an .npy header has it (`<f8`, a
    list of fields for a compound); h5py's variable-length and reference types, which
    NumPy calls object, as h5py names them (`vlen str`, `vlen <i4`, `Reference`)."""
    if (info := h5py.check_string_dtype(dt)) is not None and info.length is None:
        return "vlen str" if info.encoding == "utf-8" else "vlen bytes"
    if (base := h5py.check_vlen_dtype(dt)) is not None:
        inner = base.__name__ if isinstance(base, type) else numpy.dtype(base).str
        return f"vlen {inner}"
    if (ref := h5py.check_ref_dtype(dt)) is not None:
        return ref.__name__
    if dt.fields is None:
        return dt.str
    # h5py's metadata on a field's dtype (its string encoding), which an .npy
    # file would not keep, makes NumPy warn: the descr is the same
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return dtype_to_descr(dt)


def small(dt: numpy.dtype) -> bool:
    """Whether one element of dt is small enough to read for its value: not more bytes
    than a text values.textual keeps can take (4 bytes a character), no array type.
    A variable-length type cannot be sized before it is read."""
    return dt.itemsize <= 4 * MAX_CHARS and dt.subdtype is None


def outside(dataset: h5py.Dataset) -> str | None:
    """Where a dataset keeps its data outside this file, from its creation property
    list, before anything else is asked of it: "virtual" (mapped onto datasets of other
    files) or "external" (raw data in other files), else None."""
    dcpl = dataset.id.get_create_plist()
    if dcpl.get_layout() == h5py.h5d.VIRTUAL:
        return "virtual"
    if dcpl.get_external_count() > 0:
        return "external"
    return None


def walked(f: h5py.File, skip: Skip = nothing) -> tuple[dict, dict]:
    """original_metadata and the mapped note of a cut, from the file's objects in stored order.

    Depth first, each object once (by its address), hard links only: an
    external link (another file) and a soft link (another name) are not
    followed, and an object on the skip list is not entered. Names are joined
    with dots as found (a name holding a dot is not escaped). Nothing is read
    from outside the file: a virtual dataset gives its dtype and the extent its
    first mapping declares, a dataset with external storage no value (spec
    formats/pydata, "Nothing is read from outside the file").
    """
    walk = Walk()
    seen: set[int] = set()

    def add(name: str, value) -> None:
        value = plain(value)
        if not skip(name, value):
            walk.add(name, value)

    def attributes(obj, prefix: str) -> None:
        # No more names listed than entries can still be kept, and one to tell
        # that there are more (one group of 200,000 attributes): h5a.iterate
        # stops when the callback returns something
        names: list[bytes] = []
        room = MAX_ENTRIES - len(walk.values)

        def listed(name: bytes, *_) -> bool | None:
            names.append(name)
            return True if len(names) > room else None

        h5py.h5a.iterate(obj.id, listed)
        for raw in names:
            if walk.over():
                return
            name = raw.decode("utf-8", "replace")
            try:
                attr = h5py.h5a.open(obj.id, raw)
                # Not read: more elements than textual keeps, or too large ones
                if attr.shape is not None and numpy.prod(attr.shape) > MAX_ITEMS:
                    continue
                if not small(attr.dtype):
                    continue
                value = obj.attrs[name]
            except (OSError, TypeError, ValueError, KeyError):
                continue  # a type h5py cannot convert (a region reference, …)
            add(f"{prefix}{name}", "" if isinstance(value, h5py.Empty) else value)

    def dataset(obj: h5py.Dataset, dotted: str) -> None:
        where = outside(obj)
        if where == "virtual":
            # Its shape (H5Dget_space) opens the source files of an unlimited
            # one: the extent declared in its first mapping instead
            dcpl = obj.id.get_create_plist()
            if dcpl.get_virtual_count() > 0:
                add(f"{dotted}.shape", list(dcpl.get_virtual_vspace(0).shape))
            add(f"{dotted}.dtype", dtype_name(obj.dtype))
            return
        if obj.shape == () and where is None:
            if small(obj.dtype):
                try:
                    add(dotted, obj[()])
                except (OSError, TypeError, ValueError):
                    pass  # a type h5py cannot convert
            return
        add(f"{dotted}.shape", list(obj.shape or ()))
        add(f"{dotted}.dtype", dtype_name(obj.dtype))

    def hard_links(group: h5py.Group) -> list[bytes]:
        """The names of group's hard links in the order the file stores them, no
        more than objects can still be walked and one to tell that there are more.

        The stored order is the names' order in the groups most writers write
        (h5py's default, HDF5's symbol tables), another in groups of the newer
        format with many links. Name order there means a sorted table of all
        links first: on a group of 200,000 links, 393 MB read of a 32 MB file,
        against 69 kB for the first 5,000 in stored order."""
        names: list[bytes] = []
        room = MAX_OBJECTS - walk.objects

        def listed(name: bytes, info) -> bool | None:
            if info.type == h5py.h5l.TYPE_HARD:
                names.append(name)
            return True if len(names) > room else None

        group.id.links.iterate(listed, info=True, order=h5py.h5.ITER_NATIVE)
        return names

    def members(group: h5py.Group, prefix: str) -> bool:
        """Walks the members of group; False when a limit stopped the walk."""
        for raw in hard_links(group):
            if walk.over():
                return False
            name = raw.decode("utf-8", "replace")
            obj = group[raw]
            address = h5py.h5o.get_info(obj.id).addr
            if address in seen:
                continue  # another name of an object already walked
            seen.add(address)
            dotted = f"{prefix}{name}"
            skipped = skip(dotted, None)  # not entered: nothing below it either
            if not skipped:
                if isinstance(obj, h5py.Dataset):
                    dataset(obj, dotted)
                attributes(obj, f"{dotted}.")
            walk.objects += 1  # once done with it, skipped or not
            if (
                not skipped
                and isinstance(obj, h5py.Group)
                and not members(obj, f"{dotted}.")
            ):
                return False
        return True

    root = f["/"]
    seen.add(h5py.h5o.get_info(root.id).addr)
    attributes(root, "")
    members(root, "")
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
