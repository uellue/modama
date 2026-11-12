# Tasks

Written with the coordinator's leans of 2026-11-12 as assumptions (design D1 to D15); a review finding or an answer of @weber changes the task named with it. Every spec scenario is cited by the task that tests it.

## 1. Requirements

- [ ] 1.1 Scenario D in `design/requirements-pipeline.md` 2.1 with @weber's two requests verbatim. Verify: `git diff` shows it; the proposal's quotes match.

## 2. Crawler

- [ ] 2.1 `walk(…, top=…)` in `walk.py` (D5). Verify: `tests/test_walk.py`, one test per scenario of "A subtree is recognised as in the crawl of the whole tree" (The same datasets as the whole crawl, on the core's `mixed` fixture and the EM fixtures; A folder inside a collapsed tree, with the `bytes_read` fixture; An excluded folder); the crawler's whole suite passes.

## 3. modama-chain

- [ ] 3.1 `live.py` (D4): JSON of the dataset holding a path, its extraction and record, computed by the crawler's code. Verify: a test on a copy of the EM collection's EMPAD fixture and a plain text file; "An edited description" with a temporary `records`-like module is not practical, so the test checks that two requests run in two processes (their pids) and the spec scenario is checked by hand in the stack (task 5.3).
- [ ] 3.2 The runner of live computations (D3). Verify: tests of "A computation over the limit" and "A newer request" with a child that sleeps (its process group gone, by `os.killpg(pgid, 0)` raising).
- [ ] 3.3 `upstream.py` (D7 to D10), `views.py`, additions to `crawler.py` (the stored dataset, a collapsed ancestor, the record's metadata) and `warehouse.py` (the index document, the search hits, the repository code). Verify: unit tests of each view's assembly with the record of task 3.1's fixtures: DataCite has the title and creator; the index document validates against the schema and has the description; the emulated hit's fields; the matchmaker entry's fields (truncation at 300, five subjects, the date format).
- [ ] 3.4 `browse.py` (D11, D12, D14) and `cli.py`. Verify: tests of "A folder with tens of thousands of files", "A link to a file", "Going up", "A symlink out of the tree", "An absolute path", "A cross-site form" with werkzeug's test client; the Host check.
- [ ] 3.5 Snapshots (D13). Verify: "Save for Claude" with a temporary folder and a temporary git repository; the credential check with fake passwords in the environment.
- [ ] 3.6 README of `modama-chain` (`browse`, "What it reads" extended), `pyproject.toml` (extra `browse`). Verify: read against the spec.

## 4. Search stack

- [ ] 4.1 `browse.Dockerfile`, the service `browse` in `docker-compose.yml`, `docker-compose.override.yml` (port 7655, the test tree, a volume for snapshots), `docker-compose.staging.yml` (port 17655, `STAGING_USER`, the data tree, the crawl's TOML, the snapshot folder); `runtest.sh` (the service runs, its page answers). Verify: `docker compose config` of the test deployment and of staging (with a fake `staging.env`); `./uptest.sh --build && ./runtest.sh`.
- [ ] 4.2 `test_e2e.py`: the browser's views of `DISTINCT_FILE` and the EMPAD header (the live `<record>` equals the server's; the live index document equals the stored one apart from `emb`; the emulated hit's computed fields equal the real hit's; the DataCite equals the stored harvest event's), and a path outside the tree refused. Verify: `./runtest.sh e2e` passes, with the number of skips.
- [ ] 4.3 README "Looking around" (the browser, the tunnel), the staging runbook (build, start with `--no-deps`, the snapshot folder, the tunnel and URL). Verify: the commands run in the VM's test stack as written, with the test stack's names.

## 5. Checks by eye and hand

- [ ] 5.1 Screenshots of the page with a headless browser (or the xterm tool), in the VM's stack: a folder, a file's views, the matchmaker entry next to matchmaker's real one (the chat's cited datasets, if the chat test's answer cites the file). Verify: the PNGs read; what could not be checked said in the hand-over.
- [ ] 5.2 A folder of 70,000 files in the test tree: listing time and the live views' time. Verify: numbers in the hand-over.
- [ ] 5.3 Edit `records.py`'s description in the checkout while the stack runs; reload; the live record changes; revert. Verify: before and after in the hand-over.
- [ ] 5.4 Review by an agent that did not write the code (standing rule: more than a few hundred lines), given the code and the spec. Verify: findings verified and addressed or listed.
- [ ] 5.5 `uvx ruff format --check --diff && uvx ruff check` from the repo root; the crawler's and `modama-chain`'s suites; `./downtest.sh --reset` at the end.
