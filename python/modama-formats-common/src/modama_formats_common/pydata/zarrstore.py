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

Errors of the file system as decision 271 handles them for the crawl: a name
that is gone or a symlink (ENOENT, ELOOP, ENOTDIR) is not there for the walk;
one the file system refuses (EACCES, EPERM) is named in `unreadable` and in
the stamp, and the walk goes on; any other error (EIO, ESTALE, …) ends the
extraction and the stamp with it, which the crawl reports and tries again.
"""

import errno
import hashlib
import json
import os
import stat
from collections.abc import Callable, Iterator

from modama_crawler.formats import REFUSED
from modama_crawler.formats.values import textual

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
# Gone since the listing, or a symlink (O_NOFOLLOW): not there for the walk
GONE = frozenset({errno.ENOENT, errno.ELOOP, errno.ENOTDIR})

Skip = Callable[[str, object], bool]


def nothing(name: str, value) -> bool:
    """The skip list of a store that is not HyperSpy's: only what Walk.add refuses."""
    return False


class Unreadable(ValueError):
    """A metadata file that is not a JSON object, or nested too deeply to read."""


class _Stop(Exception):
    """The byte limit is reached."""


class Reads:
    """What a walk read: bytes, the metadata files not read for their size, and the
    paths the file system refused."""

    def __init__(self):
        self.read = 0
        self.not_read: list[str] = []
        self.refused: list[str] = []

    def failed(self, error: OSError, where: str) -> None:
        """A name the walk could not look at: gone and refused go on (refused named),
        any other error ends the walk."""
        if error.errno in REFUSED:
            self.refused.append(where)
        elif error.errno not in GONE:
            raise error


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

    def where(self, name: str) -> str:
        return f"{self.rel}/{name}" if self.rel else name


def _is_node(files: dict) -> bool:
    return V3 in files or ARRAY in files or GROUP in files


class Tree:
    """The nodes of a store, depth first, children in name order, within the bounds.

    `enter(dotted)` decides before a child folder is opened whether it is
    walked at all (a skip list's groups); `walk` counts the nodes and stops
    the tree with its cut; `too_deep` names the nodes below which nothing
    was walked.
    """

    def __init__(self, path: str, walk: Walk, reads: Reads):
        self.path = path
        self.walk = walk
        self.reads = reads
        self.enter: Callable[[str], bool] = lambda dotted: True
        self.too_deep: list[str] = []

    def nodes(self) -> Iterator[Node]:
        root = os.open(self.path, FOLDER)
        try:
            yield from self._below(Node("", 0, root, self._metadata_files(root, "")))
        finally:
            os.close(root)

    def _metadata_files(self, folder: int, rel: str) -> dict[str, os.stat_result]:
        """The metadata files of the open folder that are regular files, by lstat."""
        found = {}
        for name in METADATA:
            try:
                st = os.stat(name, dir_fd=folder, follow_symlinks=False)
            except OSError as e:
                self.reads.failed(e, f"{rel}/{name}" if rel else name)
                continue
            if stat.S_ISREG(st.st_mode):
                found[name] = st
        return found

    def _below(self, node: Node) -> Iterator[Node]:
        self.walk.objects += 1
        yield node
        if not node.descend:
            return
        if node.depth == MAX_DEPTH:
            self.too_deep.append(node.rel)
            return
        names, more = self._listing(node)
        for name in names:
            if self.walk.over():
                return
            rel = node.where(name)
            if not self.enter(rel.replace("/", ".")):
                self.walk.objects += 1  # on a skip list: not entered
                continue
            try:
                folder = os.open(name, FOLDER, dir_fd=node.folder)
            except OSError as e:
                self.reads.failed(e, rel)
                continue
            try:
                files = self._metadata_files(folder, rel)
                if _is_node(files):
                    yield from self._below(Node(rel, node.depth + 1, folder, files))
            finally:
                os.close(folder)
            if self.walk.cut:
                return
        if more:  # the walk had no room for the rest of the listing
            self.walk.cut = OBJECT_LIMIT

    def _listing(self, node: Node) -> tuple[list[str], bool]:
        """The folder's subfolders that are no symlinks, in name order, and whether the
        listing had more names than the walk has room for objects: it is read until it
        holds one name more (the HDF5 walk's rule, `hdf5.hard_links`)."""
        room = MAX_OBJECTS - self.walk.objects
        names: list[str] = []
        try:
            with os.scandir(node.folder) as listing:
                for n, entry in enumerate(listing):
                    if n > room:
                        return sorted(names), True
                    if entry.is_dir(follow_symlinks=False):
                        names.append(entry.name)
        except OSError as e:
            self.reads.failed(e, node.rel or ".")
            return [], False
        return sorted(names), False


def state(path: str) -> str:
    """A digest of the names, sizes and times of the store's metadata files, for the
    dataset's stamp (spec formats/pydata-zarr, "A change of any metadata file is
    noticed"): the nodes the extractor walks, found by lstat; only a v3 node's zarr.json
    is read, for its node_type, so that an array's folder is never listed. Bounded by
    counts only, not by time, so that the same store gives the same digest; an error
    other than gone or refused raises (walk._stamped warns)."""
    walk, reads = Walk(timed=False), Reads()
    found = []
    nodes = Tree(path, walk, reads).nodes()
    try:
        for node in nodes:
            for name, st in sorted(node.files.items()):
                found.append([node.where(name), st.st_size, st.st_mtime, st.st_ctime])
            node.descend = _group(node, reads)
    except _Stop:
        walk.cut = BYTE_LIMIT
    finally:
        nodes.close()
    return hashlib.sha256(
        json.dumps([found, reads.refused, walk.cut]).encode()
    ).hexdigest()


