"""The subtree crawl, `crawl --path` (change subtree-crawl, spec `crawl`): in this process, against a throwaway database.

The formats are the stand-ins (standin.py), whose extractor's output follows
its `variant`, and the crawler's own collapse and Zarr formats; the
extractor identity is passed in, as in test_extraction.
"""

import os
import signal

import pytest
import standin
from modama_crawler import cli, identity, selection
from modama_crawler import walk as walk_module
from modama_crawler.records import oai_identifier

P = "adhoc/lib/test-data"


def installation(dm="a") -> tuple[str, dict]:
    """An extractor identity and its ingredients, standing in for an installation (identity.ingredients)."""
    ingredients = {
        "python": "cpython 3.14.0",
        "distributions": {"modama-crawler": "0.0.1.dev0"},
        "source": {"standin.py": dm},
    }
    return identity.digest(ingredients), ingredients


A, B = installation(), installation("experiment")


@pytest.fixture
def data(tmp_path):
    """adhoc/lib/test-data with two stand-in datasets and a text file, one more stand-in in other/."""
    root = tmp_path / "data"
    for path, text in {
        f"{P}/dm/a.stand": "versioned a",
        f"{P}/dm/b.stand": "versioned b",
        f"{P}/notes.txt": "notes",
        "other/c.stand": "versioned c",
    }.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    return root


@pytest.fixture
def crawl(env, data, tmp_path, monkeypatch):
    """`modama-crawler crawl ARGS` in this process: crawl(*args, variant=, installed=, root=) -> exit status.

    The configuration is read from --config (or MODAMA_CRAWLER_CONFIG) as the
    command does; the formats are the stand-ins, collapse and zarr.
    """
    collections = selection.discover()
    formats = [
        *standin.collection(tmp_path / "calls").formats,
        *collections["collapse"].formats,
        *collections["zarr"].formats,
    ]

    def configure(args):
        config = selection.load_config(args.config)
        if args.select is not None:
            config.select = args.select
        if args.ignore is not None:
            config.ignore = args.ignore
        return config, formats, "r1"

    def run(*args, variant="1", installed=A, root=data) -> int:
        formats[0].variant = variant
        monkeypatch.setattr(cli, "configure", configure)
        monkeypatch.setattr(cli, "_installed", lambda: installed)
        handler = signal.getsignal(signal.SIGTERM)
        try:
            return cli.main(["crawl", "--root", str(root), *args])
        finally:
            signal.signal(signal.SIGTERM, handler)

    return run


def records(conn) -> dict[str, tuple]:
    """The records by identifier: (datestamp, metadata)."""
    conn.commit()
    return {
        identifier: (datestamp, metadata)
        for identifier, datestamp, metadata in conn.execute(
            "SELECT identifier, datestamp, metadata FROM records"
        )
    }


def record(conn, anchor: str):
    conn.commit()
    return conn.execute(
        "SELECT datestamp, metadata FROM records WHERE identifier = %s",
        (oai_identifier(anchor),),
    ).fetchone()


def runs(conn) -> list[tuple]:
    conn.commit()
    return conn.execute(
        "SELECT outcome, root, scope, error FROM crawl_runs ORDER BY run_id"
    ).fetchall()


def anchors(conn) -> list[str]:
    conn.commit()
    return [a for (a,) in conn.execute("SELECT anchor FROM datasets ORDER BY 1")]


def words(conn) -> dict[str, str]:
    """The stand-in extractions' words by anchor."""
    conn.commit()
    return dict(
        conn.execute(
            "SELECT anchor, extracted->'values'->>'word' FROM datasets WHERE extractor IS NOT NULL"
        ).fetchall()
    )


# Requirement: Results reach the index


def test_a_deleted_file_in_a_subtree_leaves_the_index(conn, crawl, data):
    assert crawl() == 0
    before = records(conn)
    (data / P / "dm" / "b.stand").unlink()
    assert crawl("--path", P) == 0
    after = records(conn)
    gone = oai_identifier(f"/{P}/dm/b.stand")
    assert gone in before and gone not in after
    assert after == {i: r for i, r in before.items() if i != gone}


# Requirement: A subtree crawl changes only its subtree


def test_records_outside_the_subtree_stay_as_they_are(conn, crawl, data):
    assert crawl() == 0
    before = records(conn)
    (data / "other" / "c.stand").unlink()
    (data / P / "dm" / "a.stand").write_text("versioned a2")
    assert crawl("--path", P) == 0
    after = records(conn)
    # still there, although the file is gone: outside the subtree
    assert (
        after[oai_identifier("/other/c.stand")]
        == before[oai_identifier("/other/c.stand")]
    )
    changed = {i for i in after if after[i] != before.get(i)}
    assert changed == {oai_identifier(f"/{P}/dm/a.stand")}


