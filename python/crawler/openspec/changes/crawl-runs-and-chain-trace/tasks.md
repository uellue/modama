# Tasks

## 1. Crawl runs in the crawler

- [x] 1.1 `crawl_runs` table in `ensure_tables`, run inserted and committed before the walk, ended with outcome, counts and end time after the store (D1). Verify: test "A finished crawl" and "An unchanged crawl leaves a run" with `pytest-postgresql`.
- [x] 1.2 Failure path: outcome `failed` with the error message, non-zero exit. Verify: test "The root disappears".
- [x] 1.3 Progress callback in `walk()` and throttled updates and log lines in `cmd_crawl` (D2), the interval injectable for tests. Verify: test "Progress of a slow walk" with a short interval; existing walk tests unchanged.
- [x] 1.4 Running, stale and finished from the row (D3). Verify: test "A crawl killed during the walk" (run row without end, old update time).
- [x] 1.5 `modama-crawler runs` and `--follow`, stdout/stderr split, broken pipe and Ctrl-C. Verify: tests "No crawl yet", "Following a crawl", "Piped into head", typed as command lines; the output checked by eye with `tools/xterm-shots.py` if xvfb is available, otherwise a captured transcript for @weber.

## 2. The chain tool, smoke test first

- [ ] 2.1 Package skeleton `python/search-chain/` (pyproject, `modama-chain` entry point, README with the stores, the environment variables and the crawler tables it reads as an interface), installed in the e2e crawler image. Verify: `docker compose -f compose.yml exec crawler modama-chain --help`.
- [ ] 2.2 Viewer account for Airflow in `e2e.sh setup`/`reset`, password generated into `warehouse.env` (D8). Verify: a GET of `/api/v2/dags` with the account succeeds and a PATCH is refused.
- [ ] 2.3 Smoke test, one scenario end to end before the rest: `trace` for "A file found everywhere", all seven stages, against the running e2e stack. Verify: the scenario as a test in `test_e2e.py`, and the output shown to @weber for the line layout (design, open question).
- [ ] 2.4 Members through their dataset (D5). Verify: e2e scenario "The raw file of an EMPAD pair".
- [ ] 2.5 Flags `before-harvest-window`, `synced-without-document`, `stale` (D6), with the fault injections of walk-through C as e2e scenarios. Verify: e2e scenarios "A record dated before the harvest window", "A lost index document", "A renamed file".
- [ ] 2.6 Search rank with the warning below rank 1. Verify: a unit test of the rank rule with a canned search response; the e2e scenario "A file found everywhere" shows rank 1.
- [ ] 2.7 Exit statuses and unreachable stores. Verify: e2e scenario "The warehouse database is down" (stop `postgres`, trace, start it again).
- [ ] 2.8 Keys rebuilt for paths the crawler no longer has, from a crawled record's host and URL prefix (D5, risks). Verify: a test comparing a rebuilt key with a crawled one.
- [ ] 2.9 `status` with T (D7). Verify: e2e scenarios "A complete chain", "A crawl that is not harvested yet", "A failed harvest" (a harvest of an unreachable endpoint URL, or the crawler stopped during a harvest).
- [ ] 2.10 Read-only: the tool runs with a read-only warehouse database role and the Viewer account. Verify: e2e scenario "Read-only accounts suffice", with the role created in `e2e.sh reset`.

## 3. The e2e test asserts with the trace

- [ ] 3.1 Replace the count-only assertions in `test_e2e.py` by traces of every record of the oracle, keeping the counts as a summary. Verify: `./e2e.sh test` passes; a deliberately broken stage (one of 2.5's injections left in) fails with the stage named in the assertion message.

## 4. Documentation and review

- [ ] 4.1 Crawler `README.md` (the `runs` command, progress lines), `AGENTS.md` code map, the e2e README (the chain tool, the Viewer account, the fault scenarios), `BACKLOG.md` (Next, and the handover items 3 to 5 as entries), `design/architecture.md` decision log (option C, D4). Verify: the README's commands typed as written work.
- [ ] 4.2 Review by an agent that did not write the code, given the code, the specs and `design/requirements-pipeline.md`, not this design's conclusions; findings verified before acting (`design/review.md` pattern). Verify: the review's findings and their outcomes listed in the change.
- [ ] 4.3 Lint and tests as CI and the hook run them: `uvx ruff check`, `uvx ruff format --check` from the repo root, `pytest` in `python/crawler`, `./e2e.sh test`. Verify: the commands' output.

## Workflow follow-up

- Archive the change with `/opsx:archive` once @weber has accepted the output layout and the review findings are resolved.
