# Tasks

Written after the implementation; each task is done and verified.

## 1. Crawler

- [x] 1.1 `harvest.py` and the trigger after `crawl` (D1, D2). Verify: `tests/test_trigger.py` against a stand-in Airflow: a crawl starts the harvest, an unchanged crawl too, no URL no harvest, a refused account exits 3 with the run finished.
- [x] 1.2 `modama-crawler timer --at HH:MM` (D3). Verify: `tests/test_trigger.py`, the next crawl for four times of day, and a bad time.

## 2. The search stack

- [x] 2.1 `prototypes/search-stack/`: compose file, test override, secrets per concern in `testconf/secrets/`, `init-warehouse.sh`, `airflow-init` with the two accounts, `uptest.sh`/`runtest.sh`/`downtest.sh` (D4). Verify: from `./downtest.sh --reset`, `./uptest.sh` exits 0 with every service healthy (109 s with built images); a second `./uptest.sh` changes nothing (`warehouse ready` only); `./runtest.sh` passes its five checks.
- [x] 2.2 The e2e test on the stack, its crawls starting their harvests. Verify: `./runtest.sh e2e`, 13 passed.
- [x] 2.3 `prototypes/crawler-e2e/` removed; references, READMEs, `AGENTS.md`, `BACKLOG.md`, decision log updated.

## 3. Review

- [ ] 3.1 Review by an agent that did not write it, given the code, this spec and `design/requirements-pipeline.md`; findings verified before acting, listed in `review.md`.
