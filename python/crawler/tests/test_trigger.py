"""The harvest trigger after a crawl, and the daily timer (decision log 2026-11-04, 2026-11-05)."""

import json
import signal
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from conftest import CRAWLER, shell
from modama_crawler.cli import next_run, overdue
from modama_crawler.store import CRAWL_LOCK, STORE_LOCK
from psycopg.conninfo import make_conninfo
from werkzeug.serving import make_server
from werkzeug.wrappers import Request, Response


@pytest.fixture
def airflow(conn):
    """A stand-in for Airflow's API that records the requests it gets; returns (url, requests).

    When a DAG run is requested, it also records what the database shows at that moment:
    the newest crawl run's outcome, and whether the crawl lock is free.
    """
    requests = []
    conninfo = make_conninfo(conn.info.dsn, password=conn.info.password or "")

    @Request.application
    def app(request):
        body = json.loads(request.data or b"{}")
        requests.append((request.path, body, request.headers.get("Authorization")))
        if request.path == "/auth/token":
            if body.get("password") != "secret":
                return Response("{}", status=401)
            return Response(
                json.dumps({"access_token": "t0k"}), content_type="application/json"
            )
        with psycopg.connect(conninfo) as db:
            outcome = db.execute(
                "SELECT outcome FROM crawl_runs ORDER BY run_id DESC LIMIT 1"
            ).fetchone()
            (free,) = db.execute(
                "SELECT pg_try_advisory_lock(%s, %s)", CRAWL_LOCK
            ).fetchone()
        requests.append(("database at trigger", outcome, free))
        return Response(
            json.dumps({"dag_run_id": "manual__1"}), content_type="application/json"
        )

    server = make_server("localhost", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://localhost:{server.server_port}", requests
    server.shutdown()


def crawl_env(env, url, password="secret"):
    return {
        **env,
        "MODAMA_CRAWLER_AIRFLOW_URL": url,
        "MODAMA_CRAWLER_AIRFLOW_USER": "crawler",
        "MODAMA_CRAWLER_AIRFLOW_PASSWORD": password,
        "OAI_BASE_URL": "http://crawler:7654/oai",
    }


def test_a_finished_crawl_starts_the_harvest_of_its_endpoint(env, tree, airflow):
    url, requests = airflow
    run = shell(f"{CRAWLER} crawl --root {tree}", crawl_env(env, url))
    assert run.returncode == 0, run.stderr
    assert "harvest of http://crawler:7654/oai started: manual__1" in run.stderr
    (token, _, _), (path, body, auth), at_trigger = requests
    # after the commit and after the crawl lock is released
    assert at_trigger == ("database at trigger", ("finished",), True)
    assert token == "/auth/token"
    assert path == "/api/v2/dags/warehouse_harvest_and_index/dagRuns"
    assert body == {
        "logical_date": None,
        "conf": {"harvest_urls": ["http://crawler:7654/oai"]},
    }
    assert auth == "Bearer t0k"


def test_an_unchanged_crawl_starts_a_harvest_too(env, tree, airflow):
    # so that a harvest covers it and the freshness time moves on
    url, requests = airflow
    for _ in range(2):
        assert (
            shell(f"{CRAWLER} crawl --root {tree}", crawl_env(env, url)).returncode == 0
        )
    assert [r[0] for r in requests].count("/auth/token") == 2


def test_a_refused_trigger_is_an_error_after_a_finished_crawl(conn, env, tree, airflow):
    url, _ = airflow
    run = shell(f"{CRAWLER} crawl --root {tree}", crawl_env(env, url, password="wrong"))
    assert run.returncode == 3
    assert "crawl finished, but the harvest could not be started" in run.stderr
    assert "HTTP 401" in run.stderr and "Traceback" not in run.stderr
    conn.commit()
    assert conn.execute("SELECT outcome FROM crawl_runs").fetchall() == [("finished",)]


def test_no_trigger_without_an_airflow_url(env, tree):
    run = shell(f"{CRAWLER} crawl --root {tree}", env)
    assert run.returncode == 0 and "harvest" not in run.stderr


@pytest.mark.parametrize(
    ("now", "at", "expected"),
    [
        ("2026-11-05T01:00:00", "02:00", "2026-11-05T02:00:00"),
        ("2026-11-05T02:00:00", "02:00", "2026-11-06T02:00:00"),  # just ran: tomorrow
        ("2026-11-05T23:30:00", "02:00", "2026-11-06T02:00:00"),
        ("2026-12-31T03:00:00", "02:30", "2027-01-01T02:30:00"),
    ],
)
def test_the_next_crawl(now, at, expected):
    now = datetime.fromisoformat(now).replace(tzinfo=UTC)
    assert next_run(now, at) == datetime.fromisoformat(expected).replace(tzinfo=UTC)


def test_the_timer_rejects_a_bad_time(env):
    run = shell(f"{CRAWLER} timer --at 2am", env)
    assert run.returncode == 2 and "--at takes HH:MM" in run.stderr


def test_the_timer_catches_up_on_an_overdue_crawl():
    now = datetime(2026, 11, 5, 12, tzinfo=UTC)
    assert overdue(None, now)
    assert overdue(now - timedelta(hours=25), now)
    assert not overdue(now - timedelta(hours=23), now)


def wait_until(condition, timeout=60):
    deadline = time.time() + timeout
    while not condition():
        assert time.time() < deadline, "timed out"
        time.sleep(0.2)


def test_an_overdue_timer_crawls_at_once_and_stops_on_sigterm(conn, env, tree):
    # The time of day is half a day away; without a finished crawl, the timer crawls at once
    at = (datetime.now(UTC) + timedelta(hours=12)).strftime("%H:%M")
    timer = subprocess.Popen(
        [sys.executable, "-m", "modama_crawler", "timer", "--at", at],
        env={**env, "MODAMA_DATA_ROOT": str(tree)},
        stderr=subprocess.PIPE,
        text=True,
    )

    def finished():
        conn.commit()
        return conn.execute(
            "SELECT count(*) FROM crawl_runs WHERE outcome = 'finished'"
        ).fetchone() == (1,)

    wait_until(finished)
    time.sleep(1)  # into its sleep until the time of day
    timer.send_signal(signal.SIGTERM)
    _, stderr = timer.communicate(timeout=30)
    assert timer.returncode == 0, stderr
    assert "crawling now" in stderr and "next crawl at" in stderr
    assert "Traceback" not in stderr


def test_a_crawl_stopped_by_sigterm_records_its_run_as_failed(conn, env, tree):
    # A request in flight holds the store lock shared: the crawl waits in store(), where it is stopped
    with psycopg.connect(
        make_conninfo(conn.info.dsn, password=conn.info.password or "")
    ) as request:
        request.execute("SELECT pg_advisory_xact_lock_shared(%s, %s)", STORE_LOCK)
        crawl = subprocess.Popen(
            [sys.executable, "-m", "modama_crawler", "crawl", "--root", str(tree)],
            env=env,
            stderr=subprocess.PIPE,
            text=True,
        )

        def waiting():
            return request.execute(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"
            ).fetchone() == (1,)

        wait_until(waiting)
        crawl.send_signal(signal.SIGTERM)
        _, stderr = crawl.communicate(timeout=30)
    assert crawl.returncode == 143, stderr
    assert "Traceback" not in stderr
    conn.commit()
    assert conn.execute("SELECT outcome, error FROM crawl_runs").fetchall() == [
        ("failed", "terminated (SIGTERM)")
    ], stderr
    assert conn.execute("SELECT count(*) FROM records").fetchone() == (0,)
