# Proposal

## Why

A schema change today means dropping the crawler's database (`README.md:96`, `store.py:63`). On staging that costs a full crawl, harvest and indexing, about a night, and in production it would cost the datestamps that incremental harvesting relies on. The first schema change is already waiting: `crawl_runs.scope` in the open change `subtree-crawl` (D5). @weber decided on 2026-11-12: "Let's go with alembic, now, to test it properly", after "We will need migration in production, so we may start testing it safely while we are running dev iterations here. [...] Let's follow upstream as far as sensible." The research behind it is `docs/research/schema-migrations.md` (commit 22f891d, branch of worktree `agent-a5e0aa836a67afb2f`): upstream's metadata warehouse adopted Alembic in v1.8.0.

Serves the request of 2026-11-12, to be recorded as R42 (task 1.1):

> - **R42 (must for production, @weber 2026-11-12)** A schema change reaches an existing crawler database in place, without recreating it.
>   - Datasets, extractions, records with their datestamps and the run history are kept, so a change costs no re-crawl, re-harvest or re-indexing (staging: about a night; `field-tests/search-stack-staging-findings.md`).
>   - The change is applied by one explicit step before the crawler's services start, never by two processes at once and never during a crawl.
>   - A crawler refuses a database whose schema is not the one its code expects, and names the step to take.
>   - Example: staging's database, made by commit 3251cad, gains `crawl_runs.scope`, with its 1.45 million records and their datestamps unchanged.
>   - Accepted when a database made by the code before this change migrates in a test and compares equal to a fresh one, and a copy of staging's database migrates before staging does.

## What Changes

- **New command `modama-crawler migrate`**: brings the database's schema to the code's, with Alembic, and exits. Safe to run again: `INFO schema up to date at 0001_baseline`.
- **The other database commands stop creating tables.** `crawl`, `runs`, `timer` and `serve` check the schema version instead and refuse a database that is behind or ahead of the code, with exit status 2 and the step to take. `records` needs no database and is unchanged. **BREAKING** for developers: a new database needs `migrate` once before `crawl`.
- **The search stack gets a one-shot service `crawler-migrate`** that `crawler` and `crawl-timer` wait for, as `warehouse-init` and `airflow-init` do.
- **Migrations live in `src/modama_crawler/migrations/`**, plain SQL through `op.execute`, no SQLAlchemy models, as upstream. Revision 0001 is today's `ensure_tables`, so staging's database migrates in place.
- **New dependencies**, accepted with the decision: `alembic` 1.20.1 (2026-10-22), `SQLAlchemy` 2.1.8 (2026-11-04), `Mako` 1.4.3 (2026-09-22), all MIT, current on PyPI on 2026-11-12. What they need besides (`typing-extensions`, `MarkupSafe`) is installed already, through `psycopg-pool` and `Werkzeug`.

Behaviour towards the user:
- *Operators:* a `migrate` step before the services start, which compose runs on every `up`; before an upgrade, a `pg_dump` of `crawler-db` (their step for now). A crawler on a database that does not fit says so: `ERROR the database schema is at 0001_baseline, this crawler needs 0002_crawl_runs_scope: run modama-crawler migrate`.
- *Developers:* a schema change is a new file in `migrations/versions/` (`alembic revision -m "crawl_runs scope" --rev-id 0002_crawl_runs_scope` from `python/crawler/`), never an edit of `store.py`'s DDL or of a migration that has shipped. Every test database is built by the migrations, so `pytest` runs the new one.
- *Harvesters and searchers:* nothing changes. `serve`'s responses are the same, and `modama-chain` reads the same tables.

## Assumptions

The research's leans. @weber has not answered these yet; each can be overruled before apply.

