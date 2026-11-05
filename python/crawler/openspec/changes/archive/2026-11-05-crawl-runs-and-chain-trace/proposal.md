# Proposal

## Why

Nobody can say today how fresh the search is or where an item got lost between the file tree and a search hit: a crawl leaves no record, and the four stores of the chain (crawler, harvester, warehouse, OpenSearch) use three different keys with no tool across them. The three walk-throughs of 2026-11-04 (`design/walkthroughs/`) found this from the admin's side and measured it from the agent's: 24 tool calls to diagnose two faults. Everything else in the handover of `design/requirements-pipeline.md` (the stage comparison, the purge, scheduling) builds on a crawl-run record and a per-path trace, so they come first.

## What Changes

- **Crawl runs are recorded** in the crawler's database: start, end, outcome, counts, and progress while the walk runs. A crawl that is killed shows as running with a stale heartbeat, not as finished.
- **The crawl reports progress** on stderr at most once a minute while it walks (directories and files so far), so that a two-hour crawl is not silent.
- **New command `modama-crawler runs`**: the recent runs and the running one with its progress; `--follow` repeats until the running crawl ends.
- **New tool `modama-chain`**, in its own package next to the crawler (decision of 2026-11-04, option C), which knows the warehouse's internals in one place:
  - `modama-chain trace PATH`: one line per stage (tree, crawler dataset and record, OAI-PMH, harvest, warehouse record, OpenSearch document, search rank for the path as query), each with its key and time, flagging what is inconsistent: a record dated before the window of the harvest that should have taken it, a warehouse row marked synced without an OpenSearch document, an entry downstream that the crawler no longer publishes, and a path query whose dataset is not hit 1 (a warning). A member file is traced through the dataset that holds it.
  - `modama-chain status`: per stage the last run, its outcome and time, and the freshness time T: every file whose ctime is before T is included in the search.
- **The e2e test uses the trace** for its assertions, so that a failure names the stage, and adds the two fault scenarios of walk-through C (a datestamp before the harvest window; a lost OpenSearch document behind a synced row).
- **e2e setup** creates a read-only Airflow account (Viewer role) with a generated password for the chain tool.

Behaviour towards the user: new `runs` command and progress lines during `crawl`; nothing changes in what the OAI-PMH server serves or what a harvester or a searcher sees. The new table is added by `ensure_tables`; no existing table changes.

Out of scope, each a later change: the comparison of whole stages and its report (requirements 2.5, handover 3), the purge of stale entries (4), the crawl timer and the harvest trigger (5, decision log 2026-11-04), our own compose files, deletions (`deletedRecord`), member names in records (R38, Q21), per-site configuration (2.8), the watcher.

Serves: `design/requirements-pipeline.md` 1.4 (admins without dashboards, agents), 2.5 (freshness guarantee, findability test), 2.6 (progress for long runs), 2.7 (admin tools in the style of `deploy/*.sh`); walk-through gaps A (crawl-run record, progress, status with T), B (trace by path), C (trace as the e2e assertion, fault scenarios); `design/requirements.md` R8 (path from failure to test), R9 (explainable), Q18 and Q23 (in part).

## Capabilities

### New Capabilities
- `crawl-runs`: recording crawl runs with their outcome, counts and progress, and showing them with the `runs` command.
- `chain-trace`: following one path through every stage of the search chain and stating the chain's freshness time, with the checks that flag inconsistencies between stages.

### Modified Capabilities
None. The crawl's existing requirements (`crawl`) are unchanged; recording the run is the new capability's.

## Impact

- `src/modama_crawler/`: `store.py` (new `crawl_runs` table, run start and end), `walk.py` (an optional progress callback), `cli.py` (`runs`, progress logging in `crawl`).
- New package `python/search-chain/` (`modama-search-chain`, command `modama-chain`): reads the crawler's database, the warehouse's database, OpenSearch, the search API and Airflow's REST API; dependencies `psycopg` (already used by the crawler) and the standard library's HTTP client; no new third-party dependency.
- `prototypes/crawler-e2e/`: the chain tool installed in the crawler image, `test_e2e.py` asserting with the trace, two fault scenarios, the Viewer account in `e2e.sh`.
- Interfaces we rely on, outside our control: the warehouse tables `harvest_runs`, `harvest_events`, `records`; the URL as OpenSearch `_id`; the identifier cut after the last `:`; Airflow's `/api/v2` (v1.10.0 of the warehouse).
