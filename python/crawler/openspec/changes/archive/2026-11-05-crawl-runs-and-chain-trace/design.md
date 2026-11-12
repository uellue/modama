# Design

## Context

See proposal.md for the why. State of the code and of upstream that shapes the approach:
- `cli.py cmd_crawl` walks the whole tree in memory (`walk.walk`), then `store.store` replaces `datasets` and `members` and upserts `records` in one transaction, with one datestamp per crawl taken just before the upsert. Nothing records the crawl itself; the walk logs nothing until it ends.
- Upstream (metadata-warehouse v1.10.0): a new harvest run's `from_date` is the `until_date` of the endpoint's latest *closed* run (`src/app/db_methods.py`), so closed runs form a contiguous chain of windows; a failed run stays `open`, and no new run starts while one is open (metadata-warehouse#158). Each indexing run is a run of the DAG `warehouse_transform_index` with `harvest_run_id` in its conf. The OpenSearch `_id` is the record's URL (`src/transform/transform_core.py`); the harvest keeps the OAI identifier after its last `:`.
- Walk-through C measured what the trace has to replace: 24 tool calls, four identifier mappings, two undocumented store layouts.

## Goals / Non-Goals

**Goals:**
- The crawler knows its own runs without any upstream code; `modama-crawler runs` works with the crawler's database alone.
- All knowledge of upstream internals (tables, keys, the identifier cut, the DAG names, Airflow's API) sits in one module of the chain tool, with the e2e test as its check against the real stack.
- The trace and the e2e test share one implementation: the test calls the same functions and asserts on their results.

**Non-Goals:**
- Comparing whole stages, purging, scheduling, triggering (proposal, out of scope).
- Speed at production scale for anything but a single trace and the status; both are a handful of indexed queries per stage.
- A machine-readable output format; the e2e test uses the library, people use the lines (add a format when a second consumer needs one).

## Decisions

**D1. Crawl runs in a table of the crawler's database.** `crawl_runs (run_id, root, started_at, updated_at, finished_at, outcome, directories, files, datasets, warnings, records_changed, error)`, created by `ensure_tables` like the others (no migrations; a new table needs none). The run row is inserted and committed in its own transaction before the walk, so that it exists while the walk runs and survives a failure of the store transaction. *Alternatives:* a log file (not queryable by the chain tool, lost with the container); deriving runs from record datestamps (an unchanged crawl leaves none, walk-through A).

**D2. Progress through a callback from the walk, written by a heartbeat thread.** `walk()` gets an optional `progress(directories, files)` callable, called after each directory, which only records the counts; a thread in `cmd_crawl` with its own connection writes them and a log line once a minute. The walk stays free of database code and time. *Changed after the review of 2026-11-05:* the first version wrote from the callback, so a directory that takes minutes to type or the store transaction held the updates back and a healthy crawl turned stale. *Alternative:* updates from the callback only (that failure).

**D3. Running, stale and finished from the row alone.** `finished_at IS NULL` and `updated_at` within twice the update interval is running; older is stale. Update times and the age are the database's `now()`, so that readers on other hosts agree. No locks, no PID files: a killed crawl can't clean up after itself, so the reader decides. *Alternative:* an advisory lock held for the crawl (tells "alive" exactly, but only to a reader on the same database server, and a second crawl would block silently).

**D4. The chain tool is a package of its own, `python/search-chain/` (`modama-search-chain`, command `modama-chain`).** It reads the crawler's tables as an interface (`crawl_runs`, `records`, `datasets`, `members`), written down in its README; it does not import the crawler. The upstream knowledge lives in one module (`warehouse.py`: harvest runs, events, records, the identifier cut, the index `_id`, Airflow DAG runs); the stage functions and the T computation use it. The decision of 2026-11-04 (option C) is recorded in `design/architecture.md`. *Alternative:* importing `modama_crawler.records` for the identifier and URL (couples the packages' versions; the tool reads both from the crawler's `records` table instead).

**D5. Keys follow the item, not the path.** The trace resolves PATH to a dataset in the crawler (anchor, else member), then carries that dataset's keys downstream: OAI identifier → the warehouse's `record_identifier` (cut after the last `:`) → warehouse `records` by endpoint and identifier → index document by the record's URL → the search query with the dataset's path. For a path the crawler no longer has (renamed, deleted), the keys are rebuilt from the path by the same rules as the crawler's (`oai:<host>:<path>`, the browse URL), read from the crawler's configuration in the environment, to find stale entries downstream.

**D6. Flags compare adjacent stages only.** Each flag is a rule over two neighbouring stages (spec: `before-harvest-window`, `synced-without-document`, `stale`; `before-harvest-window` compares the crawler's datestamp with the `until` of the last closed harvest, cut to the second, where the next incremental harvest starts: anything dated before it without a harvest event is lost for good; review 2026-11-05), so a new failure mode is a new rule, and the first diverging stage is the first rule that fires. *Alternative:* a full state model of the chain (more than the three faults we have examples of; YAGNI).

**D7. T from run records, not from items.** T = start of the newest crawl run with outcome `finished` whose `finished_at` ≤ the `until_date` of a closed harvest run of the endpoint, where a `warehouse_transform_index` run with that `harvest_run_id` in its conf succeeded, and so did one for every closed run before it (each indexing run indexes only its own harvest's events; found while implementing). Because closed harvest runs are contiguous and a crawl's datestamps are ≤ its `finished_at`, the covering harvest has seen every record of that crawl, unless datestamps moved backwards (which the trace flags per item). Crawler and harvest times come from different hosts' clocks; in one compose project they agree, and a skew is what `before-harvest-window` shows. *Alternative:* T from a full comparison of items (the stage comparison, a later change; it checks what run records only claim).

**D8. Airflow through its REST API with a Viewer account.** The tool gets a token from `/auth/token` with credentials from its environment (`MODAMA_CHAIN_AIRFLOW_USER`, `…_PASSWORD`) and only issues GETs. The e2e setup generates the passwords into `chain.env` (gitignored, the crawler container's `env_file`; not `warehouse.env`, so that the warehouse's secrets stay out of the crawler container), and `reset` creates the account (`airflow users create --role Viewer`) and a read-only database role `chain_reader`. Airflow does not report a failed harvest: the DAG run ends in `success` when its harvest task failed, so the tool reads the outcome from `harvest_runs`. Requirements 2.4 and the decision of 2026-11-04.

**D9. Configuration by environment, like the crawler.** Addresses and credentials of the five stores come from environment variables with the e2e stack's service names as defaults where they carry no secret (`crawler-db`, `postgres`, `opensearch:9200`, `search-api:8000`, `airflow-api-server:8080`); passwords have no default. The tool runs inside the compose network, so nothing needs a published port (requirements 1.1, 2.4).

**D10. Output.** One line per stage, fixed columns: stage, state, key, time, detail; flags in upper case so they stand out without colour (`R36`'s spirit: warnings are actionable). Exit statuses as in the spec. Broken pipe and Ctrl-C as the crawler's `records` command handles them (CLI conventions).

**D11. Locks in the crawler's database instead of timing (review 2026-11-05, findings 1 and 9).** One crawl at a time: a session-level `pg_try_advisory_lock`, which never waits (no deadlock) and which PostgreSQL releases when the session ends, also on a crash; a crawler that hangs while alive keeps it, and the refusal names the latest run, which `runs` shows as stale. Harvests and stores: `store()` takes an exclusive transaction lock just before it writes the records and only then takes the datestamp; every OAI-PMH request takes the same lock shared for its one-query transaction, or answers 503 with `Retry-After` if it can't. A record is thereby either committed before a harvest reads, or dated after the harvest's `until`. Upstream's harvester (oaipmh-scythe 0.14, `max_retries=3`, `Retry-After` honoured) retries; if a store outlasts the retries, the harvest run fails, and a failed run does not move the next window (`from` = last closed `until`), so nothing is lost, only delayed. Left: clock skew between the crawler's and the warehouse's hosts. *Alternatives:* a different `until` in the response (the harvester takes `until` from its own database, not from us); stalling requests until the commit (holds a connection and a thread per request, and the harvester's 180 s timeout then fails the run anyway); a short store via a staging table (narrows the race without closing it).

## Risks / Trade-offs

- [Upstream changes a table, the cut or the `_id`] → all of it is in `warehouse.py`, and the e2e test traces real items through the real stack, so an upgrade that changes them fails the test.
- [T trusts that a successful indexing run indexed everything; #158 and the sync flag show that runs can claim more than they did] → the trace checks per item; the stage comparison (next change) checks all items.
- [Progress updates add a write per minute to a long crawl] → one small UPDATE per minute, in its own transaction; negligible against the walk.
- [The run row and the store transaction are separate; a crash between the store's commit and the run's end leaves a finished store with a stale run] → the reader shows it as stale with its counts unknown; the next crawl corrects the data, and T ignores the run.
- [Two crawls at the same time] → the second is refused (D11).
- [A store longer than the harvester's retries (3 × `Retry-After`)] → the harvest run fails and its window is harvested again next time; noise in `status`, nothing lost.
- [Rebuilding keys for paths the crawler no longer has relies on the crawler's identifier rules] → the rules are read back from a record the crawler does have (host and URL prefix), not duplicated; a test compares a rebuilt key with a crawled one.

## Migration Plan

`ensure_tables` adds `crawl_runs` to an existing database; nothing else changes in the crawler's schema, and the OAI-PMH output is unchanged. The chain tool is new. Rollback: drop the table and uninstall the tool.

## Open Questions

- The exact column layout and wording of the trace and status lines: settled on the e2e stack's real output and checked by eye in a terminal (`tools/xterm-shots.py`), with @weber.
- The parameter set of `runs` beyond `--follow` (a limit, a root filter): go through the combinations with @weber before implementing (CLI conventions); none is needed for the scenarios.
