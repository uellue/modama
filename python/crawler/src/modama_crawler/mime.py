"""MIME type of a file, following the shared-mime-info "recommended checking order".

https://specifications.freedesktop.org/shared-mime-info/latest/ar01s02.html

Only pyxdg's parsed databases are used: its get_type2() skips the
longest-pattern rule, and its magic matching restricted to candidates checks
the lowest priority first.
"""

import fnmatch
import os
import re
import stat
from collections import defaultdict
from functools import cache

from xdg import Mime

WILDCARDS = re.compile(r"[*?\[]")


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


def detect(path: str) -> str:
    """MIME type of the file at path, without following symlinks.

    Raises OSError if path can't be stat'ed.
    """
    mode = os.lstat(path).st_mode
    if stat.S_ISDIR(mode):
        return "inode/directory"
    if stat.S_ISLNK(mode):
        return "inode/symlink"
    if not stat.S_ISREG(mode):
        return str(Mime._get_type_by_stat(mode))

    # Globs with the biggest weight, then the longest pattern
    candidates = []
    matches = glob_matches(os.path.basename(path))
    if matches:
        best = max((weight, length) for weight, length, _ in matches)
        candidates = sorted({t for w, n, t in matches if (w, n) == best}, key=str)
        if len(candidates) == 1:
            return str(candidates[0])

    # No or conflicting globs: sniff the contents
    try:
        with open(path, "rb") as f:
            data = f.read(Mime.magic.maxlen)
    except OSError:
        return str(candidates[0]) if candidates else str(Mime.octet_stream)
    sniffed = Mime.magic.match_data(data)
    if sniffed is not None:
        sniffed = sniffed.canonical()
    if not candidates:
        if sniffed is not None:
            return str(sniffed)
        return str(Mime.text if _is_text(data) else Mime.octet_stream)
    for mtype in candidates:
        if sniffed is not None and _is_a(mtype, sniffed):
            return str(mtype)
    # Not in the spec: prefer the candidate whose own magic matches, highest priority first
    rules = [(p, t, r) for t in candidates for p, r in Mime.magic.bytype.get(t, ())]
    for _, mtype, rule in sorted(rules, key=lambda x: x[0], reverse=True):
        if rule.match(data):
            return str(mtype)
    return str(candidates[0])
