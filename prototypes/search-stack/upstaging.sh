#!/bin/bash
# Bring up the staging deployment of the search stack (real data, read-only; see
# docker-compose.staging.yml) and wait until it is healthy. The crawl timer then crawls
# at once (no finished crawl yet) and starts the harvest when the crawl is done.
# Extra arguments go to `docker compose up`, for example --build after pulling changes.
set -euo pipefail
cd "$(dirname "$0")"
[ -e staging.env ] || { echo "staging.env is missing: see the runbook" >&2; exit 2; }
docker compose -p search-staging --env-file staging.env -f docker-compose.yml -f docker-compose.staging.yml \
    up -d --wait --wait-timeout "${UPSTAGING_TIMEOUT:-900}" "$@"
echo "staging is up: search on 127.0.0.1:13000, search API on 127.0.0.1:18000, Airflow on 127.0.0.1:18081"