def test_a_sibling_with_the_same_prefix_stays(conn, crawl, data):
    for name in ("b/x.txt", "bc/y.txt", "b_/z.txt", "b%/w.txt"):
        (data / "adhoc" / "a" / name).parent.mkdir(parents=True)
        (data / "adhoc" / "a" / name).write_text(name)
    assert crawl() == 0
    before = records(conn)
    listings = conn.execute(
        "SELECT path, digest FROM directories ORDER BY 1"
    ).fetchall()
    conn.commit()
    for name in ("b/x.txt", "bc/y.txt", "b_/z.txt", "b%/w.txt"):
        (data / "adhoc" / "a" / name).unlink()
    assert crawl("--path", "adhoc/a/b") == 0
    after = records(conn)
    for name in ("bc/y.txt", "b_/z.txt", "b%/w.txt"):
        identifier = oai_identifier(f"/adhoc/a/{name}")
        assert after[identifier] == before[identifier], name
    assert oai_identifier("/adhoc/a/b/x.txt") not in after
    # The siblings' stored listings are kept, so the next full crawl takes them over
    kept = conn.execute("SELECT path, digest FROM directories ORDER BY 1").fetchall()
    for sibling in ("/adhoc/a/bc", "/adhoc/a/b_", "/adhoc/a/b%"):
        assert [r for r in kept if r[0] == sibling] == [
            r for r in listings if r[0] == sibling
        ]
    assert [r for r in kept if r[0] == "/adhoc/a/b"] == []


def test_the_same_identifiers_as_a_full_crawl(conn, crawl):
    assert crawl("--path", f"/{P}") == 0
    subtree = records(conn)
    assert oai_identifier(f"/{P}/dm/a.stand") in subtree
    assert crawl() == 0
    after = records(conn)
    assert {i: after[i] for i in subtree} == subtree


# Requirement: A subtree crawl's path is a canonical path


def test_a_path_in_another_spelling(conn, crawl):
    assert crawl("--path", "adhoc/other/../lib/test-data/") == 0
    assert runs(conn)[-1][2] == f"/{P}"
    assert oai_identifier(f"/{P}/dm/a.stand") in records(conn)


def test_a_folder_whose_name_starts_with_a_dot(conn, crawl, data):
    (data / ".hidden").mkdir()
    (data / ".hidden" / "x.txt").write_text("x")
    assert crawl("--path", ".hidden") == 0
    assert runs(conn)[-1][2] == "/.hidden"
    assert anchors(conn) == ["/.hidden/x.txt"]


def test_a_file_stands_for_its_directory(conn, crawl, caplog):
    assert crawl("--path", f"{P}/dm/a.stand") == 0
    assert runs(conn)[-1][2] == f"/{P}/dm"
    assert anchors(conn) == [f"/{P}/dm/a.stand", f"/{P}/dm/b.stand"]
    assert f"is a file: crawling its directory {P}/dm" in caplog.text


# Requirement: A subtree crawl recognises and extracts its subtree again


def test_a_changed_extractor(conn, crawl, tmp_path):
    assert crawl() == 0
    before = records(conn)
    calls = len(standin.calls(tmp_path / "calls"))
    assert crawl("--path", P, variant="2", installed=B) == 0
    assert sorted(standin.calls(tmp_path / "calls")[calls:]) == [
        f"/{P}/dm/a.stand",
        f"/{P}/dm/b.stand",
    ]
    assert words(conn) == {
        f"/{P}/dm/a.stand": "a v2",
        f"/{P}/dm/b.stand": "b v2",
        "/other/c.stand": "c v1",
    }
    after = records(conn)
    changed = {i for i in after if after[i] != before[i]}
    assert changed == {
        oai_identifier(f"/{P}/dm/a.stand"),
        oai_identifier(f"/{P}/dm/b.stand"),
    }


def test_a_reverted_experiment_is_undone_by_the_next_full_crawl(conn, crawl):
    assert crawl() == 0
    first = {i: m for i, (_, m) in records(conn).items()}
    assert crawl("--path", P, variant="2", installed=B) == 0
    assert {i: m for i, (_, m) in records(conn).items()} != first
    assert crawl() == 0
    assert {i: m for i, (_, m) in records(conn).items()} == first


def test_the_same_code_gives_the_same_records(conn, crawl, caplog):
    assert crawl("--path", P) == 0
    before = records(conn)
    caplog.clear()
    assert crawl("--path", P) == 0
    assert "extraction: 2 run, 0 reused, 0 failed" in caplog.text
    assert "0 records changed" in caplog.text
    assert records(conn) == before


def test_the_next_full_crawl_takes_over_the_extractions(conn, crawl, caplog):
    assert crawl() == 0
    assert crawl("--path", P) == 0
    before = records(conn)
    caplog.clear()
    assert crawl() == 0
    # The subtree and the directories above it are recognised again, the rest taken over
    assert "extraction: 0 run, 3 reused, 0 failed" in caplog.text
    assert "0 records changed" in caplog.text
    assert records(conn) == before