- **A1, decided by @weber 2026-11-12: "We should follow the warehouse's practice unless there are specific reasons against it."** The warehouse (v1.10.0, `alembic/versions/0002` to `0005`, `alembic/env.py:46`) has no models (`target_metadata = None`, no autogenerate) and writes each migration with Alembic's operations (`op.add_column`, `op.alter_column`, `op.drop_column` with `sa` types) or `op.execute` with SQL text, whichever fits; so do we. Its revision ids are `NNNN_name`. The rest of this assumption stands as written: one linear chain, in `src/modama_crawler/migrations/` with a small `alembic.ini` in `python/crawler/`. Was: **Plain SQL, no models.** `op.execute` with the DDL as text, `target_metadata = None`, readable revision ids `NNNN_name` (at most 32 characters, Alembic's `version_num`), one linear chain, in `src/modama_crawler/migrations/` with a small `alembic.ini` in `python/crawler/` for Alembic's own command line. *Alternative:* SQLAlchemy models with autogenerate; a second description of the schema next to the SQL that `store.py` runs through psycopg.
- **A2 An explicit step, under a lock, and a refusal.** `modama-crawler migrate` runs in the one-shot service; the other commands only read the version and refuse when it differs from the code's head, in either direction, as Airflow and toolmeta-harvester do. The lock is the existing crawl lock, taken in `env.py`, so a migration waits for a running crawl and every way of running Alembic takes it (alembic#633 recommends a lock in `env.py`). *Alternatives:* migrate-on-start in every command under the lock (today's path, grown up); `migrate && exec serve` in `crawler` instead of a service; a new lock key `(0x6D6F, 3)` that does not wait for crawls (the research's form); warn and continue on a database that is ahead, which relies on every migration being expand-only.
- **A3 Baseline: 0001 is today's `ensure_tables`,** `IF NOT EXISTS` included. A database without Alembic's `alembic_version` table is at "no revision" for Alembic, so `migrate` runs 0001 on it: on an empty database that creates the schema, on one made by `ensure_tables` it changes nothing, and in both cases Alembic then records 0001. No `stamp` step, one source of the schema. *Alternative:* upstream's form, an empty `0001_baseline` plus `alembic stamp` when `alembic_version` is missing, with the schema kept in a create script (`init-warehouse.sh:32-34` shows the conditional stamp that needs).
- **A4 Downgrades only where trivial** (`DROP COLUMN` for an added column); the way back from anything else is the `pg_dump` taken before the upgrade, the operator's step until production backups exist (`/prototypes/search-stack/README.md`, "Backups"). *Alternatives:* a downgrade for every migration, as upstream; forward-only; the dump as part of `migrate`.
- **A5 Tests on migrated databases.** The `conn` fixture migrates every fresh test database; one test loads the schema the code before this change makes, adds rows, migrates, and compares the result with a fresh database. *Alternative:* pytest-alembic (0.13.2, MIT), one more dependency for checks of a few lines each.
- **A6 `scope` becomes 0002 in either order** with `subtree-crawl` (design D6).

## Not now

- A backup inside `migrate`, and backups of `crawler-db` in general (backlog).
- Migrations that cannot run in a transaction (`CREATE INDEX CONCURRENTLY`), and zero-downtime tools such as pgroll: one writer, and harvesters retry on 503.
- A `migrate --check` or a dry-run option: `runs` with the new image already says whether a migration is pending, and Alembic's `--sql` prints the SQL.
- `modama-chain` checking the schema version: it reads an interface and keeps its own checks (`crawler.py:102`).
- An automatic comparison of an adopted database with the baseline: done once by hand for staging (task 4.3).
- A frozen schema per release for the tests: there are no releases yet.

## Questions for @weber

- The leans A1 to A6: as they are, or which one differently?
- Waiting for a running crawl (A2): on staging a nightly crawl takes over an hour, and `crawler` stays down while `crawler-migrate` waits. Acceptable, or should `migrate` refuse at once and leave the timing to the operator?
- The command's name: `migrate`, or `db migrate` as in Airflow?
- Which ships first, `subtree-crawl` or this change? Both orders work (design D6); this one first saves `subtree-crawl` the `ALTER` in `ensure_tables`.

## Capabilities

### New Capabilities
- `database-schema`: how the crawler's database gets its schema and keeps it in step with the code: the `migrate` command, the lock, the refusal of a database that does not fit, and what a migration keeps.

### Modified Capabilities

## Impact

- Crawler: `migrations/` (new: `env.py`, `script.py.mako`, `versions/0001_baseline.py`), a small module for the version check and the `migrate` command, `cli.py` (the command; the check replaces `ensure_tables` at `cli.py:270`, `:402`, `:454`, `:484`), `store.py` (`ensure_tables` removed), `alembic.ini`, `pyproject.toml` (dependencies, `*.mako` as package data), tests (`conftest.py`, new `test_migrations.py`, `tests/migrations/before_migrations.sql`).
- Search stack: `docker-compose.yml` (`crawler-migrate`, `depends_on`), its README (the upgrade step), the staging runbook.
- Docs: `README.md` (setup, the schema section at line 96, how to add a migration), `AGENTS.md` (code map), `BACKLOG.md`, `design/requirements.md` (R42), the decision log.
- The open change `subtree-crawl`: D5 and task 3.1 become migration 0002 if this change ships first.
