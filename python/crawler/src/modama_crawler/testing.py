"""pytest plugin that tests any collection from its fixtures (design/testing.md T-B).

A collection's `tests/test_fixtures.py` contains one line:

    from modama_crawler.testing import test_coverage, test_fixture, test_manifest  # noqa: F401

Fixtures are directories under `tests/fixtures/` holding only wild files, or
generated at test time by a function named in the manifest `tests/fixtures.toml`
(`generator = "module:function"`, called with the target directory). Every
fixture has a manifest entry with `purpose`, `validity`, `licence` and `source`.

The recognition result of each fixture is compared with `tests/expected/<name>.json`.
A missing result is recorded on the first run, which fails and asks for a review
(decision T4, the pytest-regressions model); `--regen-expected` rewrites the
results and fails for every file that changed, naming the datasets, so that the
run itself says what to review. Every rule the collection defines itself (each
glob, each magic rule, each Python format) must fire on at least one
representative fixture. A collection is tested with its own definitions plus
the core's, whatever else is installed (R2, R3).
"""

from __future__ import annotations

import fnmatch
import importlib
import json
import os
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest
from lxml import etree
from xdg import Mime

from . import mimedb, selection
from .formats import Collection, Result
from .walk import walk

REQUIRED_KEYS = ("purpose", "validity", "licence", "source")
NOT_WILD = ("fixtures.toml", "expected", "__pycache__", ".gitkeep")
CORE = "core"
VENDORED = (
    "freedesktop.org.xml",
)  # upstream definitions, exempt from the coverage rule

_session_database: Path | None = None


@dataclass
class CollectionTests:
    collection: Collection
    tests_dir: Path
    manifest: dict[str, dict]

    @property
    def fixtures_dir(self) -> Path:
        return self.tests_dir / "fixtures"

    @property
    def expected_dir(self) -> Path:
        return self.tests_dir / "expected"

    @property
    def on_disk(self) -> set[str]:
        if not self.fixtures_dir.is_dir():
            return set()
        return {p.name for p in self.fixtures_dir.iterdir()}

    def fixture_names(self) -> list[str]:
        return sorted(self.on_disk | set(self.manifest))

    def materialise(self, name: str, target: Path) -> Path:
        """The fixture as a directory: copied from disk, or written by its generator."""
        entry = self.manifest.get(name, {})
        path = target / name
        if "generator" in entry:
            module, function = entry["generator"].split(":")
            getattr(importlib.import_module(module), function)(path)
        else:
            shutil.copytree(self.fixtures_dir / name, path, symlinks=True)
        return path


def collection_tests_for(module) -> CollectionTests:
    """The collection a test module belongs to: the package above its `tests` package."""
    package = module.__name__.rsplit(".tests", 1)[0]
    collection = importlib.import_module(package).COLLECTION
    tests_dir = Path(module.__file__).parent
    manifest_file = tests_dir / "fixtures.toml"
    manifest = (
        tomllib.loads(manifest_file.read_text()) if manifest_file.exists() else {}
    )
    return CollectionTests(collection, tests_dir, manifest)


def pytest_addoption(parser):
    parser.addoption(
        "--regen-expected", action="store_true", help="rewrite recorded fixture results"
    )


def pytest_generate_tests(metafunc):
    if "fixture_name" in metafunc.fixturenames:
        metafunc.parametrize(
            "fixture_name", collection_tests_for(metafunc.module).fixture_names()
        )


@pytest.fixture(scope="session")
def mime_database(tmp_path_factory):
    """The MIME database of every installed collection, built once per session."""
    global _session_database
    collections = selection.discover()
    _session_database = tmp_path_factory.mktemp("mime")
    mimedb.build(collections.values(), _session_database)
    return collections


@pytest.fixture(scope="module")
def collection_tests(request, mime_database, tmp_path_factory) -> CollectionTests:
    """The collection under test, with a MIME database of its own definitions plus the core's."""
    ct = collection_tests_for(request.module)
    core = mime_database.get(CORE)
    own = (
        [ct.collection]
        if core is None or core is ct.collection
        else [core, ct.collection]
    )
    mimedb.build(own, tmp_path_factory.mktemp("mime-collection"))
    yield ct
    mimedb.activate(_session_database)


def recognise(ct: CollectionTests, name: str, workdir: Path) -> Result:
    return walk(ct.materialise(name, workdir), ct.collection.formats)


