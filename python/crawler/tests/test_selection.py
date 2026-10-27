"""Selecting formats and finding collections (the `format-selection` spec)."""

import pytest
from modama_crawler import selection
from modama_crawler.selection import (
    Config,
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
    ignores = {"/legacy/**": ["empad"], "**/*.old": ["ALL"]}
    assert path_ignored("empad/empad", "/legacy/run1", ignores)
    assert path_ignored("empad/empad", "/legacy", ignores)
    assert not path_ignored("empad/empad", "/new/run1", ignores)
    assert not path_ignored("zarr/zarr", "/legacy/run1", ignores)
    assert path_ignored("zarr/zarr", "/a/b/x.old", ignores)


def test_exclusions():
    assert path_excluded("/scratch/x", ["/scratch/**"])
    assert path_excluded("/scratch", ["/scratch/**"])
    assert not path_excluded("/scratchy", ["/scratch/**"])
    assert path_excluded("/a/.Trash/b", ["**/.Trash/**"])


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
    assert set(found) >= {"core", "collapse", "zarr", "empad"}
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
    assert "empad" not in names(Config(ignore=["empad"]))
    assert "empad" in names(Config(ignore=["empad/empad"]))


def test_unknown_ids_are_rejected():
    collections = selection.discover().values()
    selection.check_ids(["core", "collapse/venv", "ALL"], collections)
    with pytest.raises(ValueError, match="nosuch"):
        selection.check_ids(["nosuch"], collections)
    with pytest.raises(ValueError, match="collapse/vnev"):
        selection.enabled_formats(
            collections, Config(per_path_ignores={"/x/**": ["collapse/vnev"]})
        )
