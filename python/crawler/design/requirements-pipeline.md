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
- **Our e2e test** (`prototypes/crawler-e2e/`; since 2026-11-05 `prototypes/search-stack/`, with traces): checks counts along the chain once, for a test tree; not a status view.
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
### 2.2 Demand uncertainties   [answered]

Confirmed by @weber (2026-11-04), nothing to add for now; fixed later as we learn more.

- **Upstream is moving.** The warehouse switched to Airflow in v1.10.0 (2026-11-02); a shared Airflow deployment (`metadata-airflow`) is new; staging and production setups are still being worked out upstream. Each upgrade can change the stores, keys and schedules that our tools read.
- **Deletions** don't work end to end (crawler and harvester); until they do, our own purge stands in (2.5).
- **Growth** of the tree and its user base (R10 of `requirements.md`); the visible quarter of the tree today, the rest behind permissions.
- **Per-user access** to search results comes later (`requirements.md`); it may change what the warehouse may hold.
- **Ranking** is upstream's: whether a path query ranks its dataset first is measured, not controlled (2.5).
- **Staying with upstream:** we expect to run the EOSC warehouse; if we become unhappy with upstream, we would probably fork it rather than replace it. So tools may know the warehouse's internals, kept in one place (walk-through C).
- **More sites:** search is planned for more modama sites, not only ER-C (2.8).

### 2.3 Interfaces with existing systems   [answered]

| System | Direction | Through | Identity | Ours? |
|---|---|---|---|---|
| Data tree | read | mount, read-only | a reader with full access (`requirements.md`) | storage: no |
| Crawler database | read, write | PostgreSQL | crawler | yes |
| Warehouse harvester | it reads us | OAI-PMH, `oai_dc` | none (internal network) | no |
| Airflow | read; trigger the harvest DAG | REST API inside the compose network | Viewer (status, trace); a trigger-capable account (crawler) | no |
| Warehouse database | read; purge stale rows | PostgreSQL | read-only account; a separate one with delete rights for the purge | no |
| OpenSearch | read; purge stale documents | REST | read; delete for the purge | no |

Write access for the purge is acceptable (@weber), as long as nothing can damage the data in the file system: the search index and the warehouse are derived data and can always be recreated from the files. Nothing in the chain gets write access to the data tree.
| Search API | read | HTTP | none | no |
| Data browser | its URLs are our identifiers | `https://er-c-data-mgmt.fz-juelich.de/browse/?path=` | none | modama |
| Management GUI | both ways, by links: a link to the search or a search box in the GUI; search hits link to the existing GUI (its data browser) | URLs | the user's own session | modama |

Upstream quirks we depend on: the identifier cut after the last `:`, the URL as OpenSearch `_id`, `endpoint::path` record ids, the due rule `until_date + harvest_schedule`, metadata-warehouse#158 (walk-throughs A to C).
### 2.4 Operating conditions   [partly answered]

