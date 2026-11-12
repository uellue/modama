"""End to end: crawl a fixture tree, harvest it through the warehouse's Airflow DAG, find it by search.

Runs inside the crawler container of the search stack (./runtest.sh e2e), on a fresh stack:
./downtest.sh --reset && ./uptest.sh first.
Assertions trace items with the chain tool (python/search-chain), so that a
failure names the first stage that diverged; the fault scenarios at the end
check that the trace finds what it is meant to find.
"""

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

import psycopg
import pytest
from lxml import etree
from modama_chain import chain
from modama_chain.cli import stores_from_env
from modama_crawler.formats import core
from modama_crawler.formats.collapse.tests import generate as collapse_fixtures
from modama_crawler.formats.zarr.tests import generate as zarr_fixtures
from modama_formats_em.empad import cheat

DATA = Path("/data")
E2E = Path("/e2e")  # this folder, mounted by docker-compose.override.yml
OAI_URL = "http://crawler:7654/oai"
AIRFLOW = "http://airflow-api-server:8080"
OPENSEARCH = "http://opensearch:9200"
SEARCH = "http://search-api:8000"
FRONTEND = "http://matchmaker:3000"
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
STRAY_TAGS = "stray/notes.gtg"
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


ACCOUNTS = {
    # starts harvests: role harvest-trigger, which the test deployment gives this container
    "crawler": ("MODAMA_CRAWLER_AIRFLOW_USER", "MODAMA_CRAWLER_AIRFLOW_PASSWORD"),
    # reads runs and their tasks: modama-chain's Viewer account
    "chain": ("MODAMA_CHAIN_AIRFLOW_USER", "MODAMA_CHAIN_AIRFLOW_PASSWORD"),
}
TOKEN = {}


def airflow(path, data=None, method=None):
    """Airflow's API: writes with the crawler's account, reads with modama-chain's."""
    account = "crawler" if data is not None else "chain"
    if account not in TOKEN:
        user, password = ACCOUNTS[account]
        TOKEN[account] = http(
            AIRFLOW + "/auth/token",
            {"username": os.environ[user], "password": os.environ[password]},
        )["access_token"]
    return http(
        AIRFLOW + path, data, method, {"Authorization": f"Bearer {TOKEN[account]}"}
    )


def wait_for(run_id, check=True):
    """Wait until the harvest DAG run ends; with check, it must succeed."""
    run_id = urllib.parse.quote(run_id, safe="")
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


def trigger_and_wait(urls, check=True):
    """A harvest started by the test rather than by a crawl."""
    run = airflow(
        f"/api/v2/dags/{DAG}/dagRuns",
        {"logical_date": None, "conf": {"harvest_urls": urls, "index_name": INDEX}},
    )
    wait_for(run["dag_run_id"], check)


