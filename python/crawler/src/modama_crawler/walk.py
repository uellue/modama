"""The post-order walk: recognise every directory after its subdirectories, never enter collapsed ones."""

from __future__ import annotations

import logging
import os
import stat
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from . import mime
from .formats import Dataset, Directory, Entry, Format, Result, run_post, run_pre
from .selection import path_excluded, path_ignored

log = logging.getLogger(__name__)


def _kind(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "dir"
    if stat.S_ISLNK(mode):
        return "symlink"
    return "other"


def _skip(result: Result, rel: str, reason: str) -> None:
    result.skipped.append((rel, reason))
    log.info("%s: skipped, %s", rel, reason)


def _entries(
    dirpath: str, rel: str, result: Result, exclude: Iterable[str]
) -> list[Entry]:
    """The directory's regular files and subdirectories, sorted by name.

    Symlinks, special files and files the crawler cannot read are skipped with
    an info line: they would not make useful records. Raises OSError if the
    directory itself cannot be listed.
    """
    with os.scandir(dirpath) as it:
        names = [e.name for e in it]
    entries = []
    for name in sorted(names):
        try:
            name.encode()
        except UnicodeEncodeError:
            result.warnings.append(
                (rel, f"skipped a name that is not valid UTF-8: {name!r}")
            )
            continue
        path = os.path.join(dirpath, name)
        child_rel = rel.rstrip("/") + "/" + name
        if path_excluded(child_rel, exclude):
            continue
        try:
            st = os.lstat(path)
        except OSError as e:
            result.warnings.append((child_rel, f"cannot stat: {e.strerror}"))
            continue
        kind = _kind(st.st_mode)
        if kind not in ("file", "dir"):
            _skip(result, child_rel, kind)
            continue
        if kind == "file" and not os.access(path, os.R_OK):
            _skip(result, child_rel, "not readable")
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
    time_limit: float = 5.0,
    byte_budget: int = 1 << 20,
) -> Result:
    root = os.path.abspath(str(root))
    ignores = per_path_ignores or {}
    result = Result()

    def formats_for(rel: str) -> list[Format]:
        return [f for f in formats if not path_ignored(f.id, rel, ignores)]

    def visit(dirpath: str, rel: str) -> list[Dataset]:
        try:
            entries = _entries(dirpath, rel, result, exclude)
        except OSError as e:
            if rel == "/":
                raise  # the root itself: the caller asked for it, so it is an error
            _skip(result, rel, f"cannot list directory: {e.strerror}")
            return []
        st = os.lstat(dirpath)
        active = formats_for(rel)
        pre = Directory(rel, dirpath, entries, [], "pre", st.st_uid, st.st_mtime)
        collapsed = run_pre(pre, active, time_limit, byte_budget)
        result.warnings.extend(pre.warnings)
        if collapsed is not None:
            log.debug("%s collapsed by %s", rel, collapsed.format)
            return [collapsed]
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
        datasets, adoptions = run_post(post, active, time_limit, byte_budget)
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
