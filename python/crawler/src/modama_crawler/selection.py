"""Which collections are installed, which formats a deployment enables, and where.

Selection follows ruff: `select` and `ignore` lists of ids (`collection` or
`collection/format`); more specific wins, ignore wins ties. Per-path ignores
and crawl exclusions are gitignore patterns, matched by pathspec. See design/architecture.md E.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path

from pathspec import GitIgnoreSpec

from .formats import Collection, Format

ENTRY_POINT_GROUP = "modama.formats"


@dataclass
class Config:
    select: list[str] = field(default_factory=list)  # empty: everything installed
    ignore: list[str] = field(default_factory=list)
    per_path_ignores: dict[str, list[str]] = field(default_factory=dict)
    exclude: list[str] = field(default_factory=list)


def load_config(path: Path | None) -> Config:
    if path is None:
        return Config()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    formats = data.get("formats", {})
    return Config(
        select=list(formats.get("select", [])),
        ignore=list(formats.get("ignore", [])),
        per_path_ignores={
            k: list(v) for k, v in formats.get("per-path-ignores", {}).items()
        },
        exclude=list(data.get("crawl", {}).get("exclude", [])),
    )


def discover() -> dict[str, Collection]:
    """Installed collections by name, from the entry-point group."""
    found: dict[str, tuple[Collection, str]] = {}
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        collection = ep.load()
        dist = ep.dist.name if ep.dist else "?"
        if collection.name in found:
            raise ValueError(
                f"collection {collection.name!r} is registered twice: "
                f"by {found[collection.name][1]} and by {dist}"
            )
        found[collection.name] = (collection, dist)
    return {name: c for name, (c, _) in found.items()}


def _specificity(spec: str, format_id: str) -> int | None:
    if spec == "ALL":
        return 0
    if spec == format_id:
        return 2
    if "/" not in spec and format_id.startswith(spec + "/"):
        return 1
    return None


def enabled(format_id: str, select: Iterable[str], ignore: Iterable[str]) -> bool:
    select = list(select)
    s = max(
        (
            x
            for x in (_specificity(spec, format_id) for spec in select)
            if x is not None
        ),
        default=0 if not select else None,
    )
    i = max(
        (
            x
            for x in (_specificity(spec, format_id) for spec in ignore)
            if x is not None
        ),
        default=None,
    )
    if s is None:
        return False
    return i is None or s > i


def check_ids(ids: Iterable[str], collections: Iterable[Collection]) -> None:
    """Raise ValueError for an id that names no installed collection or format."""
    known = {c.name for c in collections} | {
        f.id for c in collections for f in c.formats
    }
    unknown = sorted({x for x in ids if x != "ALL" and x not in known})
    if unknown:
        raise ValueError(
            f"unknown format id: {', '.join(unknown)} (installed: {', '.join(sorted(known))})"
        )


def enabled_collections(
    collections: Iterable[Collection], config: Config
) -> list[Collection]:
    """Collections whose MIME definitions are used: those not switched off as a whole.

    A collection is selected or ignored by its name like a format; ignoring one
    of its formats leaves its definitions in place.
    """
    return [c for c in collections if enabled(c.name, config.select, config.ignore)]


def enabled_formats(collections: Iterable[Collection], config: Config) -> list[Format]:
    collections = list(collections)
    check_ids(
        [
            *config.select,
            *config.ignore,
            *(x for v in config.per_path_ignores.values() for x in v),
        ],
        collections,
    )
    return [
        f
        for c in collections
        for f in c.formats
        if enabled(f.id, config.select, config.ignore)
    ]


def compile_patterns(patterns: Iterable[str]) -> GitIgnoreSpec:
    """Patterns with gitignore semantics: anchoring by a slash, directory-only
    patterns with a trailing slash, `!` negation, last match wins."""
    return GitIgnoreSpec.from_lines(patterns)


PerPath = list[tuple[GitIgnoreSpec, list[str]]]


def compile_per_path(per_path_ignores: dict[str, list[str]]) -> PerPath:
    return [
        (compile_patterns([pattern]), ids) for pattern, ids in per_path_ignores.items()
    ]


def _git_path(rel: str, is_dir: bool) -> str:
    """pathspec takes paths without the leading "/" and directories with a trailing "/"."""
    path = rel.lstrip("/")
    return path + "/" if is_dir and path else path


def path_excluded(rel: str, exclude: GitIgnoreSpec, *, is_dir: bool = False) -> bool:
    return exclude.match_file(_git_path(rel, is_dir))


def path_ignored(
    format_id: str, rel: str, per_path: PerPath, *, is_dir: bool = True
) -> bool:
    """Whether a per-path ignore keeps the format away from the directory rel."""
    path = _git_path(rel, is_dir)
    return any(
        spec.match_file(path)
        and any(_specificity(spec_id, format_id) is not None for spec_id in ids)
        for spec, ids in per_path
    )
