# Demand and requirements: maintaining and operating modama's search

Author: Claude, drafted from the chat and the recorded terminal of the staging field test (2026-11-10 to 15) and three walk-throughs. Principal: @weber. Date: 2026-11-15. Status: **draft**; the requirements below are proposals, each with its source, until @weber confirms them. Scope: the people who keep the search chain (file system crawler, harvester, warehouse, search) running and improving once it is in production: the operator, the maintainer, and the search user as far as their needs reach the other two. Builds on `requirements-pipeline.md` (how the stages work together, 2026-11-04) and `requirements.md` (the crawler); personas in `stakeholders.md`; acceptance examples in `examples.md`.

Request (@weber, 2026-11-15): "The work in the last days (monitoring runs, finding and fixing issues with specific formats, testing queries to the chat based search) starts to transition to what a maintainer of Modama, and an operator of Modama will be doing. Can you review our chat logs and all commands you can see in terminal logs to start drafting an extension to the requirements?" And: "one can use the walkthrough approach more to try see things from the perspective of a search user: What are they actually trying to accomplish, and how can we best support them?"

## 1. Demand

### 1.1 Problem and context   [from the logs; to confirm]

Five days of staging on the real tree (1.3 million datasets, nightly crawls since 2026-11-11) worked, and showed what running it takes. Each morning @weber ran commands an agent proposed, pasted or recorded their output, and the agent diagnosed: an indexing run killed by OpenSearch's heap (2026-11-14), workers idle behind a scheduler with "0 open slots", a tunnel to the GPU server, a status line showing the wrong run (item 386), 139,000 stale records in the index (387). Format work ran the same way: review lists, samples copied into a drop box, "Save for Claude" snapshots, decisions on how records read. It worked because the person knew the chain and the agent could read everything in the shared checkout. Neither holds for an admin colleague on a holiday night, or for a new maintainer.

If nothing is done, worst first: the search goes stale or wrong and nobody notices; every incident needs @weber; format fixes stay slow because every sample and server command goes through one person; search users hit an assistant written for another kind of portal and stop trusting it.

### 1.2 Current solutions   [from the repository]

`modama-chain status | trace | review | browse`, `modama-crawler runs`, the crawl timer and the harvest started by the crawl, the CPU budget, `upstaging.sh`/`downstaging.sh`, the staging runbook, the field-test scripts (`monitor.sh`, `index-tasks.sh`, `index-failures.sh`, `batch-times.sh`, `failed-headers.sh`), the open-items page as a tracker. Upstream: the Airflow UI, OpenSearch's REST API. What they lack is listed per walk-through below.

### 1.3 Benefits   [to confirm]

Admin time, the reason for this work since 2026-11-04 ("Admin time (i.e. my time!) is valuable!"); a colleague can operate it without the author; format fixes in hours instead of nights; a search users trust.

### 1.4 Users   [partly; `stakeholders.md`]

Operator, maintainer (people and coding agents), search user. How many of each, and who operates production, is open (Q1).

## 2. Requirements

### 2.1 Use scenarios

Walked on 2026-11-15 (simulated, on paper; questions in each walk-through):

- **P1. The operator checks the night's run the morning after** (`walkthroughs/operator-morning-after.md`): a re-walk of walk-through A against today's tools. Most of A's gaps are closed; still missing: one entry command, a status that recovers T and says what to do when it is `unknown`, counts per stage (the 139,000 stale records were invisible), a baseline for the night's numbers, a review with "new since", runbooks for the three incidents seen, a safe re-run.
- **P4. The maintainer fixes a format that fails on real files** (`walkthroughs/maintainer-format-fails.md`): the loop exists (review, browse, extractor identity, subtree crawl); the cost is the person in the middle (samples, server commands, decisions without examples), and there is no grouping by error, no reproducer path for private files, no "one format through the whole chain now", no before-and-after.
- **P6. A search user looks for their own recent work** (`walkthroughs/search-user-finds-own-work.md`): the assistant argues the question is out of scope because its instructions describe a public portal, some cited links are cut, it can't answer questions about the search itself (R46), and nobody can report a wrong answer.

Proposed for later walks (@weber, 2026-11-15: "collect more as we go"), each with where it was seen:

- **P2. The operator upgrades with new formats:** `./upstaging.sh --build` after a merge, the identity change that re-extracts the whole tree (2026-11-14), held-back formats, "no upgrade during harvest or indexing".
- **P3. The operator handles an incident during indexing** (measured walk possible on the e2e stack with an injected fault): OpenSearch heap, scheduler slots, the GPU tunnel (2026-11-14).
- **P5. The maintainer improves how records read and how the assistant answers:** deck representation (repeated footers, titles in text boxes), prompts and models, feedback and retry (item 385).
- **P7. The maintainer adds a new format collection:** covered by the developer-docs hallway test (2026-11-13, `hallway/`).
- **P8. The operator sets up the search at another modama site:** "We are planning to run search on more modama sites" (2026-11-04); configuration per site, branding, a GPU host or none.
- **P9. The maintainer finds a performance problem in production:** "watch production in action, a bit like we did with staging … and look for inefficiencies and bottlenecks" (2026-11-12); py-spy, perf, the CPU budget, the embedding throughput.
- **P10. A search user looks for a colleague's acquisitions by instrument or kind:** "Find Merlin acquisitions" (2026-11-11), one of the demo queries.
- **P11. The operator answers "my file is missing":** walk-through B (`walkthroughs/admin-traces-a-search-result.md`, 2026-11-04), to re-walk with `trace` and `browse`.

