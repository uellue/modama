"""The post-order walk: recognise every directory after its subdirectories, never enter collapsed ones.

The walk's steps are asyncio tasks in the calling thread; everything that may
wait for the file system (listings, stats, reads, format calls) runs in a
thread pool, so that many NFS requests are in flight at once (parallel-walk
D1). Only the tasks touch the result, and it is sorted at the end, so it does
not depend on the number of threads (D2).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import multiprocessing
import os
import stat
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
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
# File system calls in flight; the benchmark's NFS server grants about 30 session slots
DEFAULT_THREADS = 32


def _kind(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "dir"
    if stat.S_ISLNK(mode):
        return "symlink"
    return "other"


def _names(dirpath: str) -> list[str]:
    """The directory's entry names, sorted. Raises OSError if it cannot be listed."""
    with os.scandir(dirpath) as it:
        return sorted(e.name for e in it)


def _stat(path: str) -> tuple[os.stat_result, bool] | OSError:
    """The entry's lstat and, for a regular file, whether it is readable (R35); an error is returned, not raised.

    Readability is asked of the file system, never inferred from the mode
    bits: the storage enforces rules no client sees (parallel-walk D4).
    """
    try:
        st = os.lstat(path)
        return st, stat.S_ISREG(st.st_mode) and os.access(path, os.R_OK)
    except OSError as e:
        return e


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
    threads: int = DEFAULT_THREADS,
    processes: int = 0,
) -> Result:
    """Recognise the tree under root.

    `progress`, if given, is called after each directory is listed with the
    numbers of directories and files listed so far. With `previous`, the last
    crawl under the same rules, a directory whose listing and those of all
    directories below it are unchanged keeps its stored datasets: no file is
    read and no format runs for it (D3). Every directory is still listed.
    `threads` is the number of file system calls in flight; with `processes`
    above 0, MIME magic matching runs in that many worker processes
    (parallel-walk D5).
    """
    pool = ThreadPoolExecutor(threads, thread_name_prefix="walk")
    matchers = (
        ProcessPoolExecutor(
            processes,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=mime.init_worker,
            initargs=(mime.database,),
        )
        if processes
        else None
    )
    try:
        return asyncio.run(
            _walk(
                os.path.abspath(str(root)),
                formats,
                compile_patterns(exclude),
                compile_per_path(per_path_ignores or {}),
                progress,
                previous,
                pool,
                None if matchers is None else mime.match_in(matchers),
            )
        )
    finally:  # also on an error or a signal: queued work is dropped
        pool.shutdown(cancel_futures=True)
        if matchers is not None:
            matchers.shutdown(cancel_futures=True)


