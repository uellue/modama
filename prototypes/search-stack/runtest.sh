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
[ -e .env ] || echo "MODAMA_SECRETS_DIR=./testconf/secrets" > .env  # as uptest.sh
dc() { docker compose "$@"; }

if [ "${1:-}" = e2e ]; then
    # The chat test runs by default and needs a key in keys.env for the provider of the chat
    # model (the search API's default model is cesnet/agentic); without one it fails.
    # E2E_CHAT=0 skips it, with a warning.
    secrets="${MODAMA_SECRETS_DIR:-$(sed -n 's/^MODAMA_SECRETS_DIR=//p' .env)}"
    model=$(sed -n 's/^DEFAULT_LLM_MODEL=//p' "$secrets/keys.env")
    model="${model:-cesnet/agentic}"
    case "${model%%/*}" in
        blablador) var=BLABLADOR_API_KEY ;;
        cesnet | einfracz) var=CESNET_API_KEY ;;
        fedllm) var=FEDLLM_API_KEY ;;
        mistralai) var=MISTRAL_API_KEY ;;
        openrouter) var=OPENROUTER_API_KEY ;;
        *) var=OPENAI_API_KEY ;;
    esac
    key=$(sed -n "s/^$var=//p" "$secrets/keys.env")
    if [ "${E2E_CHAT:-}" = 0 ]; then
        chat=0
        echo "WARNING: E2E_CHAT=0: the chat test is skipped" >&2
    elif [ -n "$key" ] && [ "$key" != dummy ]; then
        chat=1
    else
        chat="missing:$var in $secrets/keys.env for the chat model $model"
    fi
    unset key
    exec docker compose exec -T -e E2E_CHAT="$chat" crawler pytest -v -p no:cacheprovider /e2e/test_e2e.py "${@:2}"
fi

SERVICES="crawler crawl-timer crawler-db postgres opensearch transform broker search-api
matchmaker airflow-postgres airflow-api-server airflow-scheduler airflow-dag-processor airflow-worker
airflow-worker-transform"
INITS="warehouse-init airflow-init airflow-accounts"

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

all_running() {
    local missing="" s
    for s in $SERVICES; do
        dc ps --status running --services | grep -qx "$s" || missing+=" $s"
    done
    [ -z "$missing" ] || { echo "not running:$missing"; return 1; }
}

all_healthy() {
    local states
    states=$(dc ps --format '{{.Service}} {{.Health}}' | awk '$2 != "" && $2 != "healthy"')
    [ -z "$states" ] || { echo "$states"; return 1; }
}

inits_done() {
    local s state bad=""
    for s in $INITS; do
        state=$(dc ps -a --format '{{.State}} {{.ExitCode}}' "$s")
        [ "$state" = "exited 0" ] || bad+=" $s ($state)"
    done
    [ -z "$bad" ] || { echo "not finished:$bad"; return 1; }
}

crawler_role() {
    dc exec -T airflow-api-server airflow users list -o plain 2>/dev/null \
        | awk '$2 == "crawler" {found = 1; if ($NF != "harvest-trigger") exit 1} END {exit !found}'
}

harvest_dag_unpaused() {
    dc exec -T crawl-timer python -c "
import json, os, urllib.request
A = 'http://airflow-api-server:8080'
def call(path, data=None, token=None):
    r = urllib.request.Request(A + path, json.dumps(data).encode() if data else None,
        headers={'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + token} if token else {})})
    return json.load(urllib.request.urlopen(r, timeout=30))
t = call('/auth/token', {'username': os.environ['MODAMA_CRAWLER_AIRFLOW_USER'], 'password': os.environ['MODAMA_CRAWLER_AIRFLOW_PASSWORD']})['access_token']
assert not call('/api/v2/dags/warehouse_harvest_and_index', token=t)['is_paused'], 'the harvest DAG is paused'"
}

only_our_endpoint_active() {
    local active
    active=$(dc exec -T crawler python -c "
import os, psycopg
with psycopg.connect(os.environ['MODAMA_CHAIN_WAREHOUSE_DB']) as c:
    print(*c.execute('SELECT harvest_url FROM endpoints WHERE is_active').fetchall())")
    [ "$active" = "('http://crawler:7654/oai',)" ] || { echo "active endpoints: $active"; return 1; }
}

# broker.conf reached the broker: a shorter consumer_timeout stops the default worker
# (staging finding F17; consumer-timeout/run.sh reproduces it)
broker_consumer_timeout() {
    local want got
    want=$(sed -n 's/^consumer_timeout = //p' broker.conf)
    got=$(dc exec -T broker rabbitmq-diagnostics -q environment | grep -o '{consumer_timeout,[0-9]*}')
    [ "$got" = "{consumer_timeout,$want}" ] || { echo "broker: $got, broker.conf: $want"; return 1; }
}

check "every service is running" all_running
check "every service with a health check is healthy" all_healthy
check "the init services have finished" inits_done
check "the broker's consumer_timeout is broker.conf's" broker_consumer_timeout
check "the crawler answers OAI-PMH Identify" \
    dc exec -T crawler python -c "import urllib.request; urllib.request.urlopen('http://localhost:7654/oai?verb=Identify', timeout=10)"
check "the crawler's Airflow account has the role harvest-trigger" crawler_role
check "the harvest DAG is unpaused (seen with the crawler's account)" harvest_dag_unpaused
check "the crawler is the only active endpoint" only_our_endpoint_active
check "modama-chain status reaches every store with read-only accounts" \
    dc exec -T crawler modama-chain status
exit $FAILED
