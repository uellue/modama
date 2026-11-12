"""The extractor identity: a digest of the installation, computed at the start of every crawl (R44; change `extractor-identity`, D1).

Its ingredients are the Python version, the name and version of every
installed distribution, and the content of the source files of three kinds
of import package: those of the distributions that provide formats, those of
the distributions installed from a path, an archive or a repository
(`direct_url.json`, PEP 610), and every top-level package imported from
outside site-packages and the standard library (a `PYTHONPATH` checkout, the
working directory, a directory a `.pth` file adds). Tests, `__pycache__` and
bytecode are left out, and so are settings and anything whose only effect is
numerical noise (D4). Nobody sets it; it is compared for equality only (D3).
Computed from metadata and files alone, without importing what it hashes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pkgutil
import platform
import re
import site
import sys
import sysconfig
import time
from collections.abc import Iterable
from importlib import metadata, util
from pathlib import Path

log = logging.getLogger(__name__)

ENTRY_POINTS = "modama.formats"  # the group of the distributions that provide formats
SHORT = 12  # hexadecimal digits of the short form, for people
MAX_DIFFERENCES = 5  # then "and N more" (R36)
LEFT_OUT = ("tests", "__pycache__")  # directories below a package


def _name(distribution: str) -> str:
    """A distribution's name as PEP 503 normalises it."""
    return re.sub(r"[-_.]+", "-", distribution).lower()


def _outside(path: str, excluded: list[Path]) -> bool:
    p = Path(path).resolve()
    return not any(p.is_relative_to(e) for e in excluded)


def _files(location: Path) -> Iterable[Path]:
    """The files of a package directory, tests, __pycache__ and bytecode left out."""
    for directory, subdirectories, names in os.walk(location):
        subdirectories[:] = sorted(d for d in subdirectories if d not in LEFT_OUT)
        for name in sorted(names):
            if not name.endswith((".pyc", ".pyo")):
                yield Path(directory) / name


def _hash(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _source_of(name: str) -> dict[str, str]:
    """Path -> SHA-256 of the files of the top-level import package or module `name`, where it is imported from.

    The paths are relative to the package's parent directory, so that the same
    package gives the same keys wherever it is installed.
    """
    try:
        spec = util.find_spec(name)
    except (ImportError, ValueError):
        return {}
    if spec is None:
        return {}
    out = {}
    if spec.submodule_search_locations:
        for location in spec.submodule_search_locations:
            location = Path(location)
            for file in _files(location):
                out[file.relative_to(location.parent).as_posix()] = _hash(file)
    elif spec.has_location and spec.origin and os.path.isfile(spec.origin):
        origin = Path(spec.origin)
        out[origin.name] = _hash(origin)
    return out


def _pth_directories(dist: metadata.Distribution) -> list[str]:
    """The directories that a distribution's `.pth` files add to sys.path (a bare-`.pth` editable install)."""
    out = []
    for file in dist.files or ():
        if file.suffix != ".pth":
            continue
        try:
            text = Path(file.locate()).read_text()
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "import ")) and os.path.isdir(line):
                out.append(line)
    return out


