# Demand and requirements: crawler, harvester and warehouse working together

Author: Claude (interview). Principal: @weber. Date: 2026-11-04. Interviewed: the principal in person, one section per round.
Confidence per section: answered by the principal, assumed, or unknown; see the markers. Scope: the chain from the file tree through the modama crawler (OAI-PMH) and the EOSC harvester (Airflow) to the metadata warehouse, OpenSearch and the search UI. The crawler's own requirements are in `requirements.md`; this document covers how the parts work together and how people and agents see what they are doing.

## 1. Demand

### 1.1 Problem and context   [answered]

Experience with the previous generation of the crawler: the harvester ran against a test OAI-PMH server, but search showed no results. Finding out why meant digging through several web dashboards (the workflow engine, the OpenSearch dashboard), creating an index by hand in OpenSearch, and running raw SQL to find out which harvest run was where and which actually contained entries. Every dashboard needed a port forwarded to a browser, which is annoying when everything runs in docker-compose on a remote machine. Some steps seemed to need a manual trigger, and the documented automation for regular updates looked tedious.

Wanted, in @weber's words: "some tool that shows me the current status: what is crawled, what is harvested, what is processed into OpenSearch and available through the search UI. Probably some form of progress report."

What happens if nothing is done, worst first:
- **Missing results.** Not finding something that exists is not catastrophic, but definitely unwanted. Everything visible to the user should be findable (file permissions come later).
- **Admin time.** Admin time (@weber's) is valuable; reducing it is the reason for this work. This includes the pending agent work to refine and debug the interplay of the services.
- **Bogus results** (search shows something that changed or is gone) are annoying, but not as bad as missing something.

Freshness (early answer to 2.6 and Q24 of `requirements.md`): ideally seconds behind the file system (inotify and the like); no older than a day, even for the first tries.

Boundary: the harvester, warehouse and search are used as they are, a clear box: we look inside (database, logs, APIs) but change nothing unless really necessary. Changes that would make our job easier or the outcomes better go on the wishlist below.

Mandate: tooling and workflows that make operation and development easier, including tools an agent finds useful for its own work here.

### 1.2 Current solutions   [partly: prior art found, not yet discussed]

Found in the warehouse (`v1.10.0`):
- **Airflow UI** (DAG runs, task logs): shows the harvest and indexing steps, one dashboard among several, needs a forwarded port.
- **OpenSearch Dashboards**: the index contents; another port.
- **Warehouse API** (`/health`, `/config`, `GET /harvest_run` for the latest run per endpoint).
- **`analytics/create_report.py`**: a Markdown report from SQL on the warehouse database (`summary`, `count_records_per_endpoint`, `duplicates`, `errors`). Warehouse side only; knows nothing of the crawler or the file tree.
- **`HARVEST_SCHEDULE`** (cron, in `.env`) for the `harvest_and_index` DAG; without it the DAG runs only when triggered.
- **Our e2e test** (`prototypes/crawler-e2e/`): checks counts along the chain once, for a test tree; not a status view.
- **The deployment's shell scripts** (`deploy/upprod.sh`, `downprod.sh`, `pullprod.sh`, …): the established pattern for admins, see 1.4.

Assessment (@weber): these tools were all new to him. In the end they helped; the work was finding out where to look and what for. So the existing tools stay and are made findable and accessible, not replaced.

### 1.3 Benefits   [answered; agent part assumed]

- **Investigation time.** The "search shows nothing" case took about half a day of fiddling. The target is routine operation in the future, not only the first setup.
- **Agent development efficiency** is important; @weber can't put a number on it and leaves the judgment to the agent. Assumed (Claude): the cost for an agent is the same as for an admin, multiplied by the number of iterations: each debugging round of the chain needs the state of four systems (crawler database, warehouse database, Airflow, OpenSearch), each with its own client and credentials, and the e2e test (about 2.5 minutes) reports only the first failed assertion. One command that prints the state of the whole chain, usable in a test and by hand, would cut both. To be checked with a small test before relying on it.

### 1.4 Users   [answered]

- **Admins at ER-C, @weber and others.** The others in particular need help to resolve issues in a system that is unfamiliar to them. Pattern to follow: the shell scripts in `deploy/` (`upprod.sh` and friends), so nobody has to look up or type complex commands: "look for the thing that sounds like you want to be doing". Where they work: shell commands in the deploy folder or inside a container, and `docker compose logs` (the end of `upprod.sh` follows the logs to watch startup). @weber already has a simple script of his own for the backup status.
- **How often admins look:** ideally only to resolve issues; otherwise it should just work. Proper monitoring (a signal that attention is needed) is a future topic and on the wishlist; this work is about interactive diagnostics and debugging.
- **Agents** developing and debugging the interplay (Claude): same needs as the admin, plus repeatability inside tests.
- **End users of the search,** indirectly: they should see how fresh the index is, for example the time of the last known-good complete crawl, so that they don't expect this morning's file yet; and for each entry, when the file was looked at to create it. If either needs warehouse or search UI changes, it goes on the wishlist.

## 2. Requirements
### 2.1 Use scenarios   [B simulated; A and C pending]

Walk-throughs in `walkthroughs/`, simulated by Claude on the e2e stack; questions in each go to @weber.
- **B. An admin traces a search result that looks wrong** (`admin-traces-a-search-result.md`, 2026-11-04): a file not found, a stale hit, counts that don't add up. Main findings: no crawl-run record; four stores with three different keys and no tool across them; a renamed file's old path stays in search as hit 1, confirmed live; members of a dataset are not findable by name; every query returns ten hits, so "found" needs a definition.
- **A. An admin checks whether the chain works and how far along it is** (`admin-checks-the-chain.md`, 2026-11-04): a healthy stack can be idle forever (no crawl schedule, empty `HARVEST_SCHEDULE`, paused DAGs); `docker compose logs` is noise (1,374 dag-processor lines in 15 idle minutes, broker warnings) while the crawl's and the harvest's output are elsewhere; the harvest is the only stage with a run record (`GET /harvest_run`); T can't be computed today.
- **C. A coding agent shows that the logic is sound** (`agent-checks-the-logic.md`, 2026-11-04, measured): two injected faults (a datestamp before the harvest window, a lost OpenSearch document behind a "synced" row), diagnosed correctly by a fresh agent from the documents alone in about 22 commands; what it asked for is the per-path trace of B. The assumption in 1.3 (agents pay the admin's cost per iteration) holds.
### 2.2 Demand uncertainties
### 2.3 Interfaces with existing systems
### 2.4 Operating conditions   [partly answered]

- **Scheduling** (decision log, 2026-11-04): a timer of our own runs the crawl; after a crawl that changed something, the crawler triggers the harvest DAG for its endpoint; a watcher (inotify) later. Upstream's cron (`HARVEST_SCHEDULE`) can stay as a fallback; its per-endpoint interval must then be clearly shorter than the cron period (walk-through A).
- **Airflow** stays inside the compose network. Two accounts, credentials generated at setup: a Viewer for status and trace, and one that may trigger DAGs, for the crawler.
### 2.5 Availability and reliability (consistency between file tree, OAI-PMH and search)   [partly answered]

From walk-through B's questions (@weber, 2026-11-04):
- **Freshness guarantee.** The chain states one timestamp T such that every file older than T is included. Admins see it; end users should (wishlist). "Older" is by ctime, because mtimes can predate arrival (`cp -p`, `rsync -a`, instrument software); T is the start of the last crawl that finished and whose records are all harvested and indexed (confirmed). The guarantee covers inclusion only; removals are not a concern yet, since users mostly work with fresh files.
- **Members find their dataset.** Searching for a member finds its dataset: must for datasets with few members, should for large ones (compare R31's 10 and 100). Note: compound datasets usually sit in one folder, so paths can help.
- **Findable means, for now:** a search for the file's path yields its dataset, at least with a warning if it is not hit 1 (the ranking is out of our control). File names are fine as queries only in development, with synthetic unique names. Examples where the path is not hit 1 go on the wishlist.
- **Stale entries are purged by our own tool** for the time being; a re-index is too expensive. This touches the warehouse's `records` table and the OpenSearch index, an exception to the clear-box rule in 1.1 until deletions work end to end.
- **Comparison across stages:** mostly for the e2e test; also an admin command if it runs quickly enough on production and its results are actionable and interpretable: very few or no discrepancies in normal operation.

Acceptance examples: in `walkthroughs/admin-traces-a-search-result.md`.

### 2.6 Performance
Freshness: see 1.1, and the guarantee in 2.5.
### 2.7 Testing, installation and service   [partly answered]

From an ER-C admin (relayed by @weber, 2026-11-04), for when the stack moves to `deploy/`:
- **Per-service test environments.** Bring up a test environment for specific services only. The search stack (crawler, warehouse, Airflow, OpenSearch) is substantial weight and not needed for, say, work on smbdrop and the ingest mechanisms.
- **The whole ensemble.** The production admin wants one way to bring up all services together; the search will likely interact with the management GUI in some form.
- **Tests at both levels:** tests for the whole ensemble, and more detailed tests and test environments for specific services.
### 2.8 Portability and distribution
### 2.9 Jurisdictions
### 2.10 Lifetime and decommissioning
### 2.11 Safety and risks
### 2.12 Applicable standards

## Release
Decides: @weber. Builds: Claude with @weber. Pays: unknown. Signs off: unknown.

## Wishlist for upstream (harvester, warehouse, search)

Changes that would make our job easier or the outcomes better. The bugs already parked on metadata-warehouse#151 are in `../BACKLOG.md`; this list is for what the walk-throughs add.

- **Freshness shown to end users** (1.4): the time of the last known-good complete crawl in the search UI, and per entry the time the file was looked at. Check first what the crawler can already put into the records (datestamp, `dc:date`) and what the warehouse passes through.
- **A status signal from the whole search stack** that tells an admin when attention is needed (1.4). Future monitoring; not needed to fix the basic interactions.
- **`records.opensearch_synced` only when OpenSearch took the document** (walk-through B, step 6): today it is set for the whole batch even when the bulk call reports failures.
- **`dc:date` with its time and meaning** (B, step 7): the DataCite mapping keeps only the day, as `Issued`; the crawler's date is a modification time.
- **A way to tell a match from a nearest neighbour** in the search API (B, step 8): every query returns ten hits.
- **A dataset's path as query ranks it first** (2.5): collect the examples where it doesn't, with query, expected and actual ranking.
- **`harvest_runs.records_harvested` and friends filled in** (B, step 5): already in the BACKLOG's upstream list.

## Open questions
