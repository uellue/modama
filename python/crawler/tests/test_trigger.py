"""The harvest trigger after a crawl, and the daily timer (decision log 2026-11-04, 2026-11-05)."""

import json
import threading
from datetime import UTC, datetime

import pytest
from conftest import CRAWLER, shell
from modama_crawler.cli import next_run
from werkzeug.serving import make_server
from werkzeug.wrappers import Request, Response


@pytest.fixture
def airflow():
    """A stand-in for Airflow's API that records the requests it gets; returns (url, requests)."""
    requests = []

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
    (token, _, _), (path, body, auth) = requests
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
    assert [path for path, _, _ in requests].count("/auth/token") == 2


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
