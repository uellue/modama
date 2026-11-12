# Walk-through: an admin traces a search result that looks wrong

Persona: an ER-C admin who runs the modama services with the scripts in `deploy/` and knows docker compose and a shell. Doesn't know OAI-PMH, Airflow, OpenSearch or the warehouse's database, and has never read the crawler's code. Works in a terminal on the machine running the stack; a browser only through port forwarding. Goal: find out at which stage of the chain a result went wrong, why, and what to do: wait, re-run something, or report a bug. Done for them: one sentence they can tell the user, and either the fix or a bug report with evidence.
Confidence: simulated by Claude, on paper and against the e2e stack (`prototypes/crawler-e2e/`, warehouse `v1.10.0`) on 2026-11-04. Not yet checked with a real admin. Requirements: `../requirements-pipeline.md`.
What exists: `prototypes/crawler-e2e/README.md` and `e2e.sh`, the crawler's `README.md` and `modama-crawler --help`, the warehouse README, the warehouse database (`datasetdb`: `harvest_runs`, `harvest_events`, `records`), the Airflow UI and API, OpenSearch's REST API, the search API. Read in the order the admin would find them: the e2e README first, then whatever a command or an error points to.

Triggers, from the interview: (a) a user says their file from yesterday is not found; (b) a hit points to a file that was renamed or deleted; (c) a status count does not add up.

## The chain, as the admin will have to learn it

Read from the code, not shown anywhere to the admin. Each stage has its own key for the same item:

| Stage | Where | Key of an item | Time it records |
|---|---|---|---|
| File tree | the data mount (`/data` in the crawler container) | path | mtime, ctime |
| Crawler index | `crawler-db`, table `records` (and `datasets`, `members`) | OAI identifier `oai:<host>:<quoted path>` | datestamp = when the crawl changed the record |
| OAI-PMH | `http://crawler:7654/oai` | OAI identifier | datestamp |
| Harvest | warehouse `postgres`, `datasetdb.harvest_events` per `harvest_runs` row | `record_identifier` = the OAI identifier after its last `:` | the record's datestamp; the run's `started_at`, `completed_at`, `from_date`, `until_date` |
| Transform | Airflow DAG `warehouse_transform_index`, then `datasetdb.records` | (`endpoint_id`, `record_identifier`) | `opensearch_synced_at`, `updated_at` |
| Index | OpenSearch index `test_datacite` (name from the environment) | document `_id` = the record's URL, here the browse URL (`dc:identifier`) | none of its own |
| Search | search API `/search?q=…`, the frontend | hit, top 20 of a hybrid (semantic plus keyword) ranking | none shown |

## Steps

Run on the e2e stack after `./e2e.sh up`, `reset` and `test` (4 passed, 2:33), then by hand: `notes/readme.txt` renamed to `notes/README-renamed.txt`, crawled, harvested through the DAG (70 s). Commands are the ones the admin would have had to find; none of them is written down for an admin.

1. **Take the report.** Does: asks the user for the file's path, the query they typed and when the file was written. Needs to know: how fresh the index is supposed to be, and when the last crawl, harvest and indexing finished. Goes wrong: nothing records when a crawl ran: the crawler's database keeps only per-record datestamps, which move only when a record changes, so an unchanged crawl leaves no trace; the crawl prints `15 datasets, 1 warnings, 2 records changed` to the terminal and nowhere else. The harvest has no schedule (`HARVEST_SCHEDULE` is empty; without it the DAG runs only when triggered). Would ask: "When did each stage last run, did it finish, and is the file older than that?"

2. **Check the file on disk.** Does: finds which container sees the data (`docker compose -f compose.yml exec crawler ls -l --time-style=full-iso /data/notes`). Needs to know: the mapping between the user's path and the data root inside the container, and whether the file is supposed to have a record of its own. Goes wrong: the file may legitimately have no record: a member of a dataset (the EMPAD raw file `scan/series_x4.raw` belongs to `scan/SCA2_rings.xml`), inside a collapsed tree (a venv), excluded by `[crawl] exclude`, a skipped symlink, or unreadable for the crawler. Nothing tells the admin which. Would ask: "Is this file supposed to be its own entry, and if not, which entry is it in?"

3. **Check the crawler's index.** Does: `docker compose … exec crawler-db psql -U postgres -d modama_crawler -c "select identifier, datestamp from records where identifier like '%notes%'"`. Needs to know: the database and table names, the identifier scheme (`oai:er-c-data-mgmt.fz-juelich.de:/notes/readme.txt`), and that `modama-crawler records <path>` shows what the crawler *would* publish without a database (but not what it publishes now). Goes wrong: there is no command that answers "given this path, which record covers it and since when"; the `members` table has the answer but no reader. After the rename, the old record is simply gone from the crawler: no tombstone, no log line naming it ("2 records changed" does not say which, nor that one was a removal).