def _group(node: Node, reads: Reads) -> bool:
    """Whether a node is a group, from its marker files; a v3 node from its zarr.json's
    node_type, a document that cannot be read counting as no group, one not read for
    its size as a group (as the extractor takes it)."""
    if V3 not in node.files:
        return ARRAY not in node.files
    try:
        document = _read(node, V3, reads)
    except Unreadable:
        return False
    return document is None or document.get("node_type") != "array"


def _read(node: Node, name: str, reads: Reads) -> dict | None:
    """The JSON object of a metadata file of the node; None when it is over MAX_FILE
    (named in not_read, also when it grew while it was read), refused, or no longer the
    regular file the lstat saw."""
    looked = node.files[name]
    where = node.where(name)
    if looked.st_size > MAX_FILE:
        reads.not_read.append(where)
        return None
    if reads.read + looked.st_size > MAX_BYTES:
        raise _Stop
    try:
        fd = os.open(name, FILE, dir_fd=node.folder)
    except OSError as e:
        reads.failed(e, where)
        return None
    try:
        st = os.fstat(fd)
        same = (st.st_dev, st.st_ino) == (looked.st_dev, looked.st_ino)
        if not same or not stat.S_ISREG(st.st_mode):
            return None
        data = b""
        while len(data) <= MAX_FILE and (more := os.read(fd, MAX_FILE + 1)):
            data += more
    finally:
        os.close(fd)
    reads.read += len(data)
    if len(data) > MAX_FILE:
        reads.not_read.append(where)
        return None
    try:
        document = json.loads(data)
    except (ValueError, RecursionError, MemoryError) as e:
        raise Unreadable(f"{where} is not JSON: {type(e).__name__}: {e}") from None
    if not isinstance(document, dict):
        raise Unreadable(f"{where} is not a JSON object")
    return document


def _documents(node: Node, reads: Reads) -> tuple[bool, dict, dict]:
    """(is an array, its metadata document, its attributes); {} for one not read."""
    if V3 in node.files:
        document = _read(node, V3, reads) or {}
        attributes = document.get("attributes", {})
        if not isinstance(attributes, dict):
            raise Unreadable(f"{node.where(V3)}: attributes are not an object")
        return document.get("node_type") == "array", document, attributes
    marker = ARRAY if ARRAY in node.files else GROUP
    document = _read(node, marker, reads) or {}
    attributes = {}
    if ATTRIBUTES in node.files:
        attributes = _read(node, ATTRIBUTES, reads) or {}
    return marker == ARRAY, document, attributes


# Entries of a node's document not kept: its type, said by the walk's
# structure; a copy of other nodes' documents; the attributes, the node's own
# entries under its path; zarr_format, kept as found for the root and for a
# nested store of another version only
LEFT_OUT = frozenset(
    {"node_type", "consolidated_metadata", "attributes", "zarr_format"}
)


def described(path: str) -> tuple[dict, dict, dict]:
    """original_metadata and mapped_metadata of the store at path, and the shape and
    data type of its first array (the root array, else the first one level down in
    name order) as its metadata document says them, for the summary line.

    HyperSpy's skip list applies to a store whose root says it is HyperSpy's
    (file_format ZSpy), whatever its name. Raises Unreadable when the root's
    metadata cannot be read, ValueError when the root is no node, OSError on an
    error of the file system other than gone or refused.
    """
    walk, reads = Walk(), Reads()
    tree = Tree(path, walk, reads)
    skip: Skip = nothing
    unreadable: list[str] = []
    first: dict = {}
    version = None

    def add(name: str, value, flat: bool = True) -> None:
        for dotted, found in of_data(value, name) if flat else [(name, value)]:
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
                is_array, document, attributes = _documents(node, reads)
                own = document.get("zarr_format", 3 if V3 in node.files else 2)
                if not node.rel:
                    version = own
                    if attributes.get("file_format") == ZSPY:
                        skip = hyperspy
                        tree.enter = lambda dotted: not hyperspy(dotted, None)
                if not node.rel or own != version:  # a nested store of another version
                    add(join(node.dotted, "zarr_format"), own, flat=False)
                if is_array:
                    for key, value in document.items():
                        if key not in LEFT_OUT:
                            add(join(node.dotted, key), value)
                    if not first and node.depth <= 1:
                        first = {
                            "shape": document.get("shape"),
                            "dtype": document.get("data_type", document.get("dtype")),
                        }
                for key, value in attributes.items():
                    add(join(node.dotted, key), value)
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
        ("not_read", reads.not_read),
        ("unreadable", unreadable + reads.refused),
        ("too_deep", tree.too_deep),
    ):
        if paths:
            mapped[key] = paths
    return original, mapped, first


# The summary line, the one positive list (TEMPLATE.md): a HyperSpy signal's
# title, signal type and data shape, as for .hspy files (hdf5.HEADLINE); else
# the shape and data type of the root array or of the first array one level
# down, both from that array's document (@weber, 318; code review S1)
HYPERSPY = (
    "Experiments.*.metadata.General.title",
    "Experiments.*.metadata.Signal.signal_type",
    "Experiments.*.data.shape",
)
TERMS = ("Experiments.*.metadata.Signal.signal_type",)


def summary(values: dict, first: dict) -> list[str]:
    if any(matches(HYPERSPY[2], k) for k in values):
        return headline(values, HYPERSPY)
    return headline({k: v for k, v in first.items() if textual(v)}, ("shape", "dtype"))


def terms(values: dict) -> list[str]:
    found = (
        v
        for k, v in values.items()
        if isinstance(v, str) and v and any(matches(p, k) for p in TERMS)
    )
    return list(dict.fromkeys(found))
