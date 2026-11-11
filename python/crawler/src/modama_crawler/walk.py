"""The post-order walk: recognise every directory after its subdirectories, never enter collapsed ones."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import stat
from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from pathspec import GitIgnoreSpec

from . import mime
from .formats import (
    BYTE_BUDGET,
    TIME_LIMIT,
    Dataset,
    Directory,
    Entry,
    Format,
    Listing,
    Result,
    run_post,
    run_pre,
)
from .selection import compile_patterns, compile_per_path, path_excluded, path_ignored

log = logging.getLogger(__name__)

UNLISTABLE = (
    "cannot list"  # the stored digest of a directory the crawler could not list
)


def _kind(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "dir"
    if stat.S_ISLNK(mode):
        return "symlink"
    return "other"


def _entries(
    dirpath: str, rel: str, notes: Result, exclude: GitIgnoreSpec
) -> list[Entry]:
    """The directory's regular files and subdirectories, sorted by name.

    Symlinks, special files and files the crawler cannot read are skipped:
    they would not make useful records. Skips and name problems go into
    `notes` (a throwaway Result), so that the caller can drop them if the
    directory turns out to be collapsed. Raises OSError if the directory
    itself cannot be listed.
    """
    with os.scandir(dirpath) as it:
        names = [e.name for e in it]
    entries = []
    for name in sorted(names):
        try:
            name.encode()
        except UnicodeEncodeError:
            notes.warnings.append(
                (rel, f"skipped a name that is not valid UTF-8: {name!r}")
            )
            continue
        path = os.path.join(dirpath, name)
        child_rel = rel.rstrip("/") + "/" + name
        try:
            st = os.lstat(path)
        except OSError as e:
            notes.warnings.append((child_rel, f"cannot stat: {e.strerror}"))
            continue
        kind = _kind(st.st_mode)
        if path_excluded(child_rel, exclude, is_dir=kind == "dir"):
            continue
        if kind not in ("file", "dir"):
            notes.skipped.append((child_rel, kind))
            continue
        if kind == "file" and not os.access(path, os.R_OK):
            notes.skipped.append((child_rel, "not readable"))
            continue
        entries.append(
            Entry(
                name,
                path,
                child_rel,
                kind,
                st.st_size,
                st.st_mtime,
                st.st_ctime,
                st.st_uid,
            )
        )
    return entries


class Previous(Protocol):
    """What the last crawl left, for taking over unchanged directories (D3); store.Stored implements it."""

    def listing(self, rel: str) -> Listing | None: ...

    def datasets(self, rel: str) -> list[Dataset]:
        """The datasets the directory's recognition produced, as stored."""
        ...


def _digest(st: os.stat_result, entries: list[Entry]) -> str:
    """The directory's own stat and its entries' names, kinds, sizes, owners and times."""
    state = [
        [st.st_uid, st.st_mtime, st.st_ctime],
        [[e.name, e.kind, e.size, e.uid, e.mtime, e.ctime] for e in entries],
    ]
    return hashlib.sha256(json.dumps(state).encode()).hexdigest()


