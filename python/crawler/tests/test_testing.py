"""The fixture plugin itself (the `formats-testing` spec), run on a throwaway collection.

Each scenario runs pytest in a subprocess on a package written into the test's
own directory, so that the plugin's failure paths are exercised: today's real
collections all pass, which proves nothing about the checks.
"""

import textwrap
from pathlib import Path

import pytest

ONE_LINER = "from modama_crawler.testing import test_coverage, test_fixture, test_manifest  # noqa: F401\n"
XML = """<?xml version="1.0"?>
<mime-info xmlns='http://www.freedesktop.org/standards/shared-mime-info'>
  <mime-type type="application/x.thr">
    <glob pattern="*.thr"/>{extra_glob}
    <magic priority="60"><match type="string" offset="0" value="THR!"/></magic>
  </mime-type>
</mime-info>
"""
MANIFEST = """[good]
purpose = "representative"
validity = "parser-only: made up for the plugin's tests"
licence = "MIT"
source = "typed"
"""


def write_collection(root: Path, *, extra_glob: str = "", manifest: str = MANIFEST):
    """A collection package `thr` with one shipped fixture `good` that fires every rule."""
    pkg = root / "thr"
    (pkg / "tests" / "fixtures" / "good").mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent(
            """
            from pathlib import Path

            from modama_crawler.formats import Collection

            COLLECTION = Collection("thr", [], mime_files=(Path(__file__).parent / "thr.xml",))
            """
        )
    )
    (pkg / "thr.xml").write_text(XML.format(extra_glob=extra_glob))
    (pkg / "tests" / "__init__.py").write_text("")
    (pkg / "tests" / "test_fixtures.py").write_text(ONE_LINER)
    (pkg / "tests" / "fixtures.toml").write_text(manifest)
    (pkg / "tests" / "fixtures" / "good" / "a.thr").write_bytes(b"by name only\n")
    (pkg / "tests" / "fixtures" / "good" / "noext").write_bytes(b"THR! by content\n")
    return pkg


@pytest.fixture
def collection(pytester):
    return write_collection(Path(pytester.path))


def run(pytester, *args, test: str = ""):
    """Run the throwaway collection's tests, or one of the plugin's three tests by name."""
    target = "thr/tests/test_fixtures.py" + (f"::{test}" if test else "")
    return pytester.runpytest_subprocess(target, "-p", "no:cacheprovider", *args)


def test_first_run_records_and_asks_for_review(pytester, collection):
    result = run(pytester)
    result.assert_outcomes(passed=2, failed=1)
    assert "recorded a new result in" in result.stdout.str()
    assert (collection / "tests" / "expected" / "good.json").exists()
    run(pytester).assert_outcomes(passed=3)


def test_regeneration_names_what_changed(pytester, collection):
    run(pytester, test="test_fixture")  # records
    # A rule change: the glob no longer matches a.thr, which becomes a plain single file
    (collection / "thr.xml").write_text(
        XML.format(extra_glob="").replace('"*.thr"', '"*.thrx"')
    )
    result = run(pytester, test="test_fixture")
    result.assert_outcomes(failed=1)
    out = result.stdout.str()
    assert "differs from" in out and ": /a.thr" in out
    result = run(pytester, "--regen-expected", test="test_fixture")
    result.assert_outcomes(failed=1)
    assert "changed /a.thr; review the diff" in result.stdout.str()
    # Regenerating again changes nothing and passes; so does the plain run
    run(pytester, "--regen-expected", test="test_fixture").assert_outcomes(passed=1)
    run(pytester, test="test_fixture").assert_outcomes(passed=1)


def test_missing_manifest_entry_fails(pytester, collection):
    (collection / "tests" / "fixtures" / "extra").mkdir()
    (collection / "tests" / "fixtures" / "extra" / "b.thr").write_bytes(b"THR!")
    result = run(pytester, test="test_manifest")
    result.assert_outcomes(failed=1)
    assert "fixtures without a manifest entry: ['extra']" in result.stdout.str()


def test_orphan_manifest_entry_fails(pytester, collection):
    (collection / "tests" / "fixtures.toml").write_text(
        MANIFEST
        + '\n[ghost]\npurpose = "reproducer"\nvalidity = "x"\nlicence = "MIT"\nsource = "x"\n'
    )
    result = run(pytester, test="test_manifest")
    result.assert_outcomes(failed=1)
    assert "manifest entries without a fixture: ['ghost']" in result.stdout.str()


def test_sidecar_in_the_fixture_tree_fails(pytester, collection):
    (collection / "tests" / "fixtures" / "good" / "good.expected.json").write_text("{}")
    result = run(pytester, test="test_manifest")
    result.assert_outcomes(failed=1)
    assert "good.expected.json is not a wild file" in result.stdout.str()


def test_stale_recorded_result_fails(pytester, collection):
    (collection / "tests" / "expected").mkdir()
    (collection / "tests" / "expected" / "gone.json").write_text("{}")
    result = run(pytester, test="test_manifest")
    result.assert_outcomes(failed=1)
    assert "recorded results without a fixture: ['gone']" in result.stdout.str()


def test_uncovered_glob_fails_naming_it(pytester):
    write_collection(Path(pytester.path), extra_glob='<glob pattern="*.thr2"/>')
    result = run(pytester, test="test_coverage")
    result.assert_outcomes(failed=1)
    assert (
        "globs without a representative fixture: [('application/x.thr', '*.thr2')]"
        in result.stdout.str()
    )


def test_covered_rules_pass(pytester, collection):
    # The glob fires on a.thr (whose content matches nothing) and the magic rule on noext
    run(pytester, test="test_coverage").assert_outcomes(passed=1)
