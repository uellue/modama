# Review of the implementation, 2026-11-05

By an agent that did not write the code (commit 51e780f), given the code, the spec, `design/requirements-pipeline.md` and the standing rules, and not this change's design until it had formed its view. Findings verified (roles and endpoints in the running stack, the role's permissions probed with a throwaway account) before acting; the full report is in the session transcript.

| # | Finding | Outcome |
|---|---|---|
| 1 | The base compose file fell back to the committed test secrets when `MODAMA_SECRETS_DIR` was unset | Fixed: `${MODAMA_SECRETS_DIR:?}` in the base file; `uptest.sh` writes a gitignored `.env` with the test default, as `deploy/.env` |
| 2 | The crawler image contained `python/crawler/.env`, which `load_dotenv()` found at run time | Fixed: `.dockerignore` |
| 3 | 31 upstream endpoints active: a DAG run without `harvest_urls` would harvest them all | Fixed: every init deactivates all endpoints but ours; `runtest.sh` checks it |
| 4 | The crawler's Airflow role User could pause, delete and re-run any DAG; its credentials sat in `crawler` too | Fixed: role `harvest-trigger` (read/edit on the harvest DAG, create/read its runs), only in `crawl-timer` (and in the test crawler for the e2e test); `runtest.sh` checks the role |
| 5 | One flat network, `crawler-db` with `trust`, OpenSearch without security | Deferred: listed in the README's "Moving to deploy/" |
| 6 | The search API had the warehouse's admin account | Fixed: role `search_api`, owner of `appdb` only |
| 7 | The timer ignored SIGTERM (PID 1), killing a crawl in flight, and a missed crawl waited a day | Fixed: `init: true`, SIGTERM passed on to the crawl, which records its run as failed; the timer crawls at once when the last finished crawl is older than a day; 60 s grace period |
| 8 | No test that the trigger comes after the commit and the lock release; the timer loop untested | Fixed: the stand-in Airflow checks the run's outcome and the crawl lock when the trigger arrives; the timer is run as a process (catch-up, SIGTERM) |
| 9 | Two `runtest.sh` checks passed on a broken stack | Fixed: every expected service running, the init services finished, the crawler's role checked by name, the only active endpoint |
| 10 | `init-warehouse.sh` pasted secrets and URLs into SQL; the password parse kept everything after `password=`; a changed URL added a second endpoint | Fixed: one Python block with parameters and quoted literals, `conninfo_to_dict`, our endpoint found by its repository code. Left: the index is not re-created when upstream's mapping changes (upgrade step) |
| 11 | `airflow-init` put passwords in argv and deleted and recreated the accounts on every start (a 401 window) | Fixed in part: accounts created only when missing (no window); the password is on the command line once, at creation, inside the container |
| 12 | Init services `restart: "no"`; `pg_isready` without `-h` | Fixed: `restart: on-failure`; `pg_isready -h 127.0.0.1` |
| 13 | Stale documentation (trigger "after a change", `e2e.sh`, `crawler-e2e`), and 02:00 UTC with an hours-long crawl ending in business hours | Fixed; the timer runs at 19:00 UTC |
| 14 | The README's list for `deploy/` was incomplete | Fixed: networks and authentication, production image, backups, alerting, pinned images, sizing, log timestamps, a changed URL, test environments per service |
| 15 | Minor: `(log.info if … else log.error)(…)` | Fixed; the inline Python in `runtest.sh` stays (a shell check, not a second client) |
