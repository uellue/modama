# Stakeholders

Who uses, runs and develops modama's search chain (file system crawler, harvester, warehouse, search), for walk-throughs and hallway tests. One entry per persona; each says where it comes from. Started 2026-11-15 from the chat and terminal logs of the staging field test (2026-11-10 to 15), confirmed in outline by @weber the same day (page item 388). Earlier walk-throughs (2026-11-04) used "an ER-C admin" and "a coding agent"; they are the operator and the maintainer's agent below.

## Operator

- **Who:** an ER-C admin colleague who runs one modama deployment (staging today, production later) with the scripts in `deploy/` (`upprod.sh` and friends; for staging `upstaging.sh`). Not the person who built the search chain. @weber does this today and is a co-admin; the persona is the colleague who takes over a night or a holiday.
- **Wants:** to know each morning whether the night's crawl, harvest and indexing worked, and how fresh the search is; to bring the stack up after a change or an upgrade without breaking a running night; to get it working again when it stops; "I hope an admin will only have to look at it to resolve issues" (@weber, 2026-11-04).
- **Knows:** Linux, docker compose, a shell, the institute's storage and accounts, root on the servers. Does not know OAI-PMH, Airflow, OpenSearch, the warehouse's tables, the formats or Python internals.
- **Has:** a terminal on the server (SSH); a browser only through port forwarding; the recorded terminal and the drop box folder when an agent helps.
- **Never reads:** the code, the OpenSpec specs, the decision log; reads a runbook step, a command's output and its hint, a README section that names the thing they want to do ("look for the thing that sounds like you want to be doing", @weber, 2026-11-04).
- **Seen doing (staging, 2026-11-10 to 15):** `./upstaging.sh --build`; `watch dc exec crawler modama-chain status`; `modama-crawler runs`; `df -h`, `free -m`, `top`; reading OpenSearch's logs for heap errors and raising its heap to 8 GB; restarting the Airflow scheduler that had "0 open slots"; checking an SSH tunnel to the GPU server with `journalctl` and `curl …/health`; clearing failed tasks in the Airflow UI, which showed in German; deleting a test tree from the storage; counting the index with `curl …/_count`.
- **Source:** simulated from @weber's own operator work on staging; the colleague has not been interviewed.

## Maintainer

- **Who:** a modama developer working on the formats, the extractors, the chain and its configuration (prompts, models): @weber, colleagues (among them the developer of the warehouse's interface), and coding agents briefed by them.
- **Wants:** to see which real files fail or read badly, why, and to get a fix live on staging and then production quickly; "fast turn-around when improving code here, without waiting for the whole re-crawl" (2026-11-12); to look at a file the way the search will show it; to keep track of what goes upstream.
- **Knows:** Python, the repository, the formats of their field (electron microscopy, common office and data formats); for agents, only what is in Git and the briefs.
- **Has:** the development VM (no access to the real data), the shared checkout that staging builds from, the browse tool on staging, the drop box folder `.claude/field-tests/` for samples and reports; agents have no shell on the server.
- **Never reads:** whole logs of a night (they ask a tool for what matters); the warehouse's internals unless a trace points there.
- **Seen doing:** `modama-chain review --browse … > review.md` into the drop box; `failed-headers.sh` for the first bytes of failed files; "Save for Claude" snapshots from browse with a message; copying a sample file into the drop box and deleting it afterwards; deciding how a record should read from examples; merging, rebuilding staging and waiting for the 19:00 crawl; py-spy and perf on the workers; test queries in AI mode.
- **Source:** @weber in this session (interview by conversation, 2026-11-10 to 15); agents' needs measured in walk-through C (2026-11-04).

## Search user

- **Who:** a scientist or research data manager at ER-C who looks for data in the institute's storage: their own recent work, a colleague's acquisition, files of one kind (for example Merlin acquisitions), a presentation.
- **Wants:** to find it and open it (the browse link), to know whether the answer is complete and fresh, and to ask about the search itself ("where are my AppleDouble files?", R46).
- **Knows:** their own data and its jargon; not how the index is built, which formats are read, or how fresh it is.
- **Has:** a browser inside the institute; AI mode without a login (for now).
- **Never reads:** documentation; at most the answer's caveats and the cited datasets.
- **Seen doing:** only @weber's test queries: "Find Merlin acquisitions" (2026-11-11), "the latest presentation of [a person] on RDM challenges", then "There should also be pptx datasets?" (2026-11-14), some of them genuine preparation of the demo's slides; the demo audience on 2026-11-17 (research data management experts, among them the project's sponsors).
- **Source:** simulated. To make it real (@weber, 2026-11-15, item 388): the queries stored by OpenSearch (all @weber's so far), the demo audience's questions, colleagues trying a few questions; the meta-requirement is to collect such samples easily, with the user's feedback and permission.