def walk(
    root: Path | str,
    formats: list[Format],
    *,
    exclude: Iterable[str] = (),
    per_path_ignores: dict[str, list[str]] | None = None,
    progress: Callable[[int, int], None] | None = None,
    previous: Previous | None = None,
) -> Result:
    """Recognise the tree under root.

    `progress`, if given, is called after each directory is listed with the
    numbers of directories and files listed so far. With `previous`, the last
    crawl under the same rules, a directory whose listing and those of all
    directories below it are unchanged keeps its stored datasets: no file is
    read and no format runs for it (D3). Every directory is still listed.
    """
    root = os.path.abspath(str(root))
    excluded = compile_patterns(exclude)
    ignores = compile_per_path(per_path_ignores or {})
    result = Result()
    seen = [0, 0]  # directories, files

    def formats_for(rel: str) -> list[Format]:
        return [f for f in formats if not path_ignored(f.id, rel, ignores)]

    def visit(dirpath: str, rel: str) -> tuple[list[Dataset], bool]:
        """The datasets of the subtree, and whether it is unchanged since the last crawl."""
        notes = Result()  # skips and name problems, kept only if not collapsed
        try:
            entries = _entries(dirpath, rel, notes, excluded)
        except OSError as e:
            if rel == "/":
                raise  # the root itself: the caller asked for it, so it is an error
            result.skipped.append((rel, f"cannot list directory: {e.strerror}"))
            log.info("%s: skipped, cannot list directory: %s", rel, e.strerror)
            # Unchanged if it could not be listed last time either; its entry
            # in the parent's listing is compared by the parent
            before = previous.listing(rel) if previous is not None else None
            result.listings[rel] = Listing(UNLISTABLE)
            return [], before is not None and before.digest == UNLISTABLE
        if progress is not None:
            seen[0] += 1
            seen[1] += sum(e.kind == "file" for e in entries)
            progress(seen[0], seen[1])
        st = os.lstat(dirpath)
        digest = _digest(st, entries)
        before = previous.listing(rel) if previous is not None else None
        same = before is not None and before.digest == digest and not before.retry
        stored = previous.datasets(rel) if same else []
        active = formats_for(rel)
        pre_retry = False
        if same:
            # The pre-order call sees this listing only: its answer is the stored one
            pre_warnings = list(before.pre)
            collapsed = next((d for d in stored if d.collapsed), None)
        else:
            pre = Directory(rel, dirpath, entries, [], "pre", st.st_uid, st.st_mtime)
            collapsed = run_pre(pre, active, TIME_LIMIT, BYTE_BUDGET)
            if collapsed is not None:
                # Nothing below is read: the stamp is the listing's (the D3 limit for collapsed trees)
                collapsed = replace(collapsed, stamp=digest)
            pre_warnings = pre.warnings
            pre_retry = pre.retry
        result.warnings.extend(pre_warnings)
        if collapsed is not None:
            log.debug("%s collapsed by %s", rel, collapsed.format)
            result.listings[rel] = Listing(digest, tuple(pre_warnings), retry=pre_retry)
            result.unchanged += same
            return [replace(collapsed, parent=None)], same
        for path, reason in notes.skipped:
            log.info("%s: skipped, %s", path, reason)
        result.skipped.extend(notes.skipped)
        result.warnings.extend(notes.warnings)
        subtree: list[Dataset] = []
        unchanged = same
        for e in entries:
            if e.kind == "dir":
                datasets, child_unchanged = visit(e.path, e.rel)
                subtree.extend(datasets)
                unchanged = unchanged and child_unchanged
        if unchanged:
            datasets = [replace(d, parent=None) for d in stored]
            adoptions = {p: d.anchor for d in datasets for p in d.parts}
            post_warnings = list(before.post)
            post_retry = False
            result.unchanged += 1
        else:
            datasets, adoptions, post_warnings, post_retry = recognise(
                dirpath, rel, st, entries, subtree, active
            )
        result.warnings.extend(post_warnings)
        result.listings[rel] = Listing(
            digest, tuple(pre_warnings), tuple(post_warnings), pre_retry or post_retry
        )
        subtree = [
            replace(d, parent=adoptions[d.anchor]) if d.anchor in adoptions else d
            for d in subtree
        ]
        log.debug("%s: %d datasets", rel, len(datasets))
        return subtree + datasets, unchanged

    def recognise(dirpath, rel, st, entries, subtree, active):
        """MIME detection and the post-order call; returns datasets, adoptions, warnings and whether to retry."""
        warnings = []
        typed = []
        retry = False
        for e in entries:
            if e.kind == "file":
                try:
                    detected, tie = mime.detect_with_tie(e.path)
                except OSError as err:
                    retry = True
                    warnings.append((e.rel, f"cannot read: {err.strerror}"))
                    detected, tie = "application/octet-stream", None
                if tie:
                    warnings.append(
                        (
                            e.rel,
                            f"type is ambiguous between {', '.join(tie)}; using {detected}",
                        )
                    )
                e = replace(e, mime=detected)
            typed.append(e)
        children = [d for d in subtree if d.parent is None]
        post = Directory(rel, dirpath, typed, children, "post", st.st_uid, st.st_mtime)
        datasets, adoptions = run_post(post, active, TIME_LIMIT, BYTE_BUDGET)
        return datasets, adoptions, warnings + post.warnings, retry or post.retry

    result.datasets = sorted(visit(root, "/")[0], key=lambda d: d.anchor)
    result.warnings.sort()
    result.skipped.sort()
    return result
