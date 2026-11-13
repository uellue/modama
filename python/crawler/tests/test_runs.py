"""Crawl runs (the `crawl-runs` spec): crawl and runs as typed, against a throwaway database."""

import os
import re
import shutil
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import modama_formats_common  # noqa: F401 (installed: common/text extracts the tree's text files)
import modama_formats_em
import pytest
from conftest import CRAWLER, shell
from modama_crawler import cli, identity
from modama_crawler.store import Run, end_run, progress_run, start_run
from modama_crawler.walk import walk
from psycopg.types.json import Jsonb


def runs(conn) -> list[tuple]:
    conn.commit()  # a fresh snapshot
    return conn.execute(
        "SELECT outcome, started_at, finished_at, directories, files, datasets, warnings, records_changed, error"
        " FROM crawl_runs ORDER BY run_id"
    ).fetchall()


def test_a_finished_crawl(conn, env, tree):
    run = shell(f"{CRAWLER} crawl --root {tree}", env)
    assert run.returncode == 0, run.stderr
    ((outcome, started, finished, dirs, files, datasets, warnings, changed, error),) = (
        runs(conn)
    )
    datestamps = [
        d for (d,) in conn.execute("SELECT datestamp FROM records").fetchall()
    ]
    assert outcome == "finished" and error is None
    assert started <= min(datestamps) and finished >= max(datestamps)
    assert (dirs, files, datasets, warnings, changed) == (2, 3, 3, 0, 3)
    assert "3 datasets, 0 warnings, 3 records changed" in run.stderr


def test_an_unchanged_crawl_leaves_a_run(conn, env, tree):
    crawls = [shell(f"{CRAWLER} crawl --root {tree}", env) for _ in range(2)]
    assert [c.returncode for c in crawls] == [0, 0]
    first, second = runs(conn)
    assert (first[0], first[7]) == ("finished", 3)
    assert (second[0], second[7]) == ("finished", 0)
    # The rule set's fingerprint is the same in a new process: both directories are
    # taken over, with the extractions of the three text files (common/text, installed)
    assert "0 directories unchanged" in crawls[0].stderr
    assert "extraction: 0 run, 3 reused, 0 failed; 2 directories unchanged" in (
        crawls[1].stderr
    )
    # The run keeps the extraction counts the crawl logged, and the runs command shows them
    counts = conn.execute(
        "SELECT extractions_run, extractions_reused, extractions_failed, directories_unchanged"
        " FROM crawl_runs ORDER BY run_id"
    ).fetchall()
    assert counts == [(3, 0, 0, 0), (0, 3, 0, 2)]
    newest = shell(f"{CRAWLER} runs", env).stdout.splitlines()[0]
    assert "extraction: 0 run, 3 reused, 0 failed; 2 directories unchanged" in newest


def test_the_root_disappears(conn, env, tree, tmp_path):
    assert shell(f"{CRAWLER} crawl --root {tree}", env).returncode == 0
    before = conn.execute(
        "SELECT identifier, datestamp FROM records ORDER BY 1"
    ).fetchall()
    run = shell(f"{CRAWLER} crawl --root {tmp_path / 'gone'}", env)
    assert run.returncode != 0
    assert "Traceback" not in run.stderr
    *_, (outcome, *_, error) = runs(conn)
    assert outcome == "failed" and "No such file" in error
    after = conn.execute(
        "SELECT identifier, datestamp FROM records ORDER BY 1"
    ).fetchall()
    assert after == before


# "A crawl stores no records while the user database cannot name its check user"


def test_the_name_service_is_down(conn, env, tree):
    assert shell(f"{CRAWLER} crawl --root {tree}", env).returncode == 0
    before = conn.execute(
        "SELECT identifier, datestamp FROM records ORDER BY 1"
    ).fetchall()
    (tree / "new.txt").write_text("new")  # would add a record
    # 4242: a uid the user database does not know, as when sssd does not answer
    run = shell(f"SSSD_CHECK_USER=4242 {CRAWLER} crawl --root {tree}", env)
    assert run.returncode != 0
    assert "Traceback" not in run.stderr
    assert "does not know SSSD_CHECK_USER 4242: sssd is not answering" in run.stderr
    *_, (outcome, *_, error) = runs(conn)
    assert outcome == "failed" and "SSSD_CHECK_USER 4242" in error
    after = conn.execute(
        "SELECT identifier, datestamp FROM records ORDER BY 1"
    ).fetchall()
    assert after == before


