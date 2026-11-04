# Walk-through: an admin checks whether the chain works and how far along it is

Persona: the ER-C admin of walk-through B (`admin-traces-a-search-result.md`): runs the modama services with the scripts in `deploy/`, knows docker compose and a shell, doesn't know OAI-PMH, Airflow, OpenSearch or the warehouse. Situations: right after bringing the stack up, and the morning after a night's crawl. Goal: "all good, as of T" or "stuck at stage X, because …", without opening dashboards. Done for them: one answer they trust, in the terminal, within a minute.
Confidence: simulated by Claude against the running e2e stack on 2026-11-04 (after walk-through B's rename, 34 minutes after `up`). Not yet checked with a real admin. Requirements: `../requirements-pipeline.md`; T is the freshness guarantee of its section 2.5.
What exists: `docker compose ps` and `logs`, the crawler's terminal output, the warehouse API (`/health`, `GET /harvest_run`), the Airflow UI and API, the warehouse database, OpenSearch's REST API; upstream's `deploy/runtest.sh` as the pattern admins know (one PASS or FAIL line per check).

## Steps

1. **Is everything up?** Does: `docker compose ps`. Seen: ten services `healthy`; `crawler`, `search-api` and `transform` only `Up`, they have no health check. Needs to know: whether "healthy" means "doing its job". Goes wrong: everything is healthy while nothing is scheduled to run: no crawl schedule exists (the crawl is a command someone runs), `HARVEST_SCHEDULE` is empty, and the DAGs start paused. A healthy stack can be idle forever. Would ask: "Is anything going to run on its own, and when next?"

2. **Watch the logs.** Does: `docker compose logs -f`, as at the end of `upprod.sh`. Seen, last 15 minutes of an idle stack: 1,374 lines from `airflow-dag-processor` (info lines about parsing DAGs, `next_dagrun=None`), 432 from `broker`, many of them warnings, `client unexpectedly closed TCP connection`, a few from everything else. Goes wrong: the stream is noise, and the warnings look like faults; whether they are harmless is not documented (assumed harmless here: the tests pass). What matters isn't there: the crawl's output goes to the terminal of whoever ran it, the harvester's output to Airflow task log files inside the `airflow-logs` volume (166 files after two days), the transformation's likewise. The crawler's own log shows one useful thing: the harvester's requests, with their `from` and `until` windows. Would ask: "Where do I see what the crawl and the harvest did?"

3. **The crawl: when, still running, how far?** Does: looks for crawl output or a record of runs. Finds: none. The crawler's database has per-record datestamps only, and they move only when a record changes; an unchanged crawl leaves no trace. A running crawl prints nothing until it ends (two hours for 428,000 files in the survey). Would ask: "Is a crawl running, how far is it, when did the last one finish, and did it finish cleanly?"

4. **The harvest.** Does: `curl 127.0.0.1:8080/harvest_run?harvest_url=…`, if they know the warehouse API exists and which port it's on. Seen: the latest run of the endpoint: `closed`, `from_date`, `until_date`, `started_at`, `completed_at`, `should_be_harvested: false` (the endpoint isn't due). Useful, and the only stage with a run record. Goes wrong: no counts (`records_harvested` is always 0), only the latest run, and no link to the crawl it covered. A failed harvest shows in the Airflow UI (a forwarded port, a login) or the task log files.

5. **The indexing.** Does: the Airflow UI for `warehouse_transform_index`, or `curl …:9200/test_datacite/_count`, or `max(opensearch_synced_at)` in the warehouse database. Goes wrong: a count says nothing on its own (walk-through B: 16 documents for 15 records); the sync time can claim more than OpenSearch holds (B, step 6).

6. **Work out T and decide.** Needs: the start of the last crawl that finished; a harvest that closed after that crawl's end; an indexing run that succeeded after that harvest. None of the first, and no link between the second and third except times in different systems. Today the admin can't state T, so they can't answer "should my file from yesterday be there?" either. Result: "probably working", which is not an answer.

## Product hat

What they wanted is a status in the style of `runtest.sh`: one line per stage, OK or not, with the time of the last run, what it did and what's next, and at the bottom T. "Done" is trusting that line without opening a dashboard. They would complain about: a stack that's green and idle; logs that are noise; having to know four ports and two logins; no answer to "is it still running".

## Developer hat

- **A crawl-run record** (start, end, outcome, counts, what changed) is the prerequisite for T and for progress; it is also what B's trace needs. Progress during a crawl needs the walk to report as it goes, which interacts with the single-threaded walk (BACKLOG, "Crawl scaling").
- **Linking stages by time** works when the clocks agree: in one compose project on one host they do; across hosts, skew enters (BACKLOG, "Datestamp window").
- **The harvest's coverage** of a crawl: a harvest that closed after a crawl ended has seen all its records only if the crawl's datestamps were all before the harvest's `until`; with whole-second datestamps and the shared datestamp per crawl, that holds with a margin of one second.
- **Indexing per harvest run:** `plan_indexing` collects the runs closed since its DAG run started, so which transform run covered which harvest is in Airflow, not in the warehouse database. Reading it needs the Airflow API (a token) or Airflow's database.
- **Log noise is upstream configuration,** a log level per service in our override file, not a code change; whether that is within the clear-box rule is a question below.
- **Health checks** for `crawler`, `search-api` and `transform` are missing; the crawler runs werkzeug's development server ("Press CTRL+C to quit"), fine for the e2e stack, not for production (BACKLOG, "Deployment").

## Answers from the owner (@weber, 2026-11-04)

