"""HDF5 files, NeXus and HyperSpy files among them: a bounded walk of the objects with h5py.

Every attribute of the file, its groups and datasets, each dataset's shape and
dtype, and the value of each scalar dataset, as dotted names, minus a skip
list per format (spec formats/pydata, "An HDF5 file is described by a walk of
its objects"); its external links and virtual-dataset sources as written,
counting-up links as one entry (change hdf5-links, design D2). No array is
read, no link to another file followed, nothing read from outside the file;
every file is opened through a file object of a descriptor opened without
following a symlink (design D4).
"""

import math
import os
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import h5py
import numpy
from modama_crawler import files
from modama_crawler.formats.values import MAX_CHARS
from numpy.lib.format import dtype_to_descr

from . import links
from .values import (
    MAX_ENTRIES,
    MAX_ITEMS,
    MAX_OBJECTS,
    Walk,
    headline,
    hyperspy,
    matches,
    plain,
)

# skip(dotted name, value): whether an object (with everything below it) or a
# value is on a format's skip list; value is None when an object is asked
Skip = Callable[[str, object], bool]


def nothing(name: str, value) -> bool:
    """The skip list of plain HDF5 and NeXus files: only what values.textual refuses."""
    return False


def matlab(name: str, value) -> bool:
    """MATLAB 7.3's skip list: its internal groups `#refs#` (the contents of cell arrays
    and structures, which the variables reference) and `#subsystem#` (objects)."""
    return name.split(".", 1)[0] in ("#refs#", "#subsystem#")


@contextmanager
def opened(path: str) -> Iterator[h5py.File]:
    """The file opened for reading through an unbuffered file object (files.Counted)
    of a descriptor opened only as a regular file, never through a symlink, readahead
    off, and without HDF5's file lock: on NFS a lock can fail or wait, and a crawler
    must not get in a writer's way. Not by path with HDF5's own driver, which opens
    the target of an absolute external link if anything dereferences it (review of
    hdf5-links, SHOULD 6). h5py's file is closed before the file object."""
    with (
        files.Counted(files.regular(path), name=path) as raw,
        h5py.File(raw, "r", locking=False) as f,
    ):
        yield f


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


@dataclass
class Linked:
    """What a walk found of a file's links to other files, as written (design D2, D3)."""

    external: list[str] = field(default_factory=list)  # each external link's file
    virtual: list[str] = field(default_factory=list)  # each mapping onto another file
    # Per run of external links: its first dotted name, its files in order, its path
    runs: list[tuple[str, list[str], str]] = field(default_factory=list)


