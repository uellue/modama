"""The views of one file along the chain, stored and live, each labelled by its source (change chain-browse, D6 to D10)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from lxml import etree

from . import chain, crawler, live, upstream, warehouse
from .warehouse import Unreachable

STORED, ACTUAL, EMULATED = "stored", "actual code", "emulated"
ENTRY_TITLE = "Matchmaker: cited dataset, expanded"


@dataclass
class View:
    key: str
    title: str
    source: str  # STORED, ACTUAL or EMULATED
    origin: str  # the store, or the code and lines it follows
    text: str = ""  # the content: XML or JSON
    note: str = ""  # what to know about it: missing, differs, an error
    entry: dict | None = field(default=None)  # the matchmaker entry's values


def pretty_json(value) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def pretty_xml(data: bytes | str) -> str:
    """Re-indented, so that the stored and the live documents read alike."""
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.fromstring(data.encode() if isinstance(data, str) else data, parser)
    return etree.tostring(root, pretty_print=True, encoding="unicode")


def without_embedding(doc: dict) -> dict:
    """The index document with its embedding vector replaced by its length: a vector is not readable."""
    if "emb" not in doc:
        return doc
    return {**doc, "emb": f"<{len(doc['emb'] or ())} numbers>"}


def get_record(oai_url: str, identifier: str) -> bytes:
    """The OAI-PMH server's GetRecord response for identifier, as a harvester receives it."""
    query = urllib.parse.urlencode(
        {"verb": "GetRecord", "identifier": identifier, "metadataPrefix": "oai_dc"}
    )
    try:
        with urllib.request.urlopen(f"{oai_url}?{query}", timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as e:
        if e.code == 503:  # server.py: the store lock, while a crawl stores its records
            raise Unreachable(
                f"OAI-PMH server at {oai_url}: 503, a crawl is storing its records; reload in a minute"
            ) from e
        raise Unreachable(f"OAI-PMH server at {oai_url}: HTTP {e.code}") from e
    except OSError as e:
        raise Unreachable(f"OAI-PMH server at {oai_url}: {e}") from e


def harvested_record(response: bytes | str) -> str:
    """The `<record>` of a GetRecord response as the harvester serialises it (harvester_oaipmh.py:158, D7)."""
    root = etree.fromstring(
        response.encode() if isinstance(response, str) else response
    )
    record = root.find(f"{{{upstream.OAI_NS}}}GetRecord/{{{upstream.OAI_NS}}}record")
    return etree.tostring(record, pretty_print=True, encoding="unicode")


@dataclass
class Stored:
    """What the stores hold for a path, also what the live views compare with."""

    views: list[View]
    anchor: str | None = None
    url: str | None = None
    record: tuple[datetime, dict] | None = None
    repo: str | None = None


def stored_views(stores: chain.Stores, path: str) -> Stored:
    """The stored views: the crawler's dataset and record, the index document, the search API's hit and its entry (D6)."""
    views: list[View] = []
    out = Stored(views)
    dataset = View("dataset", "Dataset", STORED, "crawler database: datasets, members")
    record = View(
        "record", "OAI-PMH record", STORED, f"GetRecord from {stores.oai_url}"
    )
    views += [dataset, record]
    try:
        with chain.connect(stores.crawler_db, "crawler database") as conn:
            found = crawler.stored_dataset(conn, path)
            rules = crawler.keys(conn)
            out.anchor = found["anchor"] if found else path
            if rules:
                identifier = rules.identifier(out.anchor)
                out.url = rules.url(out.anchor)
                out.record = crawler.stored_record(conn, identifier)
    except Unreachable as e:
        dataset.note = record.note = str(e)
        return out
    if found:
        dataset.text = pretty_json(live.summary(found))
    else:
        dataset.note = (
            "no dataset holds this path: not crawled yet, skipped or excluded"
        )
    try:  # the live index document's _repo, also for a file not crawled yet
        with chain.connect(stores.warehouse_db, "warehouse database") as conn:
            out.repo = warehouse.repository_code(conn, stores.oai_url)
    except Unreachable:
        pass  # the live index document says that its _repo is unknown
    if out.record is None:
        record.note = "the crawler publishes no record for it"
        return out
    try:
        record.text = pretty_xml(get_record(stores.oai_url, identifier))
    except Unreachable as e:
        record.note = str(e)
    doc = View(
        "document",
        "Warehouse index document",
        STORED,
        f"OpenSearch {stores.index}, _id {out.url}",
    )
    hit_view = View(
        "hit", "Search API hit", STORED, f"{stores.search_api}/search?q=<its path>"
    )
    entry = View("entry", ENTRY_TITLE, EMULATED, upstream.SOURCES["entry"][1])
    views += [doc, hit_view, entry]
    try:
        source = warehouse.document(stores.opensearch, stores.index, out.url)
    except Unreachable as e:
        doc.note = hit_view.note = entry.note = str(e)
        return out
    if source is None:
        doc.note = hit_view.note = entry.note = "not in the index"
        return out
    doc.text = pretty_json(without_embedding(source))
    try:
        hits = warehouse.search_hits(stores.search_api, out.anchor)
    except Unreachable as e:
        hit_view.note = entry.note = str(e)
        return out
    hit = next((h for h in hits if h["_source"].get("url") == out.url), None)
    if hit is None:
        hit_view.note = f"not among the {len(hits)} hits for its path"
        entry.note = "no hit, so nothing to cite"
    else:
        hit_view.note = f"rank {hits.index(hit) + 1} for its path"
        hit_view.text = pretty_json(hit)
        entry.entry = upstream.cited_entry(hit)
        entry.note = "from the real hit"
    return out


def live_views(
    stores: chain.Stores,
    code: upstream.Upstream,
    path: str,
    config: Path | None,
    before: Stored,
) -> list[View]:
    """The live views: the crawler's code on the checkout, then the harvester's, the warehouse's, the search API's, matchmaker's."""
    started = time.monotonic()
    result = live.run(
        str(stores.root),
        path,
        base_url=stores.oai_url,
        config=config,
        stored=before.record,
    )
    took = (
        f"took {time.monotonic() - started:.1f} s"  # for the large folders (review R1)
    )
    origin = (
        "the checkout's crawler and formats: the file's folder alone (walk(top=…); no"
        " subfolders, no adoption), extraction of its dataset, records.build"
    )
    if "error" in result:
        return [
            View(
                "dataset", "Dataset", ACTUAL, origin, note=f"{result['error']}\n{took}"
            )
        ]
    notes = "\n".join([took, result["report"], *result["notes"]])
    dataset = result["dataset"]
    if dataset is None:
        return [
            View(
                "dataset",
                "Dataset",
                ACTUAL,
                origin,
                note=f"no dataset holds this path\n{notes}",
            )
        ]
    views = [
        View("dataset", "Dataset", ACTUAL, origin, pretty_json(dataset), notes),
        View(
            "record",
            "OAI-PMH record",
            ACTUAL,
            "records.build and render, as the server's GetRecord",
            pretty_xml(result["record"]),
            result["record_note"],
        ),
    ]
    datacite = View("datacite", "DataCite (harvester)", *upstream.SOURCES["datacite"])
    document = View(
        "document", "Warehouse index document", *upstream.SOURCES["document"]
    )
    hit = View("hit", "Search API hit", *upstream.SOURCES["hit"])
    entry = View("entry", ENTRY_TITLE, *upstream.SOURCES["entry"])
    views += [datacite, document, hit, entry]
    harvested = harvested_record(result["record"])
    try:
        datacite.text = code.datacite(harvested)
        doc = code.document(datacite.text, harvested, before.repo, stores.oai_url)
    except Exception as e:  # noqa: BLE001 -- upstream's own failure is what the view shows
        for v in (document, hit, entry):
            v.note = f"{type(e).__name__}: {e}"
        return views
    document.text = pretty_json(doc)
    if before.repo is None:
        document.note = (
            "_repo unknown: no endpoint in the warehouse database for this OAI-PMH URL"
        )
    the_hit = upstream.search_hit(doc.get("url") or "", doc)
    hit.text = pretty_json(the_hit)
    entry.entry = upstream.cited_entry(the_hit)
    return views


def as_dicts(views: list[View]) -> list[dict]:
    return [asdict(v) for v in views]
