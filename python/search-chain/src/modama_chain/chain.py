"""The trace of one path through the chain's stages, and the chain's freshness time T (chain-trace spec)."""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import psycopg

from . import crawler, warehouse
from .warehouse import Unreachable

# The crawler updates a running crawl once a minute; a run without an end not
# updated for twice that is stale (crawl-runs spec, "A killed crawl")
STALE_AFTER = timedelta(seconds=120)

OK, MISSING, DIFFERS, WARN = "ok", "missing", "differs", "warn"
# Flags: a rule over two neighbouring stages that fired (D6); upper case so they stand out (D10)
BEFORE_HARVEST_WINDOW = "BEFORE-HARVEST-WINDOW"
SYNCED_WITHOUT_DOCUMENT = "SYNCED-WITHOUT-DOCUMENT"
STALE = "STALE"


@dataclass(frozen=True)
class Stores:
    """Addresses and credentials of the chain's stores, from the environment (cli.py)."""

    root: Path
    crawler_db: str
    warehouse_db: str
    oai_url: str
    opensearch: str
    index: str
    search_api: str
    airflow: str
    airflow_user: str
    airflow_password: str


@dataclass(frozen=True)
class Stage:
    name: str
    state: str
    key: str = ""
    time: str = ""
    detail: str = ""


def when(t: datetime | float | None) -> str:
    if t is None:
        return ""
    if isinstance(t, float | int):
        t = datetime.fromtimestamp(t, UTC)
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(conninfo: str, store: str) -> psycopg.Connection:
    """A connection whose transactions are read-only, whatever the account may do (spec: the tool only reads)."""
    try:
        return psycopg.connect(
            conninfo, connect_timeout=10, options="-c default_transaction_read_only=on"
        )
    except psycopg.OperationalError as e:
        raise Unreachable(f"{store}: {str(e).strip()}") from e


def holding(published: bool, same: bool) -> str:
    """The state of a stage that holds the item, compared with the crawler and the stage before."""
    if not published:
        return STALE
    return OK if same else DIFFERS


def oai_datestamp(oai_url: str, identifier: str) -> datetime | None:
    """The datestamp the OAI-PMH server gives the record, or None if it does not know it."""
    query = urllib.parse.urlencode(
        {"verb": "GetRecord", "identifier": identifier, "metadataPrefix": "oai_dc"}
    )
    try:
        with urllib.request.urlopen(f"{oai_url}?{query}", timeout=60) as response:
            root = ET.fromstring(response.read())
    except OSError as e:
        raise Unreachable(f"OAI-PMH server at {oai_url}: {e}") from e
    except ET.ParseError as e:
        raise Unreachable(
            f"OAI-PMH server at {oai_url}: not an XML response: {e}"
        ) from e
    stamp = root.find(".//{http://www.openarchives.org/OAI/2.0/}header/{*}datestamp")
    if stamp is None:
        return None
    return datetime.fromisoformat(stamp.text)


