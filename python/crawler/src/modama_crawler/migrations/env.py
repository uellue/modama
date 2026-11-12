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


def _wait_for_crawl_lock(connection) -> None:
    """The crawl lock for the migration's transaction, waiting if a crawl or another migration holds it.

    A transaction lock on the migration's own connection, so that it lasts
    exactly as long as the migration's transaction, also when the client is
    killed while the server still runs a statement (review 2.7, finding 6).
    Taken before the lock timeout is set, which would end the wait.
    """
    taken = connection.exec_driver_sql(
        "SELECT pg_try_advisory_xact_lock(%s, %s)", CRAWL_LOCK
    ).scalar()
    if not taken:
        log.info("waiting for the crawl lock (a crawl or another migration holds it)")
        connection.exec_driver_sql("SELECT pg_advisory_xact_lock(%s, %s)", CRAWL_LOCK)


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
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=None,
            on_version_apply=_applied,
        )
        # inside Alembic's transaction: before it, SQLAlchemy would begin one of its own
        with context.begin_transaction():
            if not context.get_context().opts.get("dont_mutate"):
                _wait_for_crawl_lock(connection)
            connection.exec_driver_sql(
                f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_SECONDS}s'"
            )
            # under the lock: a migration that waited for another finds it done
            config.attributes["before"] = context.get_context().get_current_revision()
            context.run_migrations()


if context.is_offline_mode():
    offline()
else:
    online()