4. **Check what the OAI-PMH server serves.** Does: `curl 'http://127.0.0.1:7654/oai?verb=GetRecord&metadataPrefix=oai_dc&identifier=oai:…'`, which needs a forwarded port from a remote machine, or a curl inside a container. Needs to know: OAI-PMH verbs, the identifier. Goes wrong: nothing in particular; it agrees with step 3 by construction (the server reads the same table).

5. **Check the harvest.** Does: psql into the warehouse database as `admin` (the password is in `warehouse.env`) and joins `harvest_runs`, `endpoints` and `harvest_events`. Needs to know: the table names; that the warehouse's key is the OAI identifier cut after its last `:` (`/notes/readme.txt`); that `records_harvested` is always 0 and the events must be counted instead; that an incremental run asks for `from` = the previous run's `until_date`. Seen: three closed runs with 14, 1 and 1 events, `records_harvested` 0 each. Goes wrong: comparing "harvested" with "crawled" by counts is impossible from the run table; the harvest run's `until_date` (15:22:14.40) is a warehouse clock time while the crawler's datestamps are whole seconds of the crawler's clock, so the admin can't easily tell whether a record changed during a run was skipped. Would ask: "Did the last harvest see my record, and if not, was the record newer than the harvest?"

6. **Check the transformation.** Does: `select record_identifier, url, datestamp, opensearch_synced_at from records …` in the same database, or the Airflow UI for the `warehouse_transform_index` run (port 8081, forwarded). Needs to know: that the harvest DAG triggers a second DAG, that both start paused (the e2e test unpauses them), that a failed transformation is logged at info level only and shows as a missing row here. Goes wrong (developer hat, from the code): `records.opensearch_synced` is set to true for every record of a batch even when the OpenSearch bulk call reports failures, so this table can claim "synced" for a document that isn't there.

7. **Check OpenSearch.** Does: `curl 127.0.0.1:9200/test_datacite/_doc/<url-encoded browse URL>`. Needs to know: the index name (from `INDEX_NAME` in `warehouse.env`) and that the document id is the record's URL, not the identifier of any earlier stage. Seen: the document holds title, creator, `dates: [{date: 2026-11-04, dateType: Issued}]` (the time of day and the meaning "modified" are lost in the DataCite mapping) and the whole OAI record in `_additional_metadata`, datestamp included. After the rename: 16 documents for the crawler's 15 records.

8. **Check the search.** Does: `curl '127.0.0.1:8000/search?q=readme&resource=datasets'`. Seen: the renamed file's **old path is hit 1**, the new one hit 2. A query for the EMPAD raw file's name, `series_x4.raw`, returns ten hits, none of them its dataset: members are not in the record (R38, Q21). Every query returns ten hits, related or not (the ranking is mostly semantic), so "the search returned results" says nothing about whether the file was found. Goes wrong: the admin can't tell "not indexed" from "indexed but ranked out of the top hits for this query".

9. **Decide and act.** For trigger (b), the stale entry: there is no supported way to remove it. The crawler publishes no deletion (`deletedRecord=no`), and the harvester would ignore one (BACKLOG, upstream issues). The admin's choices are to delete the row in `records` and the OpenSearch document by hand, or to reset the warehouse and harvest from scratch. Neither is written down, and nobody knows how many other ghosts there are. For trigger (c), counts that don't add up (15 against 16): finding *which* items differ needs the key mapping of the table above and a join across two databases and an index; no tool does it.

## Product hat