def ingredients(site_packages: Iterable[str] | None = None) -> tuple[dict, list[str]]:
    """The ingredients of the installed extractors' identity, and the warnings for path installs without source.

    `site_packages` are the directories whose packages count as installed from
    a package index (default: the interpreter's); tests pass others.
    """
    started = time.monotonic()
    if site_packages is None:
        site_packages = site.getsitepackages()
    paths = sysconfig.get_paths()
    excluded = [
        Path(p).resolve()
        for p in [*site_packages, paths["stdlib"], paths["platstdlib"]]
    ]
    first: dict[str, metadata.Distribution] = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if (
            name and _name(name) not in first
        ):  # as metadata.distribution(name) resolves it
            first[_name(name)] = dist
    distributions = {name: dist.version for name, dist in sorted(first.items())}

    # Import names by distribution: top_level.txt or RECORD, as packages_distributions reads them
    imports: dict[str, set[str]] = {}
    for module, names in metadata.packages_distributions().items():
        for name in names:
            imports.setdefault(_name(name), set()).add(module)
    providers = {
        _name(ep.dist.name)
        for ep in metadata.entry_points(group=ENTRY_POINTS)
        if ep.dist
    }
    from_path = {
        name for name, dist in first.items() if dist.read_text("direct_url.json")
    }
    pth = {name: _pth_directories(first[name]) for name in from_path}
    for name, directories in pth.items():
        for module in pkgutil.iter_modules(directories):
            imports.setdefault(name, set()).add(module.name)

    wanted = {m for name in providers | from_path for m in imports.get(name, ())}
    # Every top-level package found outside site-packages and the standard library
    candidates = set().union(*imports.values()) if imports else set()
    outside = [
        p
        for p in (os.path.abspath(e or os.curdir) for e in sys.path)
        if os.path.isdir(p) and _outside(p, excluded)
    ]
    candidates |= {m.name for m in pkgutil.iter_modules(outside)}
    # RECORD-inferred names include dist-info directories and None: not import names
    wanted = {m for m in wanted if isinstance(m, str) and m.isidentifier()}
    candidates = {m for m in candidates if isinstance(m, str) and m.isidentifier()}
    for module in sorted(candidates - wanted):
        try:
            spec = util.find_spec(module)
        except (ImportError, ValueError):
            continue
        if spec is None:
            continue
        locations = list(spec.submodule_search_locations or ()) or (
            [spec.origin] if spec.has_location and spec.origin else []
        )
        if any(_outside(p, excluded) for p in locations):
            wanted.add(module)

    source: dict[str, str] = {}
    for module in sorted(wanted):
        source.update(_source_of(module))
    warnings = [
        f"{name} is installed from a path, but none of its source was found; "
        "a change to it does not change the identity"
        for name in sorted(from_path)
        if not any(
            m.isidentifier() and _source_of(m)
            for m in imports.get(name, ())
            if isinstance(m, str)
        )
    ]
    out = {
        "python": f"{platform.python_implementation().lower()} {platform.python_version()}",
        "distributions": distributions,
        "source": source,
    }
    log.debug(
        "extractor identity: %d distributions, %d source files, %.2f s",
        len(distributions),
        len(source),
        time.monotonic() - started,
    )
    return out, warnings


def digest(ingredients: dict) -> str:
    """The identity: SHA-256 of the ingredients as JSON with sorted keys."""
    text = json.dumps(ingredients, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def short(identity: str | None) -> str:
    """The short form for people, the first 12 hexadecimal digits; an earlier label as it is, quoted."""
    if identity is None:
        return "none"
    if re.fullmatch(r"[0-9a-f]{64}", identity):
        return identity[:SHORT]
    return f'"{identity}"'


def _module(path: str) -> str:
    """The module a source file belongs to: `modama_crawler/records.py` -> `modama_crawler.records`."""
    parts = path.split("/")
    if parts[-1].endswith(".py"):
        stem = parts[-1].removesuffix(".py")
        parts = parts[:-1] if stem == "__init__" else [*parts[:-1], stem]
    else:  # a data file: its package
        parts = parts[:-1] or parts
    return ".".join(parts)


def differences(before: dict | None, identity: str | None, after: dict) -> list[str]:
    """What differs between a stored identity's ingredients and the current ones, cut at five (D6).

    `before` is None when the stored identity's ingredients are not known,
    such as a version label from before identities.
    """
    if before is None:
        return [f"earlier identity {short(identity)}, ingredients unknown"]
    out = []
    if before.get("python") != after["python"]:
        out.append(f"python {before.get('python')} -> {after['python']}")
    old, new = before.get("distributions", {}), after["distributions"]
    for name in sorted(old.keys() | new.keys()):
        if name not in new:
            out.append(f"{name} {old[name]} removed")
        elif name not in old:
            out.append(f"{name} {new[name]} added")
        elif old[name] != new[name]:
            out.append(f"{name} {old[name]} -> {new[name]}")
    old, new = before.get("source", {}), after["source"]
    modules = sorted(
        {_module(p) for p in old.keys() | new.keys() if old.get(p) != new.get(p)}
    )
    out += [f"source of {m} changed" for m in modules]
    if not out:
        return ["no difference in the ingredients"]
    if len(out) > MAX_DIFFERENCES:
        out = [*out[:MAX_DIFFERENCES], f"and {len(out) - MAX_DIFFERENCES} more"]
    return out
