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

# A container's own cgroup limits, as one line: cpu.max, cpuset, memory.max ("-" where a file is missing)
LIMITS='l() { cat "/sys/fs/cgroup/$1" 2> /dev/null || echo -; }
echo "cpu.max $(l cpu.max), cpuset $(l cpuset.cpus.effective), memory.max $(l memory.max)"'

failed=0
show() {  # title, service, command in its image...
    local title=$1 service=$2 out status next id running
    shift 2
    echo
    echo "== $title ($service)"
    # the limits and the weight first, from the container's own cgroup, then the service's explanation
    out=$(dc run --rm --no-deps -T --entrypoint sh "$service" -c \
        "echo \"LIMITS \$( $LIMITS )\"
         echo \"  CPU weight (cpu.weight; Docker default 100): \$(cat /sys/fs/cgroup/cpu.weight 2> /dev/null || echo unknown)\"
         exec \"\$@\"" sh "$@" 2>&1)
    status=$?
    next=$(sed -n 's/^LIMITS //p' <<< "$out")
    grep -v '^LIMITS ' <<< "$out"
    if [ "$status" -ne 0 ]; then
        echo "  cannot compute the budget: the service would not start (the message above)"
        failed=1
    fi
    # the running container, if there is one, may have been started with other limits
    id=$(dc ps -q "$service" 2> /dev/null | head -n 1)
    if [ -n "$id" ] && [ -n "$next" ]; then
        running=$(docker exec "$id" sh -c "$LIMITS" 2> /dev/null) || return 0
        if [ "$running" != "$next" ]; then
            echo "  the running container has other limits than its next start: running $running;" \
                "next start $next (docker compose up -d applies the next start's)"
        fi
    fi
}
show "crawler: matching and extraction processes" crawler modama-crawler cpu-budget
show "transform worker: indexing batches" airflow-worker-transform python /opt/modama/budget.py explain transform
show "search API: workers" search-api python /opt/modama/budget.py explain search-api
echo
echo "Background services (crawler, crawl-timer, airflow-worker, airflow-worker-transform, transform)"
echo "run at a lower CPU weight than the search API and the frontend. Details: README.md, \"CPU budget\"."
exit "$failed"
