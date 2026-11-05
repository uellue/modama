"""End to end: crawl a fixture tree, harvest it through the warehouse's Airflow DAG, find it by search.

Runs inside the crawler container of compose.yml (./e2e.sh test), after ./e2e.sh up and reset.
Assertions trace items with the chain tool (python/search-chain), so that a
failure names the first stage that diverged; the fault scenarios at the end
check that the trace finds what it is meant to find.
"""

import json
import os
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

import psycopg
import pytest
from modama_chain import chain
from modama_chain.cli import stores_from_env
from modama_crawler.formats import core
from modama_crawler.formats.collapse.tests import generate as collapse_fixtures
from modama_crawler.formats.empad import cheat
from modama_crawler.formats.zarr.tests import generate as zarr_fixtures

DATA = Path("/data")
OAI_URL = "http://crawler:7654/oai"
AIRFLOW = "http://airflow-api-server:8080"
OPENSEARCH = "http://opensearch:9200"
SEARCH = "http://search-api:8000"
INDEX = "test_datacite"
DAG = "warehouse_harvest_and_index"
DAG_TIMEOUT = 20 * 60
NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
}
DISTINCT_FILE = "notes/ferritin-lamella.txt"
ADDED_FILE = "notes/added-after-the-first-harvest.txt"
LATE_FILE = "notes/late-arrival.txt"
RENAMED = ("notes/readme.txt", "notes/readme-renamed.txt")
LOST_DOCUMENT = "notes/sample-list.csv"
MIXED = Path(core.__file__).parent / "tests" / "fixtures" / "mixed"