def trace(stores: Stores, path: str) -> Iterator[Stage]:
    """One stage after the other, so that a caller can show them before an unreachable store stops the trace."""
    path = "/" + path.strip("/")
    try:
        st = os.lstat(stores.root / path.lstrip("/"))
        yield Stage(
            "tree", OK, path, f"mtime {when(st.st_mtime)} ctime {when(st.st_ctime)}"
        )
        in_tree = True
    except FileNotFoundError:
        yield Stage("tree", MISSING, path)
        in_tree = False

    with connect(stores.crawler_db, "crawler database") as conn:
        rules = crawler.keys(conn)
        found = crawler.dataset_of(conn, path)
        anchor = found[0] if found else path
        identifier = rules.identifier(anchor) if rules else ""
        rec = crawler.record(conn, identifier) if rules else None
    published = rec is not None
    if rules is None:
        yield Stage(
            "crawler", MISSING, detail="no records, so no keys to follow downstream"
        )
        return
    if found and found[1]:
        detail = f"member of {anchor}"
    elif found:
        detail = "dataset" if published else "dataset without a record"
    else:
        detail = "keys rebuilt from the path"
    if published and not in_tree and not (found and found[1]):
        detail += "; not in the tree, the next crawl drops it"
    yield Stage(
        "crawler",
        OK if published else MISSING,
        identifier,
        when(rec and rec.datestamp),
        detail,
    )

    oai = oai_datestamp(stores.oai_url, identifier)
    if oai is None:
        yield Stage("oai-pmh", MISSING, identifier)
    else:
        same = published and oai == rec.datestamp
        yield Stage("oai-pmh", holding(published, same), identifier, when(oai))

    with connect(stores.warehouse_db, "warehouse database") as conn:
        endpoint = warehouse.endpoint(conn, stores.oai_url)
        if endpoint is None:
            yield Stage(
                "harvest",
                MISSING,
                detail=f"no endpoint with harvest URL {stores.oai_url}",
            )
            return
        local = warehouse.local_id(identifier)
        event = warehouse.latest_event(conn, endpoint, local)
        closed = [
            r for r in warehouse.harvest_runs(conn, endpoint) if r.status == "closed"
        ]
        wrec = warehouse.record(conn, endpoint, local)
    yield harvest_stage(
        local,
        rec.datestamp if published else None,
        event,
        closed[-1] if closed else None,
    )

    if wrec is None:
        yield Stage("warehouse", MISSING, f"{endpoint}::{local}")
    else:
        same = event is not None and wrec.datestamp == event.datestamp
        yield Stage(
            "warehouse",
            holding(published, same),
            wrec.id,
            when(wrec.synced_at),
            "synced" if wrec.synced else "not synced",
        )

    url = wrec.url if wrec else rules.url(anchor)
    if warehouse.has_document(stores.opensearch, stores.index, url):
        if published and wrec and not wrec.synced:
            yield Stage(
                "index",
                DIFFERS,
                url,
                detail="the warehouse holds a version not indexed yet",
            )
        else:
            yield Stage("index", holding(published, True), url)
    elif wrec and wrec.synced:
        yield Stage(
            "index",
            SYNCED_WITHOUT_DOCUMENT,
            url,
            detail="the warehouse will not index it again",
        )
    else:
        yield Stage("index", MISSING, url)

    yield search_stage(
        anchor, url, warehouse.search(stores.search_api, anchor), published
    )


def harvest_stage(local: str, datestamp, event, last_closed) -> Stage:
    """The harvest of the record's current version; datestamp is the crawler's, None if it does not publish the record."""
    window = event.run if event else last_closed
    span = (
        f"{when(window.from_date) or 'start'} .. {when(window.until_date)}"
        if window
        else ""
    )
    current = event is not None and not event.is_deleted and not event.error
    if current and (datestamp is None or event.datestamp == datestamp):
        return Stage("harvest", holding(datestamp is not None, True), local, span)
    if datestamp is None:
        return Stage("harvest", MISSING, local, span)
    state = MISSING if event is None else DIFFERS
    if event is not None and event.error:
        return Stage("harvest", state, local, span, f"error: {event.error}")
    if last_closed is None:
        return Stage("harvest", state, local, detail="no closed harvest run yet")
    # The next incremental harvest asks from the last closed run's until, cut to
    # the second as the harvester sends it; anything dated before is never asked for
    next_from = last_closed.until_date.replace(microsecond=0)
    if datestamp < next_from:
        span = f"{when(last_closed.from_date) or 'start'} .. {when(last_closed.until_date)}"
        return Stage(
            "harvest",
            BEFORE_HARVEST_WINDOW,
            local,
            span,
            f"datestamp {when(datestamp)} is before {when(next_from)}, where the next incremental harvest starts; no harvest takes it",
        )
    return Stage(
        "harvest",
        state,
        local,
        span,
        "not harvested yet: datestamp after the last harvest",
    )