def crawl(trigger=True):
    """Crawl; the crawler starts the harvest itself, which this waits for. Without trigger: crawl only."""
    env = dict(os.environ)
    if not trigger:
        env.pop("MODAMA_CRAWLER_AIRFLOW_URL")
    run = subprocess.run(
        ["modama-crawler", "crawl", "--root", str(DATA)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    if trigger:
        (run_id,) = re.findall(r"harvest of \S+ started: (\S+)", run.stderr)
        wait_for(run_id)


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
    """Published by the crawler, and no stage after it diverges (a path in no stage would count as consistent)."""
    stages, first = trace(path)
    assert first is None, f"{path}: first diverging stage {first.name}: {first}"
    assert stages["crawler"].state == "ok", (
        f"{path}: not published: {stages['crawler']}"
    )


def freshness():
    *lines, (t, reason) = chain.status(STORES)
    return t, reason, lines


def crawler_db():
    return psycopg.connect(host="crawler-db", dbname="modama_crawler", user="postgres")


TREE_CRAWL = {}  # the start of the test tree's first crawl, set by the tree fixture


def first_crawl_start():
    """Not the earliest run: the timer crawls the empty tree when the stack starts."""
    return TREE_CRAWL["started_at"]


def latest_crawl_start():
    with crawler_db() as conn:
        return conn.execute("SELECT max(started_at) FROM crawl_runs").fetchone()[0]


def warehouse_db():
    """The warehouse as its admin, for injecting faults: the test deployment's credentials, from the mounted testconf."""
    values = dict(
        line.split("=", 1)
        for line in (E2E / "testconf/secrets/warehouse-db.env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    return psycopg.connect(
        host="postgres",
        dbname=values["POSTGRES_DB"],
        user=values["POSTGRES_USER"],
        password=values["POSTGRES_PASSWORD"],
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
    # A text file named like a K2IS tag file (change recognition-checks-content)
    (DATA / "stray").mkdir()
    (DATA / STRAY_TAGS).write_text("hello\n")
    crawl()
    TREE_CRAWL["started_at"] = latest_crawl_start()
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


def test_the_crawl_started_the_harvest_and_index(tree):
    # the tree fixture's crawl started the harvest and waited for it
    n = len(tree)
    with warehouse_db() as conn:
        runs = harvest_runs(conn)
        # The timer crawled the empty tree when the stack started, and its harvest may
        # have run before the tree was written or after (then it took the tree, and the
        # tree crawl's own harvest found nothing new): count the events of all runs.
        assert all(status == "closed" for _, status, _ in runs), runs
        # records_harvested is never filled in upstream, so the events are what counts;
        # first: an empty harvest is its own failure, not "search found nothing"; more
        # than n would be a record harvested twice
        counts = [event_count(conn, run_id) for run_id, _, _ in runs]
        assert (sum(c for c, _ in counts), sum(e for _, e in counts)) == (n, 0), counts
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
    # Then the dataset's basis (spec chain-trace, change recognition-checks-content)
    assert stages["crawler"].detail.startswith(
        f"member of /scan/{header.name}; basis: "
    )
    assert stages["index"].key.endswith(f"/scan/{header.name}")


def test_the_crawler_line_shows_the_datasets_basis(tree):
    # Spec chain-trace, "A text file named like a K2IS tag file" and "A plain file"
    stages, first = trace("/" + STRAY_TAGS)
    assert first is None
    assert stages["crawler"].detail == (
        "dataset; basis: single file; em/k2is: not application/x.dm-gtg, no DM header"
    )
    stages, _ = trace("/" + DISTINCT_FILE)
    assert stages["crawler"].detail == "dataset; basis: single file"


def test_the_crawler_line_names_the_identity_behind_a_description(tree):
    # Spec chain-trace, "A description from the current installation" (change
    # extractor-identity), with the EMPAD header: the tree has no DM4 file
    (header,) = (DATA / "scan").glob("*.xml")
    stages, _ = trace(f"/scan/{header.name}")
    assert re.search(
        r"; extracted by em/empad under [0-9a-f]{12}, the last crawl's \(current\)$",
        stages["crawler"].detail,
    ), stages["crawler"].detail
    (crawl_line, *_) = freshness()[2]
    assert re.search(r"; identity [0-9a-f]{12}", crawl_line), crawl_line


def test_extracted_metadata_reaches_the_search(tree):
    # The EMPAD header's extracted values reach the index as description and subjects
    # (dc:description, dc:subject), and the search API returns them in the hit.
    (header,) = (DATA / "scan").glob("*.xml")
    url = next(u for t, u in tree.values() if t == f"/scan/{header.name}")
    (doc,) = http(f"{OPENSEARCH}/{INDEX}/_search", {"query": {"term": {"_id": url}}})[
        "hits"
    ]["hits"]
    descriptions = [d["description"] for d in doc["_source"].get("descriptions", [])]
    subjects = [s["subject"].lower() for s in doc["_source"].get("subjects", [])]
    assert descriptions and "128×128 pixel frames" in descriptions[0], descriptions
    assert any("empad" in s for s in subjects), subjects
    hits = http(
        f"{SEARCH}/search?q={urllib.parse.quote(header.stem)}&resource=datasets"
    )
    (hit,) = [h for h in hits["hits"] if h["_source"]["url"] == url]
    assert "128×128 pixel frames" in json.dumps(hit, ensure_ascii=False), hit


BROWSE = "http://browse:7655"


def browse(what, path):
    # as the page on the machine sends it: the browser refuses other host names, and live
    # views without the page's header (D14)
    return http(
        f"{BROWSE}/api/{what}?" + urllib.parse.urlencode({"path": path}),
        headers={"Host": "localhost:7655", "X-Modama-Browse": "1"},
    )


def parsed(xml):
    """An XML document without its formatting."""
    return etree.fromstring(
        xml.encode() if isinstance(xml, str) else xml,
        etree.XMLParser(remove_blank_text=True),
    )


def canonical(xml) -> bytes:
    return etree.tostring(parsed(xml), method="c14n")


def record_c14n(xml) -> bytes:
    """The `<record>` of a GetRecord response, canonical."""
    (record,) = parsed(xml).iterfind(".//oai:record", NS)
    return etree.tostring(record, method="c14n")


def test_the_browser_shows_the_record_the_server_serves(tree):
    # Spec chain-browse, "A file found everywhere": the live record, by the checkout's
    # code, equals the OAI-PMH server's for an unchanged file
    path = "/" + DISTINCT_FILE
    stored = {v["key"]: v for v in browse("stored", path)["views"]}
    live = {v["key"]: v for v in browse("live", path)["views"]}
    assert set(live) == {"dataset", "record", "datacite", "document", "hit", "entry"}
    assert set(stored) == {"dataset", "record", "document", "hit", "entry"}
    assert json.loads(stored["dataset"]["text"]) == json.loads(live["dataset"]["text"])
    identifier = "oai:er-c-data-mgmt.fz-juelich.de:" + path
    with urllib.request.urlopen(
        OAI_URL
        + "?"
        + urllib.parse.urlencode(
            {"verb": "GetRecord", "identifier": identifier, "metadataPrefix": "oai_dc"}
        )
    ) as response:
        served = response.read()
    assert live["record"]["note"].startswith("equal to the stored record")
    assert record_c14n(live["record"]["text"]) == record_c14n(served)
    assert record_c14n(stored["record"]["text"]) == record_c14n(served)


def test_the_browser_computes_what_the_warehouse_stored(tree):
    # Spec chain-browse, "The live index document matches the stored one": the harvester's
    # XSLT, the warehouse's transformation and the search API's hit, run or emulated by the
    # browser, against what the stack stored for the EMPAD header
    (header,) = (DATA / "scan").glob("*.xml")
    path = f"/scan/{header.name}"
    stored = {v["key"]: v for v in browse("stored", path)["views"]}
    live = {v["key"]: v for v in browse("live", path)["views"]}
    doc = json.loads(live["document"]["text"])
    indexed = json.loads(stored["document"]["text"])
    indexed.pop("emb")
    assert {k: v for k, v in doc.items() if k != "_additional_metadata"} == {
        k: v for k, v in indexed.items() if k != "_additional_metadata"
    }
    assert canonical(doc["_additional_metadata"]) == canonical(
        indexed["_additional_metadata"]
    )
    hit, real = json.loads(live["hit"]["text"]), json.loads(stored["hit"]["text"])
    computed = (
        "_id",
        "dataset_url",
        "title",
        "description",
        "creator",
        "publication_date",
    )
    assert {k: hit[k] for k in computed} == {k: real[k] for k in computed}
    assert hit["_source"] == real["_source"]
    with warehouse_db() as conn:
        (raw,) = conn.execute(
            "SELECT e.raw_metadata::text FROM harvest_events e JOIN records r"
            " ON r.endpoint_id = e.endpoint_id AND r.record_identifier = e.record_identifier"
            " WHERE r.url = %s ORDER BY e.datestamp DESC LIMIT 1",
            (doc["url"],),
        ).fetchone()
    assert canonical(live["datacite"]["text"]) == canonical(raw)
    assert live["entry"]["entry"]["title"] == path


def test_the_browser_refuses_a_path_outside_the_tree(tree):
    for path in ("/notes/../../etc/passwd", "etc/passwd", "//etc/passwd"):
        with pytest.raises(urllib.error.HTTPError) as e:
            browse("list", path)
        assert e.value.code == 400, path


def test_status_of_a_complete_chain(tree):
    t, reason, lines = freshness()
    assert t == first_crawl_start(), (reason, lines)


def test_search_finds_the_file(tree):
    wanted = next(url for _, url in tree.values() if url.endswith(DISTINCT_FILE))
    hits = http(f"{SEARCH}/search?q=ferritin&resource=datasets")
    urls = [h["_source"]["url"] for h in hits["hits"]]
    assert wanted in urls, (wanted, urls)


def test_the_frontend_serves_its_page(tree):
    with urllib.request.urlopen(FRONTEND + "/", timeout=30) as response:
        assert response.headers.get_content_type() == "text/html"
        page = response.read().decode()
    assert "<title>EOSC Data Commons</title>" in page, page[:500]


def test_the_chat_page_needs_no_login(tree):
    # patches/matchmaker/: the chat page's code, as its page loads it, has no login gate
    with urllib.request.urlopen(FRONTEND + "/chat", timeout=30) as response:
        page = response.read().decode()
    chunk = re.search(r"/assets/ChatPage-[\w-]+\.js", page)
    assert chunk, page[:500]
    with urllib.request.urlopen(FRONTEND + chunk[0], timeout=30) as response:
        code = response.read().decode()
    assert "Authentication Required" not in code
    assert "Conversations are kept only with an account" in code


def test_the_chat_page_leaves_the_model_to_the_search_api(tree):
    # patches/matchmaker/0002: the chat page's request names no model, so that the
    # search API's DEFAULT_LLM_MODEL applies (keys.env); upstream's page sent
    # "cesnet/agentic", which failed without a CESNET key (staging 2026-11-12). The
    # chat test below sends what the page sends, so this check keeps the two alike.
    with urllib.request.urlopen(FRONTEND + "/chat", timeout=30) as response:
        page = response.read().decode()
    requests = []
    for path in sorted(set(re.findall(r"/assets/[\w-]+\.js", page))):
        with urllib.request.urlopen(FRONTEND + path, timeout=30) as response:
            code = response.read().decode()
        # the request body, minified: `{items:messages.filter(…).map(…)}` up to its `;`
        requests += re.findall(r"=\{items:[^;]*\};\w+&&\(\w+\.thread_id=", code)
    assert len(requests) == 1, requests
    assert "model" not in requests[0], requests[0]


def test_the_chat_page_keeps_brackets_in_link_addresses(tree):
    # patches/matchmaker/0003: the chat page reads a link's address with brackets in
    # balanced pairs, so ".../SI+data+(20)/..." stays one link with its citation (staging
    # finding F19); upstream's code ended the address at the first closing bracket.
    with urllib.request.urlopen(FRONTEND + "/chat", timeout=30) as response:
        page = response.read().decode()
    code = ""
    for path in sorted(set(re.findall(r"/assets/[\w-]+\.js", page))):
        with urllib.request.urlopen(FRONTEND + path, timeout=30) as response:
            code += response.read().decode()
    assert r"]\((.+?)\)" not in code  # upstream's address pattern
    assert r"(?:[^()\n]|\(" in code  # the patch's, as the build keeps it


def test_the_frontend_finds_the_file(tree):
    # the route the frontend's search page calls (matchmaker's src/lib/api.ts), which its
    # server proxies to the search API
    wanted = next(url for _, url in tree.values() if url.endswith(DISTINCT_FILE))
    hits = http(f"{FRONTEND}/api/search/search?q=ferritin&resource=datasets")
    urls = [h["_source"]["url"] for h in hits["hits"]]
    assert wanted in urls, (wanted, urls)


# The search API's hybrid score is the weighted mean of its two legs, each normalized
# to 0..1 (min_max): kNN 0.6, keyword 0.4 (upstream's hybrid_weights), times 0.1 for a
# record without a description (description_penalty); every record of ours has one since
# change em-formats-and-extraction. The kNN leg alone gives at most 0.6; only a keyword
# match lifts a hit above that.
KNN_ONLY_MAX = 0.6


def test_the_keyword_leg_finds_a_word_of_the_title(tree):
    # "ferritin" is in this one record's title only (the record has no description
    # or subjects); without patches/search-api/ the keyword leg matches nothing
    wanted = next(url for _, url in tree.values() if url.endswith(DISTINCT_FILE))
    hits = http(f"{SEARCH}/search?q=ferritin&resource=datasets")["hits"]
    scores = {h["_source"]["url"]: h["_score"] for h in hits}
    assert scores[wanted] > KNN_ONLY_MAX * 1.01, scores


def test_chat_answers_with_a_search(tree):
    # The chat agent searches with its tool and answers; one short question, so that a
    # run costs a few requests to the language model service in keys.env. runtest.sh sets
    # E2E_CHAT: 1 run, 0 skipped on request, "missing:…" no key, which fails (README).
    # Through matchmaker's proxy without a login, the route its chat page calls
    # (src/lib/api.ts), so that one run also shows AI Mode works for visitors.
    chat = os.environ.get("E2E_CHAT", "")
    if chat == "0":
        pytest.skip("WARNING: chat not tested, E2E_CHAT=0")
    if chat != "1":
        pytest.fail(
            f"no language model key: {chat.removeprefix('missing:') or 'E2E_CHAT unset'}"
        )
    wanted = next(url for _, url in tree.values() if url.endswith(DISTINCT_FILE))
    question = {
        "items": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": "Find datasets about ferritin."}],
            }
        ]
    }
    request = urllib.request.Request(
        f"{FRONTEND}/api/search/chat",
        data=json.dumps(question).encode(),
        headers={"Content-Type": "application/json"},
    )
    events = []
    with urllib.request.urlopen(request, timeout=300) as response:
        for line in response:
            if line.startswith(b"data:"):
                events.append(json.loads(line[5:]))
    types = [e.get("type") for e in events]
    assert "RUN_ERROR" not in types, [e for e in events if e.get("type") == "RUN_ERROR"]
    assert types[0] == "RUN_STARTED" and types[-1] == "RUN_FINISHED", types
    assert any(t.startswith("TOOL_CALL") for t in types), types
    assert wanted in json.dumps(events), "the search tool's result lacks the record"
    answer = "".join(
        e.get("delta", "") for e in events if e.get("type") == "TEXT_MESSAGE_CHUNK"
    )
    assert answer.strip(), types


def test_incremental_harvest_brings_only_the_new_file(tree):
    # datestamps have seconds granularity; the new record must be newer than the first harvest
    time.sleep(2)
    (DATA / ADDED_FILE).write_text("Added after the first harvest\n")
    crawl(trigger=False)
    expected = oracle()
    assert set(expected) - set(tree) and len(expected) == len(tree) + 1
    # a crawl that is not harvested yet: T stays at the first crawl
    t, _, lines = freshness()
    assert t == first_crawl_start()
    assert "latest crawl not harvested yet" in lines[1], lines
    with warehouse_db() as conn:
        before = len(harvest_runs(conn))
    trigger_and_wait([OAI_URL])
    with warehouse_db() as conn:
        runs = harvest_runs(conn)
        assert len(runs) == before + 1, runs
        assert all(status == "closed" for _, status, _ in runs), runs
        second, _, from_date = runs[-1]
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
    names = [
        line.split()[0] for line in run.stdout.splitlines() if line[:2] in ("  ", "> ")
    ]
    stages = [
        n
        for n in names
        if n
        in ("tree", "crawler", "oai-pmh", "harvest", "warehouse", "index", "search")
    ]
    assert stages == ["tree", "crawler", "oai-pmh"], run.stdout
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


def test_a_changed_record_replaces_the_old_one(tree):
    # Same identifier, new content: the owner changes, which records.py maps to
    # dc:creator and the warehouse to creators (it drops dc:format, so a changed
    # type would not reach the index). Nothing else changes, mtime included. The new
    # owner is known only to the test directory, through sssd (records spec, scenario
    # An owner from the directory).
    path = "/" + DISTINCT_FILE
    url = next(u for t, u in tree.values() if t == path)
    identifier = next(i for i, (t, _) in tree.items() if t == path)
    with crawler_db() as conn:
        ((before, creator),) = conn.execute(
            "SELECT datestamp, metadata->'creator'->>0 FROM records WHERE identifier = %s",
            (identifier,),
        ).fetchall()
    assert creator == "root"
    count = opensearch_count()
    time.sleep(2)  # datestamps have seconds granularity
    os.chown(DATA / DISTINCT_FILE, 10001, -1)  # alice: creator "Alice Anderson"
    crawl()  # starts the harvest and waits for it
    with crawler_db() as conn:
        ((after, creator),) = conn.execute(
            "SELECT datestamp, metadata->'creator'->>0 FROM records WHERE identifier = %s",
            (identifier,),
        ).fetchall()
    assert (creator, after > before) == ("Alice Anderson", True)
    with warehouse_db() as conn:
        rows = conn.execute(
            "SELECT r.datestamp, r.opensearch_synced FROM records r "
            "JOIN endpoints e ON e.id = r.endpoint_id "
            "WHERE e.harvest_url = %s AND r.record_identifier = %s",
            (OAI_URL, path),
        ).fetchall()
    assert rows == [(after, True)], rows
    http(f"{OPENSEARCH}/{INDEX}/_refresh", method="POST")
    assert opensearch_count() == count
    docs = http(f"{OPENSEARCH}/{INDEX}/_search", {"query": {"term": {"_id": url}}})[
        "hits"
    ]["hits"]
    assert [[c.get("creatorName") for c in d["_source"]["creators"]] for d in docs] == [
        ["Alice Anderson"]
    ], docs
    hits = http(f"{SEARCH}/search?q=ferritin&resource=datasets")["hits"]
    assert [h["_source"]["url"] for h in hits].count(url) == 1, hits
    assert_consistent(path)


@pytest.fixture(scope="module")
def faults(tree):
    """Walk-through C's faults and a rename, with one crawl and one harvest."""
    time.sleep(2)
    (DATA / LATE_FILE).write_text("Arrived late\n")
    (DATA / RENAMED[0]).rename(DATA / RENAMED[1])
    # without the crawler's trigger: the fault must be in place before the harvest
    crawl(trigger=False)
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
    assert t is not None and t == t_before
