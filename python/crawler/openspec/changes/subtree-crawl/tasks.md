# Tasks

The leans for 2.2 (file as PATH), 2.3 (from scratch) and 3.1 (`scope` in place) were agreed on 2026-11-12 (`design.md`, Decisions). D7 (request 2) is open; 4.2's procedure for an improved format waits for it. Added from the decisions: 6.1.

## 1. Before the code

- [ ] 1.1 Record the request of 2026-11-12 as R41 in `design/requirements.md` (fast turn-around when improving formats: a path or subtree from scratch, and a format everywhere, through to the search, without waiting for a whole crawl), and the decisions taken on the questions in the decision log. Verify: the diff, reviewed by @weber.

## 2. Subtree crawl

- [ ] 2.1 `walk()` starts at a directory below the root, with anchors, exclusions and per-path ignores relative to the root (D3). Verify: `test_walk.py`, a walk of `root` started at `adhoc/libertem/libertem-test-data` gives the same datasets under that path as a walk of the whole tree.
- [ ] 2.2 `crawl --path PATH`: normalise, refuse `..`, symlinks, excluded, collapsed and unlistable directories on the way with status 2 before a run is recorded; a file stands for its directory with an info line (D2). Verify: `test_cli.py`, one test per scenario of "A subtree crawl only covers what a full crawl enters" and "A file stands for its directory".
- [ ] 2.3 From scratch: no stored state and no stored extractions inside the subtree (D3). Verify: tests for "A changed extractor without a new version" (an extractor whose output is changed by a test switch, not by its version) and "The same code gives the same records".
- [ ] 2.4 The store restricted to the subtree: datasets, members and records under PATH, removed ones deleted by their identifiers, listings under PATH deleted, no rule set on the run (D4). Verify: `test_store.py` and `test_cli.py` for "Records outside the subtree stay as they are", "A deleted file in a subtree leaves the index", "The same identifiers as a full crawl", "The next full crawl takes over the extractions"; a path holding `%` and `_`.
- [ ] 2.5 Lock and SIGTERM (D6). Verify: `test_trigger.py`, "A subtree crawl while the timer's crawl runs" and "A subtree crawl stopped while it extracts".
- [ ] 2.6 `--root`'s help text: the data root, which a crawl treats as the whole tree. Verify: `modama-crawler crawl --help`, typed as documented.

## 3. Runs, timer, chain

- [ ] 3.1 `crawl_runs.scope` added with `ADD COLUMN IF NOT EXISTS`; `runs` prints it after the root; `last_finished()` counts full crawls only (D5). Verify: `test_cli.py` for "A subtree crawl records its path" and "A subtree crawl's line"; `test_trigger.py` for "A subtree crawl does not make the timer wait"; `ensure_tables` on a database made by the previous version adds the column.
- [ ] 3.2 Harvest after a subtree crawl. Verify: `test_trigger.py`, "A subtree crawl starts the harvest", against the stand-in Airflow.
- [ ] 3.3 `modama-chain`: T from full crawls only; the crawl line shows a subtree crawl's path; works without the column (D5). Verify: `python/search-chain` tests for "A subtree crawl does not move T" and a database without `scope`.

## 4. End to end and docs

- [ ] 4.1 The search stack's e2e test: after the first crawl and harvest, change a file under one path, run `crawl --path` on it in `crawl-timer`, and check that the next harvest brings exactly that record, which is replaced in OpenSearch, and that `modama-chain status` keeps T. Verify: `./runtest.sh e2e` in `/prototypes/search-stack/`, with the number of skipped tests.
- [ ] 4.2 `README.md` (running the crawler: `crawl --path`, and the procedure for an improved format, D7), `/prototypes/search-stack/README.md` (the commands with `--config`, in `crawl-timer`), `BACKLOG.md` (the "Not now" items that are kept), the runbook in `design/field-tests/` (no more `libertem.toml` for a quick run). Verify: the commands in the docs typed as shown, in the e2e stack.
- [ ] 4.3 Lint and tests as CI and the hook run them. Verify: `uvx ruff format --check --diff && uvx ruff check` from the repository root, `pytest` in `python/crawler` and `python/search-chain`, with the skipped tests counted.

## 5. Review

- [ ] 5.1 Review by an agent that did not write the code, given the code, this change's specs and `design/requirements.md` (the store deletes rows: AGENTS.md asks for a review of code that changes data on its own). Findings verified before acting, in `review.md`. Verify: `review.md` and the fixes' tests.

## 6. Notes from the decisions

- [ ] 6.1 `BACKLOG.md`: (a) the timer skips its night when a subtree crawl holds the lock: fix with a test before production (acceptable until the demo, 2026-11-17); (b) schema migrations are becoming a requirement (production needs them; start testing them in dev iterations; follow upstream's practice). Verify: the diff.

## Workflow follow-up

- On staging, after the review: `crawl --path adhoc/libertem/libertem-test-data` in `crawl-timer`, timed from the start to the indexed records (`modama-chain status`), as the first measurement of the turn-around.
- Archive after @weber's review, together with or after `em-formats-and-extraction` (its `extraction` spec is the base for D7).
