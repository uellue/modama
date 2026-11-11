"""MIME type of a file, following the shared-mime-info "recommended checking order".

https://specifications.freedesktop.org/shared-mime-info/latest/ar01s02.html

Only pyxdg's parsed databases are used: its get_type2() skips the
longest-pattern rule, and its magic matching restricted to candidates checks
the lowest priority first. Ties resolve to the common ancestor (architecture C).
"""

import contextlib
import fnmatch
import os
import re
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import Executor
from functools import cache
from pathlib import Path

from xdg import Mime

WILDCARDS = re.compile(r"[*?\[]")

# The directory of the active MIME database, set by mimedb.activate(). Detection
# without one would silently use the host's definitions (Q12), so it refuses.
database: Path | None = None


@cache
def _glob_index(globs: Mime.GlobDB):
    """Literal names, extensions and other patterns, each with (weight, pattern length, type)."""
    literals, extensions, others = defaultdict(list), defaultdict(list), []
    for mtype, patterns in globs.allglobs.items():
        mtype = mtype.canonical()
        for weight, pattern, flags in patterns:
            cased = "cs" in flags
            key = pattern if cased else pattern.lower()
            match = (weight, len(pattern), mtype)
            if not WILDCARDS.search(pattern):
                literals[key, cased].append(match)
            elif pattern.startswith("*.") and not WILDCARDS.search(pattern[2:]):
                extensions[key[2:], cased].append(match)
            else:
                regex = re.compile(
                    fnmatch.translate(pattern), 0 if cased else re.IGNORECASE
                )
                others.append((regex, match))
    return literals, extensions, others


def glob_matches(name: str) -> list[tuple[int, int, Mime.MIMEtype]]:
    """All (weight, pattern length, type) whose glob matches the file name."""
    Mime.update_cache()
    literals, extensions, others = _glob_index(Mime.globs)
    found = []
    for key, cased in ((name, True), (name.lower(), False)):
        found += literals.get((key, cased), [])
        dot = key.find(".")
        while dot != -1:
            found += extensions.get((key[dot + 1 :], cased), [])
            dot = key.find(".", dot + 1)
    found += [match for regex, match in others if regex.match(name)]
    return found


def _is_a(mtype: Mime.MIMEtype, parent: Mime.MIMEtype) -> bool:
    if mtype is parent:
        return True
    if parent is Mime.text and mtype.media == "text":
        return True
    if parent is Mime.octet_stream and mtype.media != "inode":
        return True
    return any(_is_a(p.canonical(), parent) for p in mtype.inherits_from())


def _is_text(data: bytes) -> bool:
    # Same heuristic as pyxdg: no control characters in the first 32 bytes
    return not any(b <= 0x8 or 0xE <= b < 0x20 or b == 0x7F for b in data[:32])


def _ancestors(mtype: Mime.MIMEtype) -> list[Mime.MIMEtype]:
    """Ancestors nearest first, with the implicit parents last."""
    out, queue = [], [mtype]
    while queue:
        t = queue.pop(0)
        for p in sorted(t.inherits_from(), key=str):
            p = p.canonical()
            if p not in out:
                out.append(p)
                queue.append(p)
    if mtype.media == "text" and Mime.text not in out:
        out.append(Mime.text)
    if mtype.media != "inode" and Mime.octet_stream not in out:
        out.append(Mime.octet_stream)
    return out


def _common_ancestor(candidates: list[Mime.MIMEtype]) -> Mime.MIMEtype:
    """The nearest type every candidate is-a: a candidate itself when the others are its subtypes."""
    for a in [*candidates, *_ancestors(candidates[0])]:
        if all(_is_a(c, a) for c in candidates):
            return a
    return Mime.octet_stream


def _resolve(candidates: list[Mime.MIMEtype]) -> tuple[str, tuple[str, ...] | None]:
    """The common ancestor of tied candidates; reported as a tie only when it is none of them."""
    chosen = _common_ancestor(candidates)
    if chosen in candidates:
        return str(chosen), None
    return str(chosen), tuple(map(str, candidates))


def detect(path: str) -> str:
    """MIME type of the regular file at path (a convenience for tests)."""
    return detect_with_tie(path)[0]


def init_worker(directory: Path) -> None:
    """In a worker process for match_in: activate the parent's MIME database."""
    from . import mimedb  # mimedb imports this module

    mimedb.activate(directory)


def _match_name(data: bytes) -> str | None:
    found = Mime.magic.match_data(data)
    return None if found is None else str(found)


def match_in(pool: Executor) -> Callable[[bytes], Mime.MIMEtype | None]:
    """Magic matching in a pool of processes started with init_worker (parallel-walk D5).

    pyxdg's matching is pure Python and holds the GIL for about 4 ms per file;
    the type found is looked up in this process's database, so the rest of
    the detection is the same.
    """

    def match(data: bytes) -> Mime.MIMEtype | None:
        name = pool.submit(_match_name, data).result()
        return None if name is None else Mime.lookup(name)

    return match


def detect_with_tie(
    path: str, match: Callable[[bytes], Mime.MIMEtype | None] | None = None
) -> tuple[str, tuple[str, ...] | None]:
    """MIME type of the regular file at path and, if candidates tied, the tied types.

    The walk guarantees a regular file; symlinks and special files never get
    here. A tie between candidates resolves to their nearest common ancestor
    in the subclass hierarchy (architecture C); it counts as a tie only when
    that ancestor is none of the candidates. `match` replaces pyxdg's magic
    matching of the bytes read (match_in).
    """
    if database is None:
        raise RuntimeError("no MIME database active; call mimedb.build() first")

    # Globs with the biggest weight, then the longest pattern
    candidates = []
    matches = glob_matches(os.path.basename(path))
    if matches:
        best = max((weight, length) for weight, length, _ in matches)
        candidates = sorted({t for w, n, t in matches if (w, n) == best}, key=str)
        if len(candidates) == 1:
            return str(candidates[0]), None

    # No or conflicting globs: sniff the contents
    try:
        # Unbuffered: a buffered open reads a whole buffer, up to st_blksize (1 MiB on NFS)
        with open(path, "rb", buffering=0) as f:
            # No readahead either: on NFS it fetches 128 kB or more for these few bytes (parallel-walk D6)
            with contextlib.suppress(OSError):
                os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_RANDOM)
            data = f.read(Mime.magic.maxlen)
    except OSError:
        if candidates:
            return _resolve(candidates)
        return str(Mime.octet_stream), None
    sniffed = (match or Mime.magic.match_data)(data)
    if sniffed is not None:
        sniffed = sniffed.canonical()
    if not candidates:
        if sniffed is not None:
            return str(sniffed), None
        return str(Mime.text if _is_text(data) else Mime.octet_stream), None
    # A candidate that is the sniffed type or a subclass of it wins; the sniffed type itself first
    related = [c for c in candidates if sniffed is not None and _is_a(c, sniffed)]
    if sniffed in related:
        return str(sniffed), None
    if len(related) == 1:
        return str(related[0]), None
    if related:
        candidates = related
    return _resolve(candidates)
