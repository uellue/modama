"""modama-chain browse (spec chain-browse): paths, listings, the live part, the views' assembly, snapshots, the local-only rule.

The stores are not reachable here; the views from them are tested in the
search stack's e2e test. The live part runs the crawler's and the EM
collection's code on their own fixtures.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from modama_chain import live, sync, upstream, views
from modama_chain.browse import (
    SNAPSHOT_HEADER,
    BadPath,
    Browser,
    Settings,
    fenced,
    resolve,
    snapshot_name,
)
from modama_chain.chain import Stores
from modama_formats_em.empad import cheat
from test_sync import out_of_sync_commit, stack_copy
from werkzeug.test import Client

REPO = Path(__file__).resolve().parents[3]
EOSC = REPO / "prototypes" / "EOSC-Data-Commons"
UPSTREAM = upstream.Upstream(
    EOSC / "metadata-crawlers" / "harvester", EOSC / "metadata-warehouse"
)
STACK = REPO / "prototypes" / "search-stack"
NOWHERE = "host=/nonexistent dbname=x connect_timeout=1"
OAI = "http://crawler:7654/oai"
LOCAL = {"Host": "localhost:17655"}  # as through the SSH tunnel


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "data"
    cheat.pair(root / "scan")
    (root / "notes").mkdir()
    (root / "notes" / "readme.txt").write_text("Plain notes\n")
    return root


def stores(root: Path) -> Stores:
    return Stores(
        root=root,
        crawler_db=NOWHERE,
        warehouse_db=NOWHERE,
        oai_url=OAI,
        opensearch="http://127.0.0.1:9",
        index="test_datacite",
        search_api="http://127.0.0.1:9",
        airflow="",
        airflow_user="",
        airflow_password="",
    )


def client(root: Path, snapshots: Path | None = None, stack: Path = STACK) -> Client:
    app = Browser(
        Settings(
            stores=stores(root),
            upstream=UPSTREAM,
            stack=stack,
            config=None,
            host_root="/storage/er-c-data",
            snapshots=snapshots,
        )
    )
    return Client(app)


def get(root, url, **query):
    return client(root).get(url, query_string=query, headers=LOCAL)


# Paths outside the data tree are refused


@pytest.mark.parametrize(
    "path",
    [
        "/notes/../../etc/passwd",
        "/notes/./readme.txt",
        "/notes//readme.txt",
        "etc/passwd",
        "//etc/passwd",
        "/notes/out/passwd",
        "/notes/out",
        "/notes/readme.txt\0",
    ],
)
def test_paths_outside_the_tree_are_refused(tree, path):
    # Going up, A symlink out of the tree, An absolute path, A NUL
    os.symlink("/etc", tree / "notes" / "out")
    with pytest.raises(BadPath):
        resolve(str(tree), path)
    assert get(tree, "/api/list", path=path).status_code == 400


def test_encoded_forms_are_decoded_once_and_refused(tree):
    app = client(tree)
    for query in ("path=/notes/%2e%2e/%2e%2e/etc", "path=/notes/readme.txt%00"):
        assert app.get(f"/api/stored?{query}", headers=LOCAL).status_code == 400


def test_an_absolute_path_is_read_under_the_root(tree):
    # /etc/passwd is a path relative to the data root: there is none
    assert get(tree, "/api/stored", path="/etc/passwd").status_code == 404


def test_a_symlink_inside_the_tree_is_listed_but_not_followed(tree):
    # The crawler skips symlinks: nothing behind one is in the chain
    os.symlink(tree / "scan", tree / "notes" / "scan")
    with pytest.raises(BadPath):
        resolve(str(tree), "/notes/scan")
    listed = get(tree, "/api/list", path="/notes").json["entries"]
    assert listed == [["readme.txt", "file"], ["scan", "symlink"]]


def test_a_path_in_the_tree(tree):
    assert resolve(str(tree), "/notes/readme.txt") == str(tree / "notes" / "readme.txt")
    assert resolve(str(tree), "/") == str(tree)


# The browser lists a folder of the data tree


def test_a_folder_with_tens_of_thousands_of_files(tmp_path):
    folder = tmp_path / "many"
    folder.mkdir()
    for i in range(70_000):
        (folder / f"frame_{i:05d}.dm4").touch()
    (folder / "sub").mkdir()
    started = time.monotonic()
    response = get(tmp_path, "/api/list", path="/many")
    took = time.monotonic() - started
    entries = response.json["entries"]
    assert len(entries) == 70_001 and entries[0] == ["sub", "folder"]
    assert took < 2, took


def test_a_link_to_a_file(tree):
    response = get(tree, "/", path="/notes/readme.txt")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert '"hostRoot": "/storage/er-c-data"' in page and "/*SETTINGS*/" not in page
    assert get(tree, "/api/list", path="/notes/").json == {
        "path": "/notes",
        "entries": [["readme.txt", "file"]],
    }
    stored = get(tree, "/api/stored", path="/notes/readme.txt").json
    assert stored["hostPath"] == "/storage/er-c-data/notes/readme.txt"


# The browser answers only on the local machine


def test_another_host_name(tree):
    for host in ("evil.example:7655", "evil.example", "[::1]:7655"):
        assert client(tree).get("/", headers={"Host": host}).status_code == 403
    for host in ("localhost", "127.0.0.1:7655"):
        assert client(tree).get("/", headers={"Host": host}).status_code == 200


def test_a_cross_site_form(tree, tmp_path):
    folder = tmp_path / "browse"
    folder.mkdir()
    response = client(tree, folder).post(
        "/api/snapshot", query_string={"path": "/notes/readme.txt"}, headers=LOCAL
    )
    assert response.status_code == 403
    assert list(folder.iterdir()) == []


# The live views run the checkout's current code; live work is bounded


def run(root, path, **kw):
    return live.run(str(root), path, base_url=OAI, **kw)


def test_each_live_computation_is_a_new_process(tree):
    first, second = run(tree, "/notes/readme.txt"), run(tree, "/notes/readme.txt")
    assert first["dataset"]["anchor"] == "/notes/readme.txt"
    assert first["pid"] != second["pid"] != os.getpid()


def test_the_live_child_gets_no_settings(monkeypatch):
    monkeypatch.setenv("MODAMA_CHAIN_WAREHOUSE_DB", "password=secret")
    monkeypatch.setenv("PGPASSWORD", "secret")
    monkeypatch.setenv("OAI_BASE_URL", "http://x")
    assert set(live.child_env()) <= {"PATH", "HOME", "LANG"}


def test_a_file_next_to_a_large_subfolder(tree):
    # Only the file's folder is recognised, and only its dataset extracted
    for i in range(3):
        cheat.pair(tree / "scan" / "sub" / f"s{i}")
    result = run(tree, "/scan/SCA2_rings.xml")
    assert result["dataset"]["members"] == 2
    assert result["report"].startswith("extraction: 1 run,")


def test_a_folder_has_no_live_views(tree):
    response = client(tree).get(
        "/api/live",
        query_string={"path": "/scan"},
        headers={**LOCAL, SNAPSHOT_HEADER: "1"},
    )
    assert response.status_code == 400


def test_another_site_cannot_start_a_live_computation(tree):
    # an <img src="http://localhost:7655/api/live?..."> on any page (code review, finding 5)
    assert get(tree, "/api/live", path="/notes/readme.txt").status_code == 403


def test_a_file_at_the_top_of_the_tree(tree):
    # its folder is the root alone, not the whole tree (code review, finding 1)
    (tree / "top.txt").write_text("t")
    result = run(tree, "/top.txt")
    assert result["folder"] == "/" and result["dataset"]["anchor"] == "/top.txt"


def test_a_killed_computation_leaves_no_temporary_files(started, tmp_path, monkeypatch):
    # its MIME database would stay in the tmpfs (code review, finding 2)
    monkeypatch.setattr(live.tempfile, "tempdir", str(tmp_path))
    argv = [
        sys.executable,
        "-c",
        "import os, time; open(os.environ['TMPDIR'] + '/x', 'w'); time.sleep(60)",
    ]
    live.run("/", "/x", base_url=OAI, limit=1.0, argv=argv)
    assert list(tmp_path.iterdir()) == []


SLEEPER = [
    sys.executable,
    "-c",
    (
        "import subprocess, sys, time;"
        " subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
        " time.sleep(60)"
    ),
]


def gone(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    return False


@pytest.fixture
def started(monkeypatch):
    """The live children started, as Popen objects."""
    procs, real = [], subprocess.Popen

    def popen(*a, **kw):
        procs.append(real(*a, **kw))
        return procs[-1]

    monkeypatch.setattr(live.subprocess, "Popen", popen)
    return procs


def test_a_computation_over_the_limit(started):
    result = live.run("/", "/x", base_url=OAI, limit=1.0, argv=SLEEPER)
    assert result["error"].startswith("stopped after 1 s")
    time.sleep(0.2)
    assert gone(started[0].pid)


def test_a_newer_request(started, tree):
    results = []
    older = threading.Thread(
        target=lambda: results.append(live.run("/", "/x", base_url=OAI, argv=SLEEPER))
    )
    older.start()
    while not started:
        time.sleep(0.05)
    time.sleep(0.5)
    newer = run(tree, "/notes/readme.txt")
    older.join(5)
    assert results == [{"error": "ended by a newer request"}]
    assert newer["dataset"]["anchor"] == "/notes/readme.txt"
    assert gone(started[0].pid)


# A file's views show the stages, each labelled by its source


def live_views(tree: Path, path: str, record=None) -> dict[str, views.View]:
    before = views.Stored([], record=record, repo="ERC")
    found = views.live_views(stores(tree), UPSTREAM, path, None, before)
    return {v.key: v for v in found}


def test_a_file_the_crawler_has_not_seen(tree):
    stored = {
        v["key"]: v
        for v in get(tree, "/api/stored", path="/scan/SCA2_rings.xml").json["views"]
    }
    assert (
        "crawler database" in stored["dataset"]["note"]
    )  # unreachable here; the e2e test has the store
    got = live_views(tree, "/scan/SCA2_rings.xml")
    assert [v.source for v in got.values()] == [
        "actual code", "actual code", "actual code", "actual code", "emulated", "emulated",
    ]  # fmt: skip
    dataset = json.loads(got["dataset"].text)
    assert dataset["format"] == "em/empad" and dataset["members"] == 2
    assert dataset["first members"] == ["/scan/SCA2_rings.xml", "/scan/series_x4.raw"]
    assert "<dc:subject>EMPAD</dc:subject>" in got["record"].text
    assert got["record"].note == "no stored record yet"
    assert "<datacite:subject>EMPAD</datacite:subject>" in got["datacite"].text
    doc = json.loads(got["document"].text)
    assert doc["titles"] == [{"title": "/scan/SCA2_rings.xml"}]
    assert "series_count 4" in doc["descriptions"][0]["description"]
    assert doc["_repo"] == "ERC" and doc["_harvest_url"] == OAI
    assert doc["_additional_metadata"].startswith("<record")
    hit = json.loads(got["hit"].text)
    assert hit["_id"] == hit["dataset_url"] == doc["url"]
    assert hit["title"] == "/scan/SCA2_rings.xml" and hit["score"] is None
    entry = got["entry"].entry
    assert entry["title"] == "/scan/SCA2_rings.xml" and entry["subjects"] == ["EMPAD"]
    assert re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", entry["date"])
    assert entry["source"] == doc["url"]


def test_an_unchanged_record_keeps_its_datestamp(tree):
    metadata = run(tree, "/notes/readme.txt")["metadata"]
    stamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    same = live_views(tree, "/notes/readme.txt", (stamp, metadata))
    assert "<datestamp>2026-01-02T03:04:05Z</datestamp>" in same["record"].text
    assert same["record"].note.startswith("equal to the stored record")
    changed = live_views(
        tree, "/notes/readme.txt", (stamp, {**metadata, "title": ["x"]})
    )
    assert changed["record"].note.startswith("differs from the stored record")
    assert "2026-01-02" not in changed["record"].text


def test_a_file_inside_a_collapsed_tree_shows_the_collapsed_dataset(tmp_path):
    (tmp_path / "proj" / ".git" / "objects").mkdir(parents=True)
    (tmp_path / "proj" / ".git" / "objects" / "ab").write_text("x")
    result = run(tmp_path, "/proj/.git/objects/ab")
    assert result["dataset"]["anchor"] == "/proj/.git"
    assert result["dataset"]["collapsed"]


# matchmaker's entry: the limits of the component (D10)


def test_the_entry_cuts_long_values():
    source = {
        "url": "https://example.org/browse/?path=/a",
        "titles": [{"title": "t"}],
        "descriptions": [{"description": "<b>x</b>" + "y" * 400 + " &amp;"}],
        "creators": [{"creatorName": n} for n in "abcd"],
        "subjects": [{"subject": str(i)} for i in range(7)],
        "dates": [{"date": "2026-11-12", "dateType": "Issued"}],
        "publicationYear": "2026",
    }
    hit = upstream.search_hit(source["url"], source, score=0.996)
    entry = upstream.cited_entry(hit)
    assert entry["description"] == "x" + "y" * 299 + "..."
    assert entry["description_full"].endswith(" &")
    assert entry["creators"] == ["a", "b", "c"] and entry["creators_more"] == 1
    assert entry["meta"] == "2026 · a, b, +2 more"
    assert entry["subjects"] == ["0", "1", "2", "3", "4"]
    assert entry["subjects_more"] == 2
    assert entry["date"] == "2026.11.12" and entry["relevance"] == 99


# The browser writes only snapshots


def test_save_for_claude(tree, tmp_path, monkeypatch):
    monkeypatch.setenv("MODAMA_CHAIN_WAREHOUSE_DB", "host=postgres password=hunter2")
    monkeypatch.setenv("PGPASSWORD", "hunter2")
    folder = tmp_path / "browse"
    folder.mkdir()
    response = client(tree, folder).post(
        "/api/snapshot",
        query_string={"path": "/scan/SCA2_rings.xml"},
        headers={**LOCAL, SNAPSHOT_HEADER: "1"},
        json={"message": "The date is wrong.\nShould be the acquisition time."},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    (written,) = folder.iterdir()
    assert response.json["name"] == f"browse/{written.name}"
    assert re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d-SCA2_rings\.xml\.md", written.name
    )
    text = written.read_text()
    assert "Path on the server: `/storage/er-c-data/scan/SCA2_rings.xml`" in text
    assert re.search(r"Extractor: em/empad, extractor identity [0-9a-f]{12}\n", text)
    assert (
        "## Message\n\n> The date is wrong.\n> Should be the acquisition time.\n"
        in text
    )
    for title in (
        "Dataset",
        "OAI-PMH record",
        "DataCite (harvester)",
        "Search API hit",
    ):
        assert f"### {title}" in text
    assert "hunter2" not in text and "password" not in text


def test_an_emulation_out_of_sync_is_marked_on_the_page_and_in_the_snapshot(
    tree, tmp_path, monkeypatch
):
    folder = tmp_path / "browse"
    folder.mkdir()
    stack = stack_copy(tmp_path / "stack")
    # declared as the copy builds it, so that this test does not depend on test_sync's check
    monkeypatch.setattr(
        upstream,
        "FOLLOWS",
        {
            "hit": sync.built(stack, "search-api"),
            "entry": sync.built(stack, "matchmaker"),
        },
    )
    live_request = {
        "query_string": {"path": "/scan/SCA2_rings.xml"},
        "headers": {**LOCAL, SNAPSHOT_HEADER: "1"},
    }
    in_sync = client(tree, stack=stack).get("/api/live", **live_request).json["views"]
    assert [v["out_of_sync"] for v in in_sync] == [""] * 6
    _, warning = out_of_sync_commit(stack)
    browser = client(tree, folder, stack)
    marked = browser.get("/api/live", **live_request).json["views"]
    assert {v["key"]: v["out_of_sync"] for v in marked if v["out_of_sync"]} == {
        "entry": warning
    }
    assert browser.post("/api/snapshot", **live_request).status_code == 200
    (written,) = folder.iterdir()
    text = written.read_text()
    assert text.count("**out of sync") == 1
    assert f"### {views.ENTRY_TITLE} (emulated)\n\nFrom: " in text
    assert f"**{warning}**" in text.split(f"### {views.ENTRY_TITLE} (emulated)")[1]


def test_a_snapshot_without_a_message_has_no_message_section(tree, tmp_path):
    folder = tmp_path / "browse"
    folder.mkdir()
    response = client(tree, folder).post(
        "/api/snapshot",
        query_string={"path": "/scan/SCA2_rings.xml"},
        headers={**LOCAL, SNAPSHOT_HEADER: "1"},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    (written,) = folder.iterdir()
    assert "## Message" not in written.read_text()


def test_fences_are_longer_than_the_content_s():
    assert fenced("a ```` b")[0] == "`````"
    assert fenced("plain")[0] == "```"


def test_snapshot_names():
    now = datetime(2026, 11, 12, 19, 5, 3, tzinfo=UTC)
    assert (
        snapshot_name("/a/(3) Spectrum ä.dm4", now)
        == "2026-11-12T19-05-03-_3_Spectrum_.dm4.md"
    )
    assert len(snapshot_name("/" + "x" * 300, now)) == 20 + 60 + 3


def test_the_live_views_leave_the_tree_as_it_was(tree):
    before = {p: p.stat().st_mtime_ns for p in tree.rglob("*")}
    live_views(tree, "/scan/SCA2_rings.xml")
    assert {p: p.stat().st_mtime_ns for p in tree.rglob("*")} == before
