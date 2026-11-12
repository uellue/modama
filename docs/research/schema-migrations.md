# Schema migrations for the crawler's database

Research note, 2026-11-12, written by an agent at @weber's request (review of the OpenSpec
change `subtree-crawl`, D5). Not yet reviewed by a person. No code was changed.

## For people

- **Recommendation:** Alembic, as upstream's metadata warehouse uses it since v1.8.0: plain
  SQL in `op.execute`, no models, in `src/modama_crawler/migrations/`.
- **Who runs them:** a command, for example `modama-crawler migrate`, under an advisory lock,
  in a one-shot service that `crawler` and `crawl-timer` wait for (like `airflow-init` and our
  `warehouse-init`). The other commands refuse a database that is behind the code.
- **Staging keeps its database:** 0001 is today's `ensure_tables` (`IF NOT EXISTS`), which
  made staging (3251cad). 0002 adds `scope`. Migrate a copy of staging first.
- **Tests:** all test databases are built by the migrations. One test migrates the previous
  release's schema and compares it with a fresh one.
- **Why:** upstream's tool, maintained (1.20.1, 2026-10-22, MIT). Recreating the database
  costs staging a night.
- **Cost:** three new dependencies (`alembic`, `SQLAlchemy`, `Mako`, all MIT), about a day
  of work (my estimate). The alternative without dependencies: SQL files plus a version
  table, about 50 lines.
- **Decisions needed:** the questions at the end.

## Details

Paths under `python/`, `prototypes/search-stack/` and the EOSC snapshots refer to the
`crawler` branch at e35e4b4 (2026-11-12). Its submodule `metadata-warehouse` is at 0b461ce,
and `data-commons-search` is the snapshot checked out in the main checkout. GitHub facts are
from the public API and raw files, fetched 2026-11-12 with a generic User-Agent.

### 1. Upstream: how EOSC Data Commons changes schemas

There is no single upstream practice. The component with long-lived production data, the
warehouse, uses Alembic. The others create tables at start.

**metadata-warehouse (Alembic, since v1.8.0):**
- `CHANGELOG.md:23`: "alembic: setup alembic migrations (#163)", v1.8.0, 2026-10-01.
  `CHANGELOG.md:15`: v1.9.0 "rewrite DaSCh migration as an alembic migration (#182)".
  `pyproject.toml:17`: `alembic>=1.18.4`.
- Layout: `alembic.ini` at the root (`script_location = %(here)s/alembic`) and
  `alembic/env.py`. Migrations are in `alembic/versions/NNNN_name.py`, with readable revision
  ids (`0001_baseline`, `0002_record_subjects`, …) and a linear chain.
  - The snapshot holds 0001 to 0005.
  - The `development` branch (tree 800b914) adds `0006_add_cern.py`, which inserts a
    repository and its endpoint.
