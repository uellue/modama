"""Selecting formats and finding collections (the `format-selection` spec)."""

import pytest
from modama_crawler import selection
from modama_crawler.selection import (
    Config,
    compile_patterns,
    compile_per_path,
    enabled,
    load_config,
    path_excluded,
    path_ignored,
)


@pytest.mark.parametrize(
    "select, ignore, expected",
    [
        ([], [], True),  # nothing selected: everything installed
        (["gatan"], [], True),
        (["gatan"], ["gatan/dm3-legacy"], True),
        (["gatan"], ["gatan/dm4"], False),
        (["gatan/dm4"], ["gatan"], True),  # more specific wins
        (["gatan"], ["gatan"], False),  # ignore wins ties
        (["ALL"], ["gatan"], False),
        (["other"], [], False),
        ([], ["ALL"], False),
    ],
)
def test_enabled(select, ignore, expected):
    assert enabled("gatan/dm4", select, ignore) is expected


def test_per_path_ignores_only_subtract():
    ignores = compile_per_path({"/legacy/**": ["empad"], "**/*.old": ["ALL"]})
    assert path_ignored("empad/empad", "/legacy/run1", ignores)
    assert path_ignored("empad/empad", "/legacy", ignores)
    assert not path_ignored("empad/empad", "/new/run1", ignores)
    assert not path_ignored("zarr/zarr", "/legacy/run1", ignores)
    assert path_ignored("zarr/zarr", "/a/b/x.old", ignores)


def excluded(patterns, rel, *, is_dir=False):
    return path_excluded(rel, compile_patterns(patterns), is_dir=is_dir)


def test_exclusions():
    assert excluded(["/scratch/**"], "/scratch/x")
    assert excluded(["/scratch/**"], "/scratch", is_dir=True)
    assert not excluded(["/scratch/**"], "/scratchy", is_dir=True)
    assert excluded(["**/.Trash/**"], "/a/.Trash/b")


def test_exclusions_follow_gitignore():
    # The corners a user copies from a real .gitignore (review A9)
    assert excluded(["foo/bar"], "/foo/bar")
    assert not excluded(["foo/bar"], "/x/foo/bar")  # a middle slash anchors
    assert excluded(["build/"], "/src/build", is_dir=True)
    assert not excluded(["build/"], "/src/build")  # a trailing slash: directories only
    assert excluded(["*.txt", "!keep.txt"], "/other.txt")
    assert not excluded(
        ["*.txt", "!keep.txt"], "/keep.txt"
    )  # negation, last match wins


def test_load_config(tmp_path):
    f = tmp_path / "modama.toml"
    f.write_text(
        """
[formats]
select = ["core", "gatan/dm4"]
ignore = ["gatan/dm3-legacy"]
[formats.per-path-ignores]
"/legacy/**" = ["empad"]
[crawl]
exclude = ["/scratch/**"]
"""
    )
    assert load_config(f) == Config(
        ["core", "gatan/dm4"],
        ["gatan/dm3-legacy"],
        {"/legacy/**": ["empad"]},
        ["/scratch/**"],
    )
    assert load_config(None) == Config()


def test_installed_collections_and_duplicates(monkeypatch):
    found = selection.discover()
    assert set(found) >= {"core", "collapse", "zarr"}
    assert {f.id for f in found["collapse"].formats} >= {
        "collapse/venv",
        "collapse/git",
    }

    class Dup:
        def __init__(self, name):
            self.dist = type("D", (), {"name": name})()

        def load(self):
            return found["core"]

    monkeypatch.setattr(selection, "entry_points", lambda group: [Dup("a"), Dup("b")])
    with pytest.raises(ValueError, match="registered twice: by a and by b"):
        selection.discover()


def test_collection_ids_cover_mime_definitions():
    collections = list(selection.discover().values())

    def names(cfg):
        return [c.name for c in selection.enabled_collections(collections, cfg)]

    assert names(Config()) == [c.name for c in collections]
    assert names(Config(select=["core"])) == ["core"]
    assert "zarr" not in names(Config(ignore=["zarr"]))
    assert "zarr" in names(Config(ignore=["zarr/zarr"]))


def test_unknown_ids_are_rejected():
    collections = selection.discover().values()
    selection.check_ids(["core", "collapse/venv", "ALL"], collections)
    with pytest.raises(ValueError, match="nosuch"):
        selection.check_ids(["nosuch"], collections)
    with pytest.raises(ValueError, match="collapse/vnev"):
        selection.enabled_formats(
            collections, Config(per_path_ignores={"/x/**": ["collapse/vnev"]})
        )


@pytest.mark.parametrize("dist", ["modama-crawler", "modama-formats-em"])
def test_the_fingerprint_covers_the_distribution_versions(monkeypatch, dist):
    # Not a scenario of its own: a release can change a format's code without its version (review 2026-11-11, 6)
    collections = list(selection.discover().values())
    if dist == "modama-formats-em" and "em" not in {c.name for c in collections}:
        pytest.skip("modama-formats-em is not installed")
    formats = selection.enabled_formats(collections, Config())
    before = selection.fingerprint(formats, collections, Config())
    real = selection.version
    monkeypatch.setattr(selection, "version", lambda d: "999" if d == dist else real(d))
    assert selection.fingerprint(formats, collections, Config()) != before
