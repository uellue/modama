"""Zarr stores, HyperSpy's .zspy among them: a bounded walk of their metadata files.

Each node's attributes and each array's metadata document, as found, under
the node's dotted path from the store's root, as the HDF5 walk names them
(spec formats/pydata-zarr). Read with Python's json, as the Zarr v2 and v3
specifications define the documents, not with zarr-python, which follows a
symlink out of the store and fails a whole group on one codec or data type
it does not know (change zarr-stores, design D1). Only metadata files are
opened and only groups listed: never a chunk, never an array's folder, never
a symlink, never anything but a regular file.
"""

import errno
import json
import os
import stat
from collections.abc import Callable

from ..structured.entries import of_data
from .values import ZSPY, Walk, headline, hyperspy, matches

V3 = "zarr.json"
ARRAY, GROUP, ATTRIBUTES = ".zarray", ".zgroup", ".zattrs"

# The bounds besides the walk's (values.Walk): a metadata file over MAX_FILE
# is not read, the walk stops after MAX_BYTES read, a group's listing is
# read up to MAX_NAMES names (proposal zarr-stores, A5)
MAX_FILE = 1 << 20
MAX_BYTES = 16 << 20
MAX_NAMES = 10_000

# Entries of a node's document said once for the store (zarr_format, in the
# mapped values), or a copy of other nodes' documents (consolidated_metadata);
# a document's attributes are the node's, under its own path
LEFT_OUT = frozenset(
    {"zarr_format", "node_type", "consolidated_metadata", "attributes"}
)

FOLDER = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
# Non-blocking, so that opening a FIFO named like a metadata file does not wait
FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
# What opening a name that is no regular file or folder of the store gives:
# absent, a symlink (O_NOFOLLOW), a file where a folder was asked for
NOT_THERE = (errno.ENOENT, errno.ELOOP, errno.ENOTDIR)

Skip = Callable[[str, object], bool]


def nothing(name: str, value) -> bool:
    """The skip list of a store that is not HyperSpy's: only what Walk.add refuses."""
    return False


class Unreadable(ValueError):
    """A metadata file that is not a JSON object."""


class _Stop(Exception):
    """The byte limit is reached."""


