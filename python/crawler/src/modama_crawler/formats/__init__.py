"""Formats: what a dataset type is, and how the core runs formats on one directory.

A format is a class with `type`, `priority`, `reacts_to`, `collection` and
`recognize(directory)`. The core calls it twice per directory: before
descending, with names and sizes only (a collapse format may answer and end
the descent), and after the subdirectories are final, with entries, their
MIME types and the subdirectories' datasets. See design/architecture.md A, B, D.
"""

from __future__ import annotations

import errno
import hashlib
import json
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from .. import files, mime
from ..files import BudgetExceeded

if TYPE_CHECKING:
    from ..inspection import Inspected, Inspector

log = logging.getLogger(__name__)

DIRECTORY = "directory"  # in reacts_to: run on every directory, pre- and post-order

# The file system's answers about a path: the crawler may not see it, or it is
# gone. Every other error means it did not answer (change listing-errors, D1)
NOT_VISIBLE = frozenset({errno.EACCES, errno.EPERM, errno.ENOENT, errno.ENOTDIR})
REFUSED = frozenset({errno.EACCES, errno.EPERM})

# The end of every warning about a file two formats want (Directory.claimed_elsewhere):
# the marker that lists them all, to develop resolution rules (decision 344)
WANTED_TWICE = "two formats want it"
# In every warning about a file whose inspection failed, timed out or killed its
# process, and only there: it is tried again next crawl (Directory.inspect,
# decision 340). A file over its read limit is not tried again and not so marked
NOT_INSPECTED = "not inspected"
# What a format may read of one file in one call, through either reader, unless it
# declares more (Format.read_limit); past FLAG_PER_FILE it is flagged for review, in
# a warning with the marker READ_MUCH; a file over the limit is refused, in a warning
# with the marker OVER_LIMIT (change read-limit-per-file)
LIMIT_PER_FILE = 1 << 20
FLAG_PER_FILE = 64 << 10
READ_MUCH = "read more than 64 KiB"
OVER_LIMIT = "over its read limit"


def not_visible(err: OSError) -> bool:
    """Whether the file system says the path is refused or gone; an entry that is no
    longer a regular file is gone for the crawl, as the walk skips such entries."""
    return isinstance(err, files.NotRegular) or err.errno in NOT_VISIBLE


def errno_name(err: OSError) -> str:
    """`EIO`, or the number, or `no errno`."""
    if err.errno is None:
        return "no errno"
    return errno.errorcode.get(err.errno, str(err.errno))


@dataclass(frozen=True)
class Entry:
    name: str
    path: str  # absolute, for reading
    rel: str  # relative to the root, with a leading "/"
    kind: str  # "file" or "dir"; symlinks and special files never reach a format
    size: int
    mtime: float
    ctime: float
    uid: int
    mime: str | None = None  # None in the pre-order call


@dataclass(frozen=True)
class Extracted:
    """What an extractor found in a dataset's files (D2). Plain JSON values only: it is stored as JSONB."""

    summary: list[str]  # ordered "key value" phrases, the start of the description
    subjects: list[str]  # short terms: technique, instrument
    values: dict  # stored with the dataset for later use, not rendered


@dataclass(frozen=True)
class Extraction:
    """Which extractor ran on a dataset in which state of its files, under which installation, and its outcome (D3)."""

    extractor: str  # the format id
    identity: (
        str  # the extractor identity of the installation (modama_crawler.identity)
    )
    stamp: str  # the dataset's stamp when it ran
    extracted: Extracted | None = None  # None: failed, or nothing to extract
    error: str | None = None  # a failure is never reused: the next crawl runs again
    seconds: float = 0.0


