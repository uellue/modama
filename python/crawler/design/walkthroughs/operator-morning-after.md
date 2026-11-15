# Walk-through: an operator checks the night's run the morning after

Persona: the operator (`../stakeholders.md`): an ER-C admin colleague who runs the deployment with the `deploy/` scripts, knows docker compose and a shell, not Airflow, OpenSearch or the formats. Situation: the morning after the 19:00 crawl, before colleagues start searching. Goal: "all good, the search is fresh as of T" or "stage X needs attention, and this is what I do". Done for them: an answer they trust within a few minutes, and either nothing to do or one clear action.
Confidence: simulated by Claude on 2026-11-15, on paper, from what @weber did as operator on the mornings of 2026-11-13, 14 and 15 (chat and recorded terminal, `.claude/field-tests/run-3` to `run-5`) and from the tools as they are on branch `crawler` (606fa40b). Not checked with a real admin colleague. A re-walk of walk-through A (`admin-checks-the-chain.md`, 2026-11-04) against today's tools.
What exists: `prototypes/search-stack/README.md` ("Looking around", "Field-test scripts", "Upgrade"), the staging runbook (`../field-tests/search-stack-staging-runbook.md`), `modama-chain status | review | trace | browse` (`/python/search-chain/README.md`), `modama-crawler runs`, the field-test scripts (`index-tasks.sh`, `index-failures.sh`, `batch-times.sh`, `failed-headers.sh`), the Airflow UI (port 18081, forwarded), OpenSearch's REST API.

## What changed since walk-through A (2026-11-04)

A crawl-run record (`modama-crawler runs`), a timer that crawls at 19:00 and a harvest started by the crawl, `modama-chain status` with T, `review` for the flagged files, `browse` for one file's view in every stage. Walk A's "a healthy stack can be idle forever" and "T can't be computed" are fixed; the steps below find what is still missing.

## Steps

1. **Get a shell where the commands work.** Does: `ssh` to the server, `cd …/prototypes/search-stack`, then defines `dc() { docker compose -p search-staging --env-file staging.env -f docker-compose.yml -f docker-compose.staging.yml "$@"; }` from the runbook. Needs to know: the folder, the project name, the env file, the overlay files. Goes wrong: `dc` is a shell function, gone in every new shell; outside that folder it fails (@weber, 2026-11-12: "I had to change to the search stack folder for dc to work"); the recorded terminal shows the definition typed again in four of five runs. Production will have its own names (`deploy/`, `upprod.sh`). Would ask: "What do I type first, and does it work from anywhere?"

2. **Ask for the status.** Does: `dc exec crawler modama-chain status` (on 2026-11-15 also under `watch`). Seen this morning: the crawl `finished` 19:00 to 21:17; the harvest `closed` at 21:17:19; indexing `failed … ended 2026-11-14T05:32:20Z`; `fresh unknown: no closed harvest run has been indexed successfully`. In fact the night's indexing had succeeded at 21:51. Goes wrong: the indexing line showed a run cancelled the day before (fixed in 606fa40b, 386, live with the next build); `fresh unknown` stays while every harvest since the first is not indexed in the tool's sense, because a manual re-index carried no harvest run (or failed), so T never recovers on its own. Would ask: "Is the search up to date or not? And if 'unknown', what do I do?"

3. **Judge the night's numbers.** Does: reads the crawl line: 1,191,201 extractions, 527 failed, 1,226 warnings, 1,313,385 datasets, 280,154 records changed, followed by about 60 formats with "extracted again" counts. Needs to know: whether 527 failures and 138,000 fewer datasets are normal tonight. Goes wrong: no comparison with the night before or an expected range is shown; the drop in datasets was intended (a test tree deleted, AppleDouble files excluded), but only the people in the chat knew. Would ask: "Is 527 a lot? Why did 138,000 datasets disappear?"

4. **Check that the search holds what the crawl published.** Does: nothing in the tools shows it; on 2026-11-15 the agent asked for `curl …/test_datacite/_count`: 1,452,360 records against 1,313,385 datasets. Goes wrong: the 139,000 stale records (deletions are not carried through the chain, BACKLOG) are invisible to status; `_cat/indices` shows 11.6 million "documents", which an operator would read as the record count. Would ask: "Does the search have exactly what the crawl has?"

5. **Look at what the crawl flagged.** Does: `dc exec -T crawler modama-chain review --browse http://localhost:17655/ > review.md`; on 2026-11-14 the agent grouped it and asked for `failed-headers.sh` to see the first bytes of the failed files. Needs to know: which entries are new since last night, which ones need them (storage, permissions) and which a maintainer (a format bug). Goes wrong: the review lists all current flags, not the night's new ones; triage needed the agent and a field-test script. Would ask: "Is any of this my job, or do I pass it to the developers, and how?"

6. **Check the machine.** Does: `df -h`, `free -m`, `top`. Seen in the monitor log this morning: `/` at 85 %, the Docker data volume at 88 %. Goes wrong: no tool says what fills up and how fast; the monitor that recorded it is a field-test script, not part of the stack. Would ask: "Will the disk last until next week?"

