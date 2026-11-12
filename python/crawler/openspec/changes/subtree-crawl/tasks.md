# Tasks

The leans for 2.2 (file as PATH), 2.3 (from scratch) and 3.1 (`scope` in place) were agreed on 2026-11-12 (`design.md`, Decisions). D7 (request 2) is open; 4.2's procedure for an improved format waits for it. Added from the decisions: 6.1. The review of the proposal (`review.md`) is folded in with its leans (@weber, 2026-11-12); the proposal's questions (rules other than the deployment's, reverting an experiment) are open, and 2.2 and 4.2 follow their answers. The subtree crawl's own scenarios get a new test module, `tests/test_subtree.py`; the others go where their capability is tested today.

## 1. Before the code

- [ ] 1.1 Record the request of 2026-11-12 as R41 in `design/requirements.md` (fast turn-around when improving formats: a path or subtree from scratch, and a format everywhere, through to the search, without waiting for a whole crawl), and the decisions taken on the questions, including the answers to the review's findings, in the decision log. Verify: the diff, reviewed by @weber.

## 2. Subtree crawl

- [ ] 2.1 `walk()` starts at a directory below the root, with anchors, exclusions and per-path ignores relative to the root (D3); its start directory raises when it cannot be listed, as the root does (D3, review H2). Verify: `test_walk.py`, a walk of `root` started at `adhoc/libertem/libertem-test-data` gives the same datasets under that path as a walk of the whole tree; `test_subtree.py` for "The path cannot be listed when the walk reaches it" (listing made to fail after the checks, by a hook in the test).
- [ ] 2.2 `crawl --path PATH`: normalise (leading and trailing `/`, `..` inside the root), and refuse with status 2 before a run is recorded: `..` out of the root, the data root itself, a path that is not UTF-8, a path not found (naming the data root), symlinks, excluded and unlistable directories on the way and PATH itself, collapsed directories above PATH (formats after per-path ignores), and a data root other than the last full crawl's; a collapsed PATH is crawled; a file stands for its directory with an info line (D2). Verify: `test_subtree.py`, one test per scenario of "A subtree crawl's path is a canonical path", "A subtree crawl only covers what a full crawl enters", "A subtree crawl's path lies below the data root" and "A subtree crawl uses the data root of the full crawls".
- [ ] 2.3 From scratch: no stored state and no stored extractions inside the subtree (D3). Verify: `test_subtree.py` for "A changed extractor without a new version" (an extractor whose output is changed by a test switch, not by its version) and "The same code gives the same records".
- [ ] 2.4 The store restricted to the subtree: datasets, members and records under P (`directory = P OR starts_with(directory, P || '/')`, the same for `directories.path`), removed ones deleted by their identifiers, listings under P deleted, no rule set on the run (D4). Verify: `test_subtree.py` for "Records outside the subtree stay as they are", "A sibling with the same prefix stays" (with `b_` and `b%`), "A deleted file in a subtree leaves the index", "The same identifiers as a full crawl", "The next full crawl takes over the extractions".
- [ ] 2.5 Lock and SIGTERM (D6). Verify: `test_locks.py` for "A subtree crawl while the timer's crawl runs", `test_trigger.py` for "A subtree crawl stopped while it extracts".
- [ ] 2.6 `--root`'s help text: the data root, which a crawl treats as the whole tree, and to which `--path` is relative. Verify: `modama-crawler crawl --help`, typed as documented.

## 3. Runs, timer, chain

- [ ] 3.1 `crawl_runs.scope`, holding P with its leading `/` (D5). If the change `schema-migrations` has shipped: the column as migration 0002 there, and `ensure_tables` untouched. Otherwise: `ALTER TABLE crawl_runs ADD COLUMN IF NOT EXISTS scope TEXT` in `ensure_tables`, run only when `information_schema.columns` lacks the column, and the docstring corrected (review L2). `runs` prints the path after the root without the leading `/`; `last_finished()` counts full crawls only. Verify: `test_runs.py` for "A subtree crawl records its path" and "A subtree crawl's line"; `test_trigger.py` for "A subtree crawl does not make the timer wait"; the column added to a database made by the previous version (by the migration, or by `ensure_tables`), and a second `ensure_tables` issues no `ALTER`.
- [ ] 3.2 Harvest after a subtree crawl. Verify: `test_trigger.py`, "A subtree crawl starts the harvest", against the stand-in Airflow.
- [ ] 3.3 `modama-chain`: T from full crawls only; the crawl line shows a subtree crawl's path; works without the column (D5). Verify: `python/search-chain` tests for "A subtree crawl does not move T" and a database without `scope`.

## 4. End to end and docs

- [ ] 4.1 The search stack's e2e test: after the first crawl and harvest, change a file under one path, run `docker compose run --rm crawl-timer modama-crawler … crawl --path` on it, and check that the next harvest brings exactly that record, which is replaced in OpenSearch, and that `modama-chain status` keeps T. Verify: `./runtest.sh e2e` in `/prototypes/search-stack/`, with the number of skipped tests.
- [ ] 4.2 `README.md` (running the crawler: `crawl --path`; the procedure for an improved format, D7; while the extractor's identity is open, that `crawl --path` on the same path after reverting an experiment brings the old descriptions back, D3; the rollback step for subtree runs, Migration Plan), `/prototypes/search-stack/README.md` (the development loop: `docker compose build crawler`, then `docker compose run --rm crawl-timer modama-crawler --config … crawl --path …`, which leaves the timer running; that the search shows the result after one harvest only when no harvest is running, D6), `BACKLOG.md` (the "Not now" items that are kept), the runbook in `design/field-tests/` and the header of `docker-compose.staging.yml` (no more exclusions or `libertem.toml` for a first crawl of a subtree). Verify: the commands in the docs typed as shown, in the e2e stack; for `docker compose run --rm`: the timer container is not recreated (its start time in `docker compose ps` unchanged), and a `docker kill -s TERM` of the one-off container records the run as `failed` (review M8).
- [ ] 4.3 Lint and tests as CI and the hook run them. Verify: `uvx ruff format --check --diff && uvx ruff check` from the repository root, `pytest` in `python/crawler` and `python/search-chain`, with the skipped tests counted.

## 5. Review

- [ ] 5.1 Review by an agent that did not write the code, given the code, this change's specs and `design/requirements.md` (the store deletes rows: AGENTS.md asks for a review of code that changes data on its own). Findings verified before acting, in `review.md` after the review of the proposal. Verify: `review.md` and the fixes' tests.

## 6. Notes from the decisions

- [ ] 6.1 `BACKLOG.md`: the timer skips its night when a subtree crawl holds the lock: fix with a test before production (acceptable until the demo, 2026-11-17). Schema migrations, formerly item (b) here, have the change `schema-migrations`. Verify: the diff.

## Workflow follow-up

- On staging, after the review: `docker compose run --rm crawl-timer modama-crawler --config /stagingconf/full.toml crawl --path adhoc/libertem/libertem-test-data`, timed from the start to the indexed records (`modama-chain status`), as the first measurement of the turn-around. Before it, check in Airflow that no `warehouse_harvest_and_index` run is active, and say so with the time (D6).
- Archive after @weber's review, and after `em-formats-and-extraction`: this change's `extraction` delta modifies requirements that that change adds, and `openspec archive` refuses it before (its `extraction` spec is also the base for D7). With `schema-migrations`, either order works (D5).