@dataclass(frozen=True)
class Dataset:
    anchor: str  # root-relative path; the directory itself for directory datasets
    members: tuple[str, ...] = ()  # files of the directory, root-relative
    parts: tuple[str, ...] = ()  # anchors of adopted child datasets
    basis: str = ""
    warnings: tuple[str, ...] = ()
    collapsed: bool = False  # the subtree below the anchor was not visited
    # Filled by the core:
    type: str = ""
    format: str = ""  # collection/format
    version: str = ""
    parent: str | None = None
    mtime: float = 0.0  # newest mtime of members and parts
    uid: int = 0  # owner of the anchor
    size: int = 0  # total st_size of the members
    stamp: str = (
        ""  # digest of the members' names, sizes and times, and of the parts' stamps
    )
    directory: str = ""  # the directory whose recognition produced it
    extraction: Extraction | None = (
        None  # set after the walk, for formats with an extractor
    )
    # Kept from the index because the file system did not answer; not stored (listing-errors D7)
    kept: bool = False


@dataclass
class Unanswered:
    """A folder whose stored datasets a crawl kept because the file system did not answer (listing-errors D2, D3)."""

    folder: str
    path: str  # what failed: the folder, or an entry or file in it
    errno: str  # errno_name()
    reason: str  # the error's text
    whole: bool  # the folder's stored subtree is kept, else its own datasets
    kept: int = 0  # datasets kept, set after the walk
    # the error itself, raised when the folder is the walk's start (review of the code, 2)
    error: OSError | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class Listing:
    """A directory as the walk last saw it: a digest of its listing, and the warnings its recognition gave (D3)."""

    digest: str
    pre: tuple[tuple[str, str], ...] = ()  # warnings of the pre-order call
    post: tuple[tuple[str, str], ...] = ()  # of MIME detection and the post-order call
    # Recognition met the environment (a read error): the
    # directory is not taken over, the next crawl recognises it again
    retry: bool = False


@dataclass
class Result:
    datasets: list[Dataset] = field(default_factory=list)
    warnings: list[tuple[str, str]] = field(default_factory=list)  # (path, text)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (path, reason)
    unchanged: int = 0  # directories whose datasets were taken over from the last crawl
    listings: dict[str, Listing] = field(default_factory=dict)  # every directory listed
    # Folders the file system did not answer, by path (listing-errors D2, D3)
    unanswered: list[Unanswered] = field(default_factory=list)
    # (folder, errno name, stored datasets removed) of refused folders that had some (D10)
    refused: list[tuple[str, str, int]] = field(default_factory=list)

    def all_warnings(self) -> list[tuple[str, str]]:
        """The walk's warnings and those carried by datasets, in path order."""
        return sorted(
            list(self.warnings)
            + [(d.anchor, text) for d in self.datasets for text in d.warnings]
        )

    def to_json(self) -> dict:
        datasets = sorted(self.datasets, key=lambda d: d.anchor)
        return {
            "datasets": [
                {
                    "anchor": d.anchor,
                    "type": d.type,
                    "members": list(d.members),
                    "parts": list(d.parts),
                    "format": d.format,
                    "basis": d.basis,
                    "warnings": list(d.warnings),
                    "parent": d.parent,
                    "collapsed": d.collapsed,
                }
                for d in datasets
            ],
            "warnings": [list(w) for w in sorted(self.warnings)],
            "skipped": [list(s) for s in sorted(self.skipped)],
        }


