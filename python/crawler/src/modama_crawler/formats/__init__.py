"""Formats: what a dataset type is, and how the core runs formats on one directory.

A format is a class with `type`, `priority`, `reacts_to`, `collection` and
`recognize(directory)`. The core calls it twice per directory: before
descending, with names and sizes only (a collapse format may answer and end
the descent), and after the subdirectories are final, with entries, their
MIME types and the subdirectories' datasets. See design/architecture.md A, B, D.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath

DIRECTORY = "directory"  # in reacts_to: run on every directory, pre- and post-order


@dataclass(frozen=True)
class Entry:
    name: str
    path: str  # absolute, for reading
    rel: str  # relative to the root, with a leading "/"
    kind: str  # "file", "dir", "symlink" or "other"
    size: int
    mtime: float
    ctime: float
    uid: int
    mime: str | None = None  # None in the pre-order call


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


@dataclass
class Result:
    datasets: list[Dataset] = field(default_factory=list)
    warnings: list[tuple[str, str]] = field(default_factory=list)  # (path, text)

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
        }

    @classmethod
    def from_json(cls, data: dict) -> Result:
        return cls(
            datasets=[
                Dataset(
                    anchor=d["anchor"],
                    type=d["type"],
                    members=tuple(d["members"]),
                    parts=tuple(d["parts"]),
                    format=d["format"],
                    basis=d["basis"],
                    warnings=tuple(d["warnings"]),
                    parent=d["parent"],
                    collapsed=d["collapsed"],
                )
                for d in data["datasets"]
            ],
            warnings=[tuple(w) for w in data["warnings"]],
        )


class BudgetExceeded(Exception):
    pass


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
        self._budget = 0

    @property
    def name(self) -> str:
        return PurePosixPath(self.rel).name

    def entry(self, name: str) -> Entry | None:
        return self._by_name.get(name)

    def of_type(self, mime: str) -> list[Entry]:
        return [e for e in self.entries if e.mime == mime]

    def read(self, entry: Entry, n: int) -> bytes:
        """The first n bytes of an entry of this directory, within the byte budget."""
        if self._by_name.get(entry.name) is not entry:
            raise ValueError(f"{entry.rel} is not an entry of {self.rel}")
        if n > self._budget:
            raise BudgetExceeded(f"reading {n} bytes of {entry.rel} exceeds the budget")
        self._budget -= n
        with open(entry.path, "rb") as f:
            return f.read(n)

    def warn(self, rel: str, text: str) -> None:
        self.warnings.append((rel, text))


class Format:
    type: str = ""
    priority: int = 50
    reacts_to: frozenset[str] = frozenset()
    collection: bool = False
    version: str = "1"
    name: str = ""  # set by Collection: the class name, lowercased, unless given
    id: str = ""  # set by Collection: collection/name

    def recognize(self, directory: Directory) -> Iterable[Dataset]:
        return ()


@dataclass
class Collection:
    name: str
    formats: list[Format]
    mime_files: tuple[Path, ...] = ()

    def __post_init__(self):
        for f in self.formats:
            f.name = f.name or type(f).__name__.lower()
            f.id = f"{self.name}/{f.name}"


def ordered(formats: Iterable[Format]) -> list[Format]:
    return sorted(formats, key=lambda f: (-f.priority, f.id))


def _call(
    fmt: Format, d: Directory, time_limit: float, byte_budget: int
) -> list[Dataset]:
    d._budget = byte_budget
    start = time.monotonic()
    try:
        datasets = list(fmt.recognize(d))
    except BudgetExceeded as e:
        d.warn(d.rel, f"{fmt.id} skipped: {e}")
        return []
    except Exception as e:  # noqa: BLE001  a failing format must not stop the crawl
        d.warn(d.rel, f"{fmt.id} failed: {e!r}")
        return []
    if time.monotonic() - start > time_limit:
        d.warn(d.rel, f"{fmt.id} skipped: exceeded the time limit of {time_limit} s")
        return []
    return datasets


def _fill(ds: Dataset, fmt: Format, d: Directory, mtime: float, uid: int) -> Dataset:
    members = tuple(
        sorted(set(ds.members) | ({ds.anchor} if ds.anchor != d.rel else set()))
    )
    return replace(
        ds, members=members, type=fmt.type, format=fmt.id, version=fmt.version,
        mtime=mtime, uid=uid,
    )  # fmt: skip


def run_pre(
    d: Directory, formats: Iterable[Format], time_limit: float, byte_budget: int
) -> Dataset | None:
    """The pre-order call: the first collapsed dataset for the directory itself wins."""
    for fmt in ordered(formats):
        if DIRECTORY not in fmt.reacts_to:
            continue
        for ds in _call(fmt, d, time_limit, byte_budget):
            if ds.collapsed and ds.anchor == d.rel:
                return _fill(ds, fmt, d, d.mtime, d.uid)
            d.warn(
                d.rel,
                f"{fmt.id}: ignored a pre-order dataset that doesn't collapse {d.rel}",
            )
    return None


def run_post(
    d: Directory, formats: Iterable[Format], time_limit: float, byte_budget: int
) -> tuple[list[Dataset], dict[str, str]]:
    """The post-order call. Returns the directory's datasets and the adoptions (child anchor -> parent anchor)."""
    present = {e.mime for e in d.entries if e.mime}
    files = {e.rel: e for e in d.entries if e.kind == "file"}
    children = {c.anchor: c for c in d.children}
    claimed_by: dict[str, str] = {}  # file rel or child anchor -> format id
    out: list[Dataset] = []
    adoptions: dict[str, str] = {}
    for fmt in ordered(formats):
        if DIRECTORY not in fmt.reacts_to and not (fmt.reacts_to & present):
            continue
        for ds in _call(fmt, d, time_limit, byte_budget):
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
            taken = [
                (x, claimed_by[x]) for x in sorted(members | parts) if x in claimed_by
            ]
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
            for x in members | parts:
                claimed_by[x] = fmt.id
            mtimes = [files[m].mtime for m in members] + [
                children[p].mtime for p in parts
            ]
            uid = files[ds.anchor].uid if ds.anchor in files else d.uid
            filled = _fill(
                replace(ds, members=tuple(sorted(members)), parts=tuple(sorted(parts)), warnings=warnings),
                fmt, d, max(mtimes, default=d.mtime), uid,
            )  # fmt: skip
            out.append(filled)
            for p in parts:
                adoptions[p] = filled.anchor
    for rel, e in files.items():
        if rel not in claimed_by:
            out.append(
                Dataset(
                    anchor=rel,
                    members=(rel,),
                    type=e.mime or "",
                    basis="single file",
                    mtime=e.mtime,
                    uid=e.uid,
                )
            )
    return out, adoptions