7. **When a stage failed: find out why.** Happened on 2026-11-14: indexing failed. Does (what @weber ran, each command proposed by the agent): `index-failures.sh`; `dc logs opensearch | grep -i -E 'circuit|429|rejected|OutOfMemory'`; `curl …/_nodes/stats/breaker`; `free -m`. Found: OpenSearch out of heap; the fix was a change to the compose file in the repository (8 GB heap, ac4ca1f1). Later the same morning: workers idle because the scheduler's executor had "0 open slots" after a worker was recreated, found by grepping the scheduler's log; fixed by `dc restart airflow-scheduler`. The embedding tunnel to the GPU server: `journalctl -u embed-tunnel.service`, `curl …/health`. Goes wrong: every diagnosis needed someone who knew where to look; the fixes were a repository edit, a restart and a configuration line, none of them in a runbook beforehand. Would ask: "What do I restart, is it safe while something runs, and when do I call a developer?"

8. **Re-run what failed.** Does: in the Airflow UI (German: "Löschen" of the failed tasks), or `dc exec airflow-scheduler airflow dags trigger warehouse_transform_index --conf '{"harvest_run_id": "de02cfa5-…"}'`, the UUID copied from the status line. Goes wrong: two triggers queued behind each other (`max_active_runs=1`); a cancelled one stayed in the status for a day (step 2); the rule "no upgrade or restart during harvest or indexing" lived in the chat. A `modama-chain retry` is proposed (page items 364, 365). Would ask: "Which run do I re-run, and how do I know it worked?"

9. **Tell the users.** Does: nothing; the search page shows no freshness. Would ask: "Can I just tell people 'everything older than yesterday 19:00 is in'?"

## Product hat

What they wanted is walk A's `runtest.sh`-style answer, and most of it now exists: one status, one record per crawl, a list of flagged files. "Done" still needs someone who knows the chain: the status can be wrong or "unknown" for reasons the operator can't fix (steps 2, 4), the numbers have no baseline (3), the review has no "new tonight" and no owner per entry (5), and incidents are solved by knowledge that lives in the chat (7, 8). They would complain about: a shell function to start with, `unknown` with no next step, a count of 11.6 million that isn't the count, and commands with UUIDs typed by hand.

## Developer hat

- **T and manual runs:** T requires every harvest since the first to have a successful indexing run linked by `harvest_run_id`; one manual run without that link, or one failed night, leaves T unknown for good. Either the retry (364) restores the link, or T is defined from the latest successful chain, a decision for the requirements (2.5 of `requirements-pipeline.md`).
- **Counts per stage** (datasets, records published, warehouse records, documents in the index) are cheap to read and are what step 4 needs; the purge (387, `purge-stale-records`) closes the gap they show.
- **"New since last night"** in the review needs the warning's first night, which the crawler's tables may not keep (to check).
- **Restarts during a run** are unsafe in specific ways (a recreated worker left the scheduler at "0 open slots"); the tools could refuse or warn instead of a rule in someone's head.
- **The field-test scripts** (`monitor.sh`, `index-*.sh`, `failed-headers.sh`) do the operator's work today and are not part of the product; which of them become commands is a decision.
- **Port forwarding** is still needed for Airflow's UI and the search; the German UI made a click path hard to explain.

## Questions for the principal

- (1) Will production have one entry script for the operator (like `upprod.sh`) that also covers status and retry, so that nobody defines `dc`?
- (2) T stays `unknown` after one manual re-index or one failed night. Should the status instead say "fresh as of the last complete crawl-harvest-index chain", and name the gap?
- (3) Should the status compare the night with the one before (failures, datasets, records changed) and flag a jump, and what is a jump?
- (4) Which field-test scripts should become supported commands for the operator, and which stay developer tools?
- (5) What may the operator restart or re-run on their own, and what needs a developer?
- (6) Should the search page show the freshness T to users (walk A's wishlist item)?

## Answers from the principal

None yet (questions put on 2026-11-15).

## Gaps

- No stage counts and no check that the index matches the crawl (step 4).
- No baseline for the night's numbers (step 3).
- The review has no "new since" and no owner per entry (step 5).
- No disk and memory forecast in the product (step 6).
- No runbook for the three incidents seen (OpenSearch heap, scheduler slots, the tunnel) (step 7).
- No safe re-run command (step 8; `retry`, items 364 and 365).
- `fresh unknown` has no next step (step 2).

## Acceptance examples

E1, E2, E3, E4, E5 (in `../examples.md`).

## Questionnaire

Not answered for the operator yet: 2.5 (what happens when the search is a day stale and nobody notices: who is told, how), 2.7 (who operates production, with how much time per week), 2.10 (what happens to the index and the records when the search is retired), 2.11 (which actions an operator may take unattended; who is called at night: nobody, by decision?).
