#!/bin/bash
# Bring up the staging deployment of the search stack (real data, read-only; see
# docker-compose.staging.yml) and wait until it is healthy. The crawl timer then crawls
# at once (no finished crawl yet) and starts the harvest when the crawl is done.
# Extra arguments go to `docker compose up`, for example --build after pulling changes.
set -euo pipefail
cd "$(dirname "$0")"
[ -e staging.env ] || { echo "staging.env is missing: see the runbook" >&2; exit 2; }
dc() { docker compose -p search-staging --env-file staging.env -f docker-compose.yml -f docker-compose.staging.yml "$@"; }
# the base of our Airflow image, which Compose cannot build in order (docker-compose.yml)
dc build --quiet airflow-upstream
dc up -d --wait --wait-timeout "${UPSTAGING_TIMEOUT:-900}" "$@"
echo "staging is up: search on 127.0.0.1:13000, search API on 127.0.0.1:18000, Airflow on 127.0.0.1:18081"
# What the next crawl extracts again after an upgrade (change extractor-identity, D7):
# runs prints a note on stderr when stored datasets carry another extractor identity
note=$(dc exec -T crawler modama-crawler runs 2>&1 >/dev/null | grep '^note: ' || true)
if [ -n "$note" ]; then
    # the timer's own TOML (docker-compose.staging.yml): the same formats and exclusions
    config=$(sed -n 's/^STAGING_CRAWL_CONFIG=\([^[:space:]#]*\).*/\1/p' staging.env | tail -1)
    echo "$note"
    echo "the next scheduled crawl (19:00 UTC) does it; to start it now:"
    echo "  docker compose -p search-staging --env-file staging.env -f docker-compose.yml -f docker-compose.staging.yml exec crawl-timer modama-crawler --config /stagingconf/$config crawl"
fi
