"""End to end: crawl a fixture tree, harvest it through the warehouse's Airflow DAG, find it by search.

Runs inside the crawler container of compose.yml (./e2e.sh test), after ./e2e.sh up and reset.
"""

import json
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

import psycopg
import pytest
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


def trigger_and_wait(urls):
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
    trigger_and_wait([OAI_URL])
    with warehouse_db() as conn:
        runs = harvest_runs(conn)
        assert [status for _, status, _ in runs] == ["closed", "closed"], runs
        second, _, from_date = runs[1]
        assert from_date is not None, "second harvest was not incremental"
        assert event_count(conn, second) == (1, 0)
    http(f"{OPENSEARCH}/{INDEX}/_refresh", method="POST")
    assert opensearch_count() == len(expected)
