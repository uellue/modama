"""pytest plugin that tests any collection from its fixtures (design/testing.md T-B).

A collection's `tests/test_fixtures.py` contains one line:

    from modama_crawler.testing import test_coverage, test_fixture, test_manifest  # noqa: F401

Fixtures are directories under `tests/fixtures/` holding only wild files, or
generated at test time by a function named in the manifest `tests/fixtures.toml`
(`generator = "module:function"`, called with the target directory). Every
fixture has a manifest entry with `purpose`, `validity`, `licence` and `source`.
The recognition result of each fixture is compared with `tests/expected/<name>.json`;
`--regen-expected` rewrites it. Every rule the collection defines itself must fire
on at least one representative fixture.
"""

from __future__ import annotations

import importlib
import json
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest
from lxml import etree

from . import mimedb, selection
from .formats import Collection, Result
from .walk import walk

REQUIRED_KEYS = ("purpose", "validity", "licence", "source")
NOT_WILD = ("fixtures.toml", "expected", "__pycache__", ".gitkeep")


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

    def fixture_names(self) -> list[str]:
        on_disk = (
            {p.name for p in self.fixtures_dir.iterdir()}
            if self.fixtures_dir.is_dir()
            else set()
        )
        return sorted(on_disk | set(self.manifest))

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
    collections = selection.discover()
    mimedb.build(collections.values(), tmp_path_factory.mktemp("mime"))
    return collections


@pytest.fixture
def collection_tests(request, mime_database) -> CollectionTests:
    return collection_tests_for(request.module)


def _formats(ct: CollectionTests, installed: dict[str, Collection]):
    core = installed.get("core")
    return list(core.formats if core and core is not ct.collection else []) + list(
        ct.collection.formats
    )


def recognise(
    ct: CollectionTests, installed: dict[str, Collection], name: str, workdir: Path
) -> Result:
    path = ct.materialise(name, workdir)
    return walk(path, _formats(ct, installed))


def test_manifest(collection_tests: CollectionTests):
    ct = collection_tests
    on_disk = (
        {p.name for p in ct.fixtures_dir.iterdir()}
        if ct.fixtures_dir.is_dir()
        else set()
    )
    generated = {name for name, entry in ct.manifest.items() if "generator" in entry}
    missing = on_disk - set(ct.manifest)
    assert not missing, f"fixtures without a manifest entry: {sorted(missing)}"
    orphans = set(ct.manifest) - on_disk - generated
    assert not orphans, f"manifest entries without a fixture: {sorted(orphans)}"
    for name, entry in ct.manifest.items():
        absent = [k for k in REQUIRED_KEYS if k not in entry]
        assert not absent, f"fixture {name}: manifest entry lacks {absent}"
        assert entry["purpose"] in ("representative", "reproducer"), (
            f"fixture {name}: unknown purpose"
        )
    for name in on_disk:
        for p in (ct.fixtures_dir / name).rglob("*"):
            assert p.name not in NOT_WILD and not p.name.endswith(".expected.json"), (
                f"{p} is not a wild file"
            )
    if ct.expected_dir.is_dir():
        stale = {p.stem for p in ct.expected_dir.glob("*.json")} - set(
            ct.fixture_names()
        )
        assert not stale, f"recorded results without a fixture: {sorted(stale)}"


def test_fixture(
    collection_tests: CollectionTests,
    mime_database,
    fixture_name: str,
    tmp_path: Path,
    request,
):
    ct = collection_tests
    result = recognise(ct, mime_database, fixture_name, tmp_path).to_json()
    expected_file = ct.expected_dir / f"{fixture_name}.json"
    if request.config.getoption("--regen-expected") or not expected_file.exists():
        ct.expected_dir.mkdir(exist_ok=True)
        expected_file.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        if not request.config.getoption("--regen-expected"):
            pytest.fail(
                f"recorded a new result in {expected_file}; review it and run again"
            )
        return
    expected = json.loads(expected_file.read_text())
    assert result == expected, (
        f"recognition of {fixture_name} differs from {expected_file}"
    )


def test_coverage(collection_tests: CollectionTests, mime_database, tmp_path: Path):
    """Every rule the collection defines itself fires on at least one representative fixture."""
    ct = collection_tests
    own_types = set()
    for xml in ct.collection.mime_files:
        if xml.name == "freedesktop.org.xml":  # vendored upstream, exempt
            continue
        for mt in etree.parse(str(xml)).getroot().iter("{*}mime-type"):
            if any(
                isinstance(c.tag, str) and c.tag.endswith(("glob", "magic")) for c in mt
            ):
                own_types.add(mt.get("type"))
    own_formats = {f.id for f in ct.collection.formats}
    seen_types, seen_formats = set(), set()
    for name, entry in ct.manifest.items():
        if entry.get("purpose") != "representative":
            continue
        for d in recognise(ct, mime_database, name, tmp_path / name).datasets:
            seen_types.add(d.type)
            seen_formats.add(d.format)
    assert own_types <= seen_types, (
        f"rules without a representative fixture: {sorted(own_types - seen_types)}"
    )
    assert own_formats <= seen_formats, (
        f"formats without a representative fixture: {sorted(own_formats - seen_formats)}"
    )


def validate_oai(xml: bytes, schemas: Path) -> None:
    """Validate an OAI-PMH response against the local XSDs (for the records command tests)."""

    class LocalSchemas(etree.Resolver):
        def resolve(self, url, public_id, context):
            return self.resolve_filename(str(schemas / url.rsplit("/", 1)[-1]), context)

    parser = etree.XMLParser()
    parser.resolvers.add(LocalSchemas())
    schema = etree.XMLSchema(etree.parse(str(schemas / "oai-pmh-oai-dc.xsd"), parser))
    schema.assertValid(etree.fromstring(xml))