class _Store:
    """A walk of one store: the entries (Walk), bytes read, files and nodes not read."""

    def __init__(self):
        self.walk = Walk()
        self.read = 0
        self.not_read: list[str] = []
        self.unreadable: list[str] = []
        self.skip: Skip = nothing

    def document(self, folder: int, name: str, where: str) -> dict | None:
        """The JSON object of the metadata file `name` in the open folder; {} when it is
        over MAX_FILE (named in not_read); None when there is none: absent, a symlink,
        not a regular file. Raises Unreadable when it is not a JSON object."""
        try:
            fd = os.open(name, FILE, dir_fd=folder)
        except OSError as e:
            if e.errno in NOT_THERE:
                return None
            raise
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                return None
            if st.st_size > MAX_FILE:
                self.not_read.append(where)
                return {}
            if self.read + st.st_size > MAX_BYTES:
                self.walk.cut = f"cut at the byte limit of {MAX_BYTES >> 20} MiB"
                raise _Stop
            data = b""
            while len(data) <= MAX_FILE and (more := os.read(fd, MAX_FILE + 1)):
                data += more
        finally:
            os.close(fd)
        self.read += len(data)
        try:
            document = json.loads(data)
        except (ValueError, RecursionError) as e:
            raise Unreadable(f"{where} is not JSON: {e}") from None
        if not isinstance(document, dict):
            raise Unreadable(f"{where} is not a JSON object")
        return document

    def node(self, folder: int, rel: str) -> tuple[bool, dict, dict] | None:
        """(is an array, its metadata document, its attributes) of the open folder, or
        None when it is no node: neither zarr.json nor .zarray nor .zgroup."""
        where = f"{rel}/" if rel else ""
        if (document := self.document(folder, V3, where + V3)) is not None:
            attributes = document.get("attributes", {})
            if not isinstance(attributes, dict):
                raise Unreadable(f"{where}{V3}: attributes are not a JSON object")
            return document.get("node_type") == "array", document, attributes
        array = self.document(folder, ARRAY, where + ARRAY)
        if array is None and (group := self.document(folder, GROUP, where + GROUP)) is None:
            return None
        attributes = self.document(folder, ATTRIBUTES, where + ATTRIBUTES) or {}
        if array is not None:
            return True, array, attributes
        return False, group, attributes

    def add(self, path: str, value) -> None:
        """Every value of value under path, as the structured area flattens a document."""
        for name, found in of_data(value, path):
            if self.walk.over():
                raise _Stop
            if not self.skip(name, found):
                self.walk.add(name, found)

    def visit(self, folder: int, rel: str, dotted: str, found) -> None:
        """The node in the open folder, and below it the nodes of a group."""
        is_array, document, attributes = found
        if is_array:
            for key, value in document.items():
                if key not in LEFT_OUT:
                    self.add(f"{dotted}.{key}" if dotted else key, value)
        for key, value in attributes.items():
            self.add(f"{dotted}.{key}" if dotted else key, value)
        if is_array:
            return  # its folder holds chunks: never listed
        # Folders only, by the listing's own type (no stat), not symlinks; in
        # name order, as Zarr keeps no order of its own (zarr-python sorts too)
        names, more = [], False
        with os.scandir(folder) as listing:
            for n, entry in enumerate(listing):
                if n == MAX_NAMES:
                    more = True
                    break
                if entry.is_dir(follow_symlinks=False):
                    names.append(entry.name)
        for name in sorted(names):
            if self.walk.over():
                raise _Stop
            self.child(folder, f"{rel}/{name}" if rel else name, name,
                       f"{dotted}.{name}" if dotted else name)  # fmt: skip
        if more:
            self.walk.cut = f"cut at the listing limit of {MAX_NAMES} names"
            raise _Stop

    def child(self, folder: int, rel: str, name: str, dotted: str) -> None:
        """A subfolder of a group: walked if it is a node, not entered otherwise."""
        if self.skip(dotted, None):
            self.walk.objects += 1  # on the skip list: not entered
            return
        try:
            fd = os.open(name, FOLDER, dir_fd=folder)
        except OSError as e:
            if e.errno in NOT_THERE:
                return
            raise
        try:
            try:
                found = self.node(fd, rel)
            except Unreadable:
                self.unreadable.append(rel)
                self.walk.objects += 1
                return
            if found is None:
                return  # no node (.ipynb_checkpoints/): not entered
            self.walk.objects += 1
            self.visit(fd, rel, dotted, found)
        finally:
            os.close(fd)


def described(path: str) -> tuple[dict, dict]:
    """original_metadata and mapped_metadata of the store at path.

    HyperSpy's skip list applies to a store whose root says it is HyperSpy's
    (file_format ZSpy), whatever its name. Raises Unreadable when the root's
    metadata is not a JSON object, ValueError when the root is no node.
    """
    store = _Store()
    folder = os.open(path, FOLDER)
    try:
        found = store.node(folder, "")
        if found is None:
            raise ValueError("no zarr.json, .zarray or .zgroup at the store's root")
        if found[2].get("file_format") == ZSPY:
            store.skip = hyperspy
        try:
            store.visit(folder, "", "", found)
        except _Stop:
            pass
    finally:
        os.close(folder)
    original, cut = store.walk.result()
    mapped = {"zarr_format": found[1].get("zarr_format"), **cut}
    if store.not_read:
        mapped["not_read"] = store.not_read
    if store.unreadable:
        mapped["unreadable"] = store.unreadable
    return original, mapped


# The summary line, the one positive list (TEMPLATE.md): a HyperSpy signal's
# title, signal type and data shape, as for .hspy files (hdf5.HEADLINE); else
# the shape and data type of the root array or of the first array one level
# down (proposal zarr-stores, Q2)
HEADLINE = (
    "Experiments.*.metadata.General.title",
    "Experiments.*.metadata.Signal.signal_type",
    "Experiments.*.data.shape",
    "shape",
    "data_type",
    "dtype",
    "*.shape",
    "*.data_type",
    "*.dtype",
)
TERMS = ("Experiments.*.metadata.Signal.signal_type",)


def summary(values: dict) -> list[str]:
    if any(matches(HEADLINE[2], k) for k in values):
        return headline(values, HEADLINE[:3])
    return headline(values, HEADLINE[3:])


def terms(values: dict) -> list[str]:
    found = (
        v
        for k, v in values.items()
        if isinstance(v, str) and v and any(matches(p, k) for p in TERMS)
    )
    return list(dict.fromkeys(found))
