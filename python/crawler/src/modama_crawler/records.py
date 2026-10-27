"""OAI-PMH records of datasets: identifier, browse URL and the Dublin Core mapping."""

from __future__ import annotations

import hashlib
import pwd
from datetime import UTC, datetime
from functools import cache
from urllib.parse import quote_plus

from .formats import Dataset

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


def dc_metadata(dataset: Dataset) -> dict[str, list[str]]:
    """Dublin Core elements of a dataset, mapped approximately from the file system (R25, R32)."""
    relations = [browse_url(p) for p in dataset.parts]
    if dataset.parent:
        relations.append(browse_url(dataset.parent))
    metadata = {
        "title": [dataset.anchor],
        "creator": [user_name(dataset.uid)],
        "date": [format_datestamp(datetime.fromtimestamp(dataset.mtime, UTC))],
        "type": ["Dataset"],
        "format": [dataset.type],
        "identifier": [browse_url(dataset.anchor)],
        "publisher": [PUBLISHER],
    }
    if relations:
        metadata["relation"] = relations
    return metadata


def build(dataset: Dataset) -> tuple[str, dict[str, list[str]]]:
    """(identifier, Dublin Core metadata) of a dataset."""
    return oai_identifier(dataset.anchor), dc_metadata(dataset)