class Directory:
    """What a format sees: plain data plus one bounded reader."""

    def __init__(
        self,
        rel: str,
        path: str,
        entries: list[Entry],
        children: list[Dataset],
        phase: str,
        uid: int,
        mtime: float,
    ):
        self.rel = rel
        self.path = path
        self.entries = entries
        self.children = children  # datasets of subdirectories without a parent yet
        self.phase = phase  # "pre" or "post"
        self.uid = uid
        self.mtime = mtime
        self.warnings: list[tuple[str, str]] = []
        self._by_name = {e.name: e for e in entries}
        # Of the format being called (_call): its limit per file, the bytes read of
        # each file rel, the files refused
        self._limit = LIMIT_PER_FILE
        self._read: dict[str, int] = {}
        self._refused: set[str] = set()
        self.retry = False  # a format met a read error
        # (file rel, error) of the first read the file system did not answer, whatever
        # the format made of it: the crawl keeps the stored datasets (listing-errors D2, D3)
        self.unanswered: tuple[str, OSError] | None = None
        # File rel -> "<format>: not <type>, <reason>", from not_of_type; goes into the basis
        self.notes: dict[str, str] = {}
        # File rel -> "<format>: <text>", from note: also into the basis, the type kept
        self.remarks: dict[str, str] = {}
        # File name -> id of the format that claimed it, for the formats after it,
        # which are not offered the file (bug 311, decision 344)
        self.claimed: dict[str, str] = {}
        self._format = ""  # the id of the format being called
        # The crawl's pool for inspect, set by the walk; without it, a pool of the call's own
        self.inspector: Inspector | None = None

    @property
    def name(self) -> str:
        return PurePosixPath(self.rel).name

    def entry(self, name: str) -> Entry | None:
        return self._by_name.get(name)

    def of_type(self, mime: str) -> list[Entry]:
        return [e for e in self.entries if e.mime == mime]

    def read(self, entry: Entry, n: int) -> bytes:
        """The first n bytes of an entry of this directory, within the calling format's read limit per file.

        The bytes read of each file are counted per format call, as
        files.Counted counts them: past FLAG_PER_FILE the crawl warns once,
        with READ_MUCH; a read that would take them past the limit is refused
        before it reads, with a warning naming the file and OVER_LIMIT, and so
        is every later read of that file in the call. The refusal is a
        BudgetExceeded, an OSError: the format skips the file as one it cannot
        read (cannot_read), and the file stays as it would be without the
        format. Not tried again: the same file gives the same outcome (change
        read-limit-per-file).
        """
        if self._by_name.get(entry.name) is not entry:
            raise ValueError(f"{entry.rel} is not an entry of {self.rel}")
        done = self._read.get(entry.rel, 0)
        if entry.rel in self._refused or done + n > self._limit:
            if entry.rel not in self._refused:
                self._refused.add(entry.rel)
                self.warn(
                    entry.rel,
                    f"{self._format}: {entry.name} {OVER_LIMIT} of {self._limit} bytes "
                    f"({n} asked for after {done}); not read further",
                )
            raise BudgetExceeded(
                f"reading {n} bytes of {entry.rel} after {done} exceeds its read "
                f"limit of {self._limit} bytes"
            )
        try:
            # Unbuffered, as in mime.detect_with_tie: read n bytes, not a whole
            # buffer; never through a symlink the entry may have become since
            # its listing (hdf5-links, design D4)
            with files.Counted(files.regular(entry.path), name=entry.rel) as f:
                data = f.read(n)
        except OSError as e:
            # noted here, so that it counts also when the format catches it (review 3)
            self.did_not_answer(entry.rel, e)
            raise
        self._read[entry.rel] = done + len(data)
        if done <= FLAG_PER_FILE < done + len(data):
            self.warn(entry.rel, f"{self._format}: {READ_MUCH} of {entry.name}")
        return data

    def inspect(self, entries: list[Entry], fn: Callable) -> dict[str, Inspected]:
        """fn(file object) for each entry, in worker processes; the outcome per entry rel.

        Each file is opened only as a regular file, never through a symlink,
        read through a file object with the calling format's read limit per
        file (change read-limit-per-file), and given the
        inspector's time limit, enforced from outside (change hdf5-links,
        design D5). A read the file system did not answer is noted
        (did_not_answer); a function that fails, times out or kills its
        process leaves a warning with NOT_INSPECTED, and the directory is
        recognised again next crawl (decision 340); a file over the limit
        leaves a warning with OVER_LIMIT, not NOT_INSPECTED: the same file gives the same
        outcome, so it is not tried again. fn is a module-level function
        returning plain data. Only in the post-order call: the pre-order call
        has names and sizes only, and no pool of the crawl.
        """
        from ..inspection import OVER_BUDGET, RETRIED, STOPPED, UNANSWERED, Inspector

        if self.phase != "post":
            raise ValueError(f"{self.rel}: inspect in the post-order call only")
        for e in entries:
            if self._by_name.get(e.name) is not e:
                raise ValueError(f"{e.rel} is not an entry of {self.rel}")
        if not entries:
            return {}
        inspector = self.inspector or Inspector()
        try:
            got = inspector.run(fn, [e.path for e in entries], self._limit)
        finally:
            if inspector is not self.inspector:
                inspector.close()
        for e, x in zip(entries, got, strict=True):
            if x.kind == UNANSWERED:
                self.did_not_answer(e.rel, OSError(x.errno, x.detail, e.path))
            elif x.kind == STOPPED:
                self.retry = True  # the crawl is stopping: nothing of it is final
            elif x.kind in RETRIED:
                self.retry = True
                self.warn(
                    e.rel,
                    f"{self._format}: {e.name} {NOT_INSPECTED}, {x.kind} "
                    f"({x.detail}); tried again next crawl",
                )
            elif x.kind == OVER_BUDGET:
                self.warn(
                    e.rel,
                    f"{self._format}: {e.name} {OVER_LIMIT} of {self._limit} bytes; "
                    "not read further",
                )
        return {e.rel: x for e, x in zip(entries, got, strict=True)}

    def did_not_answer(self, rel: str, error: OSError) -> None:
        """Note the first error of the "did not answer" class (listing-errors D1); a read refused over the limit is not one."""
        if isinstance(error, BudgetExceeded):
            return
        if self.unanswered is None and not not_visible(error):
            self.unanswered = (rel, error)

    def not_of_type(self, entry: Entry, reason: str) -> Entry:
        """Say that a file is not of the type its name gave it; returns its entry with the type detection gives without it.

        Only a type from the one best name rule is dropped; any other stays,
        with a warning (spec recognition, recognition-checks-content D1, D2).
        Finding the new type is not charged to the read limit (decision 166);
        a read error keeps the type (cannot_read), so that one unreadable file
        does not change the rest of the directory's result.
        """
        if self.phase != "post":
            raise ValueError(f"{entry.rel}: no types in the pre-order call")
        if self._by_name.get(entry.name) is not entry:
            raise ValueError(f"{entry.rel} is not an entry of {self.rel}")
        if mime.by_name(entry.name) != entry.mime:
            self.warn(
                entry.rel,
                f"{self._format}: {entry.name} is not {entry.mime} ({reason}), but that "
                "type does not come from its name alone; type kept",
            )
            return entry
        try:
            new, tie = mime.detect_with_tie(
                entry.path, exclude=frozenset({entry.mime}), strict=True
            )
        except OSError as e:
            self.cannot_read(entry, e)
            return entry
        if tie:  # as the walk reports a tie
            self.warn(
                entry.rel, f"type is ambiguous between {', '.join(tie)}; using {new}"
            )
        replaced = replace(entry, mime=new)
        self.entries = [replaced if e is entry else e for e in self.entries]
        self._by_name[entry.name] = replaced
        self.notes[entry.rel] = f"{self._format}: not {entry.mime}, {reason}"
        return replaced

    def note(self, entry: Entry, text: str) -> None:
        """A note for the basis of the dataset that holds the file, its type kept: a file of interest (decisions 174, 183)."""
        if self._by_name.get(entry.name) is not entry:
            raise ValueError(f"{entry.rel} is not an entry of {self.rel}")
        self.remarks[entry.rel] = f"{self._format}: {text}"

    def cannot_read(self, entry: Entry, error: OSError) -> None:
        """A file a format could not check: it keeps its type, the crawl warns at it, and the directory is recognised again next crawl.

        For a read error on one file while checking it, so that the rest of the
        format's result stands (spec recognition, "A read error on one file").
        A read refused over the read limit keeps the type too, but read has
        warned already, and it is not tried again (change read-limit-per-file).
        """
        if isinstance(error, BudgetExceeded):
            return
        self.warn(
            entry.rel,
            f"{self._format}: cannot read {entry.name}: {error.strerror or error}; "
            "type kept",
        )
        self.retry = True
        self.did_not_answer(entry.rel, error)

    def warn(self, rel: str, text: str) -> None:
        self.warnings.append((rel, text))

    def claimed_elsewhere(self, rel: str, name: str) -> None:
        """Warn at rel that the file name, which the calling format's dataset needs, is claimed by a format that ran earlier.

        In one fixed wording ending in WANTED_TWICE, so that one grep or query
        lists every such case for review (decision 344).
        """
        self.warn(
            rel,
            f"{self._format}: {name} is claimed by {self.claimed[name]}; {WANTED_TWICE}",
        )


