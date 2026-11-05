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


def dataset_of(conn: psycopg.Connection, path: str) -> tuple[str, bool] | None:
    """(anchor, is a member of another dataset) of the dataset holding path, or None."""
    row = conn.execute(
        "SELECT anchor FROM datasets WHERE anchor = %s", (path,)
    ).fetchone()
    if row:
        return row[0], False
    row = conn.execute(
        "SELECT d.anchor FROM members m JOIN datasets d USING (dataset_id) WHERE m.path = %s",
        (path,),
    ).fetchone()
    return (row[0], True) if row else None


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
