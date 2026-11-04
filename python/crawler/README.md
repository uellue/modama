# modama-crawler

The crawler makes the ER-C data file system searchable. It walks the file tree, decides which files belong together as a dataset, and publishes one metadata record per dataset over [OAI-PMH](https://www.openarchives.org/OAI/openarchivesprotocol.html), the protocol that repository harvesters speak. The harvester we target is the [EOSC metadata-warehouse](https://github.com/EOSC-Data-Commons/metadata-warehouse). It collects the records, indexes them in OpenSearch and offers search on top. Both the crawler and the warehouse run inside the institute, alongside the other services in `deploy/`.

Status: alpha, on the `crawler` branch. The work goes in three steps: the OAI-PMH server (rewritten), dataset recognition (the core is rewritten; more dataset shapes follow), then metadata extraction per file format. `BACKLOG.md` says what is next and what is deferred.

## How it works

A crawl has three steps:

1. **Walk and recognise.** `walk()` goes through the tree once. In each directory the enabled *formats* look at the entries and claim the files they recognise. For example, the EMPAD format claims an XML header together with its raw file, and the Zarr format claims a whole Zarr store. Large uninteresting trees such as Python environments, `node_modules` or `.git` are *collapsed* into one dataset without being walked. Every file nobody claims becomes a single-file dataset of its MIME type. The output is a *recognition result*: a list of datasets with their members, format and the reason they were recognised. This step needs no database.
2. **Store.** `store.py` writes the result to PostgreSQL. A record's datestamp only moves when its content changes, so harvesters can fetch increments.
3. **Serve.** `server.py` answers OAI-PMH requests from the records table, in `oai_dc` (Dublin Core).

A record's identifier is the dataset's browse URL in the management interface, for example `https://er-c-data-mgmt.fz-juelich.de/browse/?path=/adhoc/livecalibration/generate.ipynb`. ELN entries link to the same URLs, so the quoting must match `python/mgmtinterface` byte for byte.

The Dublin Core mapping onto a file system is approximate. For example, the file owner goes into `dc:creator`, which does not mean authorship in the publishing sense. That is acceptable because nothing leaves the institute. `design/requirements.md` Q22 tracks what, if anything, may be passed on.

## Getting started

We develop in a Debian 13 VM made with [devvm](https://github.com/modama-rdm/devvm). The VM shares the host checkout at `/workspaces/data-management-system`, and its provisioning (`/.devvm/provision.sh`) installs Docker, `uv` and `pre-commit`. The same steps should work on any Debian 13 machine with those. Set up once:

```bash
sudo mkdir -p /etc/postgresql-common/createcluster.d
echo "create_main_cluster = false" | sudo tee /etc/postgresql-common/createcluster.d/no-main-cluster.conf
sudo apt-get install -y --no-install-recommends postgresql-17 postgresql-client-17 shared-mime-info
uv venv --python 3.14 ~/.venv
uv pip install --python ~/.venv/bin/python -e "/workspaces/data-management-system/python/crawler[test]"
# in ~/.bashrc:
export PATH="$HOME/.venv/bin:/usr/lib/postgresql/17/bin:$HOME/.local/bin:$PATH"
```

Why each step is there:

- Python 3.14 comes from `uv`, because Debian 13 ships 3.13.
- The PostgreSQL server binaries are needed without a running cluster. The tests start their own throwaway servers through `pytest-postgresql`.
- `shared-mime-info` provides `update-mime-database`. The crawler uses it to build its own MIME database at startup.

Then, from `python/crawler/`:

```bash
pytest                                  # the whole suite, under a minute
modama-crawler records tests/           # the records a crawl of this directory would publish, no database
modama-crawler records --verbose PATH   # the same, with why each dataset was recognised, as XML comments
```

`records` is the quickest way to see what the crawler makes of a directory. Use it on real data to check a format, without setting up a database or server.

To run the full chain (crawl, OAI-PMH server, harvester, warehouse and search), use the end-to-end stack in `/prototypes/crawler-e2e/`. Its README explains it, including an SSH tunnel for opening the search front end from your laptop.

## Running the crawler

```bash
modama-crawler crawl [--root PATH]      # crawl MODAMA_DATA_ROOT (or PATH) into the database
modama-crawler serve                    # OAI-PMH on port 7654
```

Settings come from the environment or from `python/crawler/.env`. `.env.example` lists the keys: data root, database, PostgreSQL connection, the base URL reported to harvesters, and `OAI_BIND`. `OAI_BIND` is the address `serve` listens on. It defaults to `localhost`; use `0.0.0.0` inside a container.

A TOML file passed with `--config` chooses the formats and the exclusions:

```toml
[formats]
select = ["ALL"]
ignore = ["empad"]                      # ids: "collection", "collection/format" or "ALL"

[formats.per-path-ignores]
"instruments/old/" = ["zarr"]          # gitignore syntax, as below

[crawl]
exclude = ["scratch/", "!scratch/keep/"]   # gitignore syntax
```

Select and ignore work as in ruff: the more specific id wins, and on a tie ignore wins. If nothing is selected, everything installed is enabled.

There are no schema migrations yet. After a schema change, drop and recreate the database.

## Adding a file format

Formats are grouped into *collections* under `src/modama_crawler/formats/` (`core`, `collapse`, `zarr`, `empad`). Each collection brings its own MIME definitions, recognisers and test fixtures. `formats/TEMPLATE.md` describes how to write one. The EMPAD collection is the most complete example of a multi-file format. Its fixture generator writes synthetic files, so no real data has to be committed.

When choosing a MIME type, use an existing one if possible. Look at freedesktop.org, Debian's package list, or reader libraries such as LiberTEM and HyperSpy. Otherwise use an unofficial `application/x.…` type, never a misleading generic one.

## Tests

- `tests/` covers the OAI-PMH protocol (including real client libraries: `sickle`, `oaipmh`, and `oaipmh-scythe`, which the EOSC harvester uses), the walk, the format runner, selection, MIME detection, rendering, records and the CLI. Responses are validated against the OAI-PMH XSDs. Matching the spec and working with real clients turned out to be different things, so we test both.
- Each collection's `tests/` holds fixture trees and their expected recognition results, run by the pytest plugin in `testing.py`. After an intended change, re-record the expectations with `pytest --regen-expected <collection dir>` and review the diff before committing.
- `pytest --cov` reports coverage.
- Lint and format run from the repository root, as CI and the commit hook do: `uvx ruff format --check --diff && uvx ruff check`.

The recognition result is the oracle throughout: what the fixture tests compare, what `store.py` writes, and what `records` prints.

## Pitfalls

- The checking order of shared-mime-info only sniffs file content when file names tie. A type with only magic rules is therefore never detected for a file whose name matches another type's glob. That is why EMPAD's `empad.xml` registers `*.xml` too: it forces the content check.
- The MIME database is built from the enabled collections only. Nothing from the host's MIME database is used.
- Symlinks, special files and unreadable files are skipped with an info line and get no record.
- The crawler doesn't publish deletions yet (`deletedRecord=no`).

## Where to read more

| | |
|---|---|
| `design/architecture.md` | the design decisions and their reasons; the decision log at the end is authoritative |
| `design/requirements.md` | requirements (R\*) and open questions (Q\*) |
| `openspec/specs/` | the behaviour contract: requirements with scenarios, one directory per capability |
| `openspec/changes/` | changes in progress, and archived ones under `archive/` |
| `BACKLOG.md` | what is next and what is deferred |
| `design/testing.md`, `design/playtest.md`, `design/review.md` | the test strategy, the play test on real data, the code review of 2026-11-03 |
| `AGENTS.md` | instructions for AI coding agents |
| `/docs/working-with-claude.md` | how we work with Claude Code on this project, and what we learned |

## How we work

- **Keep it small.** Make it work at ER-C first. Every option or mechanism should answer a requirement, a spec scenario or a decision. Add generality when a second concrete case appears, not before. Prefer small modules with a narrow interface.
- **Use libraries.** Before writing something an established library already does, look for the library. Name every new dependency in the change.
- **Specs with changes.** Larger changes go through [OpenSpec](https://openspec.dev) as a trial: a proposal, design, delta specs and tasks under `openspec/changes/<name>/`, archived into `openspec/specs/` once verified. Small fixes don't need one. `design/` remains the place for the reasoning, and the specs must not contradict it.
- **Update everything together.** A change of behaviour updates the spec scenario, the tests, the docs and the backlog in the same commit.
- **Proof-of-concept code** is being replaced. Don't take its structure as a model.

## Licence

The crawler is under the MIT licence (`LICENSE`). `src/modama_crawler/formats/core/` vendors `freedesktop.org.xml` from shared-mime-info, which is under GPL-2.0-or-later (`LICENSE.freedesktop.org.xml` beside it).
