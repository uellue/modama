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
    # None from a crawler database before the extractor identity (0002_extractor_identity)
    identity: str | None = None
    reextracted: list | None = None  # per format and stored identity: datasets, changed
    # a subtree crawl's path ("/a/b"); None for a crawl of the whole tree, and from a
    # crawler database before the subtree crawl (0003_crawl_runs_scope)
    scope: str | None = None


def short(identity: str | None) -> str:
    """The identity's short form, as `modama-crawler runs` shows it: 12 hexadecimal digits, an earlier label quoted."""
    if identity is None:
        return "none"
    if len(identity) == 64 and all(c in "0123456789abcdef" for c in identity):
        return identity[:12]
    return f'"{identity}"'


def _has_column(conn: psycopg.Connection, table: str, column: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema()"
            " AND table_name = %s AND column_name = %s",
            (table, column),
        ).fetchone()
        is not None
    )


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
    member: bool  # path is a member of the dataset, or below its collapsed anchor; not its anchor
    basis: str  # why the crawler recognised it, with the notes of dropped name types
    extractor: str | None = None  # the format whose extractor produced its description
    identity: str | None = None  # the extractor identity it was produced under
    failed: bool = False  # the extraction failed: the record has a basic description


def dataset_of(conn: psycopg.Connection, path: str) -> Holding | None:
    """The dataset holding path, or None."""
    extraction = (
        "d.extractor, d.extractor_identity, d.extract_error IS NOT NULL"
        if _has_column(conn, "datasets", "extractor_identity")
        else "NULL, NULL, false"
    )
    row = conn.execute(
        f"SELECT d.anchor, d.basis, {extraction} FROM datasets d WHERE d.anchor = %s",
        (path,),
    ).fetchone()
    if row:
        return Holding(row[0], False, *row[1:])
    row = conn.execute(
        f"SELECT d.anchor, d.basis, {extraction} FROM members m JOIN datasets d USING (dataset_id)"
        " WHERE m.path = %s",
        (path,),
    ).fetchone()
    if row is None:
        # below a collapsed directory, whose contents the crawler doesn't list (248)
        row = conn.execute(
            f"SELECT d.anchor, d.basis, {extraction} FROM datasets d"
            " WHERE d.collapsed AND d.anchor = ANY(%s) ORDER BY length(d.anchor) LIMIT 1",
            (_ancestors(path),),
        ).fetchone()
    return Holding(row[0], True, *row[1:]) if row else None


def _ancestors(path: str) -> list[str]:
    """The directories above path: /a/b/c gives /a and /a/b."""
    parts = path.strip("/").split("/")
    return ["/" + "/".join(parts[:i]) for i in range(1, len(parts))]


_DATASET_COLUMNS = (
    "anchor", "type", "format", "version", "basis", "warnings", "parent", "collapsed",
    "mtime", "uid", "parts", "size", "stamp", "directory",
)  # fmt: skip


def stored_dataset(conn: psycopg.Connection, path: str) -> dict | None:
    """The stored dataset holding path (its anchor, a member, or below a collapsed anchor), shaped as the crawler's Dataset (browse, D6)."""
    ancestors = _ancestors(path)
    # extractor_version before the extractor identity (0002_extractor_identity): the label
    identity = (
        "extractor_identity"
        if _has_column(conn, "datasets", "extractor_identity")
        else "extractor_version"
    )
    row = conn.execute(
        f"""
        SELECT {", ".join(_DATASET_COLUMNS)}, extractor, {identity}, extracted,
            extract_error, extract_seconds,
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
    extractor, identity, extracted, error, seconds, members = row[n:]
    dataset["members"] = list(members)
    dataset["extraction"] = (
        None
        if extractor is None
        else {
            "extractor": extractor,
            "identity": identity,
            "stamp": dataset["stamp"],
            "extracted": extracted,
            "error": error,
            "seconds": seconds,
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
    identity = (
        "identity, reextracted"
        if _has_column(conn, "crawl_runs", "identity")
        else "NULL, NULL"
    )
    scope = "scope" if _has_column(conn, "crawl_runs", "scope") else "NULL"
    rows = conn.execute(
        f"""
        SELECT started_at, updated_at, finished_at, outcome, directories, files,
            datasets, records_changed, error, now() - updated_at, {identity}, {scope}
        FROM crawl_runs ORDER BY started_at DESC, run_id DESC
        """
    ).fetchall()
    return [Run(*row) for row in rows]
