# Agent instructions: modama crawler

`modama-crawler` exposes a file system tree (`MODAMA_DATA_ROOT`) as a data repository over OAI-PMH, with a PostgreSQL index. Python ≥ 3.14. For the rest of the repository, see the top-level `CLAUDE.md` and `README.md`.

## Goal and status

**Goal:** make the ER-C scientific data file system searchable through the [EOSC metadata-warehouse](https://github.com/EOSC-Data-Commons/metadata-warehouse), which harvests OAI-PMH endpoints. A local snapshot of it is in `prototypes/EOSC-Data-Commons/`.

**Status:** the code started as a proof of concept with poor architecture and is being rewritten. The order of work:
1. Clean up the OAI-PMH server and the tests. Done: `records.py`, `server.py` and their tests are new.
2. Recognise datasets in the messy file tree. Done as change `recognition-core`: the walk, the format runner, four collections, the records oracle; reviewed 2026-11-03 (`design/review.md`), archived 2026-11-04 (`openspec/changes/archive/2026-11-04-recognition-core/`), its requirements now in `openspec/specs/`. Next: series directories.
3. Extract metadata per file format.

Don't copy the proof-of-concept code's style or structure, and don't preserve it for its own sake.

**Principles:** YAGNI. Make it work at ER-C first. Keep changes tight and simple, and add generality only when a concrete need appears.

**Standing rules for agents** (from the review of 2026-11-03, `design/review.md`; the reasons are in `/docs/working-with-claude.md`):
- Every mechanism, option, parameter or output detail names the requirement, spec scenario or decision-log row that asks for it. Without one, leave it out and suggest it as a next step; do not polish output or add generality on your own.
- Before writing something an established library implements (argument parsing, pattern matching, serialisation, a protocol), search for the library. A common one replaces custom code by default; a niche one is proposed for discussion; every new dependency is flagged.
- Prefer small modules with a tight, stable interface over one clever function; no abstraction without a second concrete user.
- Report evidence, not claims: the command and its output, the screenshot, the diff of a re-recorded expectation.
- Changes to behaviour update the spec scenario, the test, AGENTS.md and the backlog in the same change.
- Report "clean" or "passing" only from the command that CI or the commit hook runs (`uvx ruff …` from the repo root, `pre-commit run`, the e2e stack's `./e2e.sh test`), not from a similar command run elsewhere.
- A change of more than a few hundred lines gets a review by an agent that did not write it, given the code and the requirements, not the author's conclusions; findings are verified before they are acted on (`design/review.md` is the pattern).

**Decisions so far:**
- **Scale:** petabytes and millions of files. Change is mostly additions, roughly hundreds to thousands of files per day.
- **Datasets:** a dataset is a single file or a collection, for example header + data file(s), a Zarr directory, or a large "boring" tree such as `node_modules` or a Python environment that is collapsed into one dataset. One OAI-PMH record per dataset.
- **Access:** whatever the crawling process can read is exposed. No per-user access checks for now.
- **Landing page:** the browse URL is the resource identifier, for example `https://er-c-data-mgmt.fz-juelich.de/browse/?path=/adhoc/livecalibration/generate.ipynb`. The path is relative to the data root with a leading `/`. It must be quoted exactly like `quote_path` in `python/mgmtinterface` (`quote_plus(path, safe="!$'()*,/:;?@")`), because ELN entries match these URLs byte for byte.
- **Mapping:** DC and OAI-PMH concepts are mapped approximately onto a file system. For example, the file owner goes into `dc:creator`, which doesn't mean authorship in the publishing sense. The service is internal to the institute, and so is the metadata warehouse that harvests it (decided 2026-11-04, deployed alongside the other services in `deploy/`), so user names in metadata are fine. Whether anything is passed on beyond the institute is Q22.
- **Interoperability:** besides validating against the XSDs, the main verbs are tested with real clients: `sickle`, `oaipmh` (eth-library), and `oaipmh-scythe`, which the EOSC harvester uses. In practice, matching the spec and working with real clients are not the same thing.
- **Format:** `oai_dc` only. DataCite officially requires a registered DOI, and the warehouse converts `oai_dc` to DataCite itself.
- **Independence:** the crawler stays independent of the other modama services for now.
- **Deferred work** is tracked in `BACKLOG.md`.

## OpenSpec (trial)

Changes to the crawler go through [OpenSpec](https://openspec.dev) as a trial, starting with the dataset-recognition spike: `openspec/specs/` holds the behaviour contract (requirements with scenarios), `openspec/changes/<name>/` a proposal, design, delta specs and tasks per change, archived after verification. The `/opsx:*` slash commands and their skills live in `.claude/` here and are regenerated by `openspec update`. `design/` stays the rationale and decision log; specs must not contradict it. Small fixes don't need a change.

## Development environment (devvm VM)

Development happens in a Debian 13 VM made with https://github.com/modama-rdm/devvm (the devcontainer in `/.devcontainer/` is retired, kept for reference). The VM shares the host checkout at `/workspaces/data-management-system` and the `pyxdg` fork at `/workspaces/pyxdg` (virtiofs) and has Docker; everything else is set up inside the VM, once:

```bash
# uv, as a user tool: release binary from https://github.com/astral-sh/uv/releases into ~/.local/bin
sudo mkdir -p /etc/postgresql-common/createcluster.d
echo "create_main_cluster = false" | sudo tee /etc/postgresql-common/createcluster.d/no-main-cluster.conf
sudo apt-get install -y --no-install-recommends postgresql-17 postgresql-client-17 shared-mime-info
uv venv --python 3.14 ~/.venv
uv pip install --python ~/.venv/bin/python -e /workspaces/pyxdg -e "/workspaces/data-management-system/python/crawler[test]"
uv tool install pre-commit          # the repository's commit hook calls it
sudo apt-get install -y nodejs npm && npm install -g --prefix ~/.local @fission-ai/openspec   # the openspec CLI for /opsx:*
# in ~/.bashrc:
export PATH="$HOME/.venv/bin:/usr/lib/postgresql/17/bin:$HOME/.local/bin:$PATH"
```

- Python 3.14 comes from `uv` (Debian 13 has 3.13). The package is installed editable with `[test]` extras.
- `pyxdg` is a **local fork** with https://gitlab.freedesktop.org/xdg/pyxdg/-/merge_requests/18, installed editable from the sibling checkout. Changes to it belong in that repository. The commit is on https://gitlab.freedesktop.org/uellue/pyxdg (branch `subprocess`), not on the GitHub mirror; images install it from there.
- The PostgreSQL 17 server binaries are on `PATH` without a default cluster. The test suite uses them through `pytest-postgresql`, which spawns its own throwaway clusters.
- There is no development database, `/data` volume or real-data mount in the VM. For running the crawler, server, harvester and warehouse together, use the end-to-end stack in `/prototypes/crawler-e2e/` (`README.md` there): its `crawler` container has `/data`, a `crawler-db` and `OAI_BIND=0.0.0.0`. Outside a container, `.env.example` documents the keys; `python-dotenv` reads `python/crawler/.env`.
- The terminal check (`tools/xterm-shots.py`) needs xvfb, xterm, xdotool and imagemagick, which the VM does not have yet.
- Claude Code: sessions and memory are in `~/.claude/projects/-workspaces-data-management-system/` of the VM user. Back them up with `/.devcontainer/backup-claude-home.sh` (into the gitignored `.claude/home-backup/`, without the login credential; needs `rsync`) before discarding the VM, and restore with `cp -a .claude/home-backup/projects/-workspaces-data-management-system ~/.claude/projects/`. Plugins: `claude plugin marketplace add uellue/skills && claude plugin install kaizen@uellue --scope user`.

## Commands

Run from `python/crawler/`:

```bash
pytest                                      # whole suite, including every collection's fixtures
pytest tests/test_walk.py                   # one file
pytest src/modama_crawler/formats/empad     # one collection
pytest --regen-expected src/modama_crawler/formats/empad   # re-record its fixture results, then review the diff
pytest --cov                                # coverage (config in setup.cfg)

modama-crawler records [PATH] [--verbose] [--from D] [--until D] [--select ID] [--ignore ID]
                                            # the oracle: ListRecords for a path, no database; --verbose embeds diagnostics as XML comments
modama-crawler crawl [--root PATH]          # crawl MODAMA_DATA_ROOT (or PATH) into the database
modama-crawler serve                        # OAI-PMH endpoint on port 7654, listening on OAI_BIND (default localhost)

# Lint/format from the repo root, as CI and the pre-commit hook run it
uvx ruff format --check --diff && uvx ruff check
```

## Architecture

```
src/modama_crawler/
├── cli.py          # crawl, serve, records; the only place that reads the environment
├── walk.py         # post-order walk with pre-order collapse check -> Result
├── formats/        # Entry, Directory, Dataset, Result, Format, Collection; the runner (run_pre, run_post)
│   ├── TEMPLATE.md # how to write a collection
│   ├── core/       # vendored freedesktop.org.xml (GPL-2.0-or-later, see its LICENSE file) + er-c.xml curation (ties that force content checks)
│   ├── collapse/   # environments, .git, __pycache__, .ipynb_checkpoints, node_modules: collapsed pre-order
│   ├── zarr/       # Zarr v2 and v3 stores, collapsed pre-order; nested stores belong to the outer one
│   └── empad/      # XML header + raw pair; empad.xml rules, Empad recognizer, cheat fixture generator
├── mime.py         # MIME type of one file per the shared-mime-info checking order; ties -> common ancestor
├── mimedb.py       # builds the per-deployment MIME database from the enabled collections only
├── selection.py    # entry-point discovery, ruff-style select/ignore, per-path ignores, crawl excludes
├── records.py      # OAI identifier, browse URL, Dublin Core mapping of a Dataset
├── render.py       # oai_dc XML, shared by the server and the records command
├── store.py        # PostgreSQL schema (datasets, members, records) and storing a Result
├── server.py       # OAI-PMH WSGI app (werkzeug), reads the records table only
└── testing.py      # pytest plugin: fixtures, manifest, expected results, coverage rule
```

The pipeline is a function from a tree to a **recognition result** (`walk()` → `Result` of `Dataset`s with type, anchor, members, parts, format, basis, warnings, parent, collapsed), which runs without PostgreSQL. The result is the oracle for fixture tests, what `store.py` writes, and what `records.py`/`render.py` turn into `oai_dc`. See `design/architecture.md` for the decisions; `openspec/specs/` for the behaviour contract once the first change is archived.

**Walk** (`walk.py`): symlinks, special files, unreadable files and unlistable directories are skipped with an info line and get no record (an unreadable root is an error). Per directory, a pre-order call with names and sizes (a collapse format may return a collapsed dataset, and nothing below is visited), then the subdirectories, then classification of files with `mime.py`, then a post-order call with entries, types and the subdirectories' parentless datasets. Formats run by priority then id; claims are exclusive; a format may claim its own directory's files and adopt child datasets (`parts`), which get it as `parent`; everything unclaimed becomes a single-file dataset of its MIME type. Every format call has a byte budget, enforced, and a time limit checked after the call (a result over it is discarded); a failing format is a warning, not a crash. Results are sorted, so the walk is independent of listing order.

**Records** (`records.py`): identifier `oai:er-c-data-mgmt.fz-juelich.de:<quoted anchor path>` (shortened to 255 characters with a hash suffix if longer), `dc:identifier` is the browse URL, `dc:relation` links a collection to its parts and a part to its parent. In the database the datestamp moves only when a record's content changes; the `records` command uses the newest member mtime instead.

**Configuration** (`cli.py --config file.toml`): `[formats] select = [...]`, `ignore = [...]` (ids `collection`, `collection/format` or `ALL`; more specific wins, ignore wins ties; nothing selected means everything installed; unknown ids are errors; comma lists as in ruff; a collection id also switches its MIME definitions), `[formats.per-path-ignores] "pattern" = [ids]`, `[crawl] exclude = [patterns]` (gitignore semantics through `pathspec`: a slash anchors, `dir/` matches directories only, `!` negates, last match wins). Environment: `MODAMA_DATA_ROOT`, `MODAMA_CRAWLER_DB`, `POSTGRES_*`, `OAI_BASE_URL`, `OAI_ADMIN_EMAIL`, `OAI_BIND` (address `serve` listens on, default `localhost`; `0.0.0.0` inside a container).

## Gotchas

- There are no schema migrations: `store.ensure_tables` only creates missing tables. After a schema change, recreate the dev database, for example `dropdb -h db -U postgres modama_crawler && createdb -h db -U postgres modama_crawler`.
- The MIME database is built into a temporary directory at startup from the enabled collections; nothing from the host is used, and detection without an active database raises. `update-mime-database` (package shared-mime-info) must be installed.
- A format type with only magic rules is never detected for files whose name matches another type's glob: the checking order sniffs only when names tie. EMPAD's `empad.xml` therefore claims `*.xml` too, to force the content check.
- Output meant for people (the `records` command) is checked by eye in a real terminal, not only by parsing text: `tools/xterm-shots.py` starts an xterm under a virtual X server, sends keys and takes screenshots (needs xvfb, xterm, xdotool, imagemagick; not yet in the VM); an agent reads the PNGs. See `design/playtest.md`, visual check.
- Collection test modules are importable packages (`src/.../tests/__init__.py`); the plugin finds the collection from the test module's package.

## Tests

- `tests/conftest.py`: `conn` (a fresh `pytest-postgresql` database with the schema), `records`/`add_record` (five records with fixed datestamps on the `from`/`until` boundaries, page size 2 makes three pages), `server`, `oai` (werkzeug test client plus XSD validation), `validate_oai`, `base_url` (real HTTP for the client libraries). The plugin's session fixture `mime_database` builds the MIME database of all installed collections; it is autouse here. A collection's own tests run with its definitions plus the core's only.
- `test_server.py`, `test_clients.py` (sickle, oaipmh-scythe, oaipmh): the OAI-PMH protocol and interoperability, unchanged by recognition.
- `test_formats.py` (the runner on synthetic directories), `test_walk.py` (the walk on temporary trees), `test_selection.py`, `test_mimedb.py`, `test_mime.py` (the checking order, one test per spec scenario), `test_render.py`, `test_records.py` (identifiers, Dublin Core, store, and the walk-to-store-to-harvest path), `test_cli.py` (the `records` command as a subprocess, output validated against the XSDs; one run through the `modama-crawler` script), `test_testing.py` (the plugin's own checks on a throwaway collection, via `pytester`).
- Each collection's `tests/`: fixtures and expected results run by the plugin (`testing.py`); see `formats/TEMPLATE.md`.