def walked(
    f: h5py.File, skip: Skip = nothing, linked: Linked | None = None
) -> tuple[dict, dict]:
    """original_metadata and the mapped note of a cut, from the file's objects in stored order.

    Depth first, each object once (by its address), hard links only: an
    external link (another file) and a soft link (another name) are not
    followed, and an object on the skip list is not entered. Names are joined
    with dots as found (a name holding a dot is not escaped). Nothing is read
    from outside the file: a virtual dataset gives its dtype and the extent its
    first mapping declares, a dataset with external storage no value (spec
    formats/pydata, "Nothing is read from outside the file"). A group's
    external links are listed as written, before its members, runs of them as
    one entry (`<first> … <last>.external_link`), and a virtual dataset's
    sources in other files (`.virtual_sources`); each link counts as an
    object. What was found of them goes into `linked`, if given.
    """
    walk = Walk()
    seen: set[int] = set()
    linked = linked if linked is not None else Linked()

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
            mappings = [
                (dcpl.get_virtual_filename(i), dcpl.get_virtual_dsetname(i))
                for i in range(dcpl.get_virtual_count())
            ]
            others = [(f, p) for f, p in mappings if f != "."]
            if others:
                linked.virtual += [f for f, _ in others]
                add(f"{dotted}.virtual_sources", links.source_runs(others))
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

    def hard_links(group: h5py.Group) -> tuple[list[bytes], list[bytes]]:
        """The names of group's hard and external links in the order the file stores
        them, no more than objects can still be walked and one to tell that there
        are more.

        The stored order is the names' order in the groups most writers write
        (h5py's default, HDF5's symbol tables), another in groups of the newer
        format with many links. Name order there means a sorted table of all
        links first: on a group of 200,000 links, 393 MB read of a 32 MB file,
        against 69 kB for the first 5,000 in stored order."""
        names: list[bytes] = []
        external: list[bytes] = []
        room = MAX_OBJECTS - walk.objects

        def listed(name: bytes, info) -> bool | None:
            if info.type == h5py.h5l.TYPE_HARD:
                names.append(name)
            elif info.type == h5py.h5l.TYPE_EXTERNAL:
                external.append(name)
            return True if len(names) + len(external) > room else None

        group.id.links.iterate(listed, info=True, order=h5py.h5.ITER_NATIVE)
        return names, external

    def external_links(group: h5py.Group, prefix: str, names: list[bytes]) -> None:
        """The group's external links as written, sorted by name, runs as one entry."""
        found = []
        for raw in names:
            if walk.objects >= MAX_OBJECTS:
                break
            file, path = group.id.links.get_val(raw)  # as written, never followed
            name, file = raw.decode("utf-8", "replace"), file.decode("utf-8", "replace")
            found.append((name, file, path.decode("utf-8", "replace")))
            walk.objects += 1
        start = 0
        ordered = sorted(found, key=lambda t: t[0].encode())
        for first, last, ffile, lfile, path, count in links.runs(found):
            files_ = [file for _, file, _ in ordered[start : start + count]]
            start += count
            linked.external += files_
            linked.runs.append((f"{prefix}{first}", files_, path))
            if not walk.over():
                add(
                    f"{prefix}{links.entry(first, last)}.external_link",
                    [links.entry(ffile, lfile), path],
                )

    def members(group: h5py.Group, prefix: str) -> bool:
        """Walks the members of group; False when a limit stopped the walk."""
        hard, external = hard_links(group)
        if external:
            external_links(group, prefix, external)
        for raw in hard:
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


def described(
    path: str, skip: Skip | None = None, linked: Linked | None = None
) -> tuple[dict, dict]:
    """original_metadata, and as mapped values the note of a cut and the link counts;
    without a skip list, HyperSpy's for a file that says it is HyperSpy's (older
    HyperSpy wrote .hdf5), else none."""
    linked = linked if linked is not None else Linked()
    with opened(path) as f:
        if skip is None:
            said = f.attrs.get("file_format")
            skip = hyperspy if said in ("HyperSpy", b"HyperSpy") else nothing
        original, mapped = walked(f, skip, linked)
    return original, {**mapped, **counts(path, linked)}


def counts(path: str, linked: Linked) -> dict:
    """The link counts of a file with links to other files (design D3), by distinct
    target name other than its own: `found` a regular file of that name in the file's
    folder, `dangling` none, `elsewhere` never looked up. The folder is listed once
    (one scandir, the entries' types from it), nothing opened; an error of the
    listing raises, and the extraction fails, to be tried again next crawl."""
    if not linked.external and not linked.virtual:
        return {}
    names: set[str] = set()
    elsewhere: set[str] = set()
    for file, virtual in [(f, False) for f in linked.external] + [
        (f, True) for f in linked.virtual
    ]:
        name = links.matched(file, virtual)
        if name is None:
            elsewhere.add(file)
        else:
            names.add(name)
    names.discard(os.path.basename(path))
    regular: set[str] = set()
    if names:
        with os.scandir(os.path.dirname(path) or ".") as listing:
            regular = {
                e.name
                for e in listing
                if e.name in names and e.is_file(follow_symlinks=False)
            }
    return {
        "external_links": len(linked.external),
        "virtual_sources": len(linked.virtual),
        "found": len(regular),
        "dangling": len(names - regular),
        "elsewhere": len(elsewhere),
    }