# Requirement: A subtree crawl only covers what a full crawl enters


def test_a_collapsed_directory_as_path(conn, crawl, data):
    store = data / "adhoc" / "project" / "data.zarr"
    (store / "0").mkdir(parents=True)
    (store / ".zgroup").write_text('{"zarr_format": 2}')
    assert crawl() == 0
    full = record(conn, "/adhoc/project/data.zarr")
    assert full is not None
    conn.execute("DELETE FROM records")
    conn.execute("DELETE FROM datasets")
    conn.commit()
    assert crawl("--path", "adhoc/project/data.zarr") == 0
    assert anchors(conn) == ["/adhoc/project/data.zarr"]
    assert record(conn, "/adhoc/project/data.zarr")[1] == full[1]


def refused(conn, status, caplog, *texts):
    assert status == 2
    assert runs(conn) == [] or runs(conn)[-1][2] is None  # no subtree run recorded
    for text in texts:
        assert text in caplog.text, caplog.text
    assert "Traceback" not in caplog.text


def test_a_path_inside_a_collapsed_directory(conn, crawl, data, caplog):
    venv = data / "adhoc" / "project" / ".venv"
    (venv / "lib").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\n")
    refused(
        conn,
        crawl("--path", "adhoc/project/.venv/lib"),
        caplog,
        "/adhoc/project/.venv is collapsed by collapse/venv",
    )
    assert runs(conn) == []


def test_a_path_inside_a_stored_collapsed_dataset(conn, crawl, data, caplog):
    store = data / "adhoc" / "project" / "data.zarr"
    (store / "0").mkdir(parents=True)
    (store / "0" / "chunk.txt").write_text("c")
    (store / ".zgroup").write_text('{"zarr_format": 2}')
    assert crawl() == 0
    (store / ".zgroup").unlink()  # no longer a store, but the index still says so
    before = records(conn)
    refused(
        conn,
        crawl("--path", "adhoc/project/data.zarr/0"),
        caplog,
        "/adhoc/project/data.zarr is stored as one collapsed dataset",
        "--path adhoc/project/data.zarr",
    )
    assert len(runs(conn)) == 1
    assert records(conn) == before
    assert crawl("--path", "adhoc/project/data.zarr") == 0


def test_an_excluded_path(conn, crawl, data, tmp_path, caplog):
    (data / "scratch" / "tmp").mkdir(parents=True)
    config = tmp_path / "c.toml"
    config.write_text('[crawl]\nexclude = ["/scratch/**"]\n')
    refused(
        conn,
        crawl("--config", str(config), "--path", "scratch/tmp"),
        caplog,
        # gitignore's "/scratch/**" matches the folder itself too, as in the walk
        "cannot crawl --path scratch/tmp: /scratch is excluded by [crawl] exclude",
    )
    assert runs(conn) == []


def test_a_symlink_on_the_way(conn, crawl, data, caplog):
    (data / "adhoc" / "real" / "session1").mkdir(parents=True)
    (data / "adhoc" / "link").symlink_to("real")
    refused(
        conn,
        crawl("--path", "adhoc/link/session1"),
        caplog,
        "/adhoc/link is a symlink",
    )
    assert runs(conn) == []


def test_a_directory_on_the_way_that_cannot_be_listed(
    conn, crawl, data, caplog, monkeypatch
):
    (data / "adhoc" / "closed" / "session1").mkdir(parents=True)
    closed = str(data / "adhoc" / "closed")
    real = walk_module._names

    def names(dirpath):
        if dirpath == closed:
            raise PermissionError(13, "Permission denied", dirpath)
        return real(dirpath)

    monkeypatch.setattr(walk_module, "_names", names)
    refused(
        conn,
        crawl("--path", "adhoc/closed/session1"),
        caplog,
        "/adhoc/closed cannot be listed: Permission denied",
    )
    assert runs(conn) == []


# Requirement: A subtree crawl's path lies below the data root


@pytest.mark.parametrize("path", ["../etc", "adhoc/nosuch"])
def test_a_path_outside_the_data_root(conn, crawl, caplog, path):
    refused(conn, crawl("--path", path), caplog, f"cannot crawl --path {path}:")
    assert runs(conn) == []


def test_a_path_typed_as_the_containers_path(conn, crawl, data, caplog):
    refused(
        conn,
        crawl("--path", f"{data}/adhoc/lib"),
        caplog,
        f"cannot crawl --path {data}/adhoc/lib: no such directory under the data root {data}"
        " (--path is relative to it)",
    )


