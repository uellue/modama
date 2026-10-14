# Agent instructions: modama crawler

`modama-crawler` exposes a file system tree (`MODAMA_DATA_ROOT`) as a data repository over OAI-PMH, with a PostgreSQL index. Python ≥ 3.14. For the rest of the repository, see the top-level `CLAUDE.md` and `README.md`.

## Goal and status

**Goal:** make the ER-C scientific data file system searchable through the [EOSC metadata-warehouse](https://github.com/EOSC-Data-Commons/metadata-warehouse), which harvests OAI-PMH endpoints. A local snapshot of it is in `prototypes/EOSC-Data-Commons/`.

**Status:** the code started as a proof of concept with poor architecture and is being rewritten. The order of work:
1. Clean up the OAI-PMH server and the tests. Done: `records.py`, `server.py` and their tests are new.
2. Recognise datasets in the messy file tree. MIME detection (`mime.py`) is new; one dataset per regular file and `recognition.py` are still the proof of concept.
3. Extract metadata per file format.

Don't copy the proof-of-concept code's style or structure, and don't preserve it for its own sake.

**Principles:** YAGNI. Make it work at ER-C first. Keep changes tight and simple, and add generality only when a concrete need appears.

**Decisions so far:**
- **Scale:** petabytes and millions of files. Change is mostly additions, roughly hundreds to thousands of files per day.
- **Datasets:** a dataset is a single file or a collection, for example header + data file(s), a Zarr directory, or a large "boring" tree such as `node_modules` or a Python environment that is collapsed into one dataset. One OAI-PMH record per dataset.
- **Access:** whatever the crawling process can read is exposed. No per-user access checks for now.
- **Landing page:** the browse URL is the resource identifier, for example `https://er-c-data-mgmt.fz-juelich.de/browse/?path=/adhoc/livecalibration/generate.ipynb`. The path is relative to the data root with a leading `/`. It must be quoted exactly like `quote_path` in `python/mgmtinterface` (`quote_plus(path, safe="!$'()*,/:;?@")`), because ELN entries match these URLs byte for byte.
- **Mapping:** DC and OAI-PMH concepts are mapped approximately onto a file system. For example, the file owner goes into `dc:creator`, which doesn't mean authorship in the publishing sense. The service is internal to the institute, so user names in metadata are fine.
- **Interoperability:** besides validating against the XSDs, the main verbs are tested with real clients: `sickle`, `oaipmh` (eth-library), and `oaipmh-scythe`, which the EOSC harvester uses. In practice, matching the spec and working with real clients are not the same thing.
- **Format:** `oai_dc` only. DataCite officially requires a registered DOI, and the warehouse converts `oai_dc` to DataCite itself.
- **Independence:** the crawler stays independent of the other modama services for now.
- **Deferred work** is tracked in `BACKLOG.md`.

## Development environment (devcontainer)

Development happens in the devcontainer defined in `/.devcontainer/`. Everything below assumes you run inside it.

- Python venv at `~/.venv`, already on `PATH`. `post-create.sh` installs this package editable with `[test]` extras, plus `ruff` and `pre-commit`.
- `pyxdg` is a **local fork** with https://gitlab.freedesktop.org/xdg/pyxdg/-/merge_requests/18, installed editable from a sibling checkout mounted at `/workspaces/pyxdg`. Changes to it belong in that repository.
- The compose service `db` (Postgres 17, trust auth, database `modama_crawler`) is for running the crawler and server by hand. The connection env vars (`POSTGRES_ADDRESS=db`, `MODAMA_DATA_ROOT=/data`, `OAI_BASE_URL=http://localhost:7654/oai`, …) are set in `.devcontainer/docker-compose.yml`. Because `python-dotenv` doesn't override variables that are already set, a `python/crawler/.env` file has no effect for those keys inside the container. `.env.example` documents the keys for use outside the devcontainer.
- `/data` is an initially empty named volume (`crawler-data`) to use as a data root.
- The PostgreSQL 17 server binaries are on `PATH` without a default cluster. The test suite uses them through `pytest-postgresql`, which spawns its own throwaway clusters, so tests never touch `db`.

## Commands

Run from `python/crawler/`:

```bash
pytest                                 # whole suite
pytest tests/test_server.py            # one file
pytest tests/test_server.py::test_post # one test
pytest -k paging                       # by pattern
pytest --cov                           # coverage (config in setup.cfg)

python -m modama_crawler crawl         # crawl MODAMA_DATA_ROOT and publish records
python -m modama_crawler serve         # OAI-PMH endpoint, http://localhost:7654/oai (port forwarded)

# Lint/format from the repo root. CI and pre-commit run the same with uvx;
# in the devcontainer, ruff is in the venv.
ruff format --check --diff && ruff check
```

## Architecture

```
src/modama_crawler/
├── __main__.py     # command line: crawl, serve; the only place that reads the environment
├── database.py     # schema and crawl pipeline
├── mime.py         # MIME type of a file per the shared-mime-info checking order
├── recognition.py  # FileHandler registry for dataset types (step 2: rework)
├── records.py      # OAI identifiers, browse URLs, Dublin Core mapping, publishing records
└── server.py       # OAI-PMH WSGI app (werkzeug)
```

Data flows from the file system to `files`, then to `datasets`, then to `records`, which is all the server reads. The server never touches the file system.

**Records** (`records.py`):
- `publish_records` builds the Dublin Core metadata and the identifier of every dataset, and upserts them into `records(dataset_id, identifier, datestamp, metadata)`.
- The **datestamp** is the time the record last changed (identifier or metadata differ), truncated to seconds. It is not the file mtime: harvesters ask for records changed since their last run, and a file copied with an old mtime must still show up. Records are committed in batches to keep the gap between datestamp and commit short.
- **Identifiers** are `oai:er-c-data-mgmt.fz-juelich.de:<path>`, with the path quoted like in the browse URL but with `:` escaped. The EOSC harvester keeps only the part after the last `:` and stores it as `VARCHAR(255)`, so local parts of 255 characters or more are shortened to exactly 255: a prefix, `~` and hex digits of the path's SHA-256.

**Server** (`server.py`):
- `OAIServer(pool, base_url, admin_email, page_size=100)` is the WSGI app. It answers GET and POST on any path.
- `parse_arguments` validates verb and arguments; `OAIError` carries the OAI-PMH error code.
- Lists are paged by keyset over `(datestamp, dataset_id)`. The resumption token is `from,until,last datestamp,last dataset_id` in epoch seconds. `from`/`until` accept day and seconds granularity and are inclusive.
- `oai_dc` only, no sets, `deletedRecord=no`.

**Crawl pipeline** (`database.crawl_and_populate`, to be reworked in step 2):
1. `crawl_repository` walks the tree with `os.walk` (not following symlinks) into a TEMP table `crawl`, with `max(st_mtime, st_ctime)` and the owner's uid. Names that aren't valid UTF-8 are skipped with a warning.
2. `populate_files_from_crawl` updates `files`. Deleted files cascade to their datasets and records. New and changed files get their MIME type from `mime.detect`, and every regular file gets a dataset.
3. `publish_records` updates `records`.

**MIME detection** (`mime.py`) follows the "recommended checking order" of the [shared-mime-info spec](https://specifications.freedesktop.org/shared-mime-info/latest/ar01s02.html), using pyxdg's parsed `globs2` and `magic` databases:
- Globs match the file name only, case-insensitively unless flagged `cs`. Among matches, keep the biggest weight, then the longest pattern; a single remaining type is the result.
- Otherwise read the first `Mime.magic.maxlen` bytes (about 18 KB) and sniff. Without glob matches, the magic result wins, else `text/plain` or `application/octet-stream`. With conflicting globs, the candidate that equals the magic result or is a subclass of it wins; failing that (not in the spec), the candidate whose own magic matches, highest priority first.
- pyxdg's `get_type2()` is not used: it skips the longest-pattern rule, and `MagicDB.match_data(possible=...)` checks the lowest priority first.
- Cost: about 10 µs per file with a decisive name, about 5 ms per sniffed file (pure-Python magic) plus reading.

**Configuration** (environment variables, see `.env.example`): `MODAMA_DATA_ROOT` (default `/data`, the data root inside containers; the older `/storage/er-c-data` from bare-metal tests on one specific host is deprecated), `MODAMA_CRAWLER_DB`, `POSTGRES_*`, `OAI_BASE_URL`, `OAI_ADMIN_EMAIL`.

## Gotchas

- There are no schema migrations: `ensure_dataset_tables` only creates missing tables. After a schema change, recreate the dev database, for example `dropdb -h db -U postgres modama_crawler && createdb -h db -U postgres modama_crawler`.
- `FileHandler.install_mime_info()` writes the handlers' MIME definitions to `XDG_DATA_HOME`; the `crawl` command calls it.
- `FileHandler._registry` is a global class registry. Defining a handler class (including in a test) registers it for the rest of the process.

## Tests

- `tests/conftest.py`:
  - A session-scoped autouse fixture points `XDG_DATA_HOME` at a temp dir and installs handler MIME info, with a `Canary` self-test handler.
  - `conn`: a fresh `pytest-postgresql` database with the schema.
  - `records`: five records with fixed datestamps, inserted directly through `add_record`. Their datestamps sit on the `from`/`until` boundaries the tests use, and with page size 2 they make three pages.
  - `server`: an `OAIServer` with page size 2.
  - `oai`: sends a request through the werkzeug test client, validates the response against the XSDs in `tests/schemas/`, and returns the parsed document.
  - `base_url`: the server over real HTTP, for the client libraries.
- `test_server.py`: protocol behaviour, including a table of error cases.
- `test_clients.py`: the main verbs with `sickle`, `oaipmh-scythe` (used by the EOSC harvester) and `oaipmh`, one adapter per library.
- `test_records.py`: identifiers, browse URLs and datestamp behaviour.
- `test_crawl.py`: crawl a temporary tree and serve it.
- `test_mime.py`: MIME detection, one case per rule of the checking order.
- `test_recognition.py`: internals of the current dataset recognition; to be reworked in step 2.