def structure(path: str, target: str) -> tuple[list, object] | None:
    """The shape and dtype of the dataset at target in the HDF5 file at path, reached
    one component at a time by hard links only (`links.get_info`), never through a
    soft or external link (design D4, D6); None if it is not there that way, or is
    virtual (its shape could open its sources). No array is read."""
    with opened(path) as f:
        obj = h5py.h5g.open(f.id, b"/")
        for part in (p for p in target.split("/") if p):
            raw = part.encode()
            if not isinstance(obj, h5py.h5g.GroupID) or not obj.links.exists(raw):
                return None
            if obj.links.get_info(raw).type != h5py.h5l.TYPE_HARD:
                return None
            obj = h5py.h5o.open(obj, raw)
        if not isinstance(obj, h5py.h5d.DatasetID):
            return None
        if obj.get_create_plist().get_layout() == h5py.h5d.VIRTUAL:
            return None
        return list(obj.shape), dtype_name(obj.dtype)


def linked_data(values: dict, linked: Linked, members: dict[str, str]) -> None:
    """For each run of external links, the shape and dtype of its first target that is
    a member (name -> path), under the run's first dotted name (design D6)."""
    for dotted, files_, target in linked.runs:
        for file in files_:
            name = links.matched(file)
            if name in members:
                found = structure(members[name], target)
                if found is not None and len(values) <= MAX_ENTRIES - 2:
                    values[f"{dotted}.shape"], values[f"{dotted}.dtype"] = found
                break


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
TITLES = ("*.title", "Experiments.*.metadata.General.title")
# Without a title, the line is the file's structure (decision 316): its largest
# arrays, then a NeXus entry's start time and definition in the titled line's
# order (decision 324) and the root's file_time, a NeXus root attribute
LARGEST = 3
UNTITLED = ("*.start_time", "*.definition", "file_time")
# Before the arrays of a file without a title: a NeXus NXdetector's description,
# "name/manufacturer/model/etc. information" (NeXus manual; hdf5-links, D7, Q5)
DETECTOR = ("*.instrument.detector.description",)
# At the end of every line: the link counts of mapped_metadata, 0 left out; the
# names are ours, an exception named in TEMPLATE.md (decision 331)
COUNTS = ("external_links", "virtual_sources", "dangling", "elsewhere")
# Subjects: what names a technique, as found
TERMS = ("*.definition", "Experiments.*.metadata.Signal.signal_type")


def summary(values: dict, mapped: dict | None = None) -> list[str]:
    if headline(values, TITLES):
        line = headline(values, HEADLINE)
    else:
        line = (
            headline(values, DETECTOR)
            + arrays(values)[:LARGEST]
            + headline(values, UNTITLED)
        )
    return line + headline(mapped or {}, COUNTS)


def encoded(name: str) -> bool:
    """Whether a dotted name is in a list or tuple of HyperSpy's metadata, which
    RosettaSciIO's hspy writer stores as a dataset `_list_<key>` or a group
    `_list_<length>_<key>` (`_tuple_` alike; HierarchicalWriter.parse_structure)."""
    return any(part.startswith(("_list_", "_tuple_")) for part in name.split("."))


def arrays(values: dict) -> list[str]:
    """`<dotted path> <shape> <dtype>` of each dataset of one dimension or more whose
    shape and dtype the walk kept, the most elements first, ties in path order; in a
    HyperSpy file, not its encoded lists and tuples (decision 325)."""
    hspy = values.get("file_format") == "HyperSpy"
    found = []
    for key, shape in values.items():
        name = key.removesuffix(".shape")
        dtype = values.get(f"{name}.dtype")
        if name == key or not (isinstance(shape, list) and shape) or dtype is None:
            continue
        if not (hspy and encoded(name)):
            found.append((-math.prod(shape), name, f"{name} {shape} {dtype}"))
    return [phrase for *_, phrase in sorted(found)]


def terms(values: dict) -> list[str]:
    found = (
        v
        for k, v in values.items()
        if isinstance(v, str) and v and any(matches(p, k) for p in TERMS)
    )
    return list(dict.fromkeys(found))
