"""One crawl at a time, and harvests that come back later while a crawl writes records (review 2026-11-05)."""

import signal
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime

import oaipmh_scythe
import psycopg
from conftest import CRAWLER, shell
from modama_crawler.formats import Dataset, Result
from modama_crawler.server import OAIServer
from modama_crawler.store import CRAWL_LOCK, STORE_LOCK, store
from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool
from werkzeug.serving import make_server
from werkzeug.test import Client


def other_connection(conn) -> psycopg.Connection:
    """A second session on the test database, standing in for another process."""
    return psycopg.connect(
        make_conninfo(conn.info.dsn, password=conn.info.password or "")
    )


def run_count(conn) -> int:
    conn.commit()
    return conn.execute("SELECT count(*) FROM crawl_runs").fetchone()[0]


def test_a_second_crawl_is_refused(conn, env, tree):
    with other_connection(conn) as holder:
        holder.execute("SELECT pg_advisory_lock(%s, %s)", CRAWL_LOCK)
        run = shell(f"{CRAWLER} crawl --root {tree}", env)
        assert run.returncode == 1
        assert "another crawl is running on this database" in run.stderr
        assert "Traceback" not in run.stderr
        assert run_count(conn) == 0
    # the holder's session ended: the lock is gone
    assert shell(f"{CRAWLER} crawl --root {tree}", env).returncode == 0


def test_a_crashed_crawl_leaves_no_lock(conn, env, tree):
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import psycopg, sys, time\n"
                f"c = psycopg.connect({make_conninfo(conn.info.dsn, password=conn.info.password or '')!r})\n"
                f"c.execute('SELECT pg_advisory_lock(%s, %s)', {CRAWL_LOCK!r})\n"
                "print('locked', flush=True)\n"
                "time.sleep(600)\n"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout.readline() == "locked\n"
    assert shell(f"{CRAWLER} crawl --root {tree}", env).returncode == 1
    holder.send_signal(signal.SIGKILL)
    holder.wait()
    deadline = time.time() + 10  # the server notices the closed socket
    while (run := shell(f"{CRAWLER} crawl --root {tree}", env)).returncode != 0:
        assert time.time() < deadline, run.stderr
        time.sleep(0.2)


def test_requests_come_back_later_while_records_are_written(conn, server):
    client = Client(server)
    with other_connection(conn) as writer:
        writer.execute("SELECT pg_advisory_xact_lock(%s, %s)", STORE_LOCK)
        response = client.get("/oai", query_string={"verb": "Identify"})
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "60"
        writer.rollback()
        assert client.get("/oai", query_string={"verb": "Identify"}).status_code == 200


def test_the_datestamp_is_taken_after_requests_in_flight(conn):
    dataset = Dataset(
        anchor="/a.txt",
        members=("/a.txt",),
        type="text/plain",
        basis="single file",
        uid=0,
    )
    with other_connection(conn) as request:
        request.execute("SELECT pg_try_advisory_xact_lock_shared(%s, %s)", STORE_LOCK)
        writer = threading.Thread(target=store, args=(conn, Result([dataset]), {}))
        writer.start()
        time.sleep(1.5)
        released = datetime.now(UTC).replace(microsecond=0)
        request.rollback()
        writer.join()
    (datestamp,) = conn.execute("SELECT datestamp FROM records").fetchone()
    assert datestamp >= released


def test_a_real_harvester_comes_back_later(conn, records):
    # oaipmh-scythe with the EOSC harvester's settings, and a short Retry-After
    conninfo = make_conninfo(conn.info.dsn, password=conn.info.password or "")
    with ConnectionPool(conninfo, min_size=1, open=True) as pool:
        app = OAIServer(
            pool,
            "http://localhost/oai",
            "admin@example.org",
            page_size=2,
            retry_after=1,
        )
        http = make_server("localhost", 0, app, threaded=True)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        url = f"http://localhost:{http.server_port}/oai"
        with other_connection(conn) as writer:
            writer.execute("SELECT pg_advisory_xact_lock(%s, %s)", STORE_LOCK)
            threading.Timer(1.5, writer.rollback).start()
            with oaipmh_scythe.Scythe(
                url, timeout=180, max_retries=3, default_retry_after=60
            ) as client:
                started = time.monotonic()
                harvested = [
                    r.header.identifier
                    for r in client.list_records(metadata_prefix="oai_dc")
                ]
        http.shutdown()
    assert harvested == records
    assert time.monotonic() - started >= 1  # it did wait
