"""Whether an emulation still follows the code the search stack builds (@weber, 2026-11-12: "detect when we are out of sync").

An emulation in `upstream.py` declares what it follows (`Follows`): upstream's
version and a SHA-256 over our patches on top. The actual values are read here
from the search stack's files (`prototypes/search-stack/`), and nowhere else:
the version from the Dockerfile that builds the service, the patches from the
folder whose `*.patch` files it applies. Used by the page, the snapshot and the
unit test `tests/test_sync.py`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

# upstream -> (Dockerfile, the line that names the version, the patch folder); the Dockerfile copies `*.patch`
BUILDS = {
    "matchmaker": (
        "matchmaker.Dockerfile",
        r"^ADD https://github\.com/EOSC-Data-Commons/matchmaker\.git#([0-9a-f]{40}) ",
        "patches/matchmaker",
    ),
    "search-api": (
        "search-api.Dockerfile",
        r"^FROM ghcr\.io/eosc-data-commons/data-commons-search:([^@\s]+)@",
        "patches/search-api",
    ),
}


@dataclass(frozen=True)
class Follows:
    """What an emulation follows: `upstream` (a key of BUILDS), its `version` (commit or image version), `patches` (SHA-256)."""

    upstream: str
    version: str
    patches: str

    def short(self) -> str:
        version = (
            self.version[:7]
            if re.fullmatch(r"[0-9a-f]{40}", self.version)
            else self.version
        )
        return f"{self.upstream} {version} + patches {self.patches[:12]}"


def patches_hash(folder: Path) -> str:
    """SHA-256 over the contents of the folder's `*.patch` files in name order: `cat $(LC_ALL=C ls *.patch) | sha256sum`."""
    digest = hashlib.sha256()
    for patch in sorted(folder.glob("*.patch")):
        digest.update(patch.read_bytes())
    return digest.hexdigest()


def built(stack: Path, upstream: str) -> Follows:
    """What the search stack in folder `stack` builds of upstream. Raises OSError or ValueError when it cannot tell."""
    dockerfile, pattern, folder = BUILDS[upstream]
    found = re.search(pattern, (stack / dockerfile).read_text(), re.MULTILINE)
    if found is None:
        raise ValueError(f"{dockerfile}: no line matches {pattern}")
    if not (stack / folder).is_dir():
        raise FileNotFoundError(f"no folder {stack / folder}")
    return Follows(upstream, found[1], patches_hash(stack / folder))


def out_of_sync(stack: Path, declared: Follows) -> str:
    """The warning for an emulation that declares `declared`; empty when the stack builds just that."""
    try:
        actual = built(stack, declared.upstream)
    except (OSError, ValueError) as e:
        return f"out of sync? cannot read what the stack builds: {e}; emulates {declared.short()}"
    if actual == declared:
        return ""
    return (
        f"out of sync: emulates {declared.short()}, the stack builds"
        f" {actual.short().removeprefix(declared.upstream + ' ')}; review the emulation"
    )
