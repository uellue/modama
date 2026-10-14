# Agent instructions: modama crawler

`modama-crawler` exposes a file system tree (`MODAMA_DATA_ROOT`) as a data repository over OAI-PMH, with a PostgreSQL index. Python ≥ 3.14. For the rest of the repository, see the top-level `CLAUDE.md` and `README.md`.

## Development environment (devcontainer)

Development happens in the devcontainer defined in `/.devcontainer/`. Everything below assumes you run inside it.

- Python venv at `~/.venv`, already on `PATH`. `post-create.sh` installs this package editable with `[test]` extras, plus `ruff` and `pre-commit`.
- `pyxdg` and `oaipmh` are **local forks**, installed editable from sibling checkouts mounted at `/workspaces/pyxdg` and `/workspaces/oaipmh`. Behaviour of `xdg.Mime` and `oaipmh.datestamp` may differ from the PyPI releases. Changes to them belong in those repositories, not here.
- The compose service `db` (Postgres 17, trust auth, database `modama_crawler`) is for running the crawler and server by hand. The connection env vars (`POSTGRES_ADDRESS=db`, `MODAMA_DATA_ROOT=/data`, `OAI_BASE_URL=http://localhost:7654/oai`, …) are set in `.devcontainer/docker-compose.yml`. Because `python-dotenv` doesn't override variables that are already set, a `python/crawler/.env` file has no effect for those keys inside the container. `.env.example` documents the keys for use outside the devcontainer.
- `/data` is an initially empty named volume (`crawler-data`) to use as a data root.
- The PostgreSQL 17 server binaries are on `PATH` without a default cluster. The test suite uses them through `pytest-postgresql`, which spawns its own throwaway clusters, so tests never touch `db`.

## Commands

Run from `python/crawler/`:

```bash
pytest                                   # whole suite
pytest tests/test_server.py              # one file
pytest tests/test_server.py::test_name   # one test
pytest -k listrecords                    # by pattern
pytest tests/functional                  # end-to-end: crawl temp dir -> serve -> harvest
pytest --cov                             # coverage (config in setup.cfg)

python -m modama_crawler.server          # dev server, http://localhost:7654/oai (port forwarded)

# Lint/format (from repo root; same as CI and pre-commit)
uvx ruff format --check --diff && uvx ruff check
```

There is no crawl CLI yet. To populate the dev database by hand:

```python
import psycopg
from modama_crawler.database import PostgresConfig, ensure_dataset_tables, crawl_and_populate
from modama_crawler.recognition import FileHandler

FileHandler.install_mime_info()  # register handler MIME definitions (writes to XDG_DATA_HOME)
with psycopg.connect(PostgresConfig.from_env().connection_string()) as conn:
    ensure_dataset_tables(conn)
    print(crawl_and_populate(conn, root_path="/data"))
```

## Architecture

```
src/modama_crawler/
├── database.py     # PostgresConfig, schema, crawl pipeline
├── mime_sql.py     # bulk MIME classification in SQL -> datasets/mimes rows
├── recognition.py  # FileHandler registry and per-type metadata
├── repository.py   # RepositoryConfig, identifier <-> path conversion
└── server.py       # OAIFileDBBackend, OAIServer (verbs), create_app()
```

**Crawl pipeline** (`database.crawl_and_populate`):
1. `crawl_repository` uses `os.walk` (without following symlinks) to fill a TEMP table `crawl`. It stores `mtime` as `max(st_mtime, st_ctime)`.
2. `populate_files_from_crawl` copies the rows into `files`. It currently only does an initial population; incremental updates are a TODO.
3. `mime_sql.apply_mime_prefilter_with_resolution` runs next. It turns XDG shared-mime-info glob patterns into SQL `LIKE` filters to classify paths in bulk, and falls back to content sniffing (`pyxdg` `get_type2` plus `magika`) only for ambiguous candidates. This step writes `datasets`, `mimes` and `files_in_datasets`.

