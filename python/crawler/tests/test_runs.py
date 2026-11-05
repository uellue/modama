"""Crawl runs (the `crawl-runs` spec): crawl and runs as typed, against a throwaway database."""

import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from modama_crawler import cli
from modama_crawler.store import end_run, progress_run, start_run
from modama_crawler.walk import walk

CRAWLER = f"{sys.executable} -m modama_crawler"


@pytest.fixture
def env(conn, monkeypatch):
    """The environment that points the crawler at the test database, for subprocesses and in-process calls."""
    info = conn.info
    values = {
        "MODAMA_CRAWLER_DB": info.dbname,
        "POSTGRES_ADMIN": info.user,
        "POSTGRES_PASSWORD": info.password or "",
        "POSTGRES_ADDRESS": info.host,
        "POSTGRES_PORT": str(info.port),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return {**os.environ, **values}


def shell(command_line: str, env: dict):
    return subprocess.run(
        command_line,
        shell=True,
        executable="/bin/bash",
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env=env,
    )


def runs(conn) -> list[tuple]:
    conn.commit()  # a fresh snapshot
    return conn.execute(
        "SELECT outcome, started_at, finished_at, directories, files, datasets, warnings, records_changed, error"
        " FROM crawl_runs ORDER BY run_id"
    ).fetchall()


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "data"
    (root / "sub").mkdir(parents=True)
    for name in ("a.txt", "b.txt", "sub/c.txt"):
        (root / name).write_text(name)
    return root


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
    for _ in range(2):
        assert shell(f"{CRAWLER} crawl --root {tree}", env).returncode == 0
    first, second = runs(conn)
    assert (first[0], first[7]) == ("finished", 3)
    assert (second[0], second[7]) == ("finished", 0)


def test_the_root_disappears(conn, env, tmp_path):
    run = shell(f"{CRAWLER} crawl --root {tmp_path / 'gone'}", env)
    assert run.returncode != 0
    assert "Traceback" not in run.stderr
    ((outcome, *_, error),) = runs(conn)
    assert outcome == "failed" and "No such file" in error
    assert conn.execute("SELECT count(*) FROM records").fetchone() == (0,)


def test_progress_of_a_slow_walk(conn, tree, caplog):
    # The walk reports every directory; the CLI's throttle passes one update per
    # interval. A fake clock makes each directory take longer than the interval.
    run_id = start_run(conn, str(tree))
    ticks = iter(range(0, 1000, 61))
    progress = cli._Progress(conn, run_id, interval=60, clock=lambda: next(ticks))
    seen = []

    def watch(directories, files):
        progress(directories, files)
        seen.append(
            conn.execute(
                "SELECT directories, files FROM crawl_runs WHERE run_id = %s",
                (run_id,),
            ).fetchone()
        )

    with caplog.at_level("INFO", logger="modama_crawler"):
        walk(tree, [], progress=watch)
    assert seen == [(1, 2), (2, 3)]
    assert [r.getMessage() for r in caplog.records] == [
        "1 directories, 2 files so far",
        "2 directories, 3 files so far",
    ]


def test_progress_is_throttled(conn, tree):
    run_id = start_run(conn, str(tree))
    updated = conn.execute(
        "SELECT updated_at FROM crawl_runs WHERE run_id = %s", (run_id,)
    ).fetchone()
    progress = cli._Progress(conn, run_id, interval=60, clock=lambda: 0)
    walk(tree, [], progress=progress)
    assert (progress.directories, progress.files) == (2, 3)
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
    assert lines[1].endswith(f"0 records changed  {tree}")
    assert "No such file" in lines[0]


def test_piped_into_head(conn, env):
    for _ in range(3):
        run_id = start_run(conn, "/data")
        end_run(conn, run_id, "finished", directories=1, files=1)
    run = shell(f"{CRAWLER} runs | head -1; exit ${{PIPESTATUS[0]}}", env)
    assert run.returncode == 0
    assert len(run.stdout.splitlines()) == 1
    assert "Traceback" not in run.stderr


def test_following_a_crawl(conn, env, capsys, monkeypatch):
    monkeypatch.setattr(cli, "FOLLOW_POLL", 0.05)
    run_id = start_run(conn, "/data")

    def crawl():
        time.sleep(0.2)
        progress_run(conn, run_id, 5, 50)
        time.sleep(0.2)
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
    now = datetime(2026, 11, 5, 12, tzinfo=UTC)
    run = (1, "/data", now, now - timedelta(seconds=119), None, None) + (0,) * 6
    assert cli._state(run, now) == "running"
    stale = run[:3] + (now - timedelta(seconds=121),) + run[4:]
    assert cli._state(stale, now) == "stale"