def test_the_name_service_answers(conn, env, tree):
    uid, gid = os.getuid(), os.getgid()
    run = shell(f"SSSD_CHECK_USER={uid}:{gid} {CRAWLER} crawl --root {tree}", env)
    assert run.returncode == 0, run.stderr
    ((outcome, *_, changed, error),) = runs(conn)
    assert (outcome, changed, error) == ("finished", 3, None)


def test_the_check_user_is_not_a_uid(conn, env, tree):
    run = shell(f"SSSD_CHECK_USER=alice {CRAWLER} crawl --root {tree}", env)
    assert run.returncode == 2
    assert "SSSD_CHECK_USER must be a uid or uid:gid: 'alice'" in run.stderr
    assert runs(conn) == []


def test_progress_of_a_slow_walk(conn, tree, caplog):
    # Each directory takes longer than the interval; the heartbeat writes in between
    run_id = start_run(conn, str(tree))
    heartbeat = cli._Heartbeat(
        conn.info.dsn + f" password={conn.info.password or ''}", run_id, interval=0.05
    )
    seen = []

    def slow(directories, files):
        heartbeat(directories, files)
        time.sleep(0.3)
        conn.commit()
        seen.append(
            conn.execute(
                "SELECT directories, files, now() - updated_at < interval '1 second'"
                " FROM crawl_runs WHERE run_id = %s",
                (run_id,),
            ).fetchone()
        )

    heartbeat.start()
    with caplog.at_level("INFO", logger="modama_crawler"):
        walk(tree, [], progress=slow)
        heartbeat.stop()
    assert seen == [(1, 2, True), (2, 3, True)]
    messages = [r.getMessage() for r in caplog.records]
    assert "1 directories, 2 files so far" in messages
    assert messages[-1] == "2 directories, 3 files so far"


def test_no_update_before_the_interval(conn, tree):
    run_id = start_run(conn, str(tree))
    updated = conn.execute(
        "SELECT updated_at FROM crawl_runs WHERE run_id = %s", (run_id,)
    ).fetchone()
    heartbeat = cli._Heartbeat(conn.info.dsn, run_id, interval=60)
    heartbeat.start()
    walk(tree, [], progress=heartbeat)
    heartbeat.stop()
    assert (heartbeat.directories, heartbeat.files) == (2, 3)
    conn.commit()
    assert (
        conn.execute(
            "SELECT updated_at FROM crawl_runs WHERE run_id = %s", (run_id,)
        ).fetchone()
        == updated
    )


def test_no_crawl_yet(env):
    run = shell(f"{CRAWLER} runs", env)
    assert (run.returncode, run.stdout) == (0, "no crawl has run\n")


def test_a_crawl_killed_during_the_walk(conn, env):
    # What SIGKILL leaves: a run without an end, last updated three minutes ago
    start_run(conn, "/data")
    conn.execute("UPDATE crawl_runs SET updated_at = now() - interval '3 minutes'")
    conn.commit()
    run = shell(f"{CRAWLER} runs", env)
    assert run.returncode == 0
    assert " stale " in run.stdout and "updated " in run.stdout
    assert "running" not in run.stdout and "finished" not in run.stdout


def test_runs_newest_first(conn, env, tree):
    for _ in range(2):
        shell(f"{CRAWLER} crawl --root {tree}", env)
    shell(f"{CRAWLER} crawl --root {tree / 'gone'}", env)
    lines = shell(f"{CRAWLER} runs", env).stdout.splitlines()
    assert [line.split()[1] for line in lines] == ["failed", "finished", "finished"]
    assert re.search(
        f"2 directories unchanged; identity [0-9a-f]{{12}}  {tree}$", lines[1]
    )
    assert "0 records changed; extraction: 0 run" in lines[1]
    assert "No such file" in lines[0]


