# Tasks

The decision for Alembic is @weber's (2026-11-12). The assumptions A1 to A6 in `proposal.md` are the research's leans and not yet answered; apply waits for his answers or overrides.

## 1. Before the code

- [ ] 1.1 Record R42 in `design/requirements.md` with the wording in `proposal.md` ("Why"), next to R41 and R43 from the open changes, and the decision for Alembic plus the answers on A1 to A6 in the decision log of `design/architecture.md`. Verify: the diff, reviewed by @weber.
- [ ] 1.2 Add `alembic>=1.20` and `SQLAlchemy>=2.0` (imported directly for the engine, D1) to `pyproject.toml`, `*.mako` to the package data, and install into `~/.venv`. Verify: `~/.venv/bin/python -m pip show alembic SQLAlchemy Mako` lists 1.20.1, 2.1.8 and 1.4.3 (or the then current releases, looked up on PyPI and named in the hand-over), MIT each; no other new package in `pip list` than these three.

## 2. Migrations and the command

- [ ] 2.1 `src/modama_crawler/migrations/` with `env.py`, `script.py.mako` and `versions/0001_baseline.py` (the statements of `ensure_tables` at e35e4b4, no `downgrade()`), and `python/crawler/alembic.ini` (D2, D5). Verify: `test_migrations.py` "A fresh database"; `pip wheel --no-deps` of the crawler, and `unzip -l` lists `env.py`, `script.py.mako` and `versions/0001_baseline.py`; `alembic revision -m probe --rev-id 0002_probe` in `python/crawler/` writes a file with `down_revision = "0001_baseline"` without a database (file removed afterwards).
- [ ] 2.2 `modama-crawler migrate`: crawl lock in `env.py` with the waiting line, `lock_timeout = '10s'`, one transaction, the log lines and exit statuses of D3. Verify: `test_migrations.py`, one test per scenario of "migrate brings the database to the code's schema", "One migration at a time, and none during a crawl" and "A failed migration changes nothing", the last two with a scripts directory under `tmp_path`.
- [ ] 2.3 `schema.check` replaces `ensure_tables` at `cli.py:270`, `:402`, `:454`, `:484`; `ensure_tables` is removed from `store.py` (D4). Verify: `test_cli.py`, one test per scenario of "Commands refuse a database that is behind the code" and "Commands refuse a database that is ahead of the code"; the existing `records` tests pass without a database; the time `modama-crawler runs` takes on a migrated test database, before and after the change, in the hand-over.
- [ ] 2.4 `conn` in `tests/conftest.py` migrates; `tests/migrations/before_migrations.sql`; the tests of "An existing database migrates in place", a single head, and up-down-up for every revision with a `downgrade()` (D9). Verify: `pytest` in `python/crawler/`, whole suite, with the number of skipped tests; `uvx ruff format --check --diff && uvx ruff check` from the repository root.
- [ ] 2.5 The order with `subtree-crawl` (D6). If it merged first: 0001 without its `ALTER`, `0002_crawl_runs_scope` with `IF NOT EXISTS` and a `downgrade()`, `before_migrations.sql` with the column. Otherwise: a note in `BACKLOG.md` and in the hand-over that its D5 and task 3.1 become migration 0002 (its branch is not edited from here). Verify: "A database made before migrations" passes against the `before_migrations.sql` of that order; `grep -n "ALTER\|CREATE" src/modama_crawler/store.py` finds no DDL.
- [ ] 2.6 Docs: `README.md` (setup: `migrate` once before `crawl`; line 96 replaced by how to add a migration, never to edit a shipped one, plain DDL from 0003 on, a `downgrade()` where it is one statement, and the refusal message); `AGENTS.md` (code map: `store.py` without the schema, `migrations/`, `schema.py`; `conn` in "Writing tests"); `BACKLOG.md` (the item "Schema migrations" replaced by what is left: backups before `migrate`, "Not now" of the proposal). Verify: the README's commands run as typed against a throwaway PostgreSQL (`/usr/lib/postgresql/17/bin`), output pasted in the hand-over.
- [ ] 2.7 Review of the migration code by an agent that did not write it, given the code, the spec and R42, not this design's conclusions (AGENTS.md; `design/review.md` is the pattern); findings verified before they are acted on. Verify: `review.md` in this change, each finding with its outcome.

## 3. Search stack

- [ ] 3.1 `crawler-migrate` in `prototypes/search-stack/docker-compose.yml`; `crawler` and `crawl-timer` wait for it (D8). Verify: `./downtest.sh --reset && ./uptest.sh` with no crawler image present: `docker compose ps -a` shows `crawler-migrate` exited 0, its log `schema migrated from none to …`, and `crawler` started after it; `./runtest.sh e2e` passes.
- [ ] 3.2 The upgrade and rollback steps (dump, build, `up`, `runs` as the check for pending migrations, downgrade or restore, D7) in `/prototypes/search-stack/README.md`, and an upgrade section in `design/field-tests/search-stack-staging-runbook.md`. Verify: the commands run as written in 4.2.

## 4. Dry runs on databases made by the current code

- [ ] 4.1 Outside the stack: a database made by the crawler at e35e4b4 (a checkout at that commit, `crawl --root tests/` against a throwaway server), copied with `createdb -T`, the copy migrated by the new code. Verify: rows of every table counted before and after are equal, datestamps unchanged, the schema compared with a fresh migrated one by the test's catalog query shows no difference; `runs` on the copy prints the same lines as before.
- [ ] 4.2 On the test deployment: the stack at e35e4b4 with a crawl and a harvest done, then the new image: a copy of `crawler-db`'s database migrated with `docker compose run --rm -e MODAMA_CRAWLER_DB=<copy> crawler-migrate`, then `docker compose up -d` on the real one, with `crawl-timer` running a crawl at that moment. Verify: what compose does with the old `crawler` and `crawl-timer` while `crawler-migrate` waits, as observed (logs, `ps -a`), in the hand-over; `modama-crawler runs` and `modama-chain status` after it; `./runtest.sh e2e`.
- [ ] 4.3 Staging, with @weber: `pg_dump -Fc` of `crawler-db` (location agreed with him, runbook "Safety"), restored into a scratch database, migrated with the new image, its schema compared with a fresh one (the one-time check of D5); then `./upstaging.sh --build`. Verify: the comparison output, the migration's log line and duration, `runs` and `modama-chain status` before and after, and the count of records with their newest datestamp unchanged.

## Workflow follow-up

- Archive the change after @weber's review of the proposal, the code review (2.7) and the staging upgrade (4.3).
