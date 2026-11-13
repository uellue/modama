# modama-crawler

The crawler makes the ER-C data file system searchable. It walks the file tree, decides which files belong together as a dataset, and publishes one metadata record per dataset over [OAI-PMH](https://www.openarchives.org/OAI/openarchivesprotocol.html), the protocol that repository harvesters speak. The harvester we target is the [EOSC metadata-warehouse](https://github.com/EOSC-Data-Commons/metadata-warehouse). It collects the records, indexes them in OpenSearch and offers search on top. Both the crawler and the warehouse run inside the institute, alongside the other services in `deploy/`.

Status: alpha, on the `crawler` branch. The work goes in three steps: the OAI-PMH server (rewritten), dataset recognition (the core is rewritten; more dataset shapes follow), then metadata extraction per file format. `BACKLOG.md` says what is next and what is deferred.

## How it works

A crawl has four steps:

1. **Walk and recognise.** `walk()` goes through the tree once. In each directory the enabled *formats* look at the entries and claim the files they recognise. For example, the EMPAD format claims an XML header together with its raw file, and the Zarr format claims a whole Zarr store. Large uninteresting trees such as Python environments, `node_modules` or `.git` are *collapsed* into one dataset without being walked. Every file nobody claims becomes a single-file dataset of its MIME type. A format may also read a file's first bytes and say it is not of the type its name gave it (a text file named `notes.gtg` is no Gatan tag file): the file then gets the type it has without that name rule, for the formats after it and as a single file, and the reason goes into its dataset's basis; a type from the file's content is kept, with a warning (spec `recognition`). The output is a *recognition result*: a list of datasets with their members, format and the reason they were recognised. This step needs no database. A crawl lists every directory, but a directory whose listing (names, types, sizes, owners, times), and those of all directories below it, are unchanged since the last crawl under the same rules keeps its stored datasets: none of its files is read again. The rules include the versions of the crawler and of the packages that provide the formats. A directory whose recognition met a read error or a format's time limit is recognised again next crawl; one the crawler cannot list stays unchanged while it stays unlistable.
2. **Extract.** `extraction.py` runs the extractor of each dataset's format, if it has one, in worker processes with a time limit per dataset and a memory budget per process. A successful extraction is reused while the extractor, the dataset's files and the *extractor identity* are the same. The identity is a digest of the installation, computed at the start of every crawl (`identity.py`): the Python version, the name and version of every installed distribution, and the source of the packages that provide formats, of those installed from a path or a repository, and of any package imported from outside site-packages (a checkout on `PYTHONPATH`). Nobody sets it: a changed reader, an upgraded RosettaSciIO or a reverted experiment reaches the index with the next crawl, which extracts every dataset again. Settings (the memory and time limits, the number of processes) are not part of it. A failure is never reused: every crawl tries it again, whatever its cause, so a setting that fixes a failure brings its datasets back by the next crawl. A failure leaves the dataset with a basic description and the crawl with a warning. Each crawl also extracts a random sample of what it reuses again, 20 datasets per format, and reports any that differ from what is stored (the *spot check*, `spot check (seed …): em/dm4 20 of 20 as stored`); a new result replaces the stored one. The report says per format how many datasets were extracted again for a new identity, what changed (`rosettasciio 0.15.0 -> 0.16.0`, `source of modama_formats_em.dm changed`) and how many results changed; `runs` shows the identity and these counts, and prints a note on standard error when stored datasets carry another identity than the installed one, with what the next crawl will extract again. Before storing, NUL characters and lone surrogates in an extractor's result become U+FFFD, strings are cut to 4096 characters and lists to 1000 entries; a result that still cannot be stored (NaN) becomes the dataset's extraction error.
3. **Store.** `store.py` writes the result to PostgreSQL. The datasets stay there from crawl to crawl, for the next crawl to take over. A record's datestamp only moves when its content changes, so harvesters can fetch increments.
4. **Serve.** `server.py` answers OAI-PMH requests from the records table, in `oai_dc` (Dublin Core).

Every record has a first `dc:description`, the summary, on one line: the extracted values first, if any, then the type's name from the MIME database, the number of files, their size and the folder, for example `Plain text document, 1 file, 1.2 kB, in notes/`. A record whose format keeps the file's own tags (`values["original_metadata"]`: DM3, DM4, K2IS, block files, Merlin, EMPAD) has a second `dc:description` with them, one `name: value` per line, sorted by name, empty values left out, for example `Acquisition.Device.Active Size (pixels): [1920, 1792]` (decision 234; the harvester's conversion joins the lines with spaces). A record with extracted metadata also has a `dc:subject` for the format's display name (for example `Gatan Digital Micrograph (DM4)`: the format's `display_name`, else its MIME type's name, else its id) and for each term the extractor gives (technique, instrument).

A record's identifier is the dataset's browse URL in the management interface, for example `https://er-c-data-mgmt.fz-juelich.de/browse/?path=/adhoc/livecalibration/generate.ipynb`. ELN entries link to the same URLs, so the quoting must match `python/mgmtinterface` byte for byte.

The Dublin Core mapping onto a file system is approximate. For example, the file owner goes into `dc:creator`, which does not mean authorship in the publishing sense. The creator is the owner's full name from the user database (the GECOS field up to its first comma, which sssd fills from the directory's `cn`), else the login name, else the uid as a number. That is acceptable because nothing leaves the institute. `design/requirements.md` Q22 tracks what, if anything, may be passed on.

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

To run the full chain (crawl, OAI-PMH server, harvester, warehouse and search), use the search stack in `/prototypes/search-stack/`, our own composition of the warehouse's images and the crawler. Its README explains it, including an SSH tunnel for opening the search API and Airflow from your laptop.

## Running the crawler

```bash
modama-crawler migrate                  # bring the database's schema to this crawler's; once for a new database
modama-crawler crawl [--root PATH]      # crawl MODAMA_DATA_ROOT (or PATH) into the database
modama-crawler runs [--follow]          # the last ten crawls, newest first; --follow: the running one until it ends
modama-crawler timer --at 19:00         # crawl every day at 19:00 UTC, and at once if the last finished crawl is over a day old
modama-crawler serve                    # OAI-PMH on port 7654
modama-crawler cpu-budget               # the crawl's worker processes and threads on this machine, and why
```

**Warning:** `crawl --root PATH` treats PATH as the whole repository. Pointed at a subfolder of a crawled tree, it changes the identifiers and deletes every other record from the crawler's database (the files are untouched; a full crawl brings them back). Crawl a subfolder only into a database of its own, until `crawl --path` (change `subtree-crawl`, `BACKLOG.md` "Next") lands.

With `MODAMA_CRAWLER_AIRFLOW_URL` set (and `MODAMA_CRAWLER_AIRFLOW_USER`, `MODAMA_CRAWLER_AIRFLOW_PASSWORD`, an Airflow account allowed to start DAG runs), every finished crawl starts the EOSC warehouse's harvest of its own endpoint (`OAI_BASE_URL`), after its records are committed; also an unchanged crawl, so that a harvest covers it and the search's freshness time moves on. If the harvest cannot be started, the crawl still counts as finished, and the command exits with status 3. On SIGTERM (`docker stop`) a crawl records its run as failed and exits with 143; the timer passes SIGTERM on to its running crawl. `/prototypes/search-stack/` runs both, the timer and the trigger.

At its end a crawl logs its extraction counts and stores them with its run, for example `extraction: 2 run, 0 reused, 1 failed; 12 directories unchanged; time per format: em/dm 3.2 s`. Extraction uses `MODAMA_CRAWLER_EXTRACT_WORKERS` processes, by default the CPUs the crawler may use up to 8, each with an address space of `MODAMA_CRAWLER_EXTRACT_MEMORY` MiB, by default 4096 (a worker with RosettaSciIO loaded maps about 140 MiB), and replaced after 100 datasets; `records` extracts too, without reusing anything.

The CPUs the crawler may use are those of its affinity (a cpuset included), and no more than its cgroup v2 CPU quota, rounded up (a container started with `--cpus 4` counts 4); not the machine's CPU count, and `PYTHON_CPU_COUNT` has no effect. The worker processes start with `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` at 1, so that a reader that loads numpy starts no thread pool of its own; otherwise OpenBLAS starts one thread per CPU in every worker, and their buffers count against the address space (R43). Before the walk, `crawl` and `records` log the budget on stderr, for example `CPU budget: 8 worker processes, 1 math thread each; 8 CPUs usable (affinity 8, no quota)`, or `set by MODAMA_CRAWLER_EXTRACT_WORKERS`; `records --verbose` does not. `modama-crawler cpu-budget` prints the same line with its inputs, without crawling. How the crawler's budget fits with the search stack's services: `/prototypes/search-stack/README.md`, "CPU budget".

The walk keeps many file system requests in flight, which is what makes it fast on NFS: listings, stats, reads and format calls run in `MODAMA_CRAWLER_WALK_THREADS` threads (default 32; 1 does one thing at a time), and the magic matching of files without a decisive name runs in `MODAMA_CRAWLER_EXTRACT_WORKERS` processes, started when first needed (the same number as extraction's, which comes after the walk; `MODAMA_CRAWLER_EXTRACT_MEMORY` limits only the extraction processes). The result does not depend on either number.

Every crawl is recorded as a run in the database before it starts walking, so that a crawl shows up while it runs. While walking it logs `N directories, M files so far` on stderr and updates its run once a minute. `runs` prints one line per run: start, state, end (or the last update), counts (for a finished run also the extraction counts) and root; a failed run ends with its error. Only one crawl runs at a time: a second one exits with status 1 and `another crawl is running on this database`; a crashed crawler leaves no lock behind. With `SSSD_CHECK_USER` set (a uid that must exist, or `uid:gid`; the search stack sets it, as for sssd's health check), a crawl looks it up before it writes its records, and when the user database does not know it, the name service is down: the crawl stores nothing, so that owners' names do not turn into numbers, logs `the user database does not know SSSD_CHECK_USER 10001: sssd is not answering (check …)`, records its run as failed and exits with status 1. A value that is not a uid exits with status 2 before the run is recorded. While a crawl writes its records, which is the last step and takes seconds to minutes, `serve` answers with HTTP 503 and `Retry-After: 60`, so that a harvester comes back after the commit instead of missing the records. The states are `finished`, `failed`, `running`, and `stale` for a run without an end that has not been updated for two minutes (killed, or the machine went down). `runs --follow` exits with status 1 if the run it follows turns stale.

```
2026-11-05T08:38:43Z  failed    2026-11-05T08:38:43Z  0 directories, 0 files  /srv/gone  [Errno 2] No such file or directory: '/srv/gone'
2026-11-05T08:38:42Z  finished  2026-11-05T08:38:42Z  2 directories, 3 files, 3 datasets, 0 warnings, 0 records changed; extraction: 0 run, 0 reused, 0 failed; 2 directories unchanged  /srv/data
```

Where an item went between the tree and a search hit, and how fresh the search is, is the job of `modama-chain` (`/python/search-chain/`), which reads the crawler's `crawl_runs`, `records`, `datasets` and `members` tables.

Settings come from the environment or from `python/crawler/.env`. `.env.example` lists the keys: data root, database, PostgreSQL connection, the base URL reported to harvesters, and `OAI_BIND`. `OAI_BIND` is the address `serve` listens on. It defaults to `localhost`; use `0.0.0.0` inside a container.

A TOML file passed with `--config` chooses the formats and the exclusions:

```toml
[formats]
select = ["ALL"]
ignore = ["em/empad"]                   # ids: "collection", "collection/format" or "ALL"

[formats.per-path-ignores]
"instruments/old/" = ["zarr"]          # gitignore syntax, as below

[crawl]
exclude = ["scratch/", "!scratch/keep/"]   # gitignore syntax
```

Select and ignore work as in ruff: the more specific id wins, and on a tie ignore wins. If nothing is selected, everything installed is enabled.

## The database schema

The schema of the crawler's database is changed by migrations, so that a change reaches an existing database with its datasets, extractions, records, datestamps and run history (R42). We use [Alembic](https://alembic.sqlalchemy.org/), as the EOSC metadata warehouse does. The migrations are in `src/modama_crawler/migrations/versions/`, one file per revision, named after its id. `0001_baseline` creates the tables as the crawler made them before there were migrations, so a database made then is taken over as it is.

`modama-crawler migrate` is the only command that changes the schema. It applies the missing revisions in one transaction and exits:

```
INFO Running upgrade  -> 0001_baseline, baseline: the tables as the crawler made them before migrations
INFO Running upgrade 0001_baseline -> 0002_extractor_identity, extractor identity: reuse by a digest of the installation, failures never reused
INFO schema migrated from none to 0002_extractor_identity
```

Run again, it says `INFO schema up to date at 0002_extractor_identity` at once, also while a crawl runs. On a database made before migrations it first says `INFO tables made before migrations found: adopted as 0001_baseline`. The search stack runs it as the service `crawler-migrate` before `crawler` and `crawl-timer` start. `crawl`, `runs`, `timer` and `serve` only check the version, and exit with status 2 when it does not fit. What you see, and what to do:

| You see | Step |
|---|---|
| `ERROR the database has no schema version, this crawler needs 0002_extractor_identity: run modama-crawler migrate` | `modama-crawler migrate` |
| `ERROR the database schema is at 0001_baseline, this crawler needs 0002_…: run modama-crawler migrate` | `modama-crawler migrate` |
| `ERROR the database schema is at 0002_…, which this crawler does not know: a newer crawler migrated it; use that crawler, or downgrade with it first (README)` | the newer crawler, or its downgrade ("Upgrade" below) |
| `INFO waiting for the crawl lock (a crawl or another migration holds it)`, from `migrate` | wait until the crawl ends, then it migrates; Ctrl-C ends the wait and changes nothing |
| `ERROR migration 0002_… failed, the database is unchanged at 0001_baseline: …`, exit status 1 | the database's error follows the colon; nothing was changed. Ending in `another transaction held a table for more than 10 s: run migrate again`: run `migrate` again. Otherwise, report the error to the developers |
| `ERROR migration 0001_baseline failed, the database is unchanged at none: the existing tables lack directories.retry or have them with another type: they were made by a crawler older than e35e4b4; recreate the database (README)` | a development database made before e35e4b4 cannot be taken over: drop it, create it empty, `migrate`, crawl again |
| `NotImplementedError: no downgrade from 0001_baseline: start from an empty database and crawl again (README, Upgrade)`, from `alembic downgrade` | an empty database and a crawl ("Upgrade" below); nothing was changed |

A migration that has something to do holds the crawl lock, so it never runs during a crawl or next to another migration: a crawl started meanwhile exits with `another crawl is running on this database`.

### Upgrade

Upgrade the code and run `migrate`. In the search stack, `/prototypes/search-stack/README.md`, section "Upgrade", has the commands.

Every revision has a `downgrade()`. Where the older code reads the result correctly, it undoes the revision; otherwise it refuses with the message above and changes nothing. A downgrade needs the newer code, so run it before going back to the older one, with Alembic's command line and this directory's `alembic.ini`; from the repository root:

```bash
alembic -c python/crawler/alembic.ini current           # the database's version; takes no lock
alembic -c python/crawler/alembic.ini downgrade 0001_baseline
```

Alembic's command line reads the connection as the crawler does, from the environment or `python/crawler/.env`.

Where a downgrade refuses, or the database is damaged, the way back is an empty database and a crawl: everything in it is made again from the data tree (@weber, 2026-11-12). Keep what shows the failure first, so that it can become a test case (in the search stack, `docker compose ps -a` and `docker compose logs`). Then drop the database and create it empty (`dropdb`, `createdb`; in the search stack, `./downtest.sh --reset` empties all its stores), run `migrate` with the code you go back to, and crawl. In the search stack, the harvest and the indexing that follow take as long as a first full run. A dump taken before the upgrade (`pg_dump -Fc`) is not needed; whoever has one can restore it into the empty database instead of crawling.

### Adding a migration

A schema change is a new revision, never an edit of a revision that has shipped (a database that has run it would not run it again), and never DDL in `store.py`. From `python/crawler/`:

```bash
alembic revision -m "crawl_runs scope" --rev-id 0003_crawl_runs_scope
```

This writes `src/modama_crawler/migrations/versions/0003_crawl_runs_scope.py`. The id has at most 32 characters (Alembic's `version_num` column; a test checks it). Then:

- Write `upgrade()` with Alembic's operations (`op.add_column("crawl_runs", sa.Column("scope", sa.Text()))`) or `op.execute` with SQL text, whichever fits. There are no models.
- No `IF NOT EXISTS` after `0002`: on a database that drifted from the chain, a migration should fail loudly.
- Write `downgrade()` to undo `upgrade()` where the older code then reads the database correctly. Otherwise keep the generated body, which refuses and points to an empty database and a crawl. Think of the rows, not only the columns: dropping a column that tells two kinds of rows apart makes the older code misread them, so delete those rows first or refuse.
- Set `HEAD` in `src/modama_crawler/schema.py` to the new id. `tests/test_migrations.py` fails until you do.
- `uvx ruff format` and `uvx ruff check --fix` on the new file, from the repository root.

The tests build every database by the migrations, so `pytest` runs the new one. `tests/test_migrations.py` also checks that each `downgrade()` either undoes its revision or refuses.

## Adding a file format

Formats are grouped into *collections*: the crawler's own under `src/modama_crawler/formats/` (`core`, `collapse`, `zarr`), others in packages of their own that register an entry point, such as `em` in `/python/modama-formats-em/` (EMPAD, Digital Micrograph, Merlin). Each collection brings its own MIME definitions, recognisers and test fixtures. `formats/TEMPLATE.md` describes how to write one. The `em` collection is the most complete example of multi-file formats with metadata extraction.

When choosing a MIME type, use an existing one if possible. Look at freedesktop.org, Debian's package list, or reader libraries such as LiberTEM and HyperSpy. Otherwise use an unofficial `application/x.…` type, never a misleading generic one.

## Tests

- `tests/` covers the OAI-PMH protocol (including real client libraries: `sickle`, `oaipmh`, and `oaipmh-scythe`, which the EOSC harvester uses), the walk, the format runner, selection, MIME detection, rendering, records, the CLI and the schema migrations (`test_migrations.py`, with a database made before migrations from `tests/migrations/before_migrations.sql`). Responses are validated against the OAI-PMH XSDs. Matching the spec and working with real clients turned out to be different things, so we test both.
- Each collection's `tests/` holds fixture trees and their expected recognition results, run by the pytest plugin in `testing.py`. After an intended change, re-record the expectations with `pytest --regen-expected <collection dir>` and review the diff before committing.
- `pytest --cov` reports coverage.
- Lint and format run from the repository root, as CI and the commit hook do: `uvx ruff format --check --diff && uvx ruff check`.

The recognition result is the oracle throughout: what the fixture tests compare, what `store.py` writes, and what `records` prints.

## Pitfalls

- The checking order of shared-mime-info only sniffs file content when file names tie. A type with only magic rules is therefore never detected for a file whose name matches another type's glob. That is why EMPAD's `empad.xml` (in `modama-formats-em`) registers `*.xml` too: it forces the content check.
- The MIME database is built from the enabled collections only. Nothing from the host's MIME database is used.
- Symlinks, special files and unreadable files are skipped with an info line and get no record.
- The crawler doesn't publish deletions yet (`deletedRecord=no`).
- Stale bytecode runs under a new identity: Python checks a `.pyc` by the source's size and its mtime in whole seconds, so an edit of the same size within the same second keeps the old code while the identity changes. Keep `__pycache__` out of images (the `.dockerignore` files of the build contexts) and restart the interpreter after such an edit.
- Read file contents unbuffered (`open(path, "rb", buffering=0)`), as `mime.py` and `Directory.read` do. A buffered open reads a whole buffer for a few bytes: 128 KiB in Python 3.14, or the block size the file system reports, 1 MiB on our NFS (field-test finding F12). `tests/conftest.py` has a `bytes_read` fixture to check it. The exception is a library that reads in many tiny pieces and seeks between them (RosettaSciIO's DM reader walks the tag tree a few bytes at a time), where unbuffered means a system call per piece: give it a buffer of NFS's read size, 64 KiB, with readahead off (`posix_fadvise` with `POSIX_FADV_RANDOM`), as `modama_formats_em.dm.parsed` does (finding F14).

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
| `design/requirements-pipeline.md`, `design/walkthroughs/` | the chain crawler → harvester → warehouse → search: requirements, walk-throughs, wishlist for upstream |
| `/python/search-chain/` | `modama-chain`: trace a path through the chain, freshness time T |

## How we work

- **Keep it small.** Make it work at ER-C first. Every option or mechanism should answer a requirement, a spec scenario or a decision. Add generality when a second concrete case appears, not before. Prefer small modules with a narrow interface.
- **Use libraries.** Before writing something an established library already does, look for the library. Name every new dependency in the change.
- **Specs with changes.** Larger changes go through [OpenSpec](https://openspec.dev) as a trial: a proposal, design, delta specs and tasks under `openspec/changes/<name>/`, archived into `openspec/specs/` once verified. Small fixes don't need one. `design/` remains the place for the reasoning, and the specs must not contradict it.
- **Update everything together.** A change of behaviour updates the spec scenario, the tests, the docs and the backlog in the same commit.
- **Proof-of-concept code** is being replaced. Don't take its structure as a model.

## Licence

The crawler is under the MIT licence (`LICENSE`). `src/modama_crawler/formats/core/` vendors `freedesktop.org.xml` from shared-mime-info, which is under GPL-2.0-or-later (`LICENSE.freedesktop.org.xml` beside it).
