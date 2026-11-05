# Search stack

The modama search, as one compose project: the crawler serves the data tree over OAI-PMH, the EOSC harvester (inside the warehouse's Airflow) harvests it into the metadata warehouse, which indexes it in OpenSearch for the search API.

```
crawl-timer ─▶ crawler ─(after each crawl: start harvest)─▶ Airflow ─▶ harvester ─▶ warehouse ─▶ OpenSearch ◀─ search-api
                  └─ crawler-db                                     └─ transform, broker, postgres
```

It is our own composition of the upstream images (EOSC metadata-warehouse `v1.10.0` in `../EOSC-Data-Commons/metadata-warehouse`, built from there; data-commons-search `0.10.2`), shaped like `deploy/` so that it can move there:

- **Secrets as files**, from `MODAMA_SECRETS_DIR` (default: the throwaway test values in `testconf/secrets/`), one file per concern, and each service gets only the files it needs: the crawler has no warehouse credentials, `modama-chain` reads with a read-only database role and an Airflow Viewer account.
- **One-shot init services** instead of scripts on the host: `warehouse-init` (databases, schema, index, our endpoint, the read-only role; `init-warehouse.sh`) and `airflow-init` (Airflow's database, the admin, the crawler's account in role User, modama-chain's in role Viewer). Both are idempotent and run on every start.
- **The crawl starts the harvest:** `crawl-timer` crawls every day at 02:00 UTC; every finished crawl starts the harvest DAG for the crawler's endpoint, after its commit. Upstream's own schedule stays off, and the DAGs are unpaused at creation (every DAG has no schedule, so they run only when started).
- **Left out from upstream's compose:** pgadmin, tool-registry, opensearch-dashboards, frontend, coordinator, and the toolmeta DAG bundle (it polls GitHub every minute; without it the dag-processor logs about 230 lines in 15 minutes instead of 1,374).

## Test deployment

```bash
./uptest.sh            # build and start, wait until healthy; the first start takes a while
./runtest.sh           # quick checks, one PASS/FAIL line each
./downtest.sh --reset  # stop and delete all state; ./uptest.sh then starts fresh
./uptest.sh && ./runtest.sh e2e   # the end-to-end test, on a fresh stack, about 4 minutes
./downtest.sh          # stop, keeping the state
```

`docker-compose.override.yml` (loaded automatically, as in `deploy/`) makes it a test deployment: ports on 127.0.0.1 (crawler 7654, Airflow 8081, search API 8000, OpenSearch 9200), a volume `testdata` as the data tree, and this folder mounted into the crawler at `/e2e` for the test.

The end-to-end test (`test_e2e.py`, run by `./runtest.sh e2e` inside the crawler container) builds a tree from the crawler's fixture generators, crawls it, waits for the harvest the crawl started, and traces every record through all stages with `modama-chain`. Then an incremental harvest, and faults the trace must find: a datestamp set back (`BEFORE-HARVEST-WINDOW`), a deleted index document (`SYNCED-WITHOUT-DOCUMENT`), a renamed file (`STALE`), a stopped warehouse database, and a failed harvest, which may block the endpoint (metadata-warehouse#158), so start the next run with `./downtest.sh --reset`.

## Looking around

```bash
docker compose exec crawler bash       # a shell beside all stores, with the read-only credentials set
modama-chain status                    # last crawl, harvest, indexing; the freshness time T
modama-chain trace /notes/readme.txt   # one path through every stage
modama-crawler runs                    # the crawls
modama-crawler crawl                   # crawl now; starts the harvest when it is done
```

Airflow's UI is on http://127.0.0.1:8081 (`airflow`/`airflow`, `testconf/secrets/airflow-admin.env`). From a laptop, with the stack in a devvm VM behind a host (the VM's address: `hostname -I` inside the VM):

```bash
ssh -N -J <you>@<host> -L 8000:127.0.0.1:8000 -L 8081:127.0.0.1:8081 dev@<vm-ip>
```

Then http://localhost:8000/search?q=ferritin&resource=datasets or http://localhost:8081.

## Moving to deploy/

What is missing for production (backlog, "Deployment"): a production compose file with the data tree mounted read-only into `crawler` and `crawl-timer`, the site's secret files in `MODAMA_SECRETS_DIR` (the passwords in `airflow-db.env` and `broker.env` repeat in the connection strings of `airflow.env`), the gateway in front of the search API, and `up`/`down` scripts like `upprod.sh`. Re-check this composition against upstream's `docker-compose.yml` on every warehouse upgrade.