def http(url, data=None, method=None, headers=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data is not None else None,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def airflow(path, data=None, method=None):
    return http(AIRFLOW + path, data, method, {"Authorization": f"Bearer {TOKEN['t']}"})


TOKEN = {}


def trigger_and_wait(urls, check=True):
    TOKEN["t"] = http(
        AIRFLOW + "/auth/token", {"username": "airflow", "password": "airflow"}
    )["access_token"]
    # DAGs are created paused; the outer one triggers the transform DAG, which has to run too
    for dag in (DAG, "warehouse_transform_index"):
        airflow(f"/api/v2/dags/{dag}", {"is_paused": False}, "PATCH")
    run = airflow(
        f"/api/v2/dags/{DAG}/dagRuns",
        {"logical_date": None, "conf": {"harvest_urls": urls, "index_name": INDEX}},
    )
    run_id = urllib.parse.quote(run["dag_run_id"], safe="")
    deadline = time.time() + DAG_TIMEOUT
    while time.time() < deadline:
        state = airflow(f"/api/v2/dags/{DAG}/dagRuns/{run_id}")["state"]
        if state in ("success", "failed"):
            break
        time.sleep(5)
    tasks = airflow(f"/api/v2/dags/{DAG}/dagRuns/{run_id}/taskInstances?limit=1000")
    summary = ", ".join(
        f"{t['task_id']}[{t.get('map_index', -1)}]={t['state']}"
        for t in tasks["task_instances"]
    )
    if check:
        assert state == "success", f"DAG run ended in state {state!r}: {summary}"


def crawl():
    subprocess.run(["modama-crawler", "crawl", "--root", str(DATA)], check=True)


def oracle():
    """What the crawler should publish: OAI identifier -> (title, browse URL), from the database-free `records` command."""
    out = subprocess.run(
        ["modama-crawler", "records", str(DATA)],
        check=True,
        capture_output=True,
    ).stdout
    root = ET.fromstring(out)
    found = {}
    for record in root.iterfind(".//oai:record", NS):
        identifier = record.find("oai:header/oai:identifier", NS).text
        found[identifier] = (
            record.find(".//dc:title", NS).text,
            record.find(".//dc:identifier", NS).text,
        )
    return found


STORES = stores_from_env()  # the chain tool's read-only accounts, from chain.env


def trace(path):
    """The stages of path by name, and the first diverging one (None if consistent)."""
    stages = list(chain.trace(STORES, path))
    first = chain.diverging(stages)
    return {s.name: s for s in stages}, (stages[first] if first is not None else None)


def assert_consistent(path):
    _, first = trace(path)
    assert first is None, f"{path}: first diverging stage {first.name}: {first}"


def freshness():
    *lines, (t, reason) = chain.status(STORES)
    return t, reason, lines


def crawler_db():
    return psycopg.connect(host="crawler-db", dbname="modama_crawler", user="postgres")


def first_crawl_start():
    with crawler_db() as conn:
        return conn.execute("SELECT min(started_at) FROM crawl_runs").fetchone()[0]


def warehouse_db():
    return psycopg.connect(
        host="postgres", dbname="datasetdb", user="admin", password="test"
    )


def opensearch_count():
    return http(f"{OPENSEARCH}/{INDEX}/_count")["count"]


def harvest_runs(conn):
    return conn.execute(
        "SELECT r.id, r.status, r.from_date FROM harvest_runs r "
        "JOIN endpoints e ON e.id = r.endpoint_id WHERE e.harvest_url = %s "
        "ORDER BY r.started_at",
        (OAI_URL,),
    ).fetchall()


def event_count(conn, run_id):
    return conn.execute(
        "SELECT count(*), count(error_message) FROM harvest_events "
        "WHERE harvest_run_id = %s",
        (run_id,),
    ).fetchone()


@pytest.fixture(scope="module")
def tree():
    # The real formats, as in the crawler's own test of the whole path, plus plain files
    cheat.pair(DATA / "scan")
    zarr_fixtures.array(DATA / "store")
    collapse_fixtures.venv(DATA / "env")
    zarr_fixtures.corrupt(DATA / "broken")
    shutil.copytree(MIXED, DATA / "mixed")
    (DATA / "notes").mkdir()
    (DATA / DISTINCT_FILE).write_text("Ferritin lamella, thickness map\n")
    (DATA / "notes" / "readme.txt").write_text("Plain notes\n")
    (DATA / "notes" / "sample-list.csv").write_text("id,name\n1,a\n")
    crawl()
    expected = oracle()
    assert len(expected) >= 10, expected
    return expected


def test_crawler_serves_what_the_oracle_expects(tree):
    with urllib.request.urlopen(
        OAI_URL + "?verb=ListIdentifiers&metadataPrefix=oai_dc"
    ) as response:
        root = ET.fromstring(response.read())
    served = {e.text for e in root.iterfind(".//oai:identifier", NS)}
    assert served == set(tree)


def test_harvest_and_index(tree):
    trigger_and_wait([OAI_URL])
    n = len(tree)
    with warehouse_db() as conn:
        runs = harvest_runs(conn)
        # records_harvested is never filled in upstream, so the events are what counts
        assert [(status, from_date) for _, status, from_date in runs] == [
            ("closed", None)
        ], runs
        # first: an empty harvest is its own failure, not "search found nothing"
        assert event_count(conn, runs[0][0]) == (n, 0)
    http(f"{OPENSEARCH}/{INDEX}/_refresh", method="POST")
    assert opensearch_count() == n
    # the counts are the summary; the traces name the stage of each item that diverged
    for title, _ in tree.values():
        assert_consistent(title)


def test_a_file_found_everywhere(tree):
    path = "/" + DISTINCT_FILE
    stages, first = trace(path)
    assert first is None
    assert [s.state for s in stages.values()] == ["ok"] * 7
    url = next(u for t, u in tree.values() if t == path)
    assert (
        stages["crawler"].key
        == stages["oai-pmh"].key
        == "oai:er-c-data-mgmt.fz-juelich.de:" + path
    )
    assert stages["harvest"].key == path
    assert stages["warehouse"].key.endswith("::" + path)
    assert stages["index"].key == url
    assert stages["search"].detail == "rank 1"


def test_the_raw_file_of_an_empad_pair(tree):
    (raw,) = (DATA / "scan").glob("*.raw")
    (header,) = (DATA / "scan").glob("*.xml")
    stages, first = trace(f"/scan/{raw.name}")
    assert first is None
    assert stages["crawler"].detail == f"member of /scan/{header.name}"
    assert stages["index"].key.endswith(f"/scan/{header.name}")


def test_status_of_a_complete_chain(tree):
    t, reason, lines = freshness()
    assert t == first_crawl_start(), (reason, lines)


def test_search_finds_the_file(tree):
    wanted = next(url for _, url in tree.values() if url.endswith(DISTINCT_FILE))
    hits = http(f"{SEARCH}/search?q=ferritin&resource=datasets")
    urls = [h["_source"]["url"] for h in hits["hits"]]
    assert wanted in urls, (wanted, urls)


def test_incremental_harvest_brings_only_the_new_file(tree):
    # datestamps have seconds granularity; the new record must be newer than the first harvest
    time.sleep(2)
    (DATA / ADDED_FILE).write_text("Added after the first harvest\n")
    crawl()
    expected = oracle()
    assert set(expected) - set(tree) and len(expected) == len(tree) + 1
    # a crawl that is not harvested yet: T stays at the first crawl
    t, _, lines = freshness()
    assert t == first_crawl_start()
    assert "latest crawl not harvested yet" in lines[1], lines
    trigger_and_wait([OAI_URL])
    with warehouse_db() as conn:
        runs = harvest_runs(conn)
        assert [status for _, status, _ in runs] == ["closed", "closed"], runs
        second, _, from_date = runs[1]
        assert from_date is not None, "second harvest was not incremental"
        assert event_count(conn, second) == (1, 0)
    http(f"{OPENSEARCH}/{INDEX}/_refresh", method="POST")
    assert opensearch_count() == len(expected)
    assert_consistent("/" + ADDED_FILE)


def test_the_warehouse_database_is_down(tree):
    # As typed; an unreachable address stands in for the stopped database,
    # since the test runs inside the stack and cannot stop a service
    run = subprocess.run(
        ["modama-chain", "trace", "/" + DISTINCT_FILE],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "MODAMA_CHAIN_WAREHOUSE_DB": "host=postgres port=1"},
    )
    assert run.returncode == 2
    assert [line.split()[0] for line in run.stdout.splitlines()] == [
        "tree",
        "crawler",
        "oai-pmh",
    ]
    assert "cannot reach the warehouse database" in run.stderr


