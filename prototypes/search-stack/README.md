# Search stack

The modama search, as one compose project: the crawler serves the data tree over OAI-PMH, the EOSC harvester (inside the warehouse's Airflow) harvests it into the metadata warehouse, which indexes it in OpenSearch for the search API and its web frontend, matchmaker.

```
crawl-timer ─▶ crawl ─(after each crawl: start harvest)─▶ Airflow ─▶ harvester ─▶ warehouse ─▶ OpenSearch ◀─ search-api ◀─ matchmaker
crawler (OAI-PMH) ◀────────────────────────────────────────────────┘       └─ transform, broker, postgres
  └─ crawler-db
```

It is our own composition of the upstream images (EOSC metadata-warehouse `v1.10.0` in `../EOSC-Data-Commons/metadata-warehouse`, built from there; data-commons-search `0.10.2`, with the patches in `patches/search-api/` applied by `search-api.Dockerfile`: its keyword search queries the root copies of the nested title, description and subject fields; matchmaker `0.14.0`, upstream's image, pinned by digest), shaped like `deploy/` so that it can move there:

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

## Upgrade

A new version of the crawler may bring a schema migration (a new file in `python/crawler/src/modama_crawler/migrations/versions/`). `crawler-migrate` applies it in place, keeping the crawls, records and datestamps, so nothing is crawled, harvested or indexed again. The commands are for the test deployment; on staging, use the runbook's `dc` shorthand and `./upstaging.sh --build` (`python/crawler/design/field-tests/search-stack-staging-runbook.md`, "Upgrade").

1. After pulling, see whether the new code brings a migration, without touching the database:

   ```bash
   git diff --stat <deployed commit> HEAD -- ../../python/crawler/src/modama_crawler/migrations/versions/
   ```

   To ask the database instead: `docker compose run --rm --no-deps crawler modama-crawler runs` with the new image refuses with `… run modama-crawler migrate` when a migration is pending. Keep `--no-deps`: without it, compose runs `crawler-migrate` first, and the database is migrated before you have the dump.
2. If a migration comes, take a dump of the crawler's database first, outside the checkout (it holds the paths and owners of the data). It is the way back from anything a downgrade cannot undo:

   ```bash
   docker compose exec -T crawler-db pg_dump -U postgres -Fc modama_crawler > ~/crawler-db.dump
   docker compose exec -T crawler-db pg_restore --list < ~/crawler-db.dump | head   # the dump is readable
   ```

3. Build and start: `./uptest.sh --build`. Compose stops `crawler` and `crawl-timer` (a running crawl is recorded as failed, as on any rebuild), runs `crawler-migrate`, then starts them again. The OAI-PMH endpoint is down until `crawler` is healthy again. `docker compose logs crawler-migrate` shows `schema migrated from … to …`, or `schema up to date at …` when there was nothing to do.
4. If `up` fails with `service "crawler-migrate" didn't complete successfully: exit 1` (or `exit 2`), `docker compose logs crawler-migrate` says why and what to do; the messages and their steps are in `python/crawler/README.md`, "The database schema". The database is unchanged then.

The way back, while the newer image is still there (a downgrade needs the newer code):

```bash
docker compose stop crawl-timer
docker compose run --rm crawler-migrate alembic -c /src/alembic.ini downgrade <revision before the upgrade>
git checkout <deployed commit> && ./uptest.sh --build
```

Where a revision cannot be undone, the downgrade refuses with `NotImplementedError: no downgrade from …: restore the dump taken before the upgrade (README, Upgrade)` and changes nothing. Then restore the dump into an empty database, with the older code checked out:

```bash
docker compose stop crawler crawl-timer
docker compose exec -T crawler-db dropdb -U postgres modama_crawler
docker compose exec -T crawler-db createdb -U postgres modama_crawler
docker compose exec -T crawler-db pg_restore -U postgres -d modama_crawler < ~/crawler-db.dump
./uptest.sh --build
```

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