def test_a_subtree_crawl_records_its_path(conn, env, tree):
    assert shell(f"{CRAWLER} crawl --root {tree}", env).returncode == 0
    run = shell(f"{CRAWLER} crawl --root {tree} --path /sub", env)
    assert run.returncode == 0, run.stderr
    conn.commit()
    assert conn.execute(
        "SELECT outcome, root, scope FROM crawl_runs ORDER BY run_id"
    ).fetchall() == [("finished", str(tree), None), ("finished", str(tree), "/sub")]


def test_a_run_records_its_configuration(conn, env, tree, tmp_path):
    config = tmp_path / "full.toml"
    config.write_text(
        '[formats]\nignore = ["zarr"]\n\n[formats.per-path-ignores]\n"old/" = ["em"]\n\n'
        '[crawl]\nexclude = [".snapshot/"]\n'
    )
    run = shell(f"{CRAWLER} --config {config} crawl --root {tree}", env)
    assert run.returncode == 0, run.stderr
    conn.commit()
    assert conn.execute("SELECT config FROM crawl_runs").fetchone()[0] == {
        "file": str(config),
        "select": [],
        "ignore": ["zarr"],
        "per_path_ignores": {"old/": ["em"]},
        "exclude": [".snapshot/"],
    }


def test_a_subtree_crawls_line(conn, env, tree):
    for path in ("", "--path sub"):
        assert shell(f"{CRAWLER} crawl --root {tree} {path}", env).returncode == 0
    subtree, full = shell(f"{CRAWLER} runs", env).stdout.splitlines()
    assert subtree.endswith(f"  {tree}  sub"), subtree
    assert full.endswith(f"  {tree}"), full


def test_piped_into_head(conn, env):
    for _ in range(3):
        run_id = start_run(conn, "/data")
        end_run(conn, run_id, "finished", directories=1, files=1)
    run = shell(f"{CRAWLER} runs | head -1; exit ${{PIPESTATUS[0]}}", env)
    assert run.returncode == 0
    assert len(run.stdout.splitlines()) == 1
    assert "Traceback" not in run.stderr
    # a reader that is gone before anything is written: the write itself fails
    run = shell(f"{CRAWLER} runs | true; exit ${{PIPESTATUS[0]}}", env)
    assert (run.returncode, run.stderr) == (0, "")


def test_following_a_crawl(conn, env, capsys, monkeypatch):
    monkeypatch.setattr(cli, "FOLLOW_POLL", 0.05)
    run_id = start_run(conn, "/data")
    # The crawl moves on only after --follow printed the previous state, so the
    # test doesn't depend on how long the command takes to start (the extractor
    # identity of the installation is computed first)
    printed = [threading.Event() for _ in range(2)]
    run_line = cli._run_line

    def counted(run):
        line = run_line(run)
        next((e for e in printed if not e.is_set()), threading.Event()).set()
        return line

    monkeypatch.setattr(cli, "_run_line", counted)

    def crawl():
        printed[0].wait(30)
        progress_run(conn, run_id, 5, 50)
        printed[1].wait(30)
        end_run(
            conn,
            run_id,
            "finished",
            directories=9,
            files=90,
            datasets=40,
            warnings=0,
            records_changed=2,
        )

    crawler = threading.Thread(target=crawl)
    crawler.start()
    status = cli.main(["runs", "--follow"])
    crawler.join()
    lines = capsys.readouterr().out.splitlines()
    assert status == 0
    assert [line.split()[1] for line in lines] == ["running", "running", "finished"]
    assert "5 directories, 50 files so far" in lines[1]
    assert "40 datasets, 0 warnings, 2 records changed" in lines[2]