def search_stage(query: str, url: str, hits: list[str], published: bool) -> Stage:
    """Rank 1 is ok, a lower rank a warning (the warehouse's ranking is not ours), absence missing."""
    if url not in hits:
        first = f", first {hits[0]}" if hits else ""
        return Stage(
            "search", MISSING, query, detail=f"not among {len(hits)} hits{first}"
        )
    rank = hits.index(url) + 1
    if not published:
        return Stage("search", STALE, query, detail=f"rank {rank}")
    if rank == 1:
        return Stage("search", OK, query, detail="rank 1")
    return Stage("search", WARN, query, detail=f"rank {rank}, first hit {hits[0]}")


def diverging(stages: list[Stage]) -> int | None:
    """Index of the first stage missing, differing or flagged after a stage that has the item (or flagged itself)."""
    seen = False
    for i, stage in enumerate(stages):
        if stage.state not in (OK, WARN) and (seen or stage.state != MISSING):
            return i
        seen = seen or stage.state != MISSING
    return None


def crawl_state(run: crawler.Run) -> str:
    """By the crawler database's clock, like `modama-crawler runs`."""
    if run.finished_at is not None:
        return run.outcome
    return "running" if run.age <= STALE_AFTER else "stale"


def freshness(
    crawls: list[crawler.Run], harvests, index_runs
) -> tuple[datetime | None, str]:
    """T, or None and the stage that is missing.

    Closed harvest runs form a contiguous chain of windows. Up to the first
    one without a successful indexing run, everything they harvested is
    indexed; T is the start of the newest finished crawl that ended before
    the end of that indexed chain (D7).
    """
    indexed = {r.harvest_run_id for r in index_runs if r.state == "success"}
    covered = None
    for run in sorted(
        (r for r in harvests if r.status == "closed"), key=lambda r: r.until_date
    ):
        if run.id not in indexed:
            break
        covered = run.until_date
    if covered is None:
        return None, "no closed harvest run has been indexed successfully"
    done = [c for c in crawls if c.outcome == "finished" and c.finished_at <= covered]
    if not done:
        return None, "no finished crawl before the end of the last indexed harvest"
    return max(c.started_at for c in done), ""


def status(stores: Stores) -> Iterator[str | tuple[datetime | None, str]]:
    """The lines of `modama-chain status`: crawl, harvest, indexing, then (T, reason)."""
    with connect(stores.crawler_db, "crawler database") as conn:
        crawls = crawler.runs(conn)
    if crawls:
        c = crawls[0]
        state = crawl_state(c)
        end = when(c.finished_at) if c.finished_at else f"updated {when(c.updated_at)}"
        counts = f"{c.directories} directories, {c.files} files"
        if state == "finished":
            counts += f", {c.datasets} datasets, {c.records_changed} records changed"
        yield f"crawl     {state:<9} started {when(c.started_at)}  {end}  {counts}"
    else:
        yield "crawl     missing   no crawl run recorded"

    with connect(stores.warehouse_db, "warehouse database") as conn:
        endpoint = warehouse.endpoint(conn, stores.oai_url)
        harvests = warehouse.harvest_runs(conn, endpoint) if endpoint else []
    if harvests:
        h = harvests[-1]
        line = f"harvest   {h.status:<9} started {when(h.started_at)}  window {when(h.from_date) or 'start'} .. {when(h.until_date)}"
        closed = [r for r in harvests if r.status == "closed"]
        finished = [c for c in crawls if c.outcome == "finished"]
        if finished and (not closed or finished[0].finished_at > closed[-1].until_date):
            line += "  latest crawl not harvested yet"
        yield line
    else:
        yield f"harvest   missing   no harvest run of {stores.oai_url}"

    ours = {h.id for h in harvests}
    index_runs = [
        r
        for r in warehouse.index_runs(
            stores.airflow, stores.airflow_user, stores.airflow_password
        )
        if r.harvest_run_id in ours
    ]
    if index_runs:
        r = index_runs[0]
        yield f"indexing  {r.state:<9} started {when(r.start)}  ended {when(r.end)}  harvest run {r.harvest_run_id}"
    else:
        yield "indexing  missing   no indexing run of this endpoint's harvests"
    yield freshness(crawls, harvests, index_runs)
