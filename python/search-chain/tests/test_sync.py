"""The emulations against the code the search stack builds (sync.py; @weber, 2026-11-12: "detect when we are out of sync").

Reads the repository's prototypes/search-stack/ directly: missing files fail the test.
"""

import shutil
from pathlib import Path

import pytest
from modama_chain import sync, upstream

REPO = Path(__file__).resolve().parents[3]
STACK = REPO / "prototypes" / "search-stack"
NAMES = {"hit": "HIT", "entry": "ENTRY"}  # the declarations in upstream.py


def stack_copy(target: Path) -> Path:
    """The files sync.py reads, copied from the repository's search stack."""
    target.mkdir()
    for dockerfile, _, folder in sync.BUILDS.values():
        shutil.copy(STACK / dockerfile, target / dockerfile)
        shutil.copytree(STACK / folder, target / folder)
    return target


@pytest.mark.parametrize("key", upstream.FOLLOWS)
def test_each_emulation_follows_what_the_stack_builds(key):
    declared = upstream.FOLLOWS[key]
    actual = sync.built(STACK, declared.upstream)
    dockerfile, _, folder = sync.BUILDS[declared.upstream]
    assert actual == declared, (
        f"The search stack builds {actual.short()} ({dockerfile}, {folder}/),"
        f" the emulation of the view {key!r} follows {declared.short()}.\n"
        f"Review the emulation in python/search-chain/src/modama_chain/upstream.py against"
        f" upstream's code at the new version with our patches (the files and lines in its"
        f" docstrings and SOURCES; the change chain-browse, D9/D10), fix it, then declare"
        f" what it follows now:\n"
        f'{NAMES[key]} = Follows("{actual.upstream}", "{actual.version}", "{actual.patches}")'
    )


def out_of_sync_commit(stack: Path) -> tuple[sync.Follows, str]:
    """Changes matchmaker's commit in the copy `stack`; returns what it built before and the warning to expect."""
    before = sync.built(stack, "matchmaker")
    dockerfile = stack / "matchmaker.Dockerfile"
    dockerfile.write_text(dockerfile.read_text().replace(before.version, "1" * 40))
    return before, (
        f"out of sync: emulates matchmaker {before.version[:7]} + patches {before.patches[:12]},"
        f" the stack builds 1111111 + patches {before.patches[:12]}; review the emulation"
    )


def test_a_changed_commit_is_out_of_sync(tmp_path):
    stack = stack_copy(tmp_path / "stack")
    declared, warning = out_of_sync_commit(stack)
    assert sync.out_of_sync(stack, declared) == warning


def test_a_changed_patch_is_out_of_sync(tmp_path):
    stack = stack_copy(tmp_path / "stack")
    declared = sync.built(stack, "search-api")
    assert sync.out_of_sync(stack, declared) == ""
    (stack / "patches" / "search-api" / "0003-new.patch").write_text(
        "--- a/x\n+++ b/x\n"
    )
    warning = sync.out_of_sync(stack, declared)
    assert warning.startswith(
        f"out of sync: emulates {declared.short()}, the stack builds"
    )
    assert warning.endswith("; review the emulation")


def test_files_that_cannot_be_read_are_a_warning_too(tmp_path):
    assert sync.out_of_sync(tmp_path, upstream.HIT).startswith(
        "out of sync? cannot read what the stack builds: "
    )