class Format:
    type: str = ""
    priority: int = 50
    reacts_to: frozenset[str] = frozenset()
    collection: bool = False
    version: str = "1"
    name: str = ""  # set by Collection: the class name, lowercased, unless given
    id: str = ""  # set by Collection: collection/name
    display_name: str = ""  # for dc:subject; default: MIME type's comment, else id
    # Bytes recognition may read of one file in one call; a format that needs more
    # declares it here, an explicit number for review (change read-limit-per-file)
    read_limit: int = LIMIT_PER_FILE

    def recognize(self, directory: Directory) -> Iterable[Dataset]:
        return ()

    def extract(self, dataset: Dataset, root: str) -> Extracted | None:
        """Metadata from the files of one of this format's datasets; a format without one doesn't override it (D2).

        Runs in a worker process after the walk, with a time limit, without
        database access. A member's path on disk is `root + member`; it reads
        the dataset's members only, or, for a collapsed dataset, which has
        none, what `collapsed_state` covers below its anchor. May raise: the
        dataset then keeps a basic description and the crawl a warning, and
        the next crawl tries again. Its result is reused while the files and
        the installation are the same (the extractor identity); there is no
        version to raise.
        """
        return None

    def collapsed_state(self, path: str) -> str | None:
        """For a collapsed dataset of this format at `path` on disk: a digest of the files
        below it that its extractor reads, for the dataset's stamp; None: the folder's
        listing alone stamps it. Runs in the walk at every crawl, also when the
        folder's listing is unchanged (change zarr-stores, 319). The same files must
        give the same digest. May raise: the crawl then warns, naming the format, and
        stamps the dataset with a fixed marker instead (walk._stamped)."""
        return None

    @property
    def has_extractor(self) -> bool:
        return type(self).extract is not Format.extract


