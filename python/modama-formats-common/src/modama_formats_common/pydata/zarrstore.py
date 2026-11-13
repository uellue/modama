"""Zarr stores, HyperSpy's .zspy among them: a bounded walk of their metadata files.

Each node's attributes and each array's metadata document, as found, under
the node's dotted path from the store's root, as the HDF5 walk names them
(spec formats/pydata-zarr). Read with Python's json, as the Zarr v2 and v3
specifications define the documents, not with zarr-python (decision of
2026-11-13, 323; change zarr-stores, design D1): zarr-python 3.4.2 follows a
group that is a symlink out of the store and returns that folder's
attributes, and fails a whole group's listing on one codec or v3 data type it
does not know. Here a name is looked at with lstat before it is opened, only
folders and regular files are opened, never through a symlink, and only the
metadata files of nodes and the folders of groups: never a chunk, never an
array's folder.
"""

import hashlib
import json
import os
import stat
from collections.abc import Callable, Iterator

from ..structured.entries import of_data
from .values import MAX_OBJECTS, ZSPY, Walk, headline, hyperspy, matches

V3 = "zarr.json"
ARRAY, GROUP, ATTRIBUTES = ".zarray", ".zgroup", ".zattrs"
METADATA = (V3, ARRAY, GROUP, ATTRIBUTES)

# The bounds besides the walk's (values.Walk: entries, objects, time; a
# group's listing by the HDF5 walk's room rule): a metadata file over
# MAX_FILE is not read, the walk stops after MAX_BYTES read, and nodes below
# MAX_DEPTH are not walked, as each level holds an open folder (@weber, 320)
MAX_FILE = 1 << 20
MAX_BYTES = 16 << 20
MAX_DEPTH = 100
OBJECT_LIMIT = f"cut at the object limit of {MAX_OBJECTS}"  # as values.Walk says it
BYTE_LIMIT = f"cut at the byte limit of {MAX_BYTES >> 20} MiB"

FOLDER = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
# Non-blocking: a FIFO swapped in after the lstat must not make the open wait
FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC

Skip = Callable[[str, object], bool]


def nothing(name: str, value) -> bool:
    """The skip list of a store that is not HyperSpy's: only what Walk.add refuses."""
    return False


class Unreadable(ValueError):
    """A metadata file that is not a JSON object, or nested too deeply to read."""


class Node:
    """A folder of the store holding zarr.json, .zarray or .zgroup.

    `files` are its metadata files that are regular files, with their lstat;
    `folder` is the open folder, valid until the walk goes on. The walk lists
    and enters it after the caller has looked at it only if `descend` is set.
    """

    def __init__(self, rel: str, depth: int, folder: int, files: dict):
        self.rel = rel  # "" for the store's root, else "a/b"
        self.depth = depth
        self.folder = folder
        self.files: dict[str, os.stat_result] = files
        self.descend = False

    @property
    def dotted(self) -> str:
        return self.rel.replace("/", ".")


def _metadata_files(folder: int) -> dict[str, os.stat_result]:
    """The metadata files of the open folder that are regular files, by lstat."""
    found = {}
    for name in METADATA:
        try:
            st = os.stat(name, dir_fd=folder, follow_symlinks=False)
        except OSError:
            continue  # absent, or not to be looked at: not there for the walk
        if stat.S_ISREG(st.st_mode):
            found[name] = st
    return found


def _is_node(files: dict) -> bool:
    return V3 in files or ARRAY in files or GROUP in files