def test_manifest(collection_tests: CollectionTests):
    ct = collection_tests
    generated = {name for name, entry in ct.manifest.items() if "generator" in entry}
    missing = ct.on_disk - set(ct.manifest)
    assert not missing, f"fixtures without a manifest entry: {sorted(missing)}"
    orphans = set(ct.manifest) - ct.on_disk - generated
    assert not orphans, f"manifest entries without a fixture: {sorted(orphans)}"
    for name, entry in ct.manifest.items():
        absent = [k for k in REQUIRED_KEYS if k not in entry]
        assert not absent, f"fixture {name}: manifest entry lacks {absent}"
        assert entry["purpose"] in ("representative", "reproducer"), (
            f"fixture {name}: unknown purpose"
        )
    for name in ct.on_disk:
        for p in (ct.fixtures_dir / name).rglob("*"):
            assert p.name not in NOT_WILD and not p.name.endswith(".expected.json"), (
                f"{p} is not a wild file"
            )
    if ct.expected_dir.is_dir():
        stale = {p.stem for p in ct.expected_dir.glob("*.json")} - set(
            ct.fixture_names()
        )
        assert not stale, f"recorded results without a fixture: {sorted(stale)}"


def _changes(old: dict, new: dict) -> list[str]:
    """What differs between two recorded results, by dataset anchor."""
    before = {d["anchor"]: d for d in old["datasets"]}
    after = {d["anchor"]: d for d in new["datasets"]}
    changed = [
        a for a in sorted(before.keys() | after.keys()) if before.get(a) != after.get(a)
    ]
    for key in ("warnings", "skipped"):
        if old.get(key) != new.get(key):
            changed.append(key)
    return changed


def test_fixture(
    collection_tests: CollectionTests,
    fixture_name: str,
    tmp_path: Path,
    request,
):
    ct = collection_tests
    result = recognise(ct, fixture_name, tmp_path).to_json()
    expected_file = ct.expected_dir / f"{fixture_name}.json"
    regen = request.config.getoption("--regen-expected")
    if not expected_file.exists():
        ct.expected_dir.mkdir(exist_ok=True)
        expected_file.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        pytest.fail(
            f"recorded a new result in {expected_file}; review it and run again"
        )
    expected = json.loads(expected_file.read_text())
    if regen:
        changed = _changes(expected, result)
        if changed:
            expected_file.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n"
            )
            pytest.fail(
                f"regenerated {expected_file}: changed {', '.join(changed)}; review the diff"
            )
        return
    assert result == expected, (
        f"recognition of {fixture_name} differs from {expected_file}: "
        f"{', '.join(_changes(expected, result))}"
    )


def _own_rules(ct: CollectionTests) -> tuple[list[tuple[str, str, bool]], set[str]]:
    """The collection's own globs as (type, pattern, case-sensitive) and the types with own magic."""
    globs, magic_types = [], set()
    for xml in ct.collection.mime_files:
        if xml.name in VENDORED:
            continue
        for mt in etree.parse(str(xml)).getroot().iter("{*}mime-type"):
            for child in mt:
                if not isinstance(child.tag, str):
                    continue  # a comment
                if child.tag.endswith("glob"):
                    globs.append(
                        (
                            mt.get("type"),
                            child.get("pattern"),
                            child.get("case-sensitive") == "true",
                        )
                    )
                elif child.tag.endswith("magic"):
                    magic_types.add(mt.get("type"))
    return globs, magic_types


def _files(path: Path):
    """(name, first bytes) of every regular file below path."""
    for dirpath, _, names in os.walk(path):
        for name in names:
            file = Path(dirpath) / name
            if file.is_file() and not file.is_symlink():
                with open(file, "rb") as f:
                    yield name, f.read(Mime.magic.maxlen)


def test_coverage(collection_tests: CollectionTests, tmp_path: Path):
    """Every rule the collection defines itself fires on at least one representative fixture."""
    ct = collection_tests
    globs, magic_types = _own_rules(ct)
    own_formats = {f.id for f in ct.collection.formats}
    unfired_globs = {(t, pattern) for t, pattern, _ in globs}
    unfired_magic = {
        (str(t), i)
        for t in magic_types
        for i, _ in enumerate(Mime.magic.bytype.get(Mime.lookup(t), ()))
    }
    seen_formats = set()
    for name, entry in ct.manifest.items():
        if entry.get("purpose") != "representative":
            continue
        result = recognise(ct, name, tmp_path / name)
        seen_formats |= {d.format for d in result.datasets}
        for file_name, data in _files(tmp_path / name):
            for t, pattern, cased in globs:
                if (fnmatch.fnmatchcase if cased else fnmatch.fnmatch)(
                    file_name if cased else file_name.lower(),
                    pattern if cased else pattern.lower(),
                ):
                    unfired_globs.discard((t, pattern))
            for t in magic_types:
                for i, (_, rule) in enumerate(
                    Mime.magic.bytype.get(Mime.lookup(t), ())
                ):
                    if rule.match(data):
                        unfired_magic.discard((t, i))
    assert not unfired_globs, (
        f"globs without a representative fixture: {sorted(unfired_globs)}"
    )
    assert not unfired_magic, (
        f"magic rules without a representative fixture (type, rule index): {sorted(unfired_magic)}"
    )
    assert own_formats <= seen_formats, (
        f"formats without a representative fixture: {sorted(own_formats - seen_formats)}"
    )