@dataclass
class Collection:
    name: str
    formats: list[Format]
    mime_files: tuple[Path, ...] = ()

    def __post_init__(self):
        for f in self.formats:
            f.name = f.name or type(f).__name__.lower()
            f.id = f"{self.name}/{f.name}"


# Per format call. A call slower than SLOW is logged and keeps its result, since
# the time depends on the load (stopping a call that hangs is deferred to worker
# subprocesses, architecture G). Reads are bounded per file (Format.read_limit).
SLOW = 5.0


def ordered(formats: Iterable[Format]) -> list[Format]:
    return sorted(formats, key=lambda f: (-f.priority, f.id))


def _call(fmt: Format, d: Directory, slow: float) -> list[Dataset]:
    d._limit, d._read, d._refused = fmt.read_limit, {}, set()
    d._format = fmt.id
    # A discarded call leaves every type as it was, and its warnings go with
    # its result (D3): not_of_type replaces the list, so the old one is the
    # state before the call
    entries, notes, warned = d.entries, dict(d.notes), len(d.warnings)
    remarks = dict(d.remarks)
    start = time.monotonic()
    try:
        datasets = list(fmt.recognize(d))
    except Exception as e:  # noqa: BLE001  a failing format must not stop the crawl
        d.entries, d.notes, d.remarks = entries, notes, remarks
        d._by_name = {x.name: x for x in entries}
        del d.warnings[warned:]
        if isinstance(e, BudgetExceeded):
            # A refused read the format did not catch: a bug of the format, which
            # loses its result for the folder (change read-limit-per-file, D2)
            d.warn(d.rel, f"{fmt.id} skipped: {e}")
        else:
            d.warn(d.rel, f"{fmt.id} failed: {e!r}")
            d.retry = d.retry or isinstance(e, OSError)
            if isinstance(e, OSError):
                d.did_not_answer(d.rel, e)
        return []
    elapsed = time.monotonic() - start
    if elapsed > slow:
        log.warning(
            "%s: %s took %.1f s (slow: over %g s)", d.rel, fmt.id, elapsed, slow
        )
    return datasets


