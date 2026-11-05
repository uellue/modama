"""Crawl runs (the `crawl-runs` spec): crawl and runs as typed, against a throwaway database."""

import threading
import time
from datetime import UTC, datetime, timedelta

from conftest import CRAWLER, shell
from modama_crawler import cli
from modama_crawler.store import Run, end_run, progress_run, start_run
from modama_crawler.walk import walk


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
    for _ in range(2):
        assert shell(f"{CRAWLER} crawl --root {tree}", env).returncode == 0
    first, second = runs(conn)
    assert (first[0], first[7]) == ("finished", 3)
    assert (second[0], second[7]) == ("finished", 0)


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
    # a reader that is gone before anything is written: the write itself fails
    run = shell(f"{CRAWLER} runs | true; exit ${{PIPESTATUS[0]}}", env)
    assert (run.returncode, run.stderr) == (0, "")


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
            timedelta(seconds=age),
        )

    assert cli._state(run(119)) == "running"
    assert cli._state(run(121)) == "stale"
