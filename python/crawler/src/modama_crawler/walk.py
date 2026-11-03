"""The post-order walk: recognise every directory after its subdirectories, never enter collapsed ones."""

from __future__ import annotations

import logging
import os
import stat
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from pathspec import GitIgnoreSpec

from . import mime
from .formats import (
    BYTE_BUDGET,
    TIME_LIMIT,
    Dataset,
    Directory,
    Entry,
    Format,
    Result,
    run_post,
    run_pre,
)
from .selection import compile_patterns, compile_per_path, path_excluded, path_ignored

log = logging.getLogger(__name__)


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


def walk(
    root: Path | str,
    formats: list[Format],
    *,
    exclude: Iterable[str] = (),
    per_path_ignores: dict[str, list[str]] | None = None,
) -> Result:
    root = os.path.abspath(str(root))
    excluded = compile_patterns(exclude)
    ignores = compile_per_path(per_path_ignores or {})
    result = Result()

    def formats_for(rel: str) -> list[Format]:
        return [f for f in formats if not path_ignored(f.id, rel, ignores)]

    def visit(dirpath: str, rel: str) -> list[Dataset]:
        notes = Result()  # skips and name problems, kept only if not collapsed
        try:
            entries = _entries(dirpath, rel, notes, excluded)
        except OSError as e:
            if rel == "/":
                raise  # the root itself: the caller asked for it, so it is an error
            result.skipped.append((rel, f"cannot list directory: {e.strerror}"))
            log.info("%s: skipped, cannot list directory: %s", rel, e.strerror)
            return []
        st = os.lstat(dirpath)
        active = formats_for(rel)
        pre = Directory(rel, dirpath, entries, [], "pre", st.st_uid, st.st_mtime)
        collapsed = run_pre(pre, active, TIME_LIMIT, BYTE_BUDGET)
        result.warnings.extend(pre.warnings)
        if collapsed is not None:
            log.debug("%s collapsed by %s", rel, collapsed.format)
            return [collapsed]
        for path, reason in notes.skipped:
            log.info("%s: skipped, %s", path, reason)
        result.skipped.extend(notes.skipped)
        result.warnings.extend(notes.warnings)
        subtree: list[Dataset] = []
        for e in entries:
            if e.kind == "dir":
                subtree.extend(visit(e.path, e.rel))
        typed = []
        for e in entries:
            if e.kind == "file":
                try:
                    detected, tie = mime.detect_with_tie(e.path)
                except OSError as err:
                    result.warnings.append((e.rel, f"cannot read: {err.strerror}"))
                    detected, tie = "application/octet-stream", None
                if tie:
                    result.warnings.append(
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
        result.warnings.extend(post.warnings)
        subtree = [
            replace(d, parent=adoptions[d.anchor]) if d.anchor in adoptions else d
            for d in subtree
        ]
        log.debug("%s: %d datasets", rel, len(datasets))
        return subtree + datasets

    result.datasets = sorted(visit(root, "/"), key=lambda d: d.anchor)
    result.warnings.sort()
    result.skipped.sort()
    return result
