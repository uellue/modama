"""The schema version of the crawler's database, compared with the code's (database-schema spec, R42).

Reads Alembic's `alembic_version` table with psycopg, without importing
Alembic: every command but `migrate` only checks (design D4 of the change
`schema-migrations`). The migrations are in `migrations/versions/`, one file
per revision, named after its id.
"""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg

log = logging.getLogger(__name__)

# The newest revision in migrations/versions/; a test checks that it is Alembic's head
HEAD = "0001_baseline"
MIGRATIONS = Path(__file__).parent / "migrations"


def known() -> set[str]:
    """The revision ids of this code, from the file names in migrations/versions/."""
    return {p.stem for p in (MIGRATIONS / "versions").glob("*.py")}


def current(conn: psycopg.Connection) -> str | None:
    """The database's schema version, or None if it has none (no migration has run)."""
    ((table,),) = conn.execute("SELECT to_regclass('alembic_version')").fetchall()
    if table is None:
        return None
    rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
    return rows[0][0] if rows else None


def mismatch(version: str | None, head: str, revisions: set[str]) -> str | None:
    """Why a database at version does not fit code whose newest revision is head, with the step; None if it fits."""
    if version == head:
        return None
    if version is None:
        return f"the database has no schema version, this crawler needs {head}: run modama-crawler migrate"
    if version not in revisions:
        return (
            f"the database schema is at {version}, which this crawler does not know: a newer crawler "
            "migrated it; use that crawler, or downgrade with it first (README)"
        )
    return f"the database schema is at {version}, this crawler needs {head}: run modama-crawler migrate"


def check(conn: psycopg.Connection) -> None:
    """Exit with status 2 and the step to take if the database's schema is not this code's."""
    problem = mismatch(current(conn), HEAD, known())
    if problem is not None:
        log.error("%s", problem)
        raise SystemExit(2)
