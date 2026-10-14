"""OAI-PMH records for crawled datasets: identifier, Dublin Core metadata and datestamp."""

import hashlib
import pwd
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from urllib.parse import quote_plus

import psycopg
from psycopg.types.json import Jsonb

OAI_NAMESPACE = "er-c-data-mgmt.fz-juelich.de"
BROWSE_URL = "https://er-c-data-mgmt.fz-juelich.de/browse/?path="
PUBLISHER = "ER-C"

# The EOSC harvester keeps only the part of an identifier after the last ":"
# and stores it as VARCHAR(255).
MAX_LOCAL_ID = 255
MIN_HASH_DIGITS = 32


def format_datestamp(timestamp: datetime) -> str:
    return timestamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def browse_url(path: str) -> str:
    """Landing page of path (relative to the data root, with leading "/") in the data browser.

    The quoting must match quote_path() in python/mgmtinterface exactly, since
    ELN entries refer to these URLs and are matched byte for byte.
    """
    return BROWSE_URL + quote_plus(path, safe="!$'()*,/:;?@")


def oai_identifier(path: str) -> str:
    """OAI identifier of the dataset at path (relative to the data root, with leading "/").

    The local part is quoted like the browse URL, but with ":" escaped. Local
    parts of 255 characters or more are shortened to exactly 255: a prefix,
    "~" and hex digits of the SHA-256 of the path.
    """
    local = quote_plus(path, safe="!$'()*,/;?@")
    if len(local) >= MAX_LOCAL_ID:
        prefix = local[: MAX_LOCAL_ID - 1 - MIN_HASH_DIGITS]
        # Don't cut a %XX escape in half
        escape = prefix.rfind("%", len(prefix) - 2)
        if escape != -1:
            prefix = prefix[:escape]
        digest = hashlib.sha256(path.encode()).hexdigest()
        local = prefix + "~" + digest[: MAX_LOCAL_ID - 1 - len(prefix)]
    return f"oai:{OAI_NAMESPACE}:{local}"


@cache
def user_name(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def dc_metadata(path: str, mtime: float, uid: int, mime: str) -> dict[str, list[str]]:
    """Dublin Core elements of the dataset at path, mapped approximately from the file system."""
    return {
        "title": [path],
        "creator": [user_name(uid)],
        "date": [format_datestamp(datetime.fromtimestamp(mtime, UTC))],
        "type": ["Dataset"],
        "format": [mime],
        "identifier": [browse_url(path)],
        "publisher": [PUBLISHER],
    }


def publish_records(
    conn: psycopg.Connection, root: Path, batch_size: int = 1000
) -> int:
    """Create or update the record of every dataset. Returns the number of changed records.

    The datestamp is the time the record last changed, not the file mtime:
    harvesters ask for records changed since their last run, and a file copied
    with an old mtime must still show up. Committing in batches keeps the gap
    between datestamp and commit short, so a concurrent harvest misses nothing.
    """
    changed = 0
    with (
        conn.cursor(name="publish_records", withhold=True) as datasets,
        conn.cursor() as cur,
    ):
        datasets.execute(
            """
            SELECT d.dataset_id, f.path, f.mtime, f.uid, f.mime
            FROM datasets d JOIN files f USING (path_id)
            """
        )
        while rows := datasets.fetchmany(batch_size):
            params = []
            for dataset_id, abspath, mtime, uid, mime in rows:
                path = "/" + str(Path(abspath).relative_to(root))
                metadata = dc_metadata(path, mtime, uid, mime)
                params.append((dataset_id, oai_identifier(path), Jsonb(metadata)))
            cur.executemany(
                """
                INSERT INTO records (dataset_id, identifier, metadata, datestamp)
                VALUES (%s, %s, %s, date_trunc('second', clock_timestamp()))
                ON CONFLICT (dataset_id) DO UPDATE
                SET identifier = EXCLUDED.identifier,
                    metadata = EXCLUDED.metadata,
                    datestamp = EXCLUDED.datestamp
                WHERE (records.identifier, records.metadata)
                    IS DISTINCT FROM (EXCLUDED.identifier, EXCLUDED.metadata)
                """,
                params,
            )
            changed += cur.rowcount
            conn.commit()
    return changed
