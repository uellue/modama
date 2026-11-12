# Proposal

## Why

The search stack ran only when someone triggered its harvest by hand, and upstream's own schedule would race a crawl's store. The decision of 2026-11-04 (our timer runs the crawl, the crawler starts the harvest after it) and of 2026-11-05 (our own composition as the step before `deploy/`, `design/architecture.md`) make the chain run by itself: requirements-pipeline 2.5 (freshness), 2.7 (admins without manual triggers), handover item 5.

Written after the implementation (@weber: "go ahead with your leans"), as the contract of what was built; the tasks are therefore done.

## What Changes

- **Every finished crawl starts the harvest** of the crawler's own endpoint through Airflow's API, after its records are committed, when `MODAMA_CRAWLER_AIRFLOW_URL` is set; also an unchanged crawl, so that T moves on. A harvest that cannot be started leaves the crawl finished and makes `crawl` exit with status 3.
- **New command `modama-crawler timer --at HH:MM`**: crawls every day at that time (UTC), each crawl a process of its own, until stopped.
- **Our own composition `prototypes/search-stack/`** (not a capability of the crawler; recorded in the decision log): upstream's images, secrets as files per concern, init services, the timer as a service, DAGs unpaused, upstream's schedule off; replaces `prototypes/crawler-e2e/`; the e2e test moves there and its crawls start their harvests.

Behaviour towards the user: `crawl` may log `harvest of … started: <run>` and exit with 3; the new `timer` command. What a harvester sees is unchanged; what a searcher sees arrives without manual steps.

Out of scope: the production compose file and the move to `deploy/` (backlog "Deployment"); the purge of stale entries; the stage comparison; the watcher (inotify); a schedule other than daily; parameters of `timer` beyond `--at` (to go through with @weber, CLI conventions).

## Capabilities

### New Capabilities
- `harvest-trigger`: starting the warehouse's harvest of the crawler's endpoint after each crawl, and crawling on a daily timer.

### Modified Capabilities
None.

## Impact

- `src/modama_crawler/harvest.py` (new, Airflow API with the standard library), `cli.py` (`timer`, the trigger after `crawl`).
- `prototypes/search-stack/` new, `prototypes/crawler-e2e/` removed; READMEs, `AGENTS.md`, `BACKLOG.md`, decision log.
- No new third-party dependency. Interfaces outside our control: Airflow's `/auth/token` and `/api/v2/dags/warehouse_harvest_and_index/dagRuns` with the conf `harvest_urls` (warehouse v1.10.0).