### 2.2 Proposed requirements

Each names its source: a request, a walk-through step, a page item. IDs are provisional (OP operator, MA maintainer, SU search user).

**Operator**

- **OP1 One entry point per deployment.** Status, review, re-run and logs through one documented command, from any folder, in the style of `deploy/`'s scripts. Sources: @weber 2026-11-04 ("look for the thing that sounds like you want to be doing"); P1 step 1; E1.
- **OP2 A status that is right and says what to do.** It recovers after a manual re-index or a failed night (T from the last complete chain, the gap named), and every non-OK line has a next step. Sources: P1 step 2; item 386; E2.
- **OP3 Counts per stage, and their difference.** Datasets, records published, warehouse records, documents in the index; a difference is flagged and points to its remedy (the purge, `purge-stale-records`, item 387). Sources: @weber 2026-11-04 (an admin command "if it runs quickly enough and produces actionable, interpretable results"); P1 step 4; E4.
- **OP4 The night compared with the night before.** Failures, warnings, datasets, records changed side by side; a jump flagged. Sources: P1 step 3; E3.
- **OP5 A safe re-run.** One command re-runs what failed, refuses while a stage runs, and the status shows it afterwards. Sources: items 364, 365; P1 step 8; E5.
- **OP6 No disruption by accident.** Rebuilds and restarts warn or refuse while a crawl, harvest or indexing runs; an upgrade says beforehand what it will re-do (the whole tree or some formats). Sources: the standing rule "no upgrade during harvest or indexing" (2026-11-13); the scheduler's "0 open slots" after a worker was recreated (2026-11-14); P1 steps 7 and 8; P2.
- **OP7 A signal when attention is needed.** The stack says when a night failed, the search is stale, or a disk will fill; until then, the status covers it. Sources: @weber 2026-11-04 ("The whole search stack should probably emit some status signal that lets an admin know if attention is needed", wishlist then); P1 step 6.
- **OP8 Runbook entries for known incidents.** Symptom, the command that confirms it, the fix, whether it is safe now: OpenSearch heap, scheduler slots, the GPU tunnel so far. Source: P1 step 7.
- **OP9 Sensible defaults, probed, with helpers for the rest.** "The whole service, workers and whatnot should use sensible defaults on any machine, probe the environment they can see etc. … any complex thing the operator of the service needs to know when setting it up should be supported by appropriate helpers" (@weber, 2026-11-12, item 152); "I wouldn't want to maintain this myself as an admin of the service" (114). The CPU budget is the first case.
- **OP10 Recreate rather than back up.** The index, the warehouse and the crawler's tables are derived data; what matters is reproducing a failure in a test and bringing up a fresh deployment; migrations exist to avoid a recrawl, and a recrawl should be cheap enough "to not shed tears" (@weber, 2026-11-12).
- **OP11 A staging that resembles production.** "What we have now is 'wish.com staging' … it gets the job done today" (@weber, 2026-11-12). What production-like means (data, accounts, hosts, the GPU host) is open (Q6).

**Maintainer**

- **MA1 Failures grouped and dated.** The review groups failed extractions by format and error, with counts, one example link each, and "new since the last crawl". Sources: P4 step 1; @weber 2026-11-13 ("the link list to the review browse tool works well"); E6.
- **MA2 Agents see agreed parts of staging directly.** Read-only access for agents to agreed subtrees and to the review, through a drop box with a README now and an MCP server on staging that enforces the limits later. Sources: items 370, 372, 373; @weber 2026-11-14 ("a proper MCP server running in staging resp. production that enforces these limits could be very very nice as an actual feature"); debrief note 2026-11-14 (reviewing "files and events of interest" together).
- **MA3 A reproducer without the private file.** A documented way to get what a fix needs from a failing file (structure, header, error, reader version) without its content: a fixture script per format, run by the person on the server, as for K2IS and BLO. Sources: P4 step 3; E7. The rule that fixtures are public or self-made stays.
- **MA4 Fast turn-around through the whole chain.** For one path, for all files of one kind, and for a subtree: extraction, harvest and indexing on demand. Sources: @weber 2026-11-12 (three commands, "fast turn-around when improving code here, without waiting for the whole re-crawl"); `crawl --path` covers the subtree; P4 step 6; E9.
- **MA5 Before and after a fix.** After the crawl that took up a fix, the review shows per format which previously failing files now succeed and which still fail. Sources: P4 step 7; E8.
- **MA6 Upstream items tracked to the end.** Each issue or patch for an upstream project has a state (found, patched here, posted, merged, released, our workaround removed); "only truly closed if the issue is addressed, merged, and released, and we moved forward to the released version here", or "fire and forget" as a courtesy (@weber, 2026-11-12).
- **MA7 Decisions prepared with examples.** A maintainer (or agent) who needs the principal's decision brings the ways to find the answer, the most promising one, and options with an example of what each would look like, not "should I do A or B?". Source: @weber's debrief note of 2026-11-15. This is a working rule more than a product requirement; recorded here because it shapes the tools (browse snapshots, review links) that make examples cheap.
- **MA8 Known noise by type, not by name.** Name-based exclusions are an admin's stop-gap; the lasting rule is a dataset type the deployment leaves out (item 383, BACKLOG).
- **MA9 Prompts and models per deployment, with feedback and retry.** Try another prompt or model on a saved question, compare, keep the verdict. Source: item 385 (@weber, 2026-11-14: "we'll probably have to tailor these parts of the warehouse for modama, or even per modama deployment"); P5.
- **MA10 Watching production for inefficiencies.** The same observation tools as on staging (status, profiles, CPU use per service, embedding throughput) usable in production. Source: @weber 2026-11-12, item 112.