class Tree:
    """The nodes of a store, depth first, children in name order, within the bounds.

    `enter(dotted)` decides before a child folder is opened whether it is
    walked at all (a skip list's groups); `walk` counts the nodes and stops
    the tree with its cut; `too_deep` names the nodes below which nothing
    was walked.
    """

    def __init__(self, path: str, walk: Walk):
        self.path = path
        self.walk = walk
        self.enter: Callable[[str], bool] = lambda dotted: True
        self.too_deep: list[str] = []

    def nodes(self) -> Iterator[Node]:
        root = os.open(self.path, FOLDER)
        try:
            yield from self._below(Node("", 0, root, _metadata_files(root)))
        finally:
            os.close(root)

    def _below(self, node: Node) -> Iterator[Node]:
        self.walk.objects += 1
        yield node
        if not node.descend:
            return
        if node.depth == MAX_DEPTH:
            self.too_deep.append(node.rel)
            return
        names, more = self._listing(node.folder)
        for name in names:
            if self.walk.over():
                return
            rel = f"{node.rel}/{name}" if node.rel else name
            if not self.enter(rel.replace("/", ".")):
                self.walk.objects += 1  # on a skip list: not entered
                continue
            try:
                folder = os.open(name, FOLDER, dir_fd=node.folder)
            except OSError:
                continue  # gone, or a symlink since the listing: not walked
            try:
                files = _metadata_files(folder)
                if _is_node(files):
                    yield from self._below(Node(rel, node.depth + 1, folder, files))
            finally:
                os.close(folder)
            if self.walk.cut:
                return
        if more:  # the walk had no room for the rest of the listing
            self.walk.cut = OBJECT_LIMIT

    def _listing(self, folder: int) -> tuple[list[str], bool]:
        """The folder's subfolders that are no symlinks, in name order, and whether the
        listing had more names than the walk has room for objects: it is read until it
        holds one name more (the HDF5 walk's rule, `hdf5.hard_links`)."""
        room = MAX_OBJECTS - self.walk.objects
        names: list[str] = []
        with os.scandir(folder) as listing:
            for n, entry in enumerate(listing):
                if n > room:
                    return sorted(names), True
                if entry.is_dir(follow_symlinks=False):
                    names.append(entry.name)
        return sorted(names), False


def state(path: str) -> str:
    """A digest of the names, sizes and times of the store's metadata files, for the
    dataset's stamp (spec formats/pydata-zarr, "A change of any metadata file is
    noticed"): the nodes the extractor walks, found by lstat; only a v3 node's zarr.json
    is read, for its node_type, so that an array's folder is never listed."""
    walk, budget = Walk(), _Budget()
    found = []
    nodes = Tree(path, walk).nodes()
    try:
        for node in nodes:
            for name, st in sorted(node.files.items()):
                rel = f"{node.rel}/{name}" if node.rel else name
                found.append([rel, st.st_size, st.st_mtime, st.st_ctime])
            node.descend = _group(node, budget)
    except _Stop:
        walk.cut = BYTE_LIMIT
    except OSError as e:  # the store went away or cannot be opened: a stamp of its own
        found.append(["error", e.errno])
    finally:
        nodes.close()
    return hashlib.sha256(json.dumps([found, walk.cut]).encode()).hexdigest()


def _group(node: Node, budget: "_Budget") -> bool:
    """Whether a node is a group, from its marker files; a v3 node from its zarr.json's
    node_type, a document that cannot be read counting as no group, one not read for
    its size as a group (as the extractor takes it)."""
    if V3 not in node.files:
        return ARRAY not in node.files
    try:
        document = _read(node, V3, budget)
    except Unreadable:
        return False
    return document is None or document.get("node_type") != "array"


class _Stop(Exception):
    """The byte limit is reached."""


class _Budget:
    """Bytes read so far, and the metadata files not read for their size."""

    def __init__(self):
        self.read = 0
        self.not_read: list[str] = []


def _read(node: Node, name: str, budget: _Budget) -> dict | None:
    """The JSON object of a metadata file of the node; None when it is over MAX_FILE
    (named in not_read) or no longer the regular file the lstat saw."""
    looked = node.files[name]
    where = f"{node.rel}/{name}" if node.rel else name
    if looked.st_size > MAX_FILE:
        budget.not_read.append(where)
        return None
    if budget.read + looked.st_size > MAX_BYTES:
        raise _Stop
    try:
        fd = os.open(name, FILE, dir_fd=node.folder)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        same = (st.st_dev, st.st_ino) == (looked.st_dev, looked.st_ino)
        if not same or not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE:
            return None
        data = b""
        while len(data) <= MAX_FILE and (more := os.read(fd, MAX_FILE + 1)):
            data += more
    finally:
        os.close(fd)
    budget.read += len(data)
    try:
        document = json.loads(data)
    except (ValueError, RecursionError, MemoryError) as e:
        raise Unreadable(f"{where} is not JSON: {type(e).__name__}: {e}") from None
    if not isinstance(document, dict):
        raise Unreadable(f"{where} is not a JSON object")
    return document