def _fill(
    ds: Dataset,
    fmt: Format,
    d: Directory,
    mtime: float,
    uid: int,
    files: dict[str, Entry] | None = None,
    children: dict[str, Dataset] | None = None,
) -> Dataset:
    """The core's fields of a format's dataset. run_post passes its maps of the
    directory's files and children: built here for each dataset, they made a
    folder of n datasets take time n² (review of em-de, M2)."""
    members = tuple(
        sorted(set(ds.members) | ({ds.anchor} if ds.anchor != d.rel else set()))
    )
    if files is None:
        files = {e.rel: e for e in d.entries}
    if children is None:
        children = {c.anchor: c for c in d.children}
    return replace(
        ds, members=members, type=fmt.type, format=fmt.id, version=fmt.version,
        mtime=mtime, uid=uid, size=sum(files[m].size for m in members if m in files),
        stamp=stamp([files[m] for m in members if m in files],
                    [children[p].stamp for p in ds.parts if p in children]),
        directory=d.rel,
    )  # fmt: skip


def stamp(members: Iterable[Entry], part_stamps: Iterable[str] = ()) -> str:
    """A digest of the members' names, sizes and times and the parts' stamps: equal stamps, unchanged files (D3)."""
    state = [[e.rel, e.size, e.mtime, e.ctime] for e in members]
    return hashlib.sha256(json.dumps([state, list(part_stamps)]).encode()).hexdigest()


def run_pre(d: Directory, formats: Iterable[Format], slow: float) -> Dataset | None:
    """The pre-order call: the first collapsed dataset for the directory itself wins."""
    for fmt in ordered(formats):
        if DIRECTORY not in fmt.reacts_to:
            continue
        for ds in _call(fmt, d, slow):
            if ds.collapsed and ds.anchor == d.rel:
                return _fill(ds, fmt, d, d.mtime, d.uid)
            d.warn(
                d.rel,
                f"{fmt.id}: ignored a pre-order dataset that doesn't collapse {d.rel}",
            )
    return None


