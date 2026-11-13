# Search stack

The modama search, as one compose project: the crawler serves the data tree over OAI-PMH, the EOSC harvester (inside the warehouse's Airflow) harvests it into the metadata warehouse, which indexes it in OpenSearch for the search API and its web frontend, matchmaker.

```
crawl-timer ─▶ crawl ─(after each crawl: start harvest)─▶ Airflow ─▶ harvester ─▶ warehouse ─▶ OpenSearch ◀─ search-api ◀─ matchmaker
crawler (OAI-PMH) ◀────────────────────────────────────────────────┘       └─ transform, broker, postgres
  ├─ crawler-db
  └─ sssd (owners' names) ◀─ directory (test: ldap)
```

It is our own composition of the upstream images (EOSC metadata-warehouse `v1.10.0` in `../EOSC-Data-Commons/metadata-warehouse`, built from there, its Airflow image with the patches in `patches/warehouse/` applied by `warehouse-airflow.Dockerfile` on top of upstream's image, which the build-only service `airflow-upstream` builds unchanged; data-commons-search `0.10.2`, with the patches in `patches/search-api/` applied by `search-api.Dockerfile`: its keyword search queries the root copies of the nested title, description and subject fields; matchmaker `0.14.0`, built from upstream's source with the patches in `patches/matchmaker/` applied by `matchmaker.Dockerfile`: AI Mode works without login, see "AI Mode without login"), shaped like `deploy/` so that it can move there:

- **Secrets as files**, from `MODAMA_SECRETS_DIR`, which must be set; `./uptest.sh` writes a `.env` (gitignored, as `deploy/.env`) that points it at the throwaway test values in `testconf/secrets/`. One file per concern, and each service gets only the files it needs: the crawler has no warehouse credentials; `modama-chain` reads with a read-only database role and an Airflow Viewer account; the search API has its own role, owner of its database `appdb` only; the crawler's Airflow account (only in `crawl-timer`) has a role `harvest-trigger` that may start and read runs of the harvest DAG and nothing else (Airflow needs edit on that DAG to start its runs, so it could pause that one DAG).
- **One-shot init services** instead of scripts on the host, idempotent, run on every start and restarted on failure: `warehouse-init` (`init-warehouse.sh`: databases, schema, index, our endpoint as the only active one, the roles) `airflow-init` (Airflow's database and admin), and `airflow-accounts` (`init-airflow.sh`, once the dag-processor has written the DAGs, since Airflow's per-DAG permissions exist only then: the crawler's role and the two accounts, created when missing; to change a password, delete the account and restart). `crawler-migrate` (`modama-crawler migrate`) brings `crawler-db`'s schema to the image's before `crawler` and `crawl-timer` start, and is not restarted: when it refuses or fails, `up` fails within seconds and names it ("Upgrade" below).
- **The crawl starts the harvest:** `crawl-timer` crawls every day at 19:00 UTC (20:00 CET, 21:00 CEST; outside business hours while a full crawl takes hours), and at once when the last finished crawl is more than a day old (after a restart or a killed crawl). Every finished crawl starts the harvest DAG for the crawler's endpoint after its commit. Upstream's own schedule stays off, and the DAGs are unpaused at creation (none has a schedule, so they run only when started). `docker compose stop` passes SIGTERM to a running crawl, which records its run as failed.
- **The broker waits 48 hours for an acknowledgement** (`consumer_timeout` in `broker.conf`), not RabbitMQ's 30 minutes. Celery under Airflow acknowledges a task when it ends, and on the default queue the harvest and the harvest DAG's wait for the indexing run take hours. With 30 minutes the broker closed the default worker's channel, and the worker took no task until that one had ended (staging finding F17). `./runtest.sh` checks the broker's value; `consumer-timeout/run.sh` reproduces the failure in a compose project of its own, without published ports: about 4 minutes, exit 0 when a second task runs during a long one; `REPRO_BROKER_CONF=../broker.conf consumer-timeout/run.sh` runs it with this setting. Its host name is fixed (`hostname: broker`), so that its RabbitMQ node, `rabbit@broker`, and the queued messages survive a recreated container.
- **Left out from upstream's compose:** pgadmin, tool-registry, opensearch-dashboards, coordinator (so matchmaker, upstream's `frontend`, uses the hosted Data Player), and the toolmeta DAG bundle (it polls GitHub every minute; without it the dag-processor logs about 230 lines in 15 minutes instead of 1,374).

## Test deployment

```bash
./uptest.sh            # build and start, wait until healthy; the first start takes a while
./runtest.sh           # quick checks, one PASS/FAIL line each
./downtest.sh --reset  # stop and delete all state; ./uptest.sh then starts fresh
./uptest.sh && ./runtest.sh e2e   # the end-to-end test, on a fresh stack, about 6 minutes
# The e2e test includes a chat question, which needs a language model key ("Secrets for the
# end-to-end test" below). Without a key the chat test fails; E2E_CHAT=0 ./runtest.sh e2e
# skips it with a warning.
export MODAMA_SECRETS_DIR=~/.config/modama/e2e-secrets
./downtest.sh --reset && ./uptest.sh && ./runtest.sh e2e
./downtest.sh          # stop, keeping the state
```

### Secrets for the end-to-end test

The test values in `testconf/secrets/` are throwaway and committed; only the language
model key is real. Make a folder outside the checkout, once:

```bash
mkdir -p ~/.config/modama
cp -r testconf/secrets ~/.config/modama/e2e-secrets
chmod 700 ~/.config/modama/e2e-secrets
```

Then add three lines to `~/.config/modama/e2e-secrets/keys.env` with an editor:

```
BLABLADOR_API_KEY=<your key>
DEFAULT_LLM_MODEL=blablador/alias-large
FALLBACK_LLM_MODEL=blablador/alias-fast
```

That is all the stack needs: the Blablador key and the two models. Put no other
provider's key there; the dummy lines copied from `testconf/secrets/keys.env` stay as
they are. A Blablador key is a personal access token of Helmholtz Codebase:
https://codebase.helmholtz.cloud, then *Preferences*, *Access Tokens*, *Add new token*
with the scope `read_user`; it is valid for at most a year (Blablador's guide,
https://sdlaml.pages.jsc.fz-juelich.de/ai/guides/blablador_api_access/). Never print
`keys.env` (no `cat`, no `cmp` output, not in a chat); to check that the key is set:

```bash
grep -c '^BLABLADOR_API_KEY=.' ~/.config/modama/e2e-secrets/keys.env   # 1: set
```

### One stack per VM, from one checkout

The stack's compose project is `search-stack` wherever it is started, so a second
`./uptest.sh` from another worktree replaces the running one, and its image tags
(`search-stack-crawler`, …) are shared. Agree who uses it: one benchmark of 1 h 40 min
held up three branches (2026-11-12). `docker compose ls` shows which folder the running
stack came from.

A worktree has empty submodule folders, and the stack builds the warehouse from them
(`../EOSC-Data-Commons/metadata-warehouse`); `python/search-chain`'s tests need them too.
In a new worktree, once:

```bash
git submodule update --init prototypes/EOSC-Data-Commons/data-commons-search prototypes/EOSC-Data-Commons/metadata-crawlers prototypes/EOSC-Data-Commons/metadata-warehouse
```

### Housekeeping

Every Airflow rebuild leaves an untagged image of about 2.8 GB (about 80 of them in the
VM by 2026-11-13). Now and then, with the stack running so that its images are in use:

```bash
docker image prune                     # untagged images only
docker system df                       # what is left
```

Images and volumes named `crawler-e2e*` are left over from the folder
`prototypes/crawler-e2e/`, removed on 2026-11-11: `docker image ls 'crawler-e2e*'`,
`docker volume ls -q --filter name=crawler-e2e`, then `docker image rm` and
`docker volume rm` on what they list.

`docker-compose.override.yml` (loaded automatically, as in `deploy/`) makes it a test deployment: ports on 127.0.0.1 (crawler 7654, browser 7655, Airflow 8081, search API 8000, matchmaker 3000, OpenSearch 9200), a volume `testdata` as the data tree, and for the end-to-end test this folder mounted into the crawler at `/e2e` and the crawler's Airflow account in the crawler too.

The end-to-end test (`test_e2e.py`, run by `./runtest.sh e2e` inside the crawler container) builds a tree from the crawler's fixture generators, crawls it, waits for the harvest the crawl started, and traces every record through all stages with `modama-chain`. It searches through the search API and through matchmaker's server (its page, the chat page's code without the login gate, the search route its page calls, and the chat question, without login; no browser runs). Then an incremental harvest, and faults the trace must find: a datestamp set back (`BEFORE-HARVEST-WINDOW`), a deleted index document (`SYNCED-WITHOUT-DOCUMENT`), a renamed file (`STALE`), a stopped warehouse database, and a failed harvest, which may block the endpoint (metadata-warehouse#158), so start the next run with `./downtest.sh --reset`.

## CPU budget

Every service that runs several processes counts, at its start, what its container may use on this machine and sizes its processes and threads from it, so that by default they do not oversubscribe the CPUs; no numbers per machine in the compose files (requirements-pipeline 2.4, "CPU budget" and "The operator stays in control"; change `cpu-budget` in `python/crawler/openspec/changes/`). The math libraries would otherwise each start a thread pool for the whole machine in every process: on 48 CPUs about 119 threads per indexing batch (`docs/research/cpu-oversubscription.md`).

| Service | Counts | Starts, by default | Override |
|---|---|---|---|
| `crawler`, `crawl-timer` (a crawl, `records`) | the logical CPUs of its affinity (a cpuset included), at most its cgroup v2 CPU quota | that many matching and extraction processes, at most 8; BLAS and OpenMP with 1 thread in each | `MODAMA_CRAWLER_EXTRACT_WORKERS` |
| `airflow-worker-transform` (`cpu-budget/budget.py`) | the physical cores among those CPUs, the same quota; Airflow's task slots; the memory limit, if the container has one (1.6 GiB per batch process) | P batch processes (Celery's `--concurrency`), the smallest of the three; T = cores ÷ P threads each for ONNX Runtime and the tokenizers; BLAS 1; Airflow's pool `transform` set to P | `TRANSFORM_PROCESSES` (P), `EMBEDDING_THREADS` (T) |
| `search-api` (`cpu-budget/budget.py`) | the logical CPUs, as the crawler | one uvicorn worker per CPU, 1 embedding thread each (a query is tens of tokens) | `WORKERS`, `EMBEDDING_THREADS` |
| scheduler and workers of Airflow | — | `max_active_tasks_per_dag` and `parallelism` at 1024, a ceiling no machine of ours reaches, so that the worker's budget governs | `AIRFLOW_TASK_LIMIT` (both at once) |

Math pools (ONNX Runtime, tokenizers) count physical cores, the crawler's and the search API's I/O-bound pools logical CPUs (@weber, 2026-11-12). Each service logs its budget once at start; an active override is named in it:

```
INFO CPU budget: 8 worker processes, 1 math thread each; 8 CPUs usable (affinity 8, no quota)
CPU budget: 8 processes × 1 thread; 8 cores usable (8 logical CPUs, no quota); no memory limit; 1024 task slots (max_active_tasks_per_dag 1024, parallelism 1024); no override
CPU budget: 8 workers × 1 thread; 8 CPUs usable (affinity 8, no quota); no override
```

(the crawler's on stderr of each crawl, the others first in `docker compose logs airflow-worker-transform` and `search-api`). `./cpu-budget.sh` (`./cpu-budget.sh staging` for staging) shows, before a start, what each of the three will choose on this machine and why: the cgroup version Docker reports, the inputs, the expected memory of the batches, the CPU weight, the active overrides and how to set each. It runs the services' own code in throwaway containers started like the services, so a limit or an override in the compose files or the env file shows up there. For the transform worker and the search API, a file the count cannot parse (`cpu.max`, `memory.max`, a topology list), an override or a task limit that is not a positive integer, or a pool that cannot be set (Airflow's database not up yet) stops the service's start with a message naming it; the container then restarts in a loop, and `./cpu-budget.sh` prints the same message. The crawler stops with a message on a `MODAMA_CRAWLER_EXTRACT_WORKERS` that is not a positive integer, before it records a run.

**Priority.** The background services, `crawler`, `crawl-timer`, `airflow-worker`, `airflow-worker-transform` and `transform`, run with `cpu_shares: 512`, below Docker's default; the search API and matchmaker, which answer users, keep the default (@weber, 2026-11-12). A weight only acts when the CPUs are contended and reserves nothing. In the VM (cgroup v2, runc 1.1.15) that is `cpu.weight` 20 against 100; `./cpu-budget.sh` prints each service's.

**Overrides, and when to use them.** For a measurement (`perf/indexing-bench.sh`, `perf/embed-bench.py`), set them in the service's environment, for example in an extra compose file; for the operator of a shared machine, set the task limit in the deployment's env file: on the dev server `AIRFLOW_TASK_LIMIT=16` in `staging.env` leaves cores for PostgreSQL, OpenSearch and the devvms (@weber, 2026-11-12: "here (devvms running etc) we restrict it. 16 sounds sensible"). A CPU limit for a service (`cpus:` or `cpuset:` in its compose entry) or a memory limit (`mem_limit:`) needs no override: the count follows it. The search API on all CPUs means one model per worker, about 0.45 GiB each (48 workers on 48 CPUs, about 21.6 GiB); `WORKERS` lowers it.

**Memory.** Without a memory limit, memory does not change any count (@weber, 2026-11-12: "like upstream unless we fix a real world issue"). When the expected memory, processes × 1.6 GiB for the batches or workers × 0.45 GiB for the search API, is more than `MemAvailable` at start, the service logs a second line, `CPU budget warning: … expected at most, more than the … available now …; TRANSFORM_PROCESSES=N lowers it` (or `WORKERS`), and `./cpu-budget.sh` shows it too.

**The arithmetic.** P is the smallest of the cores, the task slots and, with a memory limit, the memory ÷ 1.6 GiB (`mem_limit: 4g` is 4.0 GiB), at least 1; T = cores ÷ P, rounded down, at least 1. With only `EMBEDDING_THREADS` set, P = cores ÷ T, within the same limits. A fractional CPU quota is rounded down, at least 1, for the math pools (the transform worker's cores), so that processes × threads stay within it, and up for the I/O-bound pools (the crawler's processes, the search API's workers), which mostly wait: `cpus: 2.5` gives the transform worker 2 cores and the search API 3 workers; `./cpu-budget.sh` says which it did. On the dev server (48 logical CPUs, 24 cores, no limits): the crawler 8 processes, the transform worker 24 × 1, or 16 × 1 with `AIRFLOW_TASK_LIMIT=16`, the search API 48 workers.

**To change it**, for the test deployment: `AIRFLOW_TASK_LIMIT` goes into `.env` next to `MODAMA_SECRETS_DIR` (staging: `staging.env`); a service's variable or limit into a compose file of your own, added with `COMPOSE_FILE=docker-compose.yml:docker-compose.override.yml:mine.yml` for `docker compose` and `./cpu-budget.sh` alike. `./cpu-budget.sh` then shows what the next start chooses; `docker compose up -d` (no `--build` needed) recreates the services whose settings changed, which applies it. Recreating `airflow-worker-transform` ends the batches it is running; Airflow retries them. What a running service chose is its start's log line, not the diagnostic's; when a running container's limits (`cpu.max`, cpuset, `memory.max`) differ from what its next start would get, `./cpu-budget.sh` says so in one line for that service. `./cpu-budget.sh` exits 1 when a budget cannot be computed, 2 on a wrong argument.

**Not done by the stack:** the weight of the whole stack against the rest of the machine. Under cgroup v2 a container's weight competes with its siblings in `system.slice`; libvirt's VMs (the devvms) are in `machine.slice`. To give them precedence over the whole stack, the host needs a slice of the stack's own with a lower `CPUWeight` and the services `cgroup_parent:` set to it: a one-time setup by the operator, not tried here (`python/crawler/BACKLOG.md`, CPU budget). Under cgroup v1 the quota is not read; the log lines and `./cpu-budget.sh` say so.

**Measured in the VM** (8 vCPUs, 2026-11-12, change `cpu-budget`): the search API's workers had 25 threads each, 7 of them pinned one each to CPUs 1 to 7 in all six workers; now 4 to 12 threads per worker, none pinned. One query's embedding on an idle machine takes 17 ms with 1 thread against 8 to 11 ms with ONNX Runtime's default of 8; 100 searches one after another through `/search`, median 38 ms (p90 51) against 60 ms (p90 105) before the change, on a freshly reset index each time, so only indicative. An indexing batch process of the e2e test has 2 threads (main and one tokenizer thread) against 23 before, and peaks at 0.30 to 0.34 GB.

**A new embedding model** (`EMBEDDING_MODEL`) needs a new measurement of the memory per batch process (`perf/batch-memory.py`): the 1.6 GiB are for bge-small-en-v1.5 at its 512 tokens, with the sub-batch of 32 texts of `patches/warehouse/0002`.

## Looking around

```bash
docker compose exec crawler bash             # a shell beside all stores, with the read-only credentials set
modama-chain status                          # last crawl, harvest, indexing; the freshness time T
modama-chain trace /notes/readme.txt         # one path through every stage
modama-crawler runs                          # the crawls
docker compose exec crawl-timer modama-crawler crawl   # crawl now; starts the harvest when it is done
```

(In the test deployment the crawler has the Airflow account too, so `modama-crawler crawl` in its shell starts the harvest as well.)

**The browser** (`modama-chain browse`, service `browse`; `python/search-chain/README.md`, "browse"): http://localhost:7655/?path=/ (staging: http://localhost:17655, the runbook's "Browse"), the data tree and, for a file, what each stage makes of it, stored and computed now by the checkout's code. The checkout's `python/crawler/src`, `python/modama-formats-em/src`, `python/modama-formats-common/src` and `python/search-chain/src` are mounted read-only over the image's, and upstream's harvester and warehouse files from `../EOSC-Data-Commons/`, so an edit to a format, an extractor, `records.py` or `render.py` shows on the next reload of the page, without a build or a crawl; after an edit to `python/search-chain/`, `docker compose restart browse`. The service is read-only (a `tmpfs` on `/tmp`) and writes only snapshots ("Save for Claude"), here into the volume `browse-snapshots`, on staging into the checkout's `.claude/field-tests/browse/`. Its image is the stage `browse` of `crawler.Dockerfile` (the crawler's, with the extra `browse`), tagged `search-stack-browse`. Starting it alone (`docker compose up -d --no-deps browse`) recreates nothing else; on staging it is in the compose profile `browse`, so `./upstaging.sh` leaves it out and it starts only by name (the runbook's "Browse").

The search's web frontend, matchmaker, is on http://localhost:3000 (staging: http://localhost:13000), Airflow's UI on http://127.0.0.1:8081 (`airflow`/`airflow`, `testconf/secrets/airflow-admin.env`). From a laptop, with the stack in a devvm VM behind a host (the VM's address: `hostname -I` inside the VM):

```bash
ssh -N -J <you>@<host> -L 3000:127.0.0.1:3000 -L 8000:127.0.0.1:8000 -L 8081:127.0.0.1:8081 dev@<vm-ip>
```

Then http://localhost:3000, http://localhost:8000/search?q=ferritin&resource=datasets or http://localhost:8081. Open matchmaker as `localhost`, as above: its page sends usage statistics to EGI's Matomo (egi.matomo.cloud) unless the page's host name is `localhost` or `127.0.0.1`. Searching needs no login; its login (EGI Check-in), the FAIR check and the Data Player reach outside services.

Use these first, before `docker exec … python`, SQL or the HTTP APIs; when one cannot answer the question, that is a finding about it (`python/crawler/README.md`, "Seeing what happens"). Two more for the broker and the index: `docker compose exec broker rabbitmqctl list_queues name messages consumers` (a queue with messages and 0 consumers is stuck), and OpenSearch's `curl -s 'localhost:9200/test_datacite/_count'` for the documents a search can find (`docs.count` of `_cat/indices` counts nested documents too).

## Field-test scripts

Read-only instruments of the staging field test (`python/crawler/design/field-tests/`), in `field-test/`. Each script's header has its exact command; most take the compose project as an argument (staging's `search-staging` by default; `search-stack` for the test deployment), and the ones read on stdin run inside a container (`dc exec -T <service> … < field-test/<script>`).

| Script | What it shows |
|---|---|
| `monitor.sh` (this folder) | every 30 s: load, memory, disk, each container's CPU, memory and I/O, the crawls, `modama-chain status` |
| `record.sh` | a recording of the person's terminal (output and timing), so that a coding agent can follow a run; a copy of the kaizen plugin's |
| `nfs-stats.sh PATH LOG` | the NFS counters of the mount that holds PATH, once a minute; `docker stats` does not see NFS reads (finding F5) |
| `nfsdelta.py LOG` | that log as rates: operations/s, round trip, requests in flight, kB received per file opened |
| `counts.py` | the directories with the most records, and the warehouse's records of our endpoint (the harvest's progress) |
| `index-tasks.sh` | the latest indexing run's tasks, one CSV row each with queued, started, ended |
| `index-failures.sh` | why the latest indexing run failed: its failed tasks with the end of their logs, and the counts in the index and the crawler |
| `batch-times.sh` | per transform batch, the model load and the batch time, from the worker's logs |
| `indexing-probe.py` | inside the transform worker, every 10 s: each process's CPU, threads and memory, a `py-spy dump` of the busiest every 30 s |
| `matchmaker-check.sh` | why the search page says "Something went wrong": one search sent three ways, and both logs |
| `check-paths.sh PATHS` | whether each path in a file (one per line, for example those a chat answer linked) is a record of the crawler |

## Measurements (`perf/`)

Benchmarks and probes of the test deployment, from the change `cpu-budget` and the indexing and harvest work (`python/crawler/openspec/changes/cpu-budget/design.md` has the results). Each file's header has its command.

| File | What it measures |
|---|---|
| `indexing-bench.sh`, `docker-compose.perf.yml`, `docker-compose.today.yml`, `seed.py`, `report.py` | the indexing: reset, seed N files, crawl, wait for the harvest and indexing, records/s, per-batch times, CPU per container; `today` is the worker as before the CPU budget |
| `harvest-bench.sh`, `harvest-report.py`, `harvest-insert-timer.py` | the harvest: records/s, py-spy records of the harvester and the warehouse API, what each database insert costs |
| `batch-probe.py`, `phase-timer.py` | inside the transform worker: each batch process's life, CPU, threads, memory; the time of each of upstream's transform steps |
| `batch-memory.py` | peak memory of one transform batch in a throwaway container, by text length, threads and sub-batch |
| `embed-bench.py`, `embedlat.py`, `searchlat.sh` | embedding throughput for P processes × T threads; one query's embedding latency; 100 searches' latency |
| `validator-check.py` | that patch 0001 changes no validation result |
| `wrap/` | `run.sh` runs `batch-memory.py` in a throwaway container under perf (`fp`, `dwarf`) or plain; `cpu.py` adds wall and CPU time to each line and switches ONNX Runtime's profile and options; `par.sh` P batches at once; `ortsum.py` sums an ONNX Runtime profile by operator; `embcmp.py` compares two bulk bodies' embeddings; `lengths.py` the texts' token lengths |

## Owners' names

A record's creator is the file owner's full name (`python/crawler/README.md`, "How it works"). The crawler's container learns the names as `deploy/`'s services do: from an `sssd` service, built from `deploy/sssd` as it is (image `search-stack-sssd`), whose sockets the volume `ssspipes` shares, read-only, with `crawler` and `crawl-timer`; the crawler image has `libnss-sss`. sssd answers name lookups only: at its start it copies the configuration mounted at `/sssd.conf.in` with `services = nss` (and mode 600, which sssd demands). Change `owner-names-in-the-search-stack` in `python/crawler/openspec/changes/`.

- **Test deployment:** the test directory of `deploy/` (service `ldap`, image `search-stack-ldap`: `alice` 10001 "Alice Anderson", `bob` 10002, `carol` 10003, `mallory` 10004), and `testconf/secrets/sssd.conf`, mounted by `docker-compose.override.yml` whatever `MODAMA_SECRETS_DIR` says. Plain LDAP inside the stack's network: the file says `ldap_id_use_start_tls = false`, since sssd 2.10 otherwise starts TLS on its own, which the test directory without a certificate refuses (`unsupported extended operation`, and sssd goes offline). Check: `docker compose exec crawler getent passwd 10001`.
- **Staging:** `/var/local/data-mgmt/sssd.conf`, the file for testing `deploy/` against the real directory (`docs/guide/src/development.md`); no test directory.
- **The check user:** `SSSD_CHECK_USER` (10001 here, `STAGING_USER` on staging) is a user that must exist. sssd is healthy once it names that user (`start_period` 120 s, since sssd waits 60 s after a failed first contact), and `crawler` and `crawl-timer` start only then. A crawl looks the same user up before it stores its records: if sssd does not answer (stopped, crashed, the directory unreachable before sssd ever saw that user), the crawl stores nothing, logs `the user database does not know SSSD_CHECK_USER …: sssd is not answering (check docker compose ps sssd and docker compose logs sssd); no records stored` and fails; the timer crawls again at the next 19:00. Without the check, a crawl during an outage would turn names into numbers, and the next one back, each a full re-index. Nothing alerts an admin yet ("Moving to deploy/", alerting); `modama-crawler runs` and `modama-chain status` show the failed run.
- **What a change of the names costs:** every crawl rebuilds every record, so a crawl whose creators differ from the last one (the first with names, or a rollback) changes every such record: the harvest and the indexing that follow take as long as a first full run. On staging (1,451,848 records) that was 5 h 14 min for the harvest and, at the indexing rates of run 3, 8 to 9 h or up to 27 h for the indexing (`python/crawler/openspec/changes/owner-names-in-the-search-stack/design.md`, D8).
- **What remains:** an owner sssd has never seen, while the directory is unreachable and sssd itself answers, gets the number; the warehouse's conversion to DataCite types a creator without a comma as an organisation (`nameType` `Organizational`, `../EOSC-Data-Commons/metadata-crawlers/harvester/dc_to_datacite.xsl`, template `creators`).

## Upgrade

A new version of the crawler may bring a schema migration (a new file in `python/crawler/src/modama_crawler/migrations/versions/`). `crawler-migrate` applies it in place, keeping the crawls, records and datestamps, so nothing is crawled, harvested or indexed again. The commands are for the test deployment; on staging, use the runbook's `dc` shorthand and `./upstaging.sh --build` (`python/crawler/design/field-tests/search-stack-staging-runbook.md`, "Upgrade").

1. After pulling, see whether the new code brings a migration, without touching the database:

   ```bash
   git diff --stat <deployed commit> HEAD -- ../../python/crawler/src/modama_crawler/migrations/versions/
   ```

   To ask the database instead, the new image must be built first (`docker compose build crawler`; from then on, any `up` starts it and migrates). Then `docker compose run --rm --no-deps crawler modama-crawler runs` refuses with `… run modama-crawler migrate` when a migration is pending. Keep `--no-deps`: without it, compose runs `crawler-migrate` first, and the database is migrated by the check.
2. Optional: a dump of the crawler's database, outside the checkout (it holds the paths and owners of the data). It is not needed: the way back is an empty database and a crawl (below; @weber, 2026-11-12). A dump only saves that crawl:

   ```bash
   docker compose exec -T crawler-db pg_dump -U postgres -Fc modama_crawler > ~/crawler-db.dump
   docker compose exec -T crawler-db pg_restore --list < ~/crawler-db.dump | head   # the dump is readable
   ```

3. Build and start: `./uptest.sh --build`. Compose stops `crawler` and `crawl-timer` (a running crawl is recorded as failed, as on any rebuild), runs `crawler-migrate`, then starts them again. The OAI-PMH endpoint is down until `crawler` is healthy again. `docker compose logs crawler-migrate` shows `schema migrated from … to …`, or `schema up to date at …` when there was nothing to do.
4. If `up` fails with `service "crawler-migrate" didn't complete successfully: exit 1` (or `exit 2`), `docker compose logs crawler-migrate` says why and what to do; the messages and their steps are in `python/crawler/README.md`, "The database schema". The database is unchanged then.
5. What the next crawl extracts again. Any change to the installed code or its dependencies changes the crawler's extractor identity, and the next crawl extracts every dataset of a format with an extractor again (`python/crawler/README.md`, "How it works"). `docker compose exec crawler modama-crawler runs` says so before the runs, on standard error, for example `note: extraction identity 6d881430e7c8 is installed; the next crawl extracts again em/dm4 150000, em/dm3 27000 datasets stored under 77b1e2d4a0c9 (rosettasciio 0.15.0 -> 0.16.0); about 50 minutes on 8 processes`; on staging, `./upstaging.sh` prints this note at its end, with the command to start the crawl now. Otherwise the timer's next crawl does it. Its report then has one line per format, `em/dm4: 150000 extracted again for a new identity (rosettasciio 0.15.0 -> 0.16.0), 1200 results changed`: only the records whose content changed get a new datestamp and are harvested and indexed again, so `0 results changed` means nothing downstream moves. The line `spot check (seed …): em/dm4 20 of 20 as stored, …` names any dataset whose stored result differs from what the installed code gives now.

The way back, while the newer image is still there (a downgrade needs the newer code):

```bash
docker compose stop crawl-timer
```
```bash
docker compose run --rm crawler-migrate alembic -c /src/alembic.ini downgrade <revision before the upgrade>
```

Only if that ended with exit status 0, the older code:

```bash
git checkout <deployed commit> && ./uptest.sh --build
```

Where a revision cannot be undone, the downgrade refuses with `NotImplementedError: no downgrade from …: start from an empty database and crawl again (README, Upgrade)` and changes nothing. There, and where the database is damaged, the way back is an empty database and a crawl. First keep what shows the failure, so that it can become a test case:

```bash
docker compose ps -a > ~/upgrade-failure.txt; docker compose logs -t >> ~/upgrade-failure.txt
```

Then empty the crawler's database and start the older code:

```bash
docker compose stop crawler crawl-timer
docker compose exec -T crawler-db dropdb -U postgres modama_crawler
docker compose exec -T crawler-db createdb -U postgres modama_crawler
git checkout <deployed commit> && ./uptest.sh --build
```

`crawler-migrate` builds the schema in the empty database, and `crawl-timer` crawls at once, since it finds no finished crawl; the harvest and the indexing that follow take as long as a first full run. Instead of the three commands before `git checkout`, `./downtest.sh --reset` empties all the stack's stores, the warehouse and the index too. Whoever took the dump of step 2 can restore it into the empty database instead (`docker compose exec -T crawler-db pg_restore -U postgres -d modama_crawler < ~/crawler-db.dump`, before `git checkout`).

## AI Mode without login

Upstream's matchmaker asks for a login before AI Mode (the chat), although the search API answers `POST /chat` without one. Our patch (`patches/matchmaker/0001-ai-mode-without-login.patch`, @weber, 2026-11-12) lets anyone use it: the AI Mode toggle on the landing and results pages works without login (on the landing page it starts on, as for a logged-in user), and the chat page has no login gate. What still needs an account: the conversation history (the search API stores a conversation only for a logged-in user; without one it lasts until the page is reloaded or closed, which the chat's sidebar says, with a login link), the profile with its API keys, and the Data Player. A visitor's conversation can be exported as Markdown or PDF while it is on the page.

The chat's language model is the search API's setting, `DEFAULT_LLM_MODEL` in `keys.env` (here Blablador). Upstream's page names a model in every chat request, `cesnet/agentic` unless someone picks another in its model selector (off unless the build sets `VITE_SHOW_MODEL_SELECTOR=true`), and the search API takes the request's model over its own; without a CESNET key every chat failed with "Something went wrong while searching" (staging, 2026-11-12). The second patch (`patches/matchmaker/0002-chat-model-from-the-search-api.patch`) sends a model only with the selector on. `test_e2e.py` checks that the chat page's request names no model, so that its chat test sends what the page sends.

A link in the chat's answer whose address holds brackets, as many of our paths do (`SI data (20)`, `(3) Spectrum of … (low-loss).dm4`), stays one link, with its number in the answer's references; upstream's page ended the link at the first closing bracket and showed the rest as text (staging finding F19, 2026-11-12). The third patch (`patches/matchmaker/0003-links-with-brackets-in-the-address.patch`, decision 212) reads a link's address as CommonMark does, with brackets in balanced pairs (nested up to three deep); a bracket without its pair makes no link. `test_e2e.py` checks that the built page code has the patch's address pattern and no longer upstream's.

`matchmaker.Dockerfile` builds upstream's commit `e7138c8` (tag v0.14.0) in upstream's stages; `npm ci` then fetches upstream's locked npm packages at build time (about 640 for the build, 340 in the image), where we used to pull upstream's prebuilt image. After a change to the patch: `docker compose build matchmaker && docker compose up -d --no-deps matchmaker`.

To check by eye, logged out (a private window): on http://localhost:3000 turn on AI Mode, ask "Find datasets about ferritin": the chat page answers, its sidebar lists the question and says conversations are kept only with an account. Reload: the conversation is gone and a new one starts. The search API's rate limit is off here (`RATE_LIMITING_ENABLED`). Turned on, it would allow a visitor without login one chat or search request per 10 seconds per client address (`rate_limit.py`); behind matchmaker, whose proxy sends no `X-Forwarded-For` (`server.ts`), that address is matchmaker's, so all visitors together would share that one request (read from the code, not tried).

## Open

- **Matomo in matchmaker** (@weber, 2026-11-12): for now we rely on its rule for `localhost` (access only through the SSH tunnel to localhost). TODO: to hash out between @weber and riwtik.
- **matchmaker's outside services** (@weber, 2026-11-12): the FAIR check (`FAIR_API_URL`, a dansdemo.nl host) and the Data Player (`GRPC_TARGET`, an ethz.ch host) keep upstream's defaults, to see how they interact with this service in tests. TODO: decide when going to production.

## Moving to deploy/

What is missing for production (backlog, "Deployment"), from the reviews of 2026-11-05:

- **A production compose file:** the data tree mounted read-only into `crawler` and `crawl-timer` (the test one mounts a volume); the site's secret files in `MODAMA_SECRETS_DIR` (the passwords in `airflow-db.env` and `broker.env` repeat in the connection strings of `airflow.env`); the gateway in front of the search API and the link from the management GUI; `up`/`down` scripts like `upprod.sh`.
- **Networks and authentication:** today one network, a `crawler-db` with `trust` (any container is its superuser) and OpenSearch without security (any container can delete the index). Split the networks (crawler with its database; warehouse; Airflow), give `crawler-db` a password and roles, and keep the harvester's workers, which run code against data from outside, away from what they don't need.
- **A production crawler image:** not editable, without `[test]` and the e2e mount, as a non-root user (the test image runs as root).
- **No backups** of `crawler-db`, `postgres` and OpenSearch: their state is recreated from the data tree by a re-crawl, re-harvest and re-indexing (@weber, 2026-11-12: "The migration is just to avoid a recrawl, but we are working to make a recrawl cheap enough to not shed tears"); what is missing is that re-crawl documented as the way back, and cheap.
- **Alerting on stalls:** a crawl that could not start its harvest exits with 3, and a failed harvest shows only in `modama-chain status`; nothing tells an admin (requirements-pipeline 2.5, wishlist "status signal").
- **Pinned image versions:** `rabbitmq:3-management-alpine`, `postgres:16`, `postgres:17` float.
- **Sizing:** the OpenSearch heap (512 MB) for about 430,000 records with embeddings; the duration of a first full crawl, harvest and indexing (not measured).
- **Log timestamps:** the crawler's log lines have none (`docker compose logs -t` adds them).
- **A changed `OAI_BASE_URL`** moves our endpoint (found by its repository code); records harvested under the old URL stay until the purge.
- **Test environments per service and for the ensemble** (requirements-pipeline 2.7): this is one project for the search; with `deploy/`'s, the ensemble needs both together.

Re-check this composition against upstream's `docker-compose.yml` on every warehouse upgrade.