- **Scheduling** (decision log, 2026-11-04): a timer of our own runs the crawl; after every finished crawl (refined 2026-11-05), the crawler triggers the harvest DAG for its endpoint; a watcher (inotify) later. Upstream's cron (`HARVEST_SCHEDULE`) could stay as a fallback; its per-endpoint interval must then be clearly shorter than the cron period (walk-through A), and the crawler's store lock makes its harvests come back later rather than race a crawl. The search stack leaves it off.
- **Airflow** stays inside the compose network. Two accounts, credentials generated at setup: a Viewer for status and trace, and one that may trigger DAGs, for the crawler.
- **The operator stays in control** (must, @weber 2026-11-12): "admin gets help, but not arcane magic, and gets easy way to influence what is happening." Every service and worker uses sensible defaults on any machine, from probing the environment it can see (CPUs, cores, limits, memory), rather than numbers the operator has to maintain ("the whole code should do it right by itself and not rely on the admin for this"). What it chose, and why, is visible; overriding it is easy and documented. Anything complex the operator needs to know to set the service up is supported by helpers: documentation of who does what and why, and helper scripts in the pattern of 1.4. Origin: the CPU budget (change `cpu-budget`), @weber "a bit overwhelmed with all the questions about the environment and what to set how".
- **CPU budget** (@weber, 2026-11-12): every service adapts its processes and threads to the machine it runs on and, by default, does not oversubscribe it ("we will run on big machines where this is super super important to avoid oversubscription. Of course we need to adapt to the local machine always. The dev server is not the same as the production server."). The code computes the budget itself at start ("the whole code should do it right by itself and not rely on the admin for this. I wouldn't want to maintain this myself as an admin of the service."): in each process tree, processes × threads per process stays within the CPUs that process may use (affinity or cpuset, and the cgroup CPU quota), not the machine's total; a fractional quota is rounded down, at least 1, for math pools, so that they stay within it, and up for I/O-bound pools, which mostly wait (@weber, 2026-11-12). Math pools (BLAS, ONNX Runtime, tokenizers) count physical cores; I/O-bound pools may count logical CPUs, since "for I/O bound tasks, hyperthreading works very well" (@weber, 2026-11-12); a measurement may change the count for a math pool. No service relies on a library's default thread count where several of its processes run. No CPU split per container by default ("no split. We may want to reduce the number of available CPUs to specific services since a lot of them are running in parallel"); a limit set for a service later is honoured by the same count. Background services (crawl, harvest, indexing) run at a lower CPU weight than the services that answer users' searches, so that live requests, and other work on the machine, go first when the CPUs are contended ("What about LOWERING the priority of crawler, harvest and indexing tasks, and keeping the live requests at normal prio? That also helps to keep dev work running on the machine, and services we don't see / handle.", @weber, 2026-11-12). Overrides are few, named and documented, for measurements and for the operator; the defaults must be right without them. Each service logs its budget at start and says when an override is active; a diagnostic script shows every service's budget and its reasons on the machine at hand ("The operator stays in control"). Checked on staging during an indexing run, per container: CPU time over the run (`cpu.stat`) not above the CPUs the container may use, and no batch process with more threads than its budget; the machine's load average is context, not the criterion (it counts NFS waits and the devvms). Background: [`docs/research/cpu-oversubscription.md`](../../../docs/research/cpu-oversubscription.md).
### 2.5 Availability and reliability (consistency between file tree, OAI-PMH and search)   [partly answered]

