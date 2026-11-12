#!/bin/bash
# What the search stack's services will choose for their CPU budget on this machine, and why
# (README, "CPU budget"): the cgroup version and driver Docker reports, then for the crawler,
# the transform worker and the search API the budget line of its next start with its inputs,
# its CPU weight and how to override it. Each is computed by the service's own code in a
# throwaway container started like the service (`docker compose run --rm --no-deps`: its
# limits, its environment, its overrides). Changes nothing; creates the project's network if
# it is missing. The images must be built (./uptest.sh, ./upstaging.sh). About half a minute.
#
#   cpu-budget.sh           the test deployment
#   cpu-budget.sh staging   the staging deployment (staging.env, docker-compose.staging.yml)
#
# Exits 1 if a service's budget cannot be computed: that service would not start either.
set -uo pipefail
cd "$(dirname "$0")"
case "${1:-}" in
    "")
        [ -e .env ] || echo "MODAMA_SECRETS_DIR=./testconf/secrets" > .env  # as uptest.sh
        dc() { docker compose --progress quiet "$@"; }
        ;;
    staging)
        [ -e staging.env ] || { echo "staging.env is missing: see the runbook" >&2; exit 2; }
        dc() { docker compose --progress quiet -p search-staging --env-file staging.env \
            -f docker-compose.yml -f docker-compose.staging.yml "$@"; }
        ;;
    -h | --help) sed -n '2,13s/^# \{0,1\}//p' "$0"; exit 0 ;;
    *) echo "usage: $0 [staging]   (--help: what it shows)" >&2; exit 2 ;;
esac

docker info --format 'Docker: cgroup v{{.CgroupVersion}} ({{.CgroupDriver}}), {{.NCPU}} CPUs, {{.MemTotal}} bytes of memory' \
    || exit 1

failed=0
show() {  # title, service, command in its image...
    local title=$1 service=$2
    shift 2
    echo
    echo "== $title ($service)"
    # the weight first, from the container's own cgroup, then the service's explanation
    if ! dc run --rm --no-deps -T --entrypoint sh "$service" -c \
        'echo "  CPU weight (cpu.weight; Docker default 100): $(cat /sys/fs/cgroup/cpu.weight 2> /dev/null || echo unknown)"
         exec "$@"' sh "$@"; then
        echo "  cannot compute the budget: the service would not start (the message above)"
        failed=1
    fi
}
show "crawler: matching and extraction processes" crawler modama-crawler cpu-budget
show "transform worker: indexing batches" airflow-worker-transform python /opt/modama/budget.py explain transform
show "search API: workers" search-api python /opt/modama/budget.py explain search-api
echo
echo "Background services (crawler, crawl-timer, airflow-worker, airflow-worker-transform, transform)"
echo "run at a lower CPU weight than the search API and the frontend. Details: README.md, \"CPU budget\"."
exit "$failed"