def test_run_states():
    def run(age, finished=None):
        now = datetime(2026, 11, 5, 12, tzinfo=UTC)
        return Run(
            1,
            "/data",
            now,
            now,
            finished,
            None,
            0,
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            timedelta(seconds=age),
        )

    assert cli._state(run(119)) == "running"
    assert cli._state(run(121)) == "stale"


# "The runs command says what the next crawl will extract again" (change extractor-identity)

DM4 = (
    Path(modama_formats_em.__file__).parent
    / "dm/tests/fixtures/cl_image_dm4/test-MonarcCL_mono-image.dm4"
)


@pytest.fixture
def dm4_tree(tmp_path):
    """Two DM4 files below /one, one below /two."""
    root = tmp_path / "dm"
    for name in ("one/a.dm4", "one/b.dm4", "two/c.dm4"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(DM4, root / name)
    return root


def crawled(conn, env, root) -> tuple[str, dict]:
    """Crawl as typed; the identity and ingredients the run recorded."""
    run = shell(f"{CRAWLER} crawl --root {root}", env)
    assert run.returncode == 0, run.stderr
    conn.commit()
    return conn.execute(
        "SELECT identity, identity_ingredients FROM crawl_runs ORDER BY run_id DESC LIMIT 1"
    ).fetchone()


def older(ingredients: dict) -> tuple[str, dict]:
    """The installation with an older RosettaSciIO."""
    before = {
        **ingredients,
        "distributions": {**ingredients["distributions"], "rosettasciio": "0.14.0"},
    }
    return identity.digest(before), before


def test_runs_after_an_upgrade(conn, env, dm4_tree):
    current, ingredients = crawled(conn, env, dm4_tree / "one")
    old, before = older(ingredients)
    conn.execute(
        "UPDATE crawl_runs SET identity = %s, identity_ingredients = %s",
        (old, Jsonb(before)),
    )
    conn.execute("UPDATE datasets SET extractor_identity = %s", (old,))
    conn.commit()
    run = shell(f"{CRAWLER} runs", env)
    assert run.returncode == 0
    assert run.stderr.startswith(
        f"note: extraction identity {identity.short(current)} is installed; the next crawl "
        f"extracts again em/dm4 2 datasets stored under {identity.short(old)} "
        "(rosettasciio 0.14.0 -> 0.15.0); under a minute on "
    )
    assert len(run.stderr.splitlines()) == 1
    assert len(run.stdout.splitlines()) == 1  # the run lines as before
    head = shell(f"{CRAWLER} runs | head -1", env)
    assert head.stdout == run.stdout


def test_runs_left_over_from_an_experiment(conn, env, dm4_tree):
    current, ingredients = crawled(conn, env, dm4_tree)
    old, before = older(ingredients)
    # A subtree crawl of /one under the other installation, before the last crawl
    conn.execute(
        "INSERT INTO crawl_runs (root, started_at, updated_at, finished_at, outcome, identity,"
        " identity_ingredients) VALUES ('/x', now() - interval '1 day', now() - interval '1 day',"
        " now() - interval '1 day', 'finished', %s, %s)",
        (old, Jsonb(before)),
    )
    conn.execute(
        "UPDATE datasets SET extractor_identity = %s WHERE anchor LIKE '/one/%%'",
        (old,),
    )
    conn.commit()
    (latest,) = conn.execute(
        "SELECT identity FROM crawl_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    assert latest == current
    run = shell(f"{CRAWLER} runs", env)
    assert f"em/dm4 2 datasets stored under {identity.short(old)}" in run.stderr


def test_runs_when_nothing_changed(conn, env, dm4_tree):
    crawled(conn, env, dm4_tree)
    run = shell(f"{CRAWLER} runs", env)
    assert (run.returncode, run.stderr) == (0, "")


# records-cli: "The records summary names the extractor identity"


def test_records_of_a_dm_file(conn, env, dm4_tree):
    current, _ = crawled(conn, env, dm4_tree / "two")
    run = shell(f"{CRAWLER} records --verbose {dm4_tree / 'two'}", env)
    assert run.returncode == 0, run.stderr
    assert f"; extraction identity {identity.short(current)} -->" in run.stdout