- `env.py:9-34` builds the URL `postgresql+psycopg://…` from `POSTGRES_*` variables.
  It falls back to the password `test` and the database `testdatasetdb`.
  - `env.py:46`: `target_metadata = None`, so there are no models and no autogenerate.
  - `env.py:85-95`: one connection and one transaction (Alembic's default).
  - No lock.
- The migrations are mostly raw SQL through `op.execute`:
  - enum changes, `0003_dasch_endpoint.py:26-29`;
  - data inserts, `0004_add_dataverseua.py:24-70`;
  - a backfill before `NOT NULL`, `0005_remove_doi.py:54-79`.
  - Only 0002 uses `op.add_column` (`0002_add_raw_and_enriched_subjects.py:26-43`).
  - Every revision has a `downgrade()`. That of 0003 is a careful enum swap
    (`0003_dasch_endpoint.py:40-80`).
- **Baseline:** `0001_baseline_root.py:22-30` is empty: "This is the first database version
  created by `create_db.py`". The schema itself is in
  `scripts/postgres_data/create_sql/<db>/*.sql`, applied by `create_db.py`.
  - The README (`README.md:108-131`) says: create with `create_db.py --db $dbname`, then
    `alembic stamp 0001_baseline` and `alembic upgrade head`.
  - "**All further changes** to the database should be done as Alembic migrations."
  - So the schema has two sources: the create SQL, frozen at the baseline, and the migrations.
- **At deploy time:** nothing runs it automatically.
  - Upstream's `docker-compose.yml` runs only Airflow's own migration (`airflow-init`,
    `_AIRFLOW_DB_MIGRATE: "true"`, lines 293-310).
  - No image contains `alembic/` (`docker/transform/Dockerfile`, `docker/airflow/Dockerfile`).
  - Their deploy repository `metadata-airflow` documents only `docker compose exec
    airflow-scheduler airflow db migrate` (README lines 277-281). Its `migrate-postgres.sh`
    moves PostgreSQL 16 to 17 and does not change the schema.
  - How EOSC migrates its production warehouse is not documented in any repository I found.
- **Tests:** `e2e/test_e2e.py:95-134` resets the database from the create SQL, then stamps
  `0001_baseline` and upgrades to head (datasetdb only; TODO for filedb, lines 118-119).
  - `test_alembic_upgrade_downgrade_one_version` (lines 691-736) downgrades to 0001, checks
    that the columns are gone, upgrades to 0002 and checks that they are back.
  - CI runs this e2e on the whole compose stack (`.github/workflows/ci_cd.yml:29-78`).
  - Nothing tests a database made by an earlier release.
- **Data in migrations:** the migrations add endpoints of other repositories, active ones.
  Our `init-warehouse.sh:98-103` deactivates them after every upgrade.

**Our search stack already runs upstream's Alembic at every start.**
- `prototypes/search-stack/init-warehouse.sh:19-35` creates empty databases with
  `create_db.py`. It stamps `0001_baseline` only if `alembic_version` is missing, then always
  runs `alembic upgrade head`.
- It runs in the one-shot service `warehouse-init` (`docker-compose.yml:205-235`,
  `restart: on-failure`), which mounts upstream's `alembic/` and `alembic.ini` read-only.

**data-commons-search (no migrations):**
- `src/data_commons_search/db.py:106-108`, `init_postgres_storage()` is
  `Base.metadata.create_all`, called at app start (`main.py:96`). The tests do the same
  (`tests/conftest.py:23`).
- The schema is exported into the warehouse's create SQL by `scripts/export_db_schema.py`
  (`README.md:132-135`).
- Unchanged on `main` (tree 02e485d, `db.py:106-108`).

**metadata-crawlers:** no database of its own. It writes through the warehouse's API
(`README.md:12-15`).

**toolmeta-harvester (EOSC, in-house versioning):** `src/toolmeta_harvester/db/database.py`
on `main` (last commit to the file 0916d74):
- `initialize_db()` (lines 111-160) takes `pg_advisory_xact_lock(7355608)`, with the comment
  "since multiple DAGs can simultaneously initialize the db".
- It keeps a one-row table `toolmeta_schema_version` and refuses a database whose version is
  newer than the code's (`RuntimeError`).
- Otherwise it runs `create_all` and `ensure_columns()`.
- `ensure_columns()` (lines 34-80) adds missing model columns with
  `ALTER TABLE … ADD COLUMN IF NOT EXISTS`. It refuses primary-key, foreign-key and
  `NOT NULL`-without-default columns: they need "an explicit database migration".
- That is our `ensure_tables` path, grown up, with a lock and a version number.

**Airflow, as a data point.** Source: `airflow-core/src/airflow/utils/db.py` on `main`
(last commit to the file f2edf56) and its docs.
- Alembic inside.
  - An empty database is created from the ORM and stamped head (lines 718-739).
  - An existing one gets `command.upgrade` under a global advisory lock
    `DBLocks.MIGRATIONS` (lines 1240-1245).
  - The lock is a PostgreSQL `pg_advisory_lock` with a `lock_timeout` (lines 1628-1660).
- `check_migrations(timeout)` (lines 900-923, `airflow db check-migrations`) waits until the
  database's heads equal the code's. `downgrade` exists (line 1411).
- `upgrading.rst:23-25`: "you must run `airflow db migrate` … it's safe to run even if
  there are no migrations to perform".
- `upgrading.rst:33-43`: back up the database first. A broken connection can leave it
  "half-migrated".
- `upgrading.rst:45-49`: custom Docker deployments "usually need to run the DB migrate
  manually". The Helm chart uses a post-upgrade hook.
- `upgrading.rst:70-78`: offline SQL (`--show-sql-only`).
- `docker-stack-docs/entrypoint.rst:327-335`: `_AIRFLOW_DB_MIGRATE` lets "one-off init
  containers (such as `airflow-init`)" migrate and exit.

### 2. Our code

- **Schema:** `python/crawler/src/modama_crawler/store.py:62-157`, `ensure_tables`.
  - It runs `CREATE TABLE / INDEX IF NOT EXISTS` for `datasets`, `members`, `directories`,
    `records` and `crawl_runs`, in one transaction.
  - Its docstring: "There are no migrations: recreate the database after a change"
    (README line 96 says the same).
  - Advisory locks use the key space `(0x6D6F, n)`: `CRAWL_LOCK = (0x6D6F, 1)` and
    `STORE_LOCK = (0x6D6F, 2)` (lines 17-24).
- **Connection:** psycopg 3, synchronous (`psycopg[binary,pool]` in `pyproject.toml`; 3.3.7
  installed in the VM, 3.3.8 latest on PyPI, 2026-11-04). `serve` uses a `ConnectionPool`.
  Every command calls `ensure_tables` first:
  - `crawl`: `cli.py:269-270`;
  - `timer`: `cli.py:401-402`;
  - `runs`: `cli.py:453-454`;
  - `serve`: `cli.py:483-484`.
  - The timer also starts each crawl as a subprocess (`cli.py:391`, `412`), which calls it
    again.
- **Readers of the tables as an interface:** `python/search-chain` reads `datasets(anchor)`,
  `members(dataset_id, path)`, `records(identifier, datestamp, metadata)` and `crawl_runs`
  (`README.md:45`, `src/modama_chain/crawler.py:1, 67-110`). It checks
  `to_regclass('crawl_runs')` to work against older crawlers (`crawler.py:102`). The
  `subtree-crawl` design (D5) adds a column check for `scope` in the same way.
- **Tests:** the fixture `conn` is `ensure_tables(postgresql)` on a fresh `pytest-postgresql`
  database (`tests/conftest.py:44-47`). The server binaries come from the VM's
  `postgresql-17` package (README lines 27-39). The crawler's tests are not in
  `.github/workflows/ci.yml` (no crawler job there).
- **Deployment, search stack:**
  - `crawler.Dockerfile` installs the crawler editable with `[test]`.
  - `crawler` (`serve`, lines 69-100) and `crawl-timer` (lines 108-123) use the same image
    and environment (`*crawler-env`) and share `crawler-db` (`postgres:17`, `trust`,
    lines 125-139).
  - `crawl-timer` waits for `crawler` to be healthy, so compose never runs the two
    `ensure_tables` calls at the same moment.
  - `docker compose exec crawl-timer modama-crawler crawl` and the timer's nightly crawl do run
    it while `serve` runs. That is harmless today (no-ops), but a real `ALTER` in that path
    would run while the server is reading.
- **The staging database** was made fresh by commit 3251cad (findings, run 3:
  `./downstaging.sh --reset`). That commit's `ensure_tables` is identical to the `crawler`
  branch head's: the md5 of the function's text is the same, b421b57d…. So today's
  `ensure_tables` is the exact baseline of staging, unless someone changed that database by
  hand (not checkable from here).
- **The trigger:** `subtree-crawl` D5 (`openspec/changes/subtree-crawl/design.md:35, 51, 68`,
  in worktree `agent-a18be288e85128605`) adds
  `ALTER TABLE crawl_runs ADD COLUMN IF NOT EXISTS scope TEXT` to `ensure_tables`. Rollback:
  "the old crawler ignores the `scope` column".

### 3. Practice and tools

Releases were looked up on PyPI and on GitHub releases on 2026-11-12.

| Tool | Latest release | Licence | What it is | Lock against two runs | Downgrade |
|---|---|---|---|---|---|
| Alembic | 1.20.1, 2026-10-22 (1.20.0 2026-09-11, 1.19.2 2026-09-04) | MIT | Python; needs SQLAlchemy ≥ 2.0 (2.1.8, 2026-11-04, MIT) and Mako (1.4.3, 2026-09-22, MIT); models optional | none built in (see below) | `downgrade()` per revision |
| yoyo-migrations | 9.0.0, 2024-08-10 (8.2.0 2022-12) | Apache-2.0 | Python, SQL or Python steps, psycopg 3 supported (`postgresql+psycopg://`) | yes, table `yoyo_lock`, `break-lock` command | rollback steps |
| Sqitch | v1.6.1, 2026-01-06 | MIT | Perl; a plan file with dependencies, no numbering (README) | not checked | not checked |
| Flyway | 13.12.1, 2026-11-05 | Apache-2.0 (open-source edition; Redgate sells other editions, README) | Java | not checked | not checked |
| dbmate | v2.38.1, 2026-11-09 | MIT | Go single binary, plain SQL, a transaction per migration, `schema.sql` dump | `--migration-lock` (PostgreSQL only) | `rollback` |
| pgroll | v0.16.3, 2026-09-08 | Apache-2.0 | Go; zero downtime by expand/contract with views per schema version, PostgreSQL ≥ 14 | n/a (README: "no database locking") | reversible by design |
| Numbered SQL files + version table | — | — | in-house, as toolmeta-harvester does | `pg_advisory_xact_lock` | optional |
| pytest-alembic | 0.13.2, 2026-10-28 | MIT | tests for Alembic: `test_single_head_revision`, `test_upgrade`, `test_model_definitions_match_ddl`, `test_up_down_consistency` | — | — |

Points about Alembic:
- **It can work without models.** Upstream does exactly that (`env.py:46`, raw SQL in
  `op.execute`). SQLAlchemy is then only the connection layer.
  - It speaks psycopg 3 (`postgresql+psycopg://`, upstream's `env.py:33`).
  - It can also wrap a connection we open ourselves: `create_engine(...,
    creator=...)` (SQLAlchemy docs, `create_engine.params.creator`; the parameter exists in
    the 2.1 docs, its behaviour was not tried here).
  - Several commands can share one connection (Alembic cookbook, "Sharing a Connection across
    one or more programmatic migration commands").
- **Transactions:** on PostgreSQL, Alembic treats DDL as transactional
  (`ddl/postgresql.py:84`). By default all pending revisions run in one transaction
  (`transaction_per_migration=False`, `runtime/environment.py:421, 495`; checked in 1.18.4,
  the version in upstream's venv).
- **No built-in lock.** Asked whether concurrent upgrades are safe, the maintainer answered
  that there is "no built-in isolation" and recommended taking a lock in `env.py` before the
  migrations run (https://github.com/sqlalchemy/alembic/issues/633). I found no advisory lock
  in Alembic 1.18.4's source. Airflow adds its own (above).
- **`script_location` as a package resource** (`package:path`) works, but Alembic's own
  comment says "there seem to be zero tests for the package resource codepath"
  (`util/pyfiles.py:62`, 1.18.4). An absolute path computed from the package's `__file__` is
  the safer choice.

Practices, with what applies to us:
- **Who runs migrations.** The models seen here:
  - an explicit command (Airflow docs, upstream's warehouse README);
  - a one-shot init container that runs it on every start (upstream's `airflow-init`, our
    `warehouse-init`);
  - migrate-on-start inside each process, under a lock (toolmeta-harvester, and our
    `ensure_tables` today, without lock or version).
  - The init container keeps the migration in one process before anything else starts.
    Every `docker compose up` still applies it without a manual step.
- **A lock.** Every tool that expects concurrent starts takes one:
  - Airflow: `pg_advisory_lock`;
  - toolmeta-harvester: `pg_advisory_xact_lock`;
  - dbmate: `--migration-lock`;
  - yoyo: a lock table.
  - On top of that, DDL takes an `ACCESS EXCLUSIVE` lock on its table "unless explicitly
    noted" (PostgreSQL 17, ALTER TABLE). A migration that waits for that lock, for example
    behind a running crawl's transaction, queues every later reader behind it. A
    `lock_timeout` makes it fail instead of stalling `serve` (PostgreSQL 17,
    runtime-config-client: "Abort any statement that waits longer than the specified amount of
    time while attempting to acquire a lock"). Airflow sets one (`db.py:1641-1647`).
- **Cheap and expensive changes.** `ADD COLUMN` without a default, or with a non-volatile
  one, needs no table rewrite. A volatile default or a type change rewrites the table and its
  indexes (PostgreSQL 17, ALTER TABLE, Notes). At 1.45 million datasets and records on
  staging, that is the difference between milliseconds and minutes.
- **Expand/contract** (pgroll README, lines 172-180): first add what the new code needs while
  the old code keeps working, then remove the old parts in a later release, once nothing uses
  them.
  - We do not need pgroll's machinery: there is one writer, and a short pause of `serve` is
    acceptable, since harvesters retry on 503 (`Retry-After: 60`, README "Running the crawler", line 69).
  - The rule itself is what makes a rollback cheap. If the old image runs on the new schema,
    rolling back is just the old image, with no downgrade. `subtree-crawl`'s migration plan
    already argues this way.
- **Forward-only vs downgrade:**
  - Upstream writes and tests downgrades.
  - Airflow offers them but tells you to back up first.
  - For us, the recovery path is a `pg_dump` before migrating plus expand-only changes. A
    `downgrade()` is worth writing where it is one statement (`DROP COLUMN`), as upstream
    does, and is not required otherwise (question below).
- **Tests against an older database.**
  - Upstream tests its own baseline → head and one down/up step. Airflow can create a
    database through the migration files instead of the ORM (`initdb(use_migration_files=…)`,
    `db.py:835-845`), to check that both give the same schema. pytest-alembic packages the
    same checks.
  - None of them starts from a database made by the previous release, which is the case that
    breaks in production. That is the gap @weber's request names.

### 4. Recommendation for the crawler

**Tool.** Alembic, following upstream: raw SQL through `op.execute`, `target_metadata =
None`, readable revision ids `NNNN_name`, a linear chain. It adds `alembic`, `SQLAlchemy` and
`Mako` as dependencies, plus `typing-extensions` through SQLAlchemy (all MIT). The crawler's
own code keeps using psycopg directly. SQLAlchemy appears only inside the migration step.
- *Against:* three packages for five tables, and a second connection layer in a package that
  so far needs only psycopg.
- *The alternative:* numbered `.sql` files, a one-row version table and `(0x6D6F, 3)` as an
  advisory lock, in about 50 lines. It needs no dependency, but it has no `stamp`, no offline
  SQL, no downgrade convention and no test helpers. It is an invention where upstream uses a
  standard tool.

**Where.** `python/crawler/src/modama_crawler/migrations/`, holding `env.py`, `script.py.mako`
and `versions/0001_baseline.py`, … . It ships as package data so that the image has it.
Alembic's `Config` is built in code, with `script_location` as an absolute path from
`__file__` (not the package-resource form, see above). There is no `alembic.ini` to copy
around. Developers still get `alembic revision -m …` through a small `alembic.ini` in
`python/crawler/` that points at the same directory (optional).

**How it runs.**
- `modama-crawler migrate` (name to be settled):
  - connects with `conninfo_from_env()` and takes `pg_advisory_lock(0x6D6F, 3)` (a new
    `MIGRATE_LOCK`, next to the crawl and store locks);
  - sets a `lock_timeout` for its DDL, runs `upgrade head` in one transaction, and logs
    "from X to Y" or "up to date";
  - exits 0 or 1.
  - It is safe to run repeatedly, like `airflow db migrate`.
- In the search stack, a one-shot service `crawler-migrate`:
  - uses the image `search-stack-crawler` with `*crawler-env`, `command: modama-crawler
    migrate` and `restart: on-failure`;
  - `crawler` and `crawl-timer` get `depends_on: crawler-migrate: condition:
    service_completed_successfully`.
  - This is the pattern of upstream's `airflow-init` and our `warehouse-init`.
  - *Alternative:* `sh -c "modama-crawler migrate && exec modama-crawler serve"` in
    `crawler`. That saves a service, but it migrates on every restart of the server and
    mixes the two logs.
- The other commands (`crawl`, `timer`, `runs`, `serve`) replace `ensure_tables` with a
  check:
  - They read `alembic_version` with psycopg and compare it with the code's head (Alembic's
    `ScriptDirectory`).
  - Behind, or no version table: they exit with status 2 and a message such as
    `database schema is at 0001_baseline, this crawler needs 0002_crawl_runs_scope: run
    modama-crawler migrate`.
  - The behaviour when the database is newer than the code is a question below.
  - Like Airflow's `check-migrations`, but without waiting: compose already orders the start.
- For a developer's local database the step is one more line in the README: run `migrate`
  once before `crawl`.

**Baseline for the existing staging database.**
- `0001_baseline` contains today's `ensure_tables` statements unchanged: the code at e35e4b4,
  identical to 3251cad, which made staging, all with `IF NOT EXISTS`.
- On an empty database it creates the schema. On staging's it changes nothing, and Alembic
  then writes `alembic_version`. One path for both cases, no `stamp` step and no second copy
  of the schema.
- *Deviation from upstream:* upstream keeps the schema in its create SQL, uses an empty 0001
  and needs a `stamp` (`init-warehouse.sh:32-34` shows the conditional stamp it then
  requires). We have no separate create script, so folding it into 0001 avoids two sources of
  truth.
- *Risk:* `IF NOT EXISTS` hides a database that differs from the baseline. So once, before
  the first upgrade of staging:
  - `pg_dump --schema-only` of staging's `crawler-db`;
  - diff it against a fresh database migrated to `0001_baseline`.
- *Literal alternative:* an empty 0001 plus `stamp` when `alembic_version` is missing.

**`scope` as the first migration.** `0002_crawl_runs_scope`:
- `upgrade()`: `ALTER TABLE crawl_runs ADD COLUMN IF NOT EXISTS scope TEXT`, which is
  nullable with no default, so no rewrite.
- `downgrade()`: `ALTER TABLE crawl_runs DROP COLUMN scope`.
- The `IF NOT EXISTS` stays, so that the order of the two changes does not matter. If
  `subtree-crawl` ships first with D5's `ALTER` in `ensure_tables`, staging already has the
  column and 0002 is a no-op that records the revision. If migrations ship first,
  `subtree-crawl` adds 0002 instead of touching `ensure_tables`.
- From 0003 on, migrations are plain (no `IF NOT EXISTS`), so that a drifted database fails
  loudly.
- `modama-chain`'s column check (D5) stays: it must also read crawlers from before the
  change.

**Tests.**
1. `tests/conftest.py`'s `conn` migrates the fresh `pytest-postgresql` database to head
   through the migration code instead of `ensure_tables`. Every database test then runs on
   the migrated schema.
2. A test module `tests/test_migrations.py`:
   - **From the previous release:** `tests/migrations/` holds one SQL file per release, the
     schema as that release made it. The first is `0001_ensure_tables.sql`, the DDL of
     `ensure_tables` at e35e4b4, which is what made staging. Later ones come from
     `pg_dump --schema-only` at each release.
     - The test loads the latest file and inserts a few rows (a finished run, a dataset with
       a member, a record), then migrates to head.
     - It checks that the rows survive (`scope IS NULL` for the old run) and that the schema
       equals a freshly migrated one. It compares `information_schema.columns`, indexes and
       constraints, or `pg_dump --schema-only` output, since the server binaries are there.
   - **Single head:** the chain has exactly one head, as in pytest-alembic's
     `test_single_head_revision`.
   - **Up-down-up** for every revision that has a `downgrade()`, as upstream does for 0002.
3. **The suite on a migrated database:** an option (for example `--db-from=previous`)
   switches `conn` to build its database from the latest release file plus the migrations,
   and the whole suite runs on it. It belongs to the final acceptance tests, not to every
   run. pytest-alembic is not needed for this: the checks are a few lines each, and it would
   be one more dependency.
4. **Before staging (and later production):**
   - `pg_dump` staging's `crawler-db` into a scratch database and run `modama-crawler
     migrate` against it;
   - then `runs` and `modama-chain status` against it;
   - then the real upgrade, with the dump kept as the way back.
   - This is the "start testing it safely while we are running dev iterations" of the
     request.
5. The search stack's `./runtest.sh e2e` covers the fresh path through `crawler-migrate`.

**Requirement to record** (proposed wording for `python/crawler/design/requirements.md`; the
highest R number there is R40; not edited):

> - **R41 (must for production, @weber 2026-11-12)** A schema change reaches an existing
>   crawler database in place, without recreating it.
>   - Datasets, extractions, records with their datestamps and the run history are kept, so
>     a change costs no re-crawl, re-harvest or re-indexing (staging: about a night;
>     `field-tests/search-stack-staging-findings.md`).
>   - The change is applied by one explicit step before the crawler's services start, never
>     by two processes at once.
>   - A crawler refuses a database that is behind its code, naming that step.
>   - Example: staging's database, made by commit 3251cad, gains `crawl_runs.scope` with its
>     1.45 million records and their datestamps unchanged.
>   - Accepted when a database made by the previous release, migrated, passes the test
>     suite, and a copy of staging's database migrates before staging does.

**Follow-up changes, in the change that implements this:**
- README line 96 ("There are no schema migrations yet…");
- the `store.py` line in `AGENTS.md`'s code map;
- the search stack README and compose files;
- `BACKLOG.md`;
- an independent review of the migration code (AGENTS.md: code that changes data on its own
  gets one).

### Questions

- Alembic with SQLAlchemy and Mako as new dependencies, or the dependency-free version table?
- The command's name: `modama-crawler migrate`, or `db upgrade` / `db migrate` as in Airflow?
- A one-shot `crawler-migrate` service, or `migrate && serve` in `crawler`?
- A database newer than the code (an image rolled back): refuse, as Airflow and
  toolmeta-harvester do (a rollback then needs a downgrade or a restore), or warn and
  continue (that relies on every migration being expand-only)?
- Baseline: 0001 with today's `ensure_tables` under `IF NOT EXISTS`, or upstream's literal
  form, an empty 0001 plus `stamp`?
- Downgrades: required for every migration, written where trivial, or forward-only with a
  `pg_dump` before each upgrade?
- Which ships first, `subtree-crawl` with D5's `ALTER` in `ensure_tables`, or the migrations?
  0002 as proposed works in either order.
- The backup before migrating: part of `migrate`, or the operator's step (the production
  backlog's "Backups")?

### Not verified

- How EOSC applies Alembic to its production warehouse: no deploy repository I found
  documents it. `metadata-airflow`'s README covers only `airflow db migrate`.
- The actual schema of staging's `crawler-db`: I had no access. It is assumed equal to
  3251cad's `ensure_tables` because run 3 started with `--reset`.
- Alembic's lack of a lock and its transaction defaults were read in 1.18.4 (upstream's
  venv), not in 1.20.1.
- SQLAlchemy's `creator` parameter was only found in the docs, not tried.
- yoyo's maintenance beyond its release dates: its repository is not on GitHub and was not
  checked.
- Sqitch's and Flyway's lock and downgrade features: only their READMEs were read.
- The effort estimate (about a day) is a guess.