**Schema** (`ensure_dataset_tables`): `files(path_id, path UNIQUE, mtime)`, `datasets(dataset_id, path_id UNIQUE → files)`, `mimes(dataset_id, mime)`, `files_in_datasets(dataset_id, path_id)`. A dataset is anchored at one path and can include several member files.

**File handlers** (`recognition.py`):
- Each subclass of `FileHandler` registers itself for its `file_types` through `__init_subclass__`.
- `FileHandler.resolve()` reads the MIME types of the path from the DB, asks every candidate handler's `matches(root, path, guesses)` for a priority from 0 to 100 (or `None`), picks the highest, and falls back to `OctetStream`. It requires a DB connection.
- A handler can override:
  - `_find_all_members()` to define dataset membership (for example, `EMPAD` pairs an `.xml` with its `.raw`)
  - `xdg_mimeinfo()` to ship its own MIME definition, installed by `install_mime_info()`
  - the metadata getters `get_titles`, `get_creators`, `get_dates`, `get_descriptions`, `get_formats` and `get_resource_type`, plus `datacite()`

**Server** (`server.py`):
- `create_app(pool, repo_config=None, config=None)` is a Flask factory with one route, `/oai`, for GET and POST.
- `OAIFileDBBackend` does the DB queries and builds handlers. `OAIServer` renders the six verbs.
- Only `oai_dc` is supported. `server._make_metadata` maps the handler getters to DC fields.
- Resumption tokens are JSON and based on paths.
- `from`/`until` filter on dataset mtimes.
- Sets are not supported: `ListSets` returns `noSetHierarchy`. A list request that passes a `set` argument raises `ValueError` in the backend, and the endpoint turns that into `badArgument`.

**Configuration:**
- `PostgresConfig.from_env()` reads `MODAMA_CRAWLER_DB`, `POSTGRES_*`. In tests, use `PostgresConfig.from_conninfo(conn.info)`.
- `RepositoryConfig.from_env()` reads `OAI_BASE_URL`, `OAI_ADMIN_EMAIL`, `OAI_REPOSITORY_NAME`, `OAI_EARLIEST_DATESTAMP`, `BATCH_SIZE` (default 10) and `MODAMA_DATA_ROOT`.
- `MODAMA_DATA_ROOT` defaults to `/data`, the data root inside containers. The older `/storage/er-c-data` from bare-metal tests on one specific host is deprecated; don't reintroduce it.

## Conventions and gotchas

- PostgreSQL only: use `%s` placeholders and cursors with `row_factory=dict_row`.
- Server code gets connections from a `psycopg_pool.ConnectionPool` passed to `create_app` or `OAIFileDBBackend`. Read config through the `*Config.from_env()` classmethods, not `os.environ` directly.
- Paths: the DB stores **absolute** paths. OAI identifiers and API output use paths relative to the data root. Convert with `repository.get_identifier`, `path_from_identifier` and `sanitize`. `sanitize` rejects paths outside the root.
- `FileHandler._registry` is a global class registry. Defining a handler class (including in a test) registers it for the rest of the process.

## Tests

- `tests/conftest.py`:
  - A session-scoped autouse fixture points `XDG_DATA_HOME` at a temp dir and installs handler MIME info, with a `Canary` self-test handler. Tests never touch the real user MIME database.
  - `pg_unit_test`: empty DB connection.
  - `test_database` + `test_files`: schema plus 6 single-file datasets whose fixed mtimes span the 2024-06-01 to 2024-12-31 `from`/`until` boundaries. Tests depend on these dates.
  - `repo_config`, `backend_with_db`.
  - `running_http_server`: a real werkzeug server on a random port. `sickle_client` and `oaipmh_client` use it.
- `flask_client` is defined in `tests/test_server.py`.
- `tests/test_server_oaipmh.py` and `tests/test_server_scythe.py` check interoperability with third-party harvesting clients.
- `tests/functional/` is self-contained, with its own `conftest.py`. It builds realistic directory trees, runs the real crawl pipeline, and harvests with `oaipmh-scythe`.
- Responses are validated against the XSDs in `tests/schemas/`.