@pytest.mark.parametrize("path", ["/", ".", "", "README.txt"])
def test_the_data_root_as_path(conn, crawl, data, caplog, path):
    (data / "README.txt").write_text("read me")
    refused(
        conn,
        crawl("--path", path),
        caplog,
        "the data root is crawled by `crawl` without --path",
    )
    assert runs(conn) == []


def test_a_path_that_is_not_utf8(conn, crawl, data, caplog):
    os.mkdir(os.fsencode(data / "adhoc") + b"/caf\xe9")
    path = os.fsdecode(b"adhoc/caf\xe9")
    refused(conn, crawl("--path", path), caplog, repr(path))
    assert runs(conn) == []


# Requirement: A subtree crawl uses the data root of the full crawls


def test_another_data_root(conn, crawl, data, caplog):
    assert crawl() == 0
    refused(
        conn,
        crawl("--path", "lib", root=data / "adhoc"),
        caplog,
        str(data / "adhoc"),
        f"ran under {data}",
    )
    assert len(runs(conn)) == 1


# Requirement: A subtree crawl uses the formats of the full crawls


def test_only_some_formats(conn, crawl, caplog):
    refused(
        conn,
        crawl("--path", P, "--select", "t/stand"),
        caplog,
        "--select and --ignore cannot be used with --path",
    )
    assert runs(conn) == []


# Requirement: A subtree crawl uses the configuration of the full crawls


def test_another_configuration(conn, crawl, tmp_path, caplog):
    full = tmp_path / "full.toml"
    full.write_text('[crawl]\nexclude = [".snapshot/"]\n')
    other = tmp_path / "other.toml"
    other.write_text("")
    assert crawl("--config", str(full)) == 0
    refused(
        conn,
        crawl("--config", str(other), "--path", P),
        caplog,
        f"{other} differs from that of the last crawl of the whole tree, {full}, in exclude"
        " ([] here, ['.snapshot/'] in the last crawl of the whole tree)",
    )
    assert len(runs(conn)) == 1


def test_another_selection_names_both_values(conn, crawl, caplog):
    assert crawl("--select", "t/stand") == 0
    refused(
        conn,
        crawl("--path", P),
        caplog,
        "its configuration none differs from that of the last crawl of the whole tree, none,"
        " in select ([] here, ['t/stand'] in the last crawl of the whole tree)",
    )


def test_the_same_configuration_from_another_file(conn, crawl, tmp_path):
    full = tmp_path / "full.toml"
    full.write_text(
        '[formats]\nselect = ["t", "collapse"]\nignore = ["zarr", "collapse/git"]\n'
        '[crawl]\nexclude = [".snapshot/", "tmp/"]\n'
    )
    copy = tmp_path / "copy.toml"
    copy.write_text(
        '# the same, select and ignore in another order\n[crawl]\nexclude = [".snapshot/", "tmp/"]\n\n'
        '[formats]\nignore = ["collapse/git", "zarr"]\nselect = ["collapse", "t"]\n'
    )
    assert crawl("--config", str(full)) == 0
    assert crawl("--config", str(copy), "--path", P) == 0


def test_exclusions_in_another_order(conn, crawl, tmp_path, caplog):
    # gitignore's "!" patterns depend on the order: another order is another configuration
    full = tmp_path / "full.toml"
    full.write_text('[crawl]\nexclude = ["tmp/", "!tmp/keep/"]\n')
    other = tmp_path / "other.toml"
    other.write_text('[crawl]\nexclude = ["!tmp/keep/", "tmp/"]\n')
    assert crawl("--config", str(full)) == 0
    refused(conn, crawl("--config", str(other), "--path", P), caplog, "in exclude (")


def test_a_full_crawl_without_a_recorded_configuration(conn, crawl, caplog):
    assert crawl() == 0
    conn.execute("UPDATE crawl_runs SET config = NULL")
    conn.commit()
    assert crawl("--path", P) == 0
    assert (
        "WARNING" in caplog.text
        and "the configuration of the last crawl of the whole tree is not recorded"
        in caplog.text
    )


# Requirement: A subtree crawl fails when its path cannot be listed


def test_the_path_cannot_be_listed_when_the_walk_reaches_it(
    conn, crawl, data, caplog, monkeypatch
):
    assert crawl() == 0
    before = records(conn)
    path, real, listed = str(data / P), walk_module._names, []

    def names(dirpath):
        if dirpath == path:
            listed.append(dirpath)
            if len(listed) > 1:  # after the checks
                raise OSError(116, "Stale file handle", dirpath)
        return real(dirpath)

    monkeypatch.setattr(walk_module, "_names", names)
    assert crawl("--path", P) == 2
    assert len(listed) == 2
    assert f"cannot read {path}: Stale file handle" in caplog.text
    outcome, _, scope, error = runs(conn)[-1]
    assert (outcome, scope) == ("failed", f"/{P}") and "Stale file handle" in error
    assert records(conn) == before
