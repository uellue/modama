#!/bin/bash
# Stop the staging deployment. A running crawl gets SIGTERM and records its run as
# failed; the state stays, and the next ./upstaging.sh crawls again at once.
#
#   downstaging.sh           stop the containers
#   downstaging.sh --reset   also delete the staging state (databases, index, Airflow);
#                            never the data tree, which is mounted read-only
set -euo pipefail
cd "$(dirname "$0")"
[ -e staging.env ] || { echo "staging.env is missing: see the runbook" >&2; exit 2; }
dc() { docker compose -p search-staging --env-file staging.env -f docker-compose.yml -f docker-compose.staging.yml "$@"; }
case "${1:-}" in
    "") dc down ;;
    --reset) dc down --volumes ;;
    *) echo "usage: $0 [--reset]" >&2; exit 2 ;;
esac
