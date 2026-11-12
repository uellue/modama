"""`modama-crawler migrate`: bring the database's schema to the code's with Alembic (database-schema spec, R42).

The only module that imports Alembic (design D4 of `schema-migrations`), and
only when it migrates, so that its logging is set first. It
looks at the version first, without a lock, so that a database at the head
is reported at once, also during a crawl; only with revisions pending does
it run Alembic's upgrade, whose `env.py` takes the crawl lock (D3).
"""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg

from . import schema

log = logging.getLogger(__name__)

# A statement that waits longer for a table lock fails (env.py), rather than
# queueing the OAI-PMH server's requests behind it
LOCK_TIMEOUT_SECONDS = 10


def _quiet_alembic() -> None:
    """Of Alembic's own lines only `Running upgrade …`, one per revision, which names a failing one (D3)."""
    logging.getLogger("alembic").setLevel(logging.WARNING)
    migration = logging.getLogger("alembic.runtime.migration")
    migration.setLevel(logging.INFO)
    if not migration.filters:
        migration.addFilter(lambda record: record.getMessage().startswith("Running "))


def upgrade(conninfo: str, script_location: Path = schema.MIGRATIONS) -> int:
    """Apply every pending revision in one transaction; the exit status: 0 done or up to date, 1 failed, 2 ahead."""
    _quiet_alembic()  # before the import, which logs its plugins' setup
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option("script_location", str(script_location))
    config.attributes["conninfo"] = conninfo
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    chain = [r.revision for r in reversed(list(script.walk_revisions()))]
    with psycopg.connect(conninfo, autocommit=True) as conn:
        version = schema.current(conn)
        ((tables,),) = conn.execute(
            "SELECT to_regclass('crawl_runs') IS NOT NULL"
        ).fetchall()
    problem = schema.mismatch(version, head, set(chain))
    if problem is None:
        log.info("schema up to date at %s", head)
        return 0
    if version is not None and version not in chain:
        log.error("%s", problem)
        return 2
    try:
        command.upgrade(config, "head")
    except Exception as e:  # noqa: BLE001  the database's error or the revision's own: either way, rolled back
        before = config.attributes.get("before", version)
        applied = config.attributes.get("applied", [])
        start = chain.index(applied[-1]) + 1 if applied else _after(chain, before)
        failed = chain[start] if start < len(chain) else head
        reason = _reason(e)
        log.error(
            "migration %s failed, the database is unchanged at %s: %s",
            failed,
            before or "none",
            reason,
        )
        return 1
    before = config.attributes["before"]
    if before == head:  # another migration did it while this one waited
        log.info("schema up to date at %s", head)
        return 0
    if before is None and tables:
        log.info("tables made before migrations found: adopted as %s", chain[0])
    log.info("schema migrated from %s to %s", before or "none", head)
    return 0


def _after(chain: list[str], version: str | None) -> int:
    return 0 if version is None else chain.index(version) + 1


def _reason(e: Exception) -> str:
    """The database's error, or after a lock timeout what happened and the step."""
    from sqlalchemy.exc import DBAPIError

    original = e.orig if isinstance(e, DBAPIError) else e
    if isinstance(original, psycopg.errors.LockNotAvailable):
        return f"another transaction held a table for more than {LOCK_TIMEOUT_SECONDS} s: run migrate again"
    # the first line: PostgreSQL's LINE and caret lines would split the log line
    return (str(original).strip().splitlines() or [type(original).__name__])[0]