async def _walk(
    root: str,
    formats: list[Format],
    excluded: GitIgnoreSpec,
    ignores,
    progress: Callable[[int, int], None] | None,
    previous: Previous | None,
    pool: ThreadPoolExecutor,
    match: Callable | None,
) -> Result:
    loop = asyncio.get_running_loop()
    result = Result()
    seen = [0, 0]  # directories, files

    def io(fn, *args) -> asyncio.Future:
        """Run fn in the thread pool: started now, awaited later."""
        return loop.run_in_executor(pool, fn, *args)

    def detect(path: str) -> tuple[str, tuple[str, ...] | None] | OSError:
        try:
            return mime.detect_with_tie(path, match=match)
        except OSError as err:
            return err

    def start_detection(entries: list[Entry]) -> list[asyncio.Future]:
        return [io(detect, e.path) for e in entries if e.kind == "file"]

    def formats_for(rel: str) -> list[Format]:
        return [f for f in formats if not path_ignored(f.id, rel, ignores)]

    async def entries_of(dirpath: str, rel: str, notes: Result) -> list[Entry]:
        """The directory's regular files and subdirectories, sorted by name.

        Symlinks, special files and files the crawler cannot read are skipped:
        they would not make useful records. Skips and name problems go into
        `notes` (a throwaway Result), so that the caller can drop them if the
        directory turns out to be collapsed. Raises OSError if the directory
        itself cannot be listed. The entries are stat'ed in parallel.
        """
        names = []
        for name in await io(_names, dirpath):
            try:
                name.encode()
            except UnicodeEncodeError:
                notes.warnings.append(
                    (rel, f"skipped a name that is not valid UTF-8: {name!r}")
                )
                continue
            names.append(name)
        stats = await asyncio.gather(
            *(io(_stat, os.path.join(dirpath, name)) for name in names)
        )
        entries = []
        for name, got in zip(names, stats, strict=True):
            path = os.path.join(dirpath, name)
            child_rel = rel.rstrip("/") + "/" + name
            if isinstance(got, OSError):
                notes.warnings.append((child_rel, f"cannot stat: {got.strerror}"))
                continue
            st, readable = got
            kind = _kind(st.st_mode)
            if path_excluded(child_rel, excluded, is_dir=kind == "dir"):
                continue
            if kind not in ("file", "dir"):
                notes.skipped.append((child_rel, kind))
                continue
            if kind == "file" and not readable:
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

    async def visit(dirpath: str, rel: str) -> tuple[list[Dataset], bool]:
        """The datasets of the subtree, and whether it is unchanged since the last crawl."""
        notes = Result()  # skips and name problems, kept only if not collapsed
        try:
            entries = await entries_of(dirpath, rel, notes)
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
        st = await io(os.lstat, dirpath)
        digest = _digest(st, entries)
        before = previous.listing(rel) if previous is not None else None
        same = before is not None and before.digest == digest and not before.retry
        stored = await io(previous.datasets, rel) if same else []
        active = formats_for(rel)
        pre_retry = False
        if same:
            # The pre-order call sees this listing only: its answer is the stored one
            pre_warnings = list(before.pre)
            collapsed = next((d for d in stored if d.collapsed), None)
        else:
            pre = Directory(rel, dirpath, entries, [], "pre", st.st_uid, st.st_mtime)
            collapsed = await io(run_pre, pre, active, TIME_LIMIT, BYTE_BUDGET)
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
        # Types are needed unless the whole subtree turns out unchanged: start now, while the subdirectories run
        detections = None if same else start_detection(entries)
        children = [
            asyncio.create_task(visit(e.path, e.rel))
            for e in entries
            if e.kind == "dir"
        ]
        subtree: list[Dataset] = []
        unchanged = same
        for datasets, child_unchanged in await asyncio.gather(*children):
            subtree.extend(datasets)
            unchanged = unchanged and child_unchanged
        if unchanged:
            datasets = [replace(d, parent=None) for d in stored]
            adoptions = {p: d.anchor for d in datasets for p in d.parts}
            post_warnings = list(before.post)
            post_retry = False
            result.unchanged += 1
        else:
            if detections is None:
                detections = start_detection(entries)
            datasets, adoptions, post_warnings, post_retry = await recognise(
                dirpath, rel, st, entries, subtree, active, detections
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

    async def recognise(dirpath, rel, st, entries, subtree, active, detections):
        """MIME types and the post-order call; returns datasets, adoptions, warnings and whether to retry."""
        warnings = []
        typed = []
        retry = False
        detected_types = iter(await asyncio.gather(*detections))
        for e in entries:
            if e.kind == "file":
                got = next(detected_types)
                if isinstance(got, OSError):
                    retry = True
                    warnings.append((e.rel, f"cannot read: {got.strerror}"))
                    detected, tie = "application/octet-stream", None
                else:
                    detected, tie = got
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
        datasets, adoptions = await io(run_post, post, active, TIME_LIMIT, BYTE_BUDGET)
        return datasets, adoptions, warnings + post.warnings, retry or post.retry

    result.datasets = sorted((await visit(root, "/"))[0], key=lambda d: d.anchor)
    result.warnings.sort()
    result.skipped.sort()
    result.listings = dict(sorted(result.listings.items()))
    return result
