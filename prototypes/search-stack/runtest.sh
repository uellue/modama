#!/bin/bash
# Checks of the running test deployment (./uptest.sh first), one PASS/FAIL line each,
# exit 1 if any failed.
#
#   runtest.sh        quick checks of the running stack
#   runtest.sh e2e    the end-to-end test (test_e2e.py): builds a test tree, crawls,
#                     harvests, searches, injects faults. About 4 minutes; it needs a
#                     fresh stack: ./downtest.sh --reset && ./uptest.sh first.
set -uo pipefail
cd "$(dirname "$0")"
dc() { docker compose "$@"; }

if [ "${1:-}" = e2e ]; then
    exec docker compose exec -T crawler pytest -v -p no:cacheprovider /e2e/test_e2e.py "${@:2}"
fi

FAILED=0
check() {  # what, command...
    local what=$1 out
    shift
    if out=$("$@" 2>&1); then
        echo "PASS  $what"
    else
        echo "FAIL  $what"
        [ -n "$out" ] && echo "$out" | head -n 8 | sed 's/^/        /'
        FAILED=1
    fi
}

all_healthy() {
    local states
    states=$(dc ps --format '{{.Service}} {{.Health}}' | awk '$2 != "" && $2 != "healthy"')
    [ -z "$states" ] || { echo "$states"; return 1; }
}

check "every service with a health check is healthy" all_healthy
check "the crawler answers OAI-PMH Identify" \
    dc exec -T crawler python -c "import urllib.request; urllib.request.urlopen('http://localhost:7654/oai?verb=Identify', timeout=10)"
check "the crawler's Airflow account may start the harvest DAG" \
    dc exec -T crawler python -c "
import json, os, urllib.request
A = 'http://airflow-api-server:8080'
def call(path, data=None, token=None, method=None):
    r = urllib.request.Request(A + path, json.dumps(data).encode() if data else None, method=method,
        headers={'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + token} if token else {})})
    return json.load(urllib.request.urlopen(r, timeout=30))
t = call('/auth/token', {'username': os.environ['MODAMA_CRAWLER_AIRFLOW_USER'], 'password': os.environ['MODAMA_CRAWLER_AIRFLOW_PASSWORD']})['access_token']
dag = call('/api/v2/dags/warehouse_harvest_and_index', token=t)
assert not dag['is_paused'], 'the harvest DAG is paused'"
check "modama-chain status reaches every store with read-only accounts" \
    dc exec -T crawler modama-chain status
check "the crawl timer is running" sh -c "docker compose ps --status running --services | grep -qx crawl-timer"
exit $FAILED