- (2) **Log noise:** yes, reduce it in our override files; we will probably write our own compose files anyway.
- (3) **Follow a long crawl:** yes, progress while it runs, not only a one-shot status.
- (5) **Airflow access:** Airflow will not be exposed outside the compose environment, so the status and trace tools run inside it and get credentials injected or created at setup. Assumed (Claude), from the organisation rule against hardcoded secrets: a dedicated account with read-only rights (Airflow's Viewer role), its password generated at setup and kept with the other secrets, not the e2e stack's `airflow`/`airflow`.
- (1) **Who runs crawl and harvest:** still open; see the upstream model below.

## Upstream's scheduling model (researched 2026-11-04, sources checked by a sub-agent, key claims re-checked)

- **One DAG, an optional cron, a per-endpoint interval.** `warehouse_harvest_and_index` runs on `HARVEST_SCHEDULE` (cron; empty in `env.template`, then manual triggers only), `catchup=False`, `max_active_runs=1`. Each run asks the API which endpoints are due: an endpoint is due when `NOW() >= until_date of its latest run + harvest_schedule` (`src/app/db_methods.py`, v1.10.0). Indexing has no schedule of its own: the DAG triggers `warehouse_transform_index` for the runs it closed. `deduplicate` is manual.
- **DAGs start paused** (`AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION`); unpausing is by hand or through the API (PR #192: "`HARVEST_SCHEDULE` (cron, replaces the external trigger); DAGs start paused"). The new shared deployment repository `metadata-airflow` lists `airflow dags unpause <dag-id>` as a manual step too.
- **No push or event-driven harvesting** anywhere in the organisation; incremental harvests by `from` only. The DAG accepts `harvest_urls` to harvest given endpoints now (what our e2e test uses).
- **Monitoring is the Airflow UI**; no reports or alerts for harvest runs.
- **Open upstream bug, metadata-warehouse#158:** "If there is a failed harvest_run - the endpoint is not returned to be harvested!" A single failed harvest stops an endpoint for good, silently.
- **Since v1.10.0** (latest tag, 2026-11-02): only a new endpoint on `development`; nothing about scheduling.

Consequences for us (Claude's reading, for discussion):
- **The two layers can add up to two days.** With a daily cron and our endpoint's `harvest_schedule` of one day (`endpoint.sql`), the next day's run starts seconds before `until_date + 1 day`, finds the endpoint not due, and skips it until the day after. The interval has to be clearly shorter than the cron period, for example one hour against a daily or hourly cron.
- **#158 is exactly the "green but idle" case** of step 1: the status has to show when the last harvest failed and the endpoint has been stuck since.
- **Our setup must unpause the DAGs**, in our own compose files (the `airflow dags unpause` command at setup).
- **For the "seconds behind" ideal,** the only upstream mechanism is triggering the DAG with `harvest_urls` after a crawl, through the Airflow API. That needs an account allowed to trigger DAGs, more than the Viewer role agreed for status and trace.

Options for question 1, what runs the crawl:
- (a) A timer for the crawl in or beside the crawler container; the warehouse's cron harvests independently. Simple; the lag is crawl period plus cron period.
- (b) As (a), and the crawler triggers the harvest DAG for its endpoint after each crawl that changed something. Shortest lag without upstream changes; needs a trigger-capable account.
- (c) A DAG of ours in the warehouse's Airflow that crawls, then triggers the harvest. One scheduler and one UI; couples the crawler to their Airflow and their deployment.
- (d) Later, a watcher (inotify) feeding incremental crawls, with (b) for the harvest.

The questions as asked:

- (1) What runs the crawl in production: a timer (cron, systemd) in or beside the container, a DAG of ours in the warehouse's Airflow, or a watcher (inotify) for the "seconds behind" ideal? This decides where crawl runs are recorded and what "next run" means.
- (1) Should the e2e and production setups unpause the DAGs and set `HARVEST_SCHEDULE`, so that a healthy stack is a working one?
- (2) May our override files turn down upstream log levels (dag-processor, broker), or does that count as touching the clear box?
- (3) Is a one-shot status enough, or do you want to follow a long crawl (progress, estimated end)?
- (5) For status and trace, is reading Airflow's API (or its database) acceptable, or only the warehouse API and database plus OpenSearch?

## Gaps

- A schedule for crawl and harvest; today nothing runs unless someone triggers it (steps 1, 3).
- A record of crawl runs with start, end, outcome and counts (step 3; also B).
- Progress output from a running crawl (step 3).
- A status command that states T and, per stage, the last run, its outcome and what's next (step 6).
- Health checks for the crawler, the search API and the transform service (step 1).
- Documentation for admins of where the crawl's and the harvest's output go (step 2).

## Acceptance examples

- When the chain is up but no crawl has ever run, then the status says so and names what would start one; it does not show all green.
- When a crawl started at 02:00 and finished at 03:40, the harvest closed at 04:00 and the indexing succeeded at 04:05, then the status shows T = 02:00 and every stage OK.
- When the harvest after the last crawl failed, then the status shows T from the crawl before, marks the harvest as failed and points to its log.
- When a crawl is running, then the status says since when and how far it is (directories or files so far), and T stays at the previous crawl's start.
- When the admin runs `docker compose logs -f` on an idle, healthy stack, then nothing at warning level appears.

## Questionnaire

Sections of `../requirements-pipeline.md` this walk-through informs: 2.4 (what schedules what, on which host), 2.5 (an idle stack noticed by whom), 2.6 (how long a status may take), 2.7 (health checks, log levels, the status in the style of `runtest.sh`).
