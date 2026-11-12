"""The crawler's database, read as an interface: datasets, members, records, crawl_runs (README, "What it reads").

The key rules below repeat the crawler's (modama_crawler.records) so that the
tool can rebuild the keys of a path the crawler no longer has. The namespace
and URL prefix are read back from a record the crawler does have, and a test
compares rebuilt keys with crawled ones.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import psycopg

MAX_LOCAL_ID = 255
MIN_HASH_DIGITS = 32


@dataclass(frozen=True)
class Keys:
    """Where the crawler's identifiers come from: 'oai:<namespace>:' and the browse URL up to the path."""

    oai_prefix: str
    url_prefix: str

    def identifier(self, path: str) -> str:
        local = quote_plus(path, safe="!$'()*,/;?@")
        if len(local) >= MAX_LOCAL_ID:
            prefix = local[: MAX_LOCAL_ID - 1 - MIN_HASH_DIGITS]
            escape = prefix.rfind("%", len(prefix) - 2)
            if escape != -1:
                prefix = prefix[:escape]
            digest = hashlib.sha256(path.encode()).hexdigest()
            local = prefix + "~" + digest[: MAX_LOCAL_ID - 1 - len(prefix)]
        return self.oai_prefix + local

    def url(self, path: str) -> str:
        return self.url_prefix + quote_plus(path, safe="!$'()*,/:;?@")


@dataclass(frozen=True)
class Record:
    identifier: str
    datestamp: datetime


@dataclass(frozen=True)
class Run:
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    outcome: str | None
    directories: int
    files: int
    datasets: int | None
    records_changed: int | None
    error: str | None
    age: timedelta  # since the last update, by the database's clock


def keys(conn: psycopg.Connection) -> Keys | None:
    """The key rules, learnt from one record: its identifier, title (the path) and dc:identifier (the URL)."""
    row = conn.execute(
        "SELECT identifier, metadata->'title'->>0, metadata->'identifier'->>0 FROM records LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    identifier, path, url = row
    oai_prefix = identifier[: identifier.rindex(":") + 1]
    quoted = Keys("", "").url(path)
    if not url.endswith(quoted):
        raise ValueError(f"cannot learn the URL rule from {identifier}: {url}")
    return Keys(oai_prefix, url[: len(url) - len(quoted)])


@dataclass(frozen=True)
class Holding:
    """The dataset that holds a path, as the crawler stored it."""

    anchor: str
    member: bool  # path is a member of the dataset, not its anchor
    basis: str  # why the crawler recognised it, with the notes of dropped name types


def dataset_of(conn: psycopg.Connection, path: str) -> Holding | None:
    """The dataset holding path, or None."""
    row = conn.execute(
        "SELECT anchor, basis FROM datasets WHERE anchor = %s", (path,)
    ).fetchone()
    if row:
        return Holding(row[0], False, row[1])
    row = conn.execute(
        "SELECT d.anchor, d.basis FROM members m JOIN datasets d USING (dataset_id) WHERE m.path = %s",
        (path,),
    ).fetchone()
    return Holding(row[0], True, row[1]) if row else None


_DATASET_COLUMNS = (
    "anchor", "type", "format", "version", "basis", "warnings", "parent", "collapsed",
    "mtime", "uid", "parts", "size", "stamp", "directory",
)  # fmt: skip


def stored_dataset(conn: psycopg.Connection, path: str) -> dict | None:
    """The stored dataset holding path (its anchor, a member, or below a collapsed anchor), shaped as the crawler's Dataset (browse, D6)."""
    ancestors = []
    parts = path.strip("/").split("/")
    for i in range(1, len(parts)):
        ancestors.append("/" + "/".join(parts[:i]))
    row = conn.execute(
        f"""
        SELECT {", ".join(_DATASET_COLUMNS)}, extractor, extractor_version, extracted,
            extract_error, extract_seconds, extract_retry,
            array(SELECT m.path FROM members m WHERE m.dataset_id = d.dataset_id ORDER BY m.path)
        FROM datasets d
        WHERE anchor = %s
            OR dataset_id IN (SELECT dataset_id FROM members WHERE path = %s)
            OR (collapsed AND anchor = ANY(%s))
        ORDER BY anchor = %s DESC LIMIT 1
        """,
        (path, path, ancestors, path),
    ).fetchone()
    if row is None:
        return None
    n = len(_DATASET_COLUMNS)
    dataset = dict(zip(_DATASET_COLUMNS, row[:n], strict=True))
    extractor, version, extracted, error, seconds, retry, members = row[n:]
    dataset["members"] = list(members)
    dataset["extraction"] = (
        None
        if extractor is None
        else {
            "extractor": extractor,
            "version": version,
            "stamp": dataset["stamp"],
            "extracted": extracted,
            "error": error,
            "seconds": seconds,
            "retry": retry,
        }
    )
    return dataset


def stored_record(
    conn: psycopg.Connection, identifier: str
) -> tuple[datetime, dict] | None:
    """The record's datestamp and Dublin Core metadata, as the crawler stored them."""
    row = conn.execute(
        "SELECT datestamp, metadata FROM records WHERE identifier = %s", (identifier,)
    ).fetchone()
    return (row[0], row[1]) if row else None


def record(conn: psycopg.Connection, identifier: str) -> Record | None:
    row = conn.execute(
        "SELECT identifier, datestamp FROM records WHERE identifier = %s", (identifier,)
    ).fetchone()
    return Record(*row) if row else None


def runs(conn: psycopg.Connection) -> list[Run]:
    """All crawl runs, newest first; none if the crawler predates crawl_runs."""
    exists = conn.execute("SELECT to_regclass('crawl_runs')").fetchone()[0]
    if exists is None:
        return []
    rows = conn.execute(
        """
        SELECT started_at, updated_at, finished_at, outcome, directories, files,
            datasets, records_changed, error, now() - updated_at
        FROM crawl_runs ORDER BY started_at DESC, run_id DESC
        """
    ).fetchall()
    return [Run(*row) for row in rows]
