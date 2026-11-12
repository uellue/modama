"""The extractor identity (the `extraction` spec, "The extractor identity is derived from the installation" and the two requirements after it).

Each identity is computed in a fresh interpreter, as a crawl computes it at
its start, with made-up distributions in site directories of the test's
(`site.addsitedir`, which also processes their `.pth` files) and packages on
`PYTHONPATH` or in the working directory.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from conftest import CRAWLER, shell
from modama_crawler import identity

# The site directories in argv count as site-packages, as an index install's would
COMPUTE = """
import json, site, sys
from modama_crawler import identity
extra = sys.argv[1:]
for d in extra:
    site.addsitedir(d)
ingredients, warnings = identity.ingredients([*site.getsitepackages(), *extra])
print(json.dumps({"identity": identity.digest(ingredients), "ingredients": ingredients, "warnings": warnings}))
"""


def computed(cwd: Path, *sites: Path, pythonpath: Path | None = None, **env) -> dict:
    environment = {**os.environ, **env}
    environment.pop("PYTHONPATH", None)
    if pythonpath is not None:
        environment["PYTHONPATH"] = str(pythonpath)
    cwd.mkdir(parents=True, exist_ok=True)
    run = subprocess.run(
        [sys.executable, "-c", COMPUTE, *map(str, sites)],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(run.stdout)


def package(parent: Path, name: str, text: str = "X = 1\n") -> Path:
    (parent / name).mkdir(parents=True, exist_ok=True)
    (parent / name / "__init__.py").write_text(text)
    return parent / name


def distribution(site: Path, name: str, version: str, *, url=None, pth=None) -> None:
    """A dist-info as an installer writes it; with `url` a direct_url.json (PEP 610), with `pth` a .pth file adding that directory."""
    info = site / f"{name}-{version}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    )
    record = [f"{info.name}/METADATA,,"]
    if url is not None:
        (info / "direct_url.json").write_text(
            json.dumps({"url": url, "dir_info": {"editable": True}})
        )
    if pth is not None:
        (site / f"_{name}.pth").write_text(f"{pth}\n")
        record.append(f"_{name}.pth,,")
    (info / "RECORD").write_text("\n".join(record) + "\n")


# "The extractor identity is derived from the installation"


def test_the_same_installation_in_two_places(tmp_path):
    for place in ("one", "two"):
        package(tmp_path / place, "shadowed", "VALUE = 'same'\n")
    one = computed(tmp_path / "cwd", pythonpath=tmp_path / "one")
    two = computed(tmp_path / "cwd", pythonpath=tmp_path / "two")
    assert "shadowed/__init__.py" in one["ingredients"]["source"]
    assert one["identity"] == two["identity"]


def test_a_test_file_does_not_count(tmp_path):
    pkg = package(tmp_path / "path", "fmtpkg")
    (pkg / "tests").mkdir()
    (pkg / "tests" / "test_x.py").write_text("def test(): pass\n")
    (pkg / "tests" / "fixture.dm4").write_bytes(b"\0")
    before = computed(tmp_path / "cwd", pythonpath=tmp_path / "path")
    (pkg / "tests" / "test_x.py").write_text("def test(): assert True\n")
    (pkg / "tests" / "fixture.dm4").write_bytes(b"\1")
    after = computed(tmp_path / "cwd", pythonpath=tmp_path / "path")
    assert before["identity"] == after["identity"]
    (pkg / "__init__.py").write_text("X = 2\n")
    assert computed(tmp_path / "cwd", pythonpath=tmp_path / "path") != after


def test_a_dependency_installed_from_a_repository(tmp_path):
    # A non-editable install from a path lands in site-packages, beside index installs
    site = tmp_path / "site"
    distribution(site, "fromgit", "1.0", url="git+https://example.org/fromgit.git")
    (site / "fromgit-1.0.dist-info" / "top_level.txt").write_text("fromgit\n")
    pkg = package(site, "fromgit")
    before = computed(tmp_path / "cwd", site)
    assert "fromgit/__init__.py" in before["ingredients"]["source"]
    (pkg / "__init__.py").write_text("X = 2\n")
    after = computed(tmp_path / "cwd", site)
    assert after["ingredients"]["distributions"]["fromgit"] == "1.0"
    assert before["identity"] != after["identity"]


def test_a_package_on_pythonpath_shadows_an_installed_one(tmp_path):
    # python-dotenv is installed with the crawler; its import name is dotenv
    pkg = package(tmp_path / "path", "dotenv", "A = 1\n")
    before = computed(tmp_path / "cwd", pythonpath=tmp_path / "path")
    (pkg / "__init__.py").write_text("A = 2\n")
    after = computed(tmp_path / "cwd", pythonpath=tmp_path / "path")
    assert (
        before["ingredients"]["distributions"]["python-dotenv"]
        == after["ingredients"]["distributions"]["python-dotenv"]
    )
    assert before["identity"] != after["identity"]


def test_a_stale_egg_info_ahead_of_the_real_metadata(tmp_path):
    checkout = tmp_path / "checkout"  # the working directory, first on sys.path
    pkg = package(checkout, "editable")
    (checkout / "editable.egg-info").mkdir()
    (checkout / "editable.egg-info" / "PKG-INFO").write_text(
        "Metadata-Version: 2.1\nName: editable\nVersion: 0.9\n"
    )
    site = tmp_path / "site"
    distribution(site, "editable", "1.0", url=checkout.as_uri(), pth=checkout)
    before = computed(checkout, site)
    assert (
        before["ingredients"]["distributions"]["editable"] == "0.9"
    )  # the first found
    (pkg / "__init__.py").write_text("X = 2\n")
    assert computed(checkout, site)["identity"] != before["identity"]


def test_a_bare_pth_editable_install(tmp_path):
    # As hatchling, flit, pdm and uv_build install editable: no import name mapped
    src = tmp_path / "src"
    pkg = package(src, "hatched")
    site = tmp_path / "site"
    distribution(site, "hatched", "1.0", url=src.as_uri(), pth=src)
    before = computed(tmp_path / "cwd", site)
    assert before["warnings"] == []
    (pkg / "__init__.py").write_text("X = 2\n")
    assert computed(tmp_path / "cwd", site)["identity"] != before["identity"]


# "Settings and numerical noise are not part of the identity"


def test_a_changed_limit_does_not_count(tmp_path):
    before = computed(tmp_path / "cwd")
    after = computed(
        tmp_path / "cwd",
        MODAMA_CRAWLER_EXTRACT_MEMORY="400",
        MODAMA_CRAWLER_EXTRACT_WORKERS="2",
        OMP_NUM_THREADS="4",
    )
    assert before["identity"] == after["identity"]


# "A path install without source is named"

WARNING = (
    "nosource is installed from a path, but none of its source was found; "
    "a change to it does not change the identity"
)


def test_a_distribution_installed_from_a_path_without_source_found(
    tmp_path, conn, env, tree
):
    site = tmp_path / "site"
    distribution(site, "nosource", "1.0", url=(tmp_path / "gone").as_uri())
    assert computed(tmp_path / "cwd", site)["warnings"] == [WARNING]
    # The crawl's report and log: a site directory added at start-up
    (tmp_path / "custom").mkdir()
    (tmp_path / "custom" / "sitecustomize.py").write_text(
        f"import site\nsite.addsitedir({str(site)!r})\n"
    )
    run = shell(
        f"{CRAWLER} crawl --root {tree}",
        {**env, "PYTHONPATH": str(tmp_path / "custom")},
    )
    assert run.returncode == 0, run.stderr
    assert f"WARNING {WARNING}\n" in run.stderr


# What changed between two identities (design D6), and the cost


def test_the_wording_of_each_difference():
    before = {
        "python": "cpython 3.14.0",
        "distributions": {"numpy": "2.3.4", "old": "1.0", "rosettasciio": "0.15.0"},
        "source": {
            "modama_formats_em/dm/__init__.py": "a",
            "modama_formats_em/dm/dm.xml": "b",
            "modama_crawler/records.py": "c",
        },
    }
    after = {
        "python": "cpython 3.14.1",
        "distributions": {"new": "2.0", "numpy": "2.3.4", "rosettasciio": "0.16.0"},
        "source": {
            "modama_formats_em/dm/__init__.py": "a",
            "modama_formats_em/dm/dm.xml": "b2",
            "modama_crawler/records.py": "c",
        },
    }
    assert identity.differences(before, "x", after) == [
        "python cpython 3.14.0 -> cpython 3.14.1",
        "new 2.0 added",
        "old 1.0 removed",
        "rosettasciio 0.15.0 -> 0.16.0",
        "source of modama_formats_em.dm changed",
    ]
    after["source"]["modama_crawler/records.py"] = "c2"
    assert identity.differences(before, "x", after)[-1] == "and 1 more"
    assert identity.differences(None, "4", after) == [
        'earlier identity "4", ingredients unknown'
    ]


def test_computed_in_under_a_second():
    started = time.monotonic()
    ingredients, _ = identity.ingredients()
    assert time.monotonic() - started < 1
    assert "modama_crawler/identity.py" in ingredients["source"]
    assert "modama_crawler/tests/conftest.py" not in ingredients["source"]
    assert (
        identity.short(identity.digest(ingredients))
        == identity.digest(ingredients)[:12]
    )