def run_post(
    d: Directory, formats: Iterable[Format], slow: float
) -> tuple[list[Dataset], dict[str, str]]:
    """The post-order call. Returns the directory's datasets and the adoptions (child anchor -> parent anchor).

    A format may drop a file's name type (Directory.not_of_type): the formats
    after it see the new type, and the file's dataset carries the note in its
    basis (recognition-checks-content D3, D4). A claimed file or child dataset
    is not offered to the formats after the one that claimed it, so none of
    them can drop its type (spec recognition, exclusive claims).
    """
    files = {e.rel: e for e in d.entries if e.kind == "file"}
    children = {c.anchor: c for c in d.children}
    claimed_by: dict[str, str] = {}  # file rel or child anchor -> format id
    out: list[Dataset] = []
    adoptions: dict[str, str] = {}
    order = ordered(formats)
    for i, fmt in enumerate(order):
        present = {e.mime for e in d.entries if e.mime}
        if DIRECTORY not in fmt.reacts_to and not (fmt.reacts_to & present):
            continue
        before = set(d.notes)
        datasets = _call(fmt, d, slow)
        _check_order(d, order[:i], fmt, set(d.notes) - before)
        for ds in datasets:
            members = set(ds.members) | ({ds.anchor} if ds.anchor in files else set())
            parts = set(ds.parts) | ({ds.anchor} if ds.anchor in children else set())
            if (
                ds.anchor != d.rel
                and ds.anchor not in members
                and ds.anchor not in parts
            ):
                d.warn(
                    ds.anchor,
                    f"{fmt.id}: anchor is not a member, a part or the directory",
                )
                continue
            outside = [m for m in members if m not in files] + [
                p for p in parts if p not in children
            ]
            if outside:
                d.warn(
                    ds.anchor,
                    f"{fmt.id}: claim outside {d.rel} rejected: {', '.join(sorted(outside))}",
                )
                continue
            # The directory itself is claimable too: two formats anchoring at it
            # would produce two datasets with one anchor, which the index rejects
            claims = members | parts | ({d.rel} if ds.anchor == d.rel else set())
            taken = [(x, claimed_by[x]) for x in sorted(claims) if x in claimed_by]
            if taken:
                d.warn(
                    ds.anchor,
                    f"{fmt.id}: {taken[0][0]} already claimed by {taken[0][1]}",
                )
                continue
            warnings = ds.warnings
            if parts and not fmt.collection:
                warnings += (
                    f"{fmt.id} is not a collection type but adopts {', '.join(sorted(parts))}",
                )
            if ds.parent is not None or ds.collapsed:
                warnings += (f"{fmt.id}: parent and collapsed are set by the core",)
            for x in claims:
                claimed_by[x] = fmt.id
            mtimes = [files[m].mtime for m in members] + [
                children[p].mtime for p in parts
            ]
            uid = files[ds.anchor].uid if ds.anchor in files else d.uid
            filled = _fill(
                replace(ds, members=tuple(sorted(members)), parts=tuple(sorted(parts)),
                        warnings=warnings, parent=None, collapsed=False),
                fmt, d, max(mtimes, default=d.mtime), uid, files, children,
            )  # fmt: skip
            out.append(filled)
            for p in parts:
                adoptions[p] = filled.anchor
        # What is claimed is not offered to the formats after this one (bug 311),
        # but they can ask who claimed a file (decision 344)
        for e in d.entries:
            if e.kind == "file" and e.rel in claimed_by:
                d.claimed[e.name] = claimed_by[e.rel]
        d.entries = [e for e in d.entries if e.name not in d.claimed]
        d._by_name = {e.name: e for e in d.entries}
        d.children = [c for c in d.children if c.anchor not in claimed_by]
    for e in d.entries:  # the current entries, with the types formats dropped
        if e.kind == "file":
            out.append(
                Dataset(
                    anchor=e.rel,
                    members=(e.rel,),
                    type=e.mime or "",
                    basis="single file",
                    mtime=e.mtime,
                    uid=e.uid,
                    size=e.size,
                    stamp=stamp([e]),
                    directory=d.rel,
                )
            )
    return [_noted(ds, d.notes, d.remarks) for ds in out], adoptions


def _check_order(
    d: Directory, earlier: list[Format], fmt: Format, dropped: set[str]
) -> None:
    """Warn when a format that ran before fmt reacts to the new type of a file fmt dropped (D3)."""
    for rel in sorted(dropped):
        new = next(e.mime for e in d.entries if e.rel == rel)
        for f in earlier:
            if new in f.reacts_to:
                d.warn(
                    rel,
                    f"{f.id} runs before {fmt.id} and did not see "
                    f"{PurePosixPath(rel).name} as {new}",
                )


def _noted(ds: Dataset, notes: dict[str, str], remarks: dict[str, str]) -> Dataset:
    """The dataset with its members' notes in its basis: a dropped name type (D4), then a remark (note)."""
    mine = [n[m] for m in ds.members for n in (notes, remarks) if m in n]
    if not mine:
        return ds
    return replace(ds, basis="; ".join([ds.basis, *mine]))
