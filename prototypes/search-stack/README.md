# Search stack

The modama search, as one compose project: the crawler serves the data tree over OAI-PMH, the EOSC harvester (inside the warehouse's Airflow) harvests it into the metadata warehouse, which indexes it in OpenSearch for the search API and its web frontend, matchmaker.

```
crawl-timer ─▶ crawl ─(after each crawl: start harvest)─▶ Airflow ─▶ harvester ─▶ warehouse ─▶ OpenSearch ◀─ search-api ◀─ matchmaker
crawler (OAI-PMH) ◀────────────────────────────────────────────────┘       └─ transform, broker, postgres
  └─ crawler-db
```

It is our own composition of the upstream images (EOSC metadata-warehouse `v1.10.0` in `../EOSC-Data-Commons/metadata-warehouse`, built from there, its Airflow image with the patches in `patches/warehouse/` applied by `warehouse-airflow.Dockerfile` on top of upstream's image, which the build-only service `airflow-upstream` builds unchanged; data-commons-search `0.10.2`, with the patches in `patches/search-api/` applied by `search-api.Dockerfile`: its keyword search queries the root copies of the nested title, description and subject fields; matchmaker `0.14.0`, upstream's image, pinned by digest), shaped like `deploy/` so that it can move there:

- **Secrets as files**, from `MODAMA_SECRETS_DIR`, which must be set; `./uptest.sh` writes a `.env` (gitignored, as `deploy/.env`) that points it at the throwaway test values in `testconf/secrets/`. One file per concern, and each service gets only the files it needs: the crawler has no warehouse credentials; `modama-chain` reads with a read-only database role and an Airflow Viewer account; the search API has its own role, owner of its database `appdb` only; the crawler's Airflow account (only in `crawl-timer`) has a role `harvest-trigger` that may start and read runs of the harvest DAG and nothing else (Airflow needs edit on that DAG to start its runs, so it could pause that one DAG).
- **One-shot init services** instead of scripts on the host, idempotent, run on every start and restarted on failure: `warehouse-init` (`init-warehouse.sh`: databases, schema, index, our endpoint as the only active one, the roles) `airflow-init` (Airflow's database and admin), and `airflow-accounts` (`init-airflow.sh`, once the dag-processor has written the DAGs, since Airflow's per-DAG permissions exist only then: the crawler's role and the two accounts, created when missing; to change a password, delete the account and restart).
- **The crawl starts the harvest:** `crawl-timer` crawls every day at 19:00 UTC (20:00 CET, 21:00 CEST; outside business hours while a full crawl takes hours), and at once when the last finished crawl is more than a day old (after a restart or a killed crawl). Every finished crawl starts the harvest DAG for the crawler's endpoint after its commit. Upstream's own schedule stays off, and the DAGs are unpaused at creation (none has a schedule, so they run only when started). `docker compose stop` passes SIGTERM to a running crawl, which records its run as failed.
- **The broker waits 48 hours for an acknowledgement** (`consumer_timeout` in `broker.conf`), not RabbitMQ's 30 minutes. Celery under Airflow acknowledges a task when it ends, and on the default queue the harvest and the harvest DAG's wait for the indexing run take hours. With 30 minutes the broker closed the default worker's channel, and the worker took no task until that one had ended (staging finding F17). `./runtest.sh` checks the broker's value; `consumer-timeout/run.sh` reproduces the failure in a compose project of its own, without published ports: about 4 minutes, exit 0 when a second task runs during a long one; `REPRO_BROKER_CONF=../broker.conf consumer-timeout/run.sh` runs it with this setting. Its host name is fixed (`hostname: broker`), so that its RabbitMQ node, `rabbit@broker`, and the queued messages survive a recreated container.
- **Left out from upstream's compose:** pgadmin, tool-registry, opensearch-dashboards, coordinator (so matchmaker, upstream's `frontend`, uses the hosted Data Player), and the toolmeta DAG bundle (it polls GitHub every minute; without it the dag-processor logs about 230 lines in 15 minutes instead of 1,374).

## Test deployment

```bash
./uptest.sh            # build and start, wait until healthy; the first start takes a while
./runtest.sh           # quick checks, one PASS/FAIL line each
./downtest.sh --reset  # stop and delete all state; ./uptest.sh then starts fresh
./uptest.sh && ./runtest.sh e2e   # the end-to-end test, on a fresh stack, about 6 minutes
# The e2e test includes a chat question, which needs a language model key: a secrets folder
# outside git whose keys.env has the key and the model (Blablador: BLABLADOR_API_KEY,
# DEFAULT_LLM_MODEL=blablador/alias-large, FALLBACK_LLM_MODEL=blablador/alias-fast).
# Without a key the chat test fails; E2E_CHAT=0 ./runtest.sh e2e skips it with a warning.
export MODAMA_SECRETS_DIR=~/.config/modama/e2e-secrets
./downtest.sh --reset && ./uptest.sh && ./runtest.sh e2e
./downtest.sh          # stop, keeping the state
```

`docker-compose.override.yml` (loaded automatically, as in `deploy/`) makes it a test deployment: ports on 127.0.0.1 (crawler 7654, Airflow 8081, search API 8000, matchmaker 3000, OpenSearch 9200), a volume `testdata` as the data tree, and for the end-to-end test this folder mounted into the crawler at `/e2e` and the crawler's Airflow account in the crawler too.

The end-to-end test (`test_e2e.py`, run by `./runtest.sh e2e` inside the crawler container) builds a tree from the crawler's fixture generators, crawls it, waits for the harvest the crawl started, and traces every record through all stages with `modama-chain`. It searches through the search API and through matchmaker's server (its page, and the search route its page calls; no browser runs). Then an incremental harvest, and faults the trace must find: a datestamp set back (`BEFORE-HARVEST-WINDOW`), a deleted index document (`SYNCED-WITHOUT-DOCUMENT`), a renamed file (`STALE`), a stopped warehouse database, and a failed harvest, which may block the endpoint (metadata-warehouse#158), so start the next run with `./downtest.sh --reset`.

## CPU budget

Every service that runs several processes counts, at its start, what its container may use on this machine and sizes its processes and threads from it, so that by default they do not oversubscribe the CPUs; no numbers per machine in the compose files (requirements-pipeline 2.4, "CPU budget" and "The operator stays in control"; change `cpu-budget` in `python/crawler/openspec/changes/`). The math libraries would otherwise each start a thread pool for the whole machine in every process: on 48 CPUs about 119 threads per indexing batch (`docs/research/cpu-oversubscription.md`).

| Service | Counts | Starts, by default | Override |
|---|---|---|---|
| `crawler`, `crawl-timer` (a crawl, `records`) | the logical CPUs of its affinity (a cpuset included), at most its cgroup v2 CPU quota | that many matching and extraction processes, at most 8; BLAS and OpenMP with 1 thread in each | `MODAMA_CRAWLER_EXTRACT_WORKERS` |
| `airflow-worker-transform` (`cpu-budget/budget.py`) | the physical cores among those CPUs, the same quota; Airflow's task slots; the memory limit, if the container has one (1.7 GB per batch process) | P batch processes (Celery's `--concurrency`), the smallest of the three; T = cores ÷ P threads each for ONNX Runtime and the tokenizers; BLAS 1; Airflow's pool `transform` set to P | `TRANSFORM_PROCESSES` (P), `EMBEDDING_THREADS` (T) |
| `search-api` (`cpu-budget/budget.py`) | the logical CPUs, as the crawler | one uvicorn worker per CPU, 1 embedding thread each (a query is tens of tokens) | `WORKERS`, `EMBEDDING_THREADS` |
| scheduler and workers of Airflow | — | `max_active_tasks_per_dag` and `parallelism` at 1024, a ceiling no machine of ours reaches, so that the worker's budget governs | `AIRFLOW_TASK_LIMIT` (both at once) |

Math pools (ONNX Runtime, tokenizers) count physical cores, the crawler's and the search API's I/O-bound pools logical CPUs (@weber, 2026-11-12). Each service logs its budget once at start; an active override is named in it:

```
INFO CPU budget: 8 worker processes, 1 math thread each; 8 CPUs usable (affinity 8, no quota)
CPU budget: 8 processes × 1 thread; 8 cores usable (8 logical CPUs, no quota); no memory limit; 1024 task slots (max_active_tasks_per_dag 1024, parallelism 1024); no override
CPU budget: 8 workers × 1 thread; 8 CPUs usable (affinity 8, no quota); no override
```

(the crawler's on stderr of each crawl, the others first in `docker compose logs airflow-worker-transform` and `search-api`). `./cpu-budget.sh` (`./cpu-budget.sh staging` for staging) shows, before a start, what each of the three will choose on this machine and why: the cgroup version Docker reports, the inputs, the expected memory of the batches, the CPU weight, the active overrides and how to set each. It runs the services' own code in throwaway containers started like the services, so a limit or an override in the compose files or the env file shows up there. A file the count cannot parse (`cpu.max`, `memory.max`, a topology list) or an override that is not a positive integer stops the service's start with a message naming it; the container then restarts in a loop, and `./cpu-budget.sh` prints the same message.

**Priority.** The background services, `crawler`, `crawl-timer`, `airflow-worker`, `airflow-worker-transform` and `transform`, run with `cpu_shares: 512`, below Docker's default; the search API and matchmaker, which answer users, keep the default (@weber, 2026-11-12). A weight only acts when the CPUs are contended and reserves nothing. In the VM (cgroup v2, runc 1.1.15) that is `cpu.weight` 20 against 100; `./cpu-budget.sh` prints each service's.

**Overrides, and when to use them.** For a measurement (`perf/indexing-bench.sh`, `perf/embed-bench.py`), set them in the service's environment, for example in an extra compose file; for the operator of a shared machine, set the task limit in the deployment's env file: on the dev server `AIRFLOW_TASK_LIMIT=16` in `staging.env` leaves cores for PostgreSQL, OpenSearch and the devvms (@weber, 2026-11-12: "here (devvms running etc) we restrict it. 16 sounds sensible"). A CPU limit for a service (`cpus:` or `cpuset:` in its compose entry) or a memory limit (`mem_limit:`) needs no override: the count follows it. The search API on all CPUs means one model per worker, about 0.45 GB each (48 workers on 48 CPUs, about 22 GB); `WORKERS` lowers it.

**The arithmetic.** P is the smallest of the cores, the task slots and, with a memory limit, the memory ÷ 1.7 GB (10⁹ bytes; `mem_limit: 4g` is 4.3 GB), at least 1; T = cores ÷ P, rounded down, at least 1. With only `EMBEDDING_THREADS` set, P = cores ÷ T, within the same limits. A fractional quota counts as the next whole CPU (`cpus: 2.5` counts 3). On the dev server (48 logical CPUs, 24 cores, no limits): the crawler 8 processes, the transform worker 24 × 1, or 16 × 1 with `AIRFLOW_TASK_LIMIT=16`, the search API 48 workers.

**To change it**, for the test deployment: `AIRFLOW_TASK_LIMIT` goes into `.env` next to `MODAMA_SECRETS_DIR` (staging: `staging.env`); a service's variable or limit into a compose file of your own, added with `COMPOSE_FILE=docker-compose.yml:docker-compose.override.yml:mine.yml` for `docker compose` and `./cpu-budget.sh` alike. `./cpu-budget.sh` then shows what the next start chooses; `docker compose up -d` (no `--build` needed) recreates the services whose settings changed, which applies it. Recreating `airflow-worker-transform` ends the batches it is running; Airflow retries them. What a running service chose is its start's log line, not the diagnostic's. `./cpu-budget.sh` exits 1 when a budget cannot be computed, 2 on a wrong argument.

**Not done by the stack:** the weight of the whole stack against the rest of the machine. Under cgroup v2 a container's weight competes with its siblings in `system.slice`; libvirt's VMs (the devvms) are in `machine.slice`. To give them precedence over the whole stack, the host needs a slice of the stack's own with a lower `CPUWeight` and the services `cgroup_parent:` set to it: a one-time setup by the operator, not tried here (`python/crawler/BACKLOG.md`, CPU budget). Under cgroup v1 the quota is not read; the log lines and `./cpu-budget.sh` say so.

**Measured in the VM** (8 vCPUs, 2026-11-12, change `cpu-budget`): the search API's workers had 25 threads each, 7 of them pinned one each to CPUs 1 to 7 in all six workers; now 4 to 12 threads per worker, none pinned. One query's embedding on an idle machine takes 17 ms with 1 thread against 8 to 11 ms with ONNX Runtime's default of 8; 100 searches one after another through `/search`, median 38 ms (p90 51) against 60 ms (p90 105) before the change, on a freshly reset index each time, so only indicative. An indexing batch process of the e2e test has 2 threads (main and one tokenizer thread) against 23 before, and peaks at 0.30 to 0.34 GB.

**A new embedding model** (`EMBEDDING_MODEL`) needs a new measurement of the memory per batch process (`perf/batch-memory.py`): the 1.7 GB are for bge-small-en-v1.5 at its 512 tokens, with the sub-batch of 32 texts of `patches/warehouse/0002`.

## Looking around

```bash
docker compose exec crawler bash             # a shell beside all stores, with the read-only credentials set
modama-chain status                          # last crawl, harvest, indexing; the freshness time T
modama-chain trace /notes/readme.txt         # one path through every stage
modama-crawler runs                          # the crawls
docker compose exec crawl-timer modama-crawler crawl   # crawl now; starts the harvest when it is done
```

(In the test deployment the crawler has the Airflow account too, so `modama-crawler crawl` in its shell starts the harvest as well.)

The search's web frontend, matchmaker, is on http://localhost:3000 (staging: http://localhost:13000), Airflow's UI on http://127.0.0.1:8081 (`airflow`/`airflow`, `testconf/secrets/airflow-admin.env`). From a laptop, with the stack in a devvm VM behind a host (the VM's address: `hostname -I` inside the VM):

```bash
ssh -N -J <you>@<host> -L 3000:127.0.0.1:3000 -L 8000:127.0.0.1:8000 -L 8081:127.0.0.1:8081 dev@<vm-ip>
```

Then http://localhost:3000, http://localhost:8000/search?q=ferritin&resource=datasets or http://localhost:8081. Open matchmaker as `localhost`, as above: its page sends usage statistics to EGI's Matomo (egi.matomo.cloud) unless the page's host name is `localhost` or `127.0.0.1`. Searching needs no login; its login (EGI Check-in), the FAIR check and the Data Player reach outside services.

## Open

- **Matomo in matchmaker** (@weber, 2026-11-12): for now we rely on its rule for `localhost` (access only through the SSH tunnel to localhost). TODO: to hash out between @weber and riwtik.
- **matchmaker's outside services** (@weber, 2026-11-12): the FAIR check (`FAIR_API_URL`, a dansdemo.nl host) and the Data Player (`GRPC_TARGET`, an ethz.ch host) keep upstream's defaults, to see how they interact with this service in tests. TODO: decide when going to production.

## Moving to deploy/

What is missing for production (backlog, "Deployment"), from the reviews of 2026-11-05:

- **A production compose file:** the data tree mounted read-only into `crawler` and `crawl-timer` (the test one mounts a volume); the site's secret files in `MODAMA_SECRETS_DIR` (the passwords in `airflow-db.env` and `broker.env` repeat in the connection strings of `airflow.env`); the gateway in front of the search API and the link from the management GUI; `up`/`down` scripts like `upprod.sh`.
- **Networks and authentication:** today one network, a `crawler-db` with `trust` (any container is its superuser) and OpenSearch without security (any container can delete the index). Split the networks (crawler with its database; warehouse; Airflow), give `crawler-db` a password and roles, and keep the harvester's workers, which run code against data from outside, away from what they don't need.
- **A production crawler image:** not editable, without `[test]` and the e2e mount, as a non-root user (the test image runs as root).
- **Backups** of `crawler-db`, `postgres` and OpenSearch (or a documented re-crawl and re-harvest instead), like `deploy/`'s backup service.
- **Alerting on stalls:** a crawl that could not start its harvest exits with 3, and a failed harvest shows only in `modama-chain status`; nothing tells an admin (requirements-pipeline 2.5, wishlist "status signal").
- **Pinned image versions:** `rabbitmq:3-management-alpine`, `postgres:16`, `postgres:17` float.
- **Sizing:** the OpenSearch heap (512 MB) for about 430,000 records with embeddings; the duration of a first full crawl, harvest and indexing (not measured).
- **Log timestamps:** the crawler's log lines have none (`docker compose logs -t` adds them).
- **A changed `OAI_BASE_URL`** moves our endpoint (found by its repository code); records harvested under the old URL stay until the purge.
- **Test environments per service and for the ensemble** (requirements-pipeline 2.7): this is one project for the search; with `deploy/`'s, the ensemble needs both together.

Re-check this composition against upstream's `docker-compose.yml` on every warehouse upgrade.