The admin wanted one sentence for the user ("your file is in the crawl from 03:00 but the harvest after that hasn't run", "the old path is a known leftover and will disappear by tomorrow") and got an archaeology session through four stores with three different keys (half a day in @weber's own case, `../requirements-pipeline.md` 1.3). "Done" for them is a single command, in the style of `deploy/*.sh`, that takes a path or a URL from a search hit and prints its state at every stage with times, and the first stage where it is missing or different. They would complain most about: bogus hits that never go away; not knowing whether something is broken or just not yet run; having to learn psql, the Airflow API and OpenSearch's REST API to answer a user.

## Developer hat

- **No common key across stages:** path → OAI identifier → identifier cut after the last `:` → URL as OpenSearch id. A trace tool has to reproduce each mapping, and the cut and the URL-as-id are upstream choices that can change. The browse URL is the only key that survives to the end; the identifier cut works for our identifiers only because the local part has no `:` (it is escaped, `records.py`).
- **No run records on our side:** the crawler stores no crawl runs, so "as of when" has no answer, for the admin or for a freshness note to end users.
- **Deletions are the main consistency hole:** removed and renamed files accumulate in the warehouse and the index forever, and rank as well as live ones. This is a crawler gap (`deletedRecord`) and an upstream one (the harvester's deleted-status check); both are known, neither is scheduled.
- **The warehouse's own sync flag can lie** (step 6), so a consistency check must compare against OpenSearch itself, not against `records.opensearch_synced`.
- **Timestamp granularity and clocks:** whole-second crawler datestamps, a microsecond harvest window from the warehouse's clock; a record written in the same second as a harvest's `until` may be missed (BACKLOG, "Datestamp window"). A check must be able to show such a record.
- **Credentials:** a trace tool needs read access to two databases, OpenSearch and the Airflow API; the e2e credentials are in `warehouse.env` and the compose file. For production these must not be hardcoded and should be read-only.
- **Scale:** a per-path trace is cheap at every stage. A full reconciliation at millions of records needs set comparisons (identifier lists from the crawler, `records`, and an OpenSearch scroll of `_id`s), not per-record calls.

## Answers from the owner (@weber, 2026-11-04)

1. **Freshness reference:** the timestamp that guarantees that all files older than it are included.
2. **Members:** a dataset should be findable from a member: a must for datasets with few members, a should for large ones. Note, not a requirement: a compound dataset is typically hierarchical within a common folder (a Zarr store), not scattered over the file system, so paths can help.
3. **Findable, as a test for now:** searching for the path yields the dataset. Searching for the file name is fine for development with synthetic, unique names; in production it would collide too often.
4. **Stale entries:** a re-index is expensive, so we write our own purge for the time being. The comparison of stages is mostly for the e2e test, because production has very many files; it could also be an admin command if it runs quickly enough and gives actionable, interpretable results: in normal operation very few or no discrepancies.

The questions as asked:

- (1) What is the reference point for freshness that users and admins should see: the start of the last complete crawl, its end, or the last indexing? "Known good complete crawl": known good by what check?
- (2) When a file has no record of its own because it belongs to a dataset, what should a trace of its path say: the dataset that holds it? And should searching for its name find that dataset (R38, Q21)?
- (8) What does "findable" mean as a test: the file's dataset among the top *N* hits for a query containing its file name? For which queries (file name, words in the path, words in the title)?
- (9) Until deletions work end to end, what is an acceptable workaround for stale entries: a documented manual purge, a periodic full re-harvest into a fresh index, or nothing (wait for the fix)?
- (9) Is a reconciliation (lists of what is missing or extra at each stage) wanted as an admin command, as part of the e2e test, or both?

## Gaps

- A record of each crawl run (start, end, outcome, counts, what changed) in the crawler's database (steps 1, 3).
- A command that traces one path or URL through every stage (steps 2 to 8).
- A command that compares the sets of items at every stage and lists the differences (step 9, trigger c).
- Deletions end to end: `deletedRecord` in the crawler, and the harvester honouring it (step 9, trigger b).
- Documentation for admins of where each stage keeps its state and how to reach it without forwarded ports (all steps).
- Member file names in records, so that a member is findable through its dataset (step 8; R38, Q21).

## Acceptance examples

- When a file arrives (ctime) before T, the start of the last crawl that is harvested and indexed, then a search for its path returns its dataset, with a warning if not as hit 1.
- When a file is renamed and the chain has run once since, then a search for its old name does not return the old path. (Fails today: hit 1. Deferred: removals are not a concern yet, 2.5; the purge comes first.)
- When the admin traces `notes/readme.txt` after the rename, then the output shows: not on disk; no crawler record (removed in the crawl of <time>); still in the warehouse's `records` and in OpenSearch, a stale entry; the next action.
- When the admin traces `scan/series_x4.raw`, then the output says it is a member of the dataset `scan/SCA2_rings.xml` and shows that dataset's state at every stage.
- When the crawler holds 15 records and OpenSearch 16 documents, then the comparison names the one extra document and the stage where it should have been removed.
- When the last crawl finished at T and nothing changed, then the status still shows T as the time of the last complete crawl.

## Questionnaire

Sections of `../requirements-pipeline.md` this walk-through informs but which the record doesn't answer yet:
- 2.5: how a wrong result is noticed, and by whom, when no user reports it.
- 2.6: the freshness reference point (question 1 above) and *N* for "findable" (question 3).
- 2.7: who may hold read credentials for all four stores in production.
- 2.10: how long stale entries may live after a deletion.