def test_read_only_accounts_suffice(tree):
    # every trace and status above ran with these accounts
    with psycopg.connect(STORES.warehouse_db) as conn:
        user, insert = conn.execute(
            "SELECT current_user, has_table_privilege('records', 'INSERT')"
        ).fetchone()
    assert (user, insert) == ("chain_reader", False)
    run = subprocess.run(
        ["modama-chain", "status"], check=False, capture_output=True, text=True
    )
    assert run.returncode == 0 and "fresh     as of" in run.stdout, run


@pytest.fixture(scope="module")
def faults(tree):
    """Walk-through C's faults and a rename, with one crawl and one harvest."""
    time.sleep(2)
    (DATA / LATE_FILE).write_text("Arrived late\n")
    (DATA / RENAMED[0]).rename(DATA / RENAMED[1])
    crawl()
    # clock skew or the datestamp-window race: a datestamp an hour back, in whole seconds as store.py writes them
    with crawler_db() as conn:
        conn.execute(
            "UPDATE records SET datestamp = date_trunc('second', datestamp - interval '1 hour') "
            "WHERE metadata->'title'->>0 = %s",
            ("/" + LATE_FILE,),
        )
    trigger_and_wait([OAI_URL])
    lost = next(u for t, u in tree.values() if t == "/" + LOST_DOCUMENT)
    http(
        f"{OPENSEARCH}/{INDEX}/_doc/{urllib.parse.quote(lost, safe='')}",
        method="DELETE",
    )
    http(f"{OPENSEARCH}/{INDEX}/_refresh", method="POST")


def test_a_record_dated_before_the_harvest_window(faults):
    stages, first = trace("/" + LATE_FILE)
    assert (stages["crawler"].state, stages["oai-pmh"].state) == ("ok", "ok")
    assert first.name == "harvest" and first.state == "BEFORE-HARVEST-WINDOW"
    assert [stages[s].state for s in ("warehouse", "index", "search")] == [
        "missing"
    ] * 3


def test_a_lost_index_document(faults):
    stages, first = trace("/" + LOST_DOCUMENT)
    assert stages["warehouse"].state == "ok"
    assert first.name == "index" and first.state == "SYNCED-WITHOUT-DOCUMENT"


def test_a_renamed_file(faults):
    stages, first = trace("/" + RENAMED[0])
    assert (stages["tree"].state, stages["crawler"].state) == ("missing", "missing")
    assert (stages["warehouse"].state, stages["index"].state) == ("STALE", "STALE")
    assert first.state == "STALE"
    assert_consistent("/" + RENAMED[1])


def test_a_failed_harvest(faults):
    # Last: a failed run may block the endpoint (metadata-warehouse#158). The
    # endpoint's URL points at a closed port for one harvest, then back.
    t_before, _, _ = freshness()
    unreachable = "http://crawler:7655/oai"
    with warehouse_db() as conn:
        conn.execute(
            "UPDATE endpoints SET harvest_url = %s WHERE harvest_url = %s",
            (unreachable, OAI_URL),
        )
    try:
        # the DAG run itself ends in success although its harvest task failed;
        # the warehouse's run row is what records the failure
        trigger_and_wait([unreachable], check=False)
    finally:
        with warehouse_db() as conn:
            conn.execute(
                "UPDATE endpoints SET harvest_url = %s WHERE harvest_url = %s",
                (OAI_URL, unreachable),
            )
    t, _, lines = freshness()
    assert lines[1].split()[:2] == ["harvest", "failed"], lines
    assert t == t_before
