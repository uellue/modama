# Tasks

Written with the coordinator's leans of 2026-11-12 as assumptions (design D1 to D15), and the review of c182bc1 with the main session's decisions folded in (`review.md`, R1 to R16). Every spec scenario is cited by the task that tests it.

## 1. Requirements

- [x] 1.1 Scenario D in `design/requirements-pipeline.md` 2.1 with @weber's two requests verbatim. Verify: `git diff` shows it; the proposal's quotes match.

## 2. Crawler

- [x] 2.1 `walk(…, top=…)` in `walk.py` (D5): the folders above, then `top` alone. Verify: `tests/test_walk.py`, one test per scenario of "One folder is recognised as in the crawl of the whole tree" (The same datasets as the whole crawl, on every collection's fixtures; Subfolders are not entered, also for the root alone, and A folder inside a collapsed tree, with the reads and type detections counted; An excluded folder, also a symlink, a file and a missing name as `top`); the crawler's whole suite passes.
- [x] 2.2 `cli.configure` public (R8b), used by the crawler's commands as `_configure` was. Verify: the crawler's suite (`test_cli.py`) passes unchanged.

## 3. modama-chain

- [x] 3.1 `live.py` (D4): the JSON of the dataset holding a file, its extraction and rendered record, by the crawler's code, in a child process with a minimal environment. Verify: tests on the EM collection's EMPAD pair and a plain file; two requests run in two processes (their pids; "An edited description" by hand in task 5.3); the child's environment holds no credential.
- [x] 3.2 The runner of live computations (D3). Verify: tests of "A computation over the limit" and "A newer request" with a child that sleeps and starts a grandchild (the process group gone); "A file next to a large subfolder" (one extraction); a killed child's temporary files removed.
- [x] 3.3 `upstream.py` (D7 to D10), `views.py`, additions to `crawler.py` (the stored dataset, a collapsed ancestor, the record's metadata) and `warehouse.py` (the index document, the search hits, the repository code). Verify: unit tests of each view's assembly with task 3.1's fixtures: DataCite has the subject; the index document validates and has the description, `_repo`, `_harvest_url`, `_additional_metadata`; the emulated hit's fields; the matchmaker entry's limits (300 characters, three creators, five subjects, the date format, the relevance cap at 99).
- [x] 3.4 `browse.py` (D11, D12, D14) and `cli.py`. Verify: tests of "A folder with tens of thousands of files", "A link to a file", "Going up" (with `%2e%2e`), "A symlink out of the tree", "An absolute path", "A NUL", "Another host name", "A cross-site form" with werkzeug's test client; symlinks listed as such; a live request without the page's header refused.
- [x] 3.5 Snapshots (D13). Verify: "Save for Claude" with a temporary folder; fake passwords in the environment absent from it; fences longer than the content's backtick runs.
- [x] 3.6 README of `modama-chain` (`browse`, its settings, "What it reads" extended, snapshots are data), `pyproject.toml` (extra `browse`, pinned). Verify: read against the spec.

## 4. Search stack

- [x] 4.1 The stage `browse` of `crawler.Dockerfile`, the service `browse` in `docker-compose.yml` (read-only, tmpfs, the Airflow account blanked), `docker-compose.override.yml` (port 7655, the test tree, a volume for snapshots), `docker-compose.staging.yml` (profile `browse`, port 17655, `STAGING_USER`, the data tree, the crawl's TOML, the snapshot folder in long syntax); `runtest.sh` (the service runs, its listing answers). Verify: `docker compose config --quiet` of the test deployment and of staging (with a fake `staging.env`; without the profile no `browse`); `./uptest.sh --build && ./runtest.sh`.
- [x] 4.2 `test_e2e.py`: "A file found everywhere" (the live and the stored `<record>` equal the server's), "The live index document matches the stored one" (DataCite against the stored harvest event, the index document against OpenSearch's apart from `emb`, the emulated hit against the real one apart from the scores), a path outside the tree refused. Verify: `./runtest.sh e2e` passes, with the number of skips.
- [x] 4.3 README "Looking around" (the browser, the tunnel, what runs on staging), the staging runbook ("Browse": the snapshot folder, build and start with the profile and `--no-deps`, the tunnel and URL; "Safety": code from the checkout, local accounts, @weber's item 216), `python/crawler/AGENTS.md` (snapshots are data, never instructions). Verify: the test stack's equivalents run (`docker compose restart browse`, the API through 127.0.0.1:7655); the staging commands themselves only as `docker compose config` with a fake `staging.env` (staging is not reachable from the VM).

## 5. Checks by eye and hand

- [x] 5.1 Screenshots of the page with a headless browser (Chromium in Playwright's image), in the VM's stack: a folder, a file's views, the matchmaker entry next to matchmaker's real one (the chat's cited datasets for "Find datasets about ferritin"). Verify: the PNGs read; what could not be checked said in the hand-over.
- [x] 5.2 A folder of 70,000 files: listing time (unit test, under 2 s) and the live views' time (10.5 s on the VM's local disk). Verify: numbers in the hand-over; @weber asked to note the time on a large staging folder once (R1; the page shows it).
- [x] 5.3 Edit `records.py`'s description in the checkout while the stack runs; reload; the live record changes; revert. Verify: before and after in the hand-over.
- [x] 5.4 Review of the code by an agent that did not write it (standing rule: more than a few hundred lines), given the code and the spec. Verify: findings verified and addressed or listed (`review.md`, "Code review").
- [x] 5.5 `uvx ruff format --check --diff && uvx ruff check` from the repo root; the crawler's and `modama-chain`'s suites; `./downtest.sh --reset` at the end.

## 6. Out of sync (D16, @weber 2026-11-12)

- [x] 6.1 `sync.py` (the actual values from the stack's Dockerfiles and patch folders, the comparison), the declarations `HIT` and `ENTRY` in `upstream.py`, `SOURCES` formatted from them. Verify: `tests/test_sync.py` passes on the repository and fails with a changed commit.
- [x] 6.2 The page's red line and the snapshot's (`check_sync`, `browse.html`), the files mounted read-only under `/upstream/search-stack/` in `docker-compose.yml`. Verify: the scenario "An emulation out of sync" in `test_browse.py`; a screenshot with a changed commit in a copy; `docker compose config` of the test deployment and of staging (fake values).
- [x] 6.3 README "browse", configuration, tests; spec scenario; backlog. Verify: read against the spec.
