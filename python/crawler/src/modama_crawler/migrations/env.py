"""Alembic's environment for the crawler's database (database-schema spec; design D1 to D3 of `schema-migrations`).

Run by `modama-crawler migrate` and by Alembic's own command line
(`alembic -c python/crawler/alembic.ini …`). No models: the revisions use
Alembic's operations or `op.execute` with SQL text, as upstream's warehouse.
Every way in that writes takes the crawl lock first, so that a migration
never runs next to a crawl or another migration; `alembic current` and
`--sql` take none.
"""

import logging
from logging.config import fileConfig

import psycopg
import sqlalchemy as sa
from alembic import context
from modama_crawler.migrate import LOCK_TIMEOUT_SECONDS
from modama_crawler.store import CRAWL_LOCK

log = logging.getLogger("modama_crawler.migrations")
config = context.config

# Alembic's command line only: `migrate` keeps the crawler's logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def offline() -> None:
    """`--sql`: print the SQL, as upstream's offline branch; connects to no database."""
    context.configure(
        url="postgresql+psycopg://",
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _wait_for_crawl_lock(conninfo: str) -> psycopg.Connection:
    """The crawl lock, on a connection of its own, waiting for it if a crawl or another migration holds it."""
    lock = psycopg.connect(conninfo, autocommit=True)
    ((taken,),) = lock.execute(
        "SELECT pg_try_advisory_lock(%s, %s)", CRAWL_LOCK
    ).fetchall()
    if not taken:
        log.info("waiting for the crawl lock (a crawl or another migration holds it)")
        lock.execute("SELECT pg_advisory_lock(%s, %s)", CRAWL_LOCK)
    return lock


def _applied(step, **kwargs) -> None:
    config.attributes.setdefault("applied", []).append(step.up_revision_id)


def online() -> None:
    conninfo = config.attributes.get("conninfo")
    # Alembic's command line: the database the crawler's commands use
    if conninfo is None:
        from dotenv import load_dotenv
        from modama_crawler.cli import conninfo_from_env

        load_dotenv()  # python/crawler/.env, as modama-crawler reads it
        conninfo = conninfo_from_env()
    engine = sa.create_engine(
        "postgresql+psycopg://",
        creator=lambda: psycopg.connect(conninfo),
        poolclass=sa.pool.NullPool,
    )
    lock = None
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=None,
                on_version_apply=_applied,
            )
            if not context.get_context().opts.get("dont_mutate"):
                lock = _wait_for_crawl_lock(conninfo)
            with context.begin_transaction():
                # inside Alembic's transaction: before it, SQLAlchemy would begin one of its own
                connection.exec_driver_sql(
                    f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_SECONDS}s'"
                )
                # under the lock: a migration that waited for another finds it done
                config.attributes["before"] = (
                    context.get_context().get_current_revision()
                )
                context.run_migrations()
    finally:
        # after the migration's transaction has ended
        if lock is not None:
            lock.close()


if context.is_offline_mode():
    offline()
else:
    online()