def _documents(node: Node, budget: _Budget) -> tuple[bool, dict, dict]:
    """(is an array, its metadata document, its attributes); {} for one not read."""
    if V3 in node.files:
        document = _read(node, V3, budget) or {}
        attributes = document.get("attributes", {})
        if not isinstance(attributes, dict):
            raise Unreadable(f"{node.rel or '.'}/{V3}: attributes are not an object")
        return document.get("node_type") == "array", document, attributes
    marker = ARRAY if ARRAY in node.files else GROUP
    document = _read(node, marker, budget) or {}
    attributes = {}
    if ATTRIBUTES in node.files:
        attributes = _read(node, ATTRIBUTES, budget) or {}
    return marker == ARRAY, document, attributes


# Entries of a node's document not kept: its type, said by the walk's
# structure; a copy of other nodes' documents; the attributes, the node's own
# entries under its path (and zarr_format, but for the root's and that of a
# nested store of another version)
LEFT_OUT = frozenset({"node_type", "consolidated_metadata", "attributes"})


def described(path: str) -> tuple[dict, dict]:
    """original_metadata and mapped_metadata of the store at path.

    HyperSpy's skip list applies to a store whose root says it is HyperSpy's
    (file_format ZSpy), whatever its name. Raises Unreadable when the root's
    metadata cannot be read, ValueError when the root is no node.
    """
    walk, budget = Walk(), _Budget()
    tree = Tree(path, walk)
    skip: Skip = nothing
    unreadable: list[str] = []
    version = None

    def add(name: str, value) -> None:
        for dotted, found in of_data(value, name):
            if walk.over():
                raise _Stop
            if not skip(dotted, found):
                walk.add(dotted, found)

    def join(dotted: str, key: str) -> str:
        return f"{dotted}.{key}" if dotted else key

    nodes = tree.nodes()
    try:
        for node in nodes:
            if not node.rel and not _is_node(node.files):
                raise ValueError("no zarr.json, .zarray or .zgroup at the store's root")
            try:
                is_array, document, attributes = _documents(node, budget)
                pairs = [
                    (join(node.dotted, k), v)
                    for k, v in document.items()
                    if is_array and k not in LEFT_OUT and k != "zarr_format"
                ]
                own = document.get("zarr_format", version)
                if node.rel and own != version:  # a nested store of another version
                    pairs.append((join(node.dotted, "zarr_format"), own))
                pairs += [(join(node.dotted, k), v) for k, v in attributes.items()]
                if not node.rel:
                    version = document.get("zarr_format", 3 if V3 in node.files else 2)
                    pairs.insert(0, ("zarr_format", version))
                    if attributes.get("file_format") == ZSPY:
                        skip = hyperspy
                        tree.enter = lambda dotted: not hyperspy(dotted, None)
                for name, value in pairs:
                    add(name, value)
            except (Unreadable, RecursionError, MemoryError) as e:
                if not node.rel:
                    raise Unreadable(str(e)) from None
                unreadable.append(node.rel)
                continue
            node.descend = not is_array
    except _Stop:
        walk.cut = walk.cut or BYTE_LIMIT
    finally:
        nodes.close()
    original, cut = walk.result()
    mapped = dict(cut)
    for key, paths in (
        ("not_read", budget.not_read),
        ("unreadable", unreadable),
        ("too_deep", tree.too_deep),
    ):
        if paths:
            mapped[key] = paths
    return original, mapped


# The summary line, the one positive list (TEMPLATE.md): a HyperSpy signal's
# title, signal type and data shape, as for .hspy files (hdf5.HEADLINE); else
# the shape and data type of the root array or of the first array one level
# down (@weber, 318)
HYPERSPY = (
    "Experiments.*.metadata.General.title",
    "Experiments.*.metadata.Signal.signal_type",
    "Experiments.*.data.shape",
)
PLAIN = ("shape", "data_type", "dtype", "*.shape", "*.data_type", "*.dtype")
TERMS = ("Experiments.*.metadata.Signal.signal_type",)


def summary(values: dict) -> list[str]:
    if any(matches(HYPERSPY[2], k) for k in values):
        return headline(values, HYPERSPY)
    return headline(values, PLAIN)


def terms(values: dict) -> list[str]:
    found = (
        v
        for k, v in values.items()
        if isinstance(v, str) and v and any(matches(p, k) for p in TERMS)
    )
    return list(dict.fromkeys(found))