**Search user** (through the maintainer and the operator)

- **SU1 The assistant knows what this search is.** Its instructions describe the deployment's content (an institute's file store: data, documents, presentations, code), not a public catalogue. Source: P6 step 2; E10.
- **SU2 Questions about the search are answered (R46).** Which formats are read, what is excluded and why, how fresh the index is (T). Sources: R46 (2026-11-14); P6 step 4; E11, E12.
- **SU3 Feedback and samples, with permission.** A user can mark an answer wrong or incomplete and add a comment; the question, the answer and the comment are kept for the maintainers only with the user's agreement. Sources: @weber 2026-11-15 ("the meta-requirement is to easily collect these samples, with user feedback and their permission"); item 385; P6 step 5; E13.
- **SU4 Nothing visible is missing; missing is worse than bogus.** Carried over from 2026-11-04 (`requirements-pipeline.md` 1.1); measured by the stage counts (OP3).
- **SU5 Access before production.** A login before production (item 178, 2026-11-12); per-user access to results later (`requirements.md`); until then, what the crawl account may read is what everyone sees (Q5).

### 2.3 to 2.12

Not drafted yet. The walk-throughs' questionnaire sections list what is unanswered: who operates production and with how much time (2.7), what happens when the search is stale or wrong and nobody notices (2.5), personal data in queries, feedback and owners' names (2.9), which actions an agent or operator may take unattended (2.11).

## Open questions

Each with ways to find the answer and the one that looks most promising to start, so that the question asks for a decision, not for the research.

- **Q1 Who operates production, and with how much time?** Ways: ask the ER-C admin team; look at how the existing modama services (`deploy/`) are operated today and by whom; decide that the operator is @weber until the search is stable. Most promising: the second, since it shows the real practice and its limits; then the first. [lean: the same people who run `deploy/` today, with OP1 to OP8 as the condition for handing over]
- **Q2 What should the status say after a manual re-index or a failed night (OP2)?** Ways: define T from the latest complete chain and name gaps; keep the strict T and make `retry` restore the link; show both. Most promising: write the three status lines for the 2026-11-15 situation side by side and pick by eye. [lean: the latest complete chain, with the gap named]
- **Q3 Which field-test scripts become commands (OP1, OP3, OP8)?** Ways: count which ones were used on more than one morning (from the recorded terminals: `index-failures.sh`, `batch-times.sh`, `index-tasks.sh`, `failed-headers.sh`, the monitor); ask which ones an operator would understand; fold them into `status`. Most promising: the count, already in the logs. [lean: counts per stage and the failed-indexing summary into `status`; `failed-headers.sh` into `review`; the rest stay developer tools]
- **Q4 Which subtrees may agents read directly (MA2)?** Ways: @weber names them (item 370: the infrastructure project, LiberTEM's test data); derive them from the storage's permissions (a group that is public inside the institute); start with the drop box and see what is asked for. Most promising: name two now, extend by need. [lean: the two named, through a read-only mount, before the MCP server]
- **Q5 Who sees which records before per-user access (SU5)?** Ways: index only areas readable by everyone in the institute; index everything the crawl account reads and rely on the login; ask data protection. Most promising: list which top-level areas the crawl account reads that a typical user cannot (one `find -maxdepth 2` with two accounts), to see how big the difference is. [lean: measure first; decide with the numbers]
- **Q6 What makes staging production-like (OP11)?** Ways: list the differences (accounts, host, data, GPU host, compose files, `deploy/` vs. `prototypes/`); move staging onto `deploy/`'s compose files; a second small production. Most promising: the list of differences, then decide which matter. [lean: staging from `deploy/` once the search moves there]
- **Q7 Where do feedback and samples live, and for how long (SU3)?** Ways: in the warehouse's database (upstream's tables, if they have any); in a store of ours next to the crawler's; as files in the drop box for now. Most promising: check what upstream's AI mode already stores (its `top_queries` index keeps queries today) and what EOSC Data Commons plans. [lean: look at upstream first; decide after the demo]