From walk-through B's questions (@weber, 2026-11-04):
- **Freshness guarantee.** The chain states one timestamp T such that every file older than T is included. Admins see it; end users should (wishlist). "Older" is by ctime, because mtimes can predate arrival (`cp -p`, `rsync -a`, instrument software); T is the start of the last crawl that finished and whose records are all harvested and indexed (confirmed). The guarantee covers inclusion only; removals are not a concern yet, since users mostly work with fresh files.
- **Members find their dataset.** Searching for a member finds its dataset: must for datasets with few members, should for large ones (compare R31's 10 and 100). Note: compound datasets usually sit in one folder, so paths can help.
- **Findable means, for now:** a search for the file's path yields its dataset, at least with a warning if it is not hit 1 (the ranking is out of our control). File names are fine as queries only in development, with synthetic unique names. Examples where the path is not hit 1 go on the wishlist.
- **Stale entries are purged by our own tool** for the time being; a re-index is too expensive. This touches the warehouse's `records` table and the OpenSearch index, an exception to the clear-box rule in 1.1 until deletions work end to end.
- **Comparison across stages:** mostly for the e2e test; also an admin command if it runs quickly enough on production and its results are actionable and interpretable: very few or no discrepancies in normal operation.

Acceptance examples: in `walkthroughs/admin-traces-a-search-result.md`.

### 2.6 Performance   [answered]

Freshness: see 1.1, and the guarantee in 2.5: T no older than a day, ideally seconds.

Measured so far:
- **Crawl:** the visible quarter of `/er-c-data` (525,533 files, 17.9 TB) took two hours for 428,000 files, about 60 files per second, single-threaded (2026-10-27). The whole tree, if the proportions hold, is about four times that: some 8 hours, a third of the daily budget.
- **OAI-PMH:** all 428,856 records harvested by oaipmh-scythe (the harvester's client) in 58 s, without the warehouse.
- **Warehouse:** in the e2e stack, one harvest-and-index DAG run for one changed record takes about 70 s, mostly Airflow overhead. Transformation and embeddings for 430,000 records are **not measured**; they are the likely bottleneck of a first full harvest.
- **Change rate:** hundreds to thousands of new files a day (R10); 58 changed files in a week in the visible quarter (2026-10-15).

Answered (@weber, 2026-11-04):
- **A first full harvest** may take long (hours or days) if the status shows its progress.
- **Status and trace** within about a minute (walk-through A); **the stage comparison** on production may take a while to produce a large report. Settled when we get there.
### 2.7 Testing, installation and service   [partly answered]

From an ER-C admin (relayed by @weber, 2026-11-04), for when the stack moves to `deploy/`:
- **Per-service test environments.** Bring up a test environment for specific services only. The search stack (crawler, warehouse, Airflow, OpenSearch) is substantial weight and not needed for, say, work on smbdrop and the ingest mechanisms.
- **The whole ensemble.** The production admin wants one way to bring up all services together; the search will likely interact with the management GUI in some form.
- **Tests at both levels:** tests for the whole ensemble, and more detailed tests and test environments for specific services.
### 2.8 Portability and distribution   [answered: later]

First make it work at ER-C and learn from that. Streamlining configuration and deployment per site is a bigger endeavour of its own, branding included (@weber, 2026-11-04). The points below are notes for then, not requirements now.

- **More modama sites** will run the search (2.2). Per site, at least: the data root, the browse URL base and the OAI identifier's host (both ER-C's today, in `records.py`), the warehouse endpoint registration, credentials.
- **Distribution:** container images and compose files in `deploy/`; per service or service group, so that a site or a developer can bring up the search stack alone or everything together (2.7). "Search is deployable on its own" is already decided (`architecture.md`, 2026-10-16).
- **The warehouse** comes from upstream's repository and images, with our compose files and settings around it.
### 2.9 Jurisdictions   [answered]

- **Records stay inside the institute:** the warehouse runs internally (decision log, 2026-11-04), so owners' names and paths in the records are an internal matter (Q22 of `requirements.md`, narrowed).
- **Except through the search API's language models.** The search API (`data-commons-search`) has chat and agent features that call external LLM providers (default `cesnet/agentic`, fallback `mistralai/mistral-medium-latest`, keys for OpenAI, OpenRouter, Mistral). With real keys, queries and the records they retrieve, paths and owner names included, would leave the institute. The e2e stack has placeholder keys; `/search` itself uses local models (fastembed embeddings, a local reranker). Downloading the models from Hugging Face is network egress, not data egress.
- **Answered (@weber, 2026-11-04):** external services approved for the institute are fine, for example Blablador (FZJ). The team plans to run its own language model service on a large machine, *grace*. So the requirement is: language model calls go only to approved services; none of the commercial providers in the default configuration.
- **Licences:** the warehouse and the search are upstream's (their licences apply as they are, nothing is redistributed by us beyond our compose files); the crawler's own are in `requirements.md`, 2.9.

### 2.10 Lifetime and decommissioning   [assumed from the record]

- The search index and the warehouse are derived data and can be recreated from the files (2.3); losing them costs time, not data.
- The identifiers are browse URLs; they outlive a re-index only while the data browser keeps its URL scheme (Q25 of `requirements.md`).

### 2.11 Safety and risks   [answered]

- **No write access to the data tree** anywhere in the chain (2.3); the purge writes only to derived stores.
- **Stale and missing entries** (walk-throughs B and C); the purge and the stage comparison are the mitigation.
- **Silent stalls:** a failed harvest stops an endpoint for good (metadata-warehouse#158), a paused DAG never runs; the status must show them (walk-through A).
- **Credentials:** read-only accounts for status and trace, a trigger account for the crawler, delete rights only for the purge; generated at setup, never committed (organisation rule).
- **Load:** a full crawl's I/O on the storage that instruments write to is not measured (`requirements.md`, 2.11). To begin with, crawl outside business hours until the impact can be judged (@weber); this constrains the crawl timer (2.4) and, with eight hours for the whole tree (2.6), uses most of a night.
- **External LLMs** in the search API, see 2.9.

### 2.12 Applicable standards   [answered from the record]

OAI-PMH 2.0 and `oai_dc` towards the harvester (incremental harvesting by `from`/`until`, `deletedRecord` once deletions work); DataCite inside the warehouse (its mapping, not ours); the institute's IT rules for the deployment.

## Release
Decides and signs off: the modama maintainer team, @weber included. Builds: Claude with @weber. Owns and controls: the team, for everything in the chain except Blablador (an FZJ service).

## Wishlist for upstream (harvester, warehouse, search)

Changes that would make our job easier or the outcomes better. The bugs already parked on metadata-warehouse#151 are in `../BACKLOG.md`; this list is for what the walk-throughs add.

- **Freshness shown to end users** (1.4): the time of the last known-good complete crawl in the search UI, and per entry the time the file was looked at. Check first what the crawler can already put into the records (datestamp, `dc:date`) and what the warehouse passes through.
- **A status signal from the whole search stack** that tells an admin when attention is needed (1.4). Future monitoring; not needed to fix the basic interactions.
- **`records.opensearch_synced` only when OpenSearch took the document** (walk-through B, step 6): today it is set for the whole batch even when the bulk call reports failures.
- **`dc:date` with its time and meaning** (B, step 7): the DataCite mapping keeps only the day, as `Issued`; the crawler's date is a modification time.
- **A way to tell a match from a nearest neighbour** in the search API (B, step 8): every query returns ten hits.
- **A dataset's path as query ranks it first** (2.5): collect the examples where it doesn't, with query, expected and actual ranking.
- **`harvest_runs.records_harvested` and friends filled in** (B, step 5): already in the BACKLOG's upstream list.
- **A failed harvest fails the DAG run** (found by the e2e scenario "A failed harvest", 2026-11-05): when the harvest task of `warehouse_harvest_and_index` fails, the DAG run still ends in `success`; only `harvest_runs.status` says `failed`, so Airflow's own view shows nothing wrong.

## Handover: what the builder needs first

**Unknowns**
- Duration of a first full harvest and indexing (embeddings) at ER-C scale: measure, with progress in the status (2.6).
- I/O load of a full crawl on the instruments' storage: crawl at night until judged (2.11).
- The language model service on *grace*: endpoint, and whether the search API can use it (2.9).
- How long identifiers must stay valid (Q25 of `requirements.md`, 2.10).
- Per-site configuration and branding: later, a project of its own (2.8).

**Interfaces outside our control** (2.3): the warehouse harvester, database and API; Airflow; OpenSearch; the search API and its language model providers. Their quirks: the identifier cut after the last `:`, the URL as OpenSearch `_id`, `endpoint::path` record ids, the due rule `until_date + harvest_schedule`, paused DAGs, metadata-warehouse#158, `opensearch_synced` set for failed documents.

**Risks** (2.11): stale and missing entries without anyone noticing; silent stalls of the harvest; credentials with more rights than needed; crawl load on production storage; records reaching unapproved language model services.

## Open questions

- The configuration of *grace* (planned language model service): not in this repository and not reachable from the development VM; for @weber, resolves 2.9.
