# Search stack

The modama search, as one compose project: the crawler serves the data tree over OAI-PMH, the EOSC harvester (inside the warehouse's Airflow) harvests it into the metadata warehouse, which indexes it in OpenSearch for the search API.

```
crawl-timer ─▶ crawl ─(after each crawl: start harvest)─▶ Airflow ─▶ harvester ─▶ warehouse ─▶ OpenSearch ◀─ search-api
crawler (OAI-PMH) ◀────────────────────────────────────────────────┘       └─ transform, broker, postgres
  └─ crawler-db
```

It is our own composition of the upstream images (EOSC metadata-warehouse `v1.10.0` in `../EOSC-Data-Commons/metadata-warehouse`, built from there; data-commons-search `0.10.2`), shaped like `deploy/` so that it can move there:

- **Secrets as files**, from `MODAMA_SECRETS_DIR`, which must be set; `./uptest.sh` writes a `.env` (gitignored, as `deploy/.env`) that points it at the throwaway test values in `testconf/secrets/`. One file per concern, and each service gets only the files it needs: the crawler has no warehouse credentials; `modama-chain` reads with a read-only database role and an Airflow Viewer account; the search API has its own role, owner of its database `appdb` only; the crawler's Airflow account (only in `crawl-timer`) has a role `harvest-trigger` that may start and read runs of the harvest DAG and nothing else (Airflow needs edit on that DAG to start its runs, so it could pause that one DAG).
- **One-shot init services** instead of scripts on the host, idempotent, run on every start and restarted on failure: `warehouse-init` (`init-warehouse.sh`: databases, schema, index, our endpoint as the only active one, the roles) `airflow-init` (Airflow's database and admin), and `airflow-accounts` (`init-airflow.sh`, once the dag-processor has written the DAGs, since Airflow's per-DAG permissions exist only then: the crawler's role and the two accounts, created when missing; to change a password, delete the account and restart).
- **The crawl starts the harvest:** `crawl-timer` crawls every day at 19:00 UTC (20:00 CET, 21:00 CEST; outside business hours while a full crawl takes hours), and at once when the last finished crawl is more than a day old (after a restart or a killed crawl). Every finished crawl starts the harvest DAG for the crawler's endpoint after its commit. Upstream's own schedule stays off, and the DAGs are unpaused at creation (none has a schedule, so they run only when started). `docker compose stop` passes SIGTERM to a running crawl, which records its run as failed.
- **Left out from upstream's compose:** pgadmin, tool-registry, opensearch-dashboards, frontend, coordinator, and the toolmeta DAG bundle (it polls GitHub every minute; without it the dag-processor logs about 230 lines in 15 minutes instead of 1,374).

## Test deployment

```bash
./uptest.sh            # build and start, wait until healthy; the first start takes a while
./runtest.sh           # quick checks, one PASS/FAIL line each
./downtest.sh --reset  # stop and delete all state; ./uptest.sh then starts fresh
./uptest.sh && ./runtest.sh e2e   # the end-to-end test, on a fresh stack, about 4 minutes
./downtest.sh          # stop, keeping the state
```

`docker-compose.override.yml` (loaded automatically, as in `deploy/`) makes it a test deployment: ports on 127.0.0.1 (crawler 7654, Airflow 8081, search API 8000, OpenSearch 9200), a volume `testdata` as the data tree, and for the end-to-end test this folder mounted into the crawler at `/e2e` and the crawler's Airflow account in the crawler too.

The end-to-end test (`test_e2e.py`, run by `./runtest.sh e2e` inside the crawler container) builds a tree from the crawler's fixture generators, crawls it, waits for the harvest the crawl started, and traces every record through all stages with `modama-chain`. Then an incremental harvest, and faults the trace must find: a datestamp set back (`BEFORE-HARVEST-WINDOW`), a deleted index document (`SYNCED-WITHOUT-DOCUMENT`), a renamed file (`STALE`), a stopped warehouse database, and a failed harvest, which may block the endpoint (metadata-warehouse#158), so start the next run with `./downtest.sh --reset`.

## Looking around

```bash
docker compose exec crawler bash             # a shell beside all stores, with the read-only credentials set
modama-chain status                          # last crawl, harvest, indexing; the freshness time T
modama-chain trace /notes/readme.txt         # one path through every stage
modama-crawler runs                          # the crawls
docker compose exec crawl-timer modama-crawler crawl   # crawl now; starts the harvest when it is done
```

(In the test deployment the crawler has the Airflow account too, so `modama-crawler crawl` in its shell starts the harvest as well.)

Airflow's UI is on http://127.0.0.1:8081 (`airflow`/`airflow`, `testconf/secrets/airflow-admin.env`). From a laptop, with the stack in a devvm VM behind a host (the VM's address: `hostname -I` inside the VM):

```bash
ssh -N -J <you>@<host> -L 8000:127.0.0.1:8000 -L 8081:127.0.0.1:8081 dev@<vm-ip>
```

Then http://localhost:8000/search?q=ferritin&resource=datasets or http://localhost:8081.

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
