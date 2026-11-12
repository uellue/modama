#!/bin/bash
# Harvest benchmark on a running test stack (after perf/indexing-bench.sh, which leaves it up
# without crawl-timer): seed N files again (new mtimes: every record changes), crawl, and
# profile the harvest until its task ends: records/s, CPU per container, and py-spy records
# of the harvester process (in airflow-worker) and of the warehouse API (`transform`).
#
#   perf/harvest-bench.sh N [OUT]
#
# py-spy comes from the Airflow image, run in a throwaway container that shares the target
# container's process namespace (the transform image has no py-spy). Test deployment only.
# The indexing that follows the harvest is not waited for.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
stack=$(dirname "$here")
n=${1:?usage: harvest-bench.sh N [OUT]}
out=${2:-$(mktemp -d /tmp/harvest-bench-XXXX)}
mkdir -p "$out"
out=$(cd "$out" && pwd)
: "${MODAMA_SECRETS_DIR:?set MODAMA_SECRETS_DIR (see README.md)}"
export COMPOSE_FILE="$stack/docker-compose.yml:$stack/docker-compose.override.yml:$here/docker-compose.perf.yml"
export COMPOSE_PROJECT_NAME=search-stack  # never another project (staging runs as search-staging)
rm -f "$out"/cpu-*.txt "$out"/*.raw  # a reused OUT keeps nothing of an earlier run
cd "$stack"
dc() { docker compose "$@"; }
sql() { dc exec -T airflow-postgres psql -U airflow -d airflow -At -F'|' -c "$1"; }
say() { echo "[$(date -u +%T)] $*" >&2; }
spy() {  # name, target service, command run in the py-spy container (sh -c)
    docker run -d --name "perf-spy-$1" --pid "container:$(dc ps -q "$2")" --cap-add SYS_PTRACE \
        --user root -v "$out:/out" --entrypoint sh search-stack-airflow:3.3.2 -c "$3" > /dev/null
}
SPY="/home/airflow/.local/bin/py-spy record --idle --nonblocking --rate 100 --format raw"
docker rm -f perf-spy-api perf-spy-harvester > /dev/null 2>&1 || true
trap 'docker rm -f perf-spy-api perf-spy-harvester > /dev/null 2>&1 || true' EXIT

dc exec -T crawler python3 - "$n" < "$here/seed.py" >&2
dc ps --format '{{.ID}} {{.Service}}' | while read -r id service; do
    echo "$(docker inspect -f '{{.Id}}' "$id") $service"
done > "$out/containers.txt"
cpu() { while read -r id service; do
    echo "$service $(sed -n 's/^usage_usec //p' "/sys/fs/cgroup/system.slice/docker-$id.scope/cpu.stat")"
done < "$out/containers.txt"; }

# the warehouse API is PID 1 of `transform`; the harvester a harvester-venv Python in airflow-worker
spy api transform "exec $SPY -o /out/api.raw --pid 1 > /out/api-spy.log 2>&1"
spy harvester airflow-worker "while :; do for p in /proc/[0-9]*; do
      c=\$(tr '\0' ' ' < \$p/cmdline 2>/dev/null); case \"\$c\" in /opt/airflow/harvester-venv/bin/python\ -c*) ;;
      /opt/airflow/harvester-venv/bin/python*) exec $SPY -o /out/harvester.raw --pid \${p#/proc/} > /out/harvester-spy.log 2>&1;; esac
    done; sleep 0.05; done"

load=$(cut -d' ' -f1-3 /proc/loadavg)
t0=$(date +%s.%N)
say "crawl (load $load)"
dc exec -T crawler modama-crawler crawl 2>&1 | tail -2 >&2
deadline=$(($(date +%s) + ${BENCH_TIMEOUT:-7200}))
while :; do
    if [ "$(date +%s)" -gt "$deadline" ]; then say "timeout waiting for the harvest task"; exit 1; fi
    row=$(sql "select ti.state, extract(epoch from ti.start_date), extract(epoch from ti.end_date) from task_instance ti
               join dag_run dr on dr.dag_id = ti.dag_id and dr.run_id = ti.run_id
               where ti.task_id = 'harvest_independent' and dr.start_date >= to_timestamp($t0)")
    case "$row" in running*) [ -e "$out/cpu-start.txt" ] || cpu > "$out/cpu-start.txt" ;; success* | failed*) break ;; esac
    sleep 1
done
cpu > "$out/cpu-end.txt"
docker kill --signal INT perf-spy-api > /dev/null
sleep 3
docker rm -f perf-spy-api perf-spy-harvester > /dev/null
IFS='|' read -r state start end <<< "$row"
events=$(dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "select count(*) from harvest_events
    where harvest_run_id = (select id from harvest_runs order by started_at desc limit 1)"')
echo "harvest task: $state, $(awk "BEGIN {printf \"%.1f\", $end - $start}") s for $events harvest events" \
     "= $(awk "BEGIN {printf \"%.1f\", $events / ($end - $start)}") records/s (load at start $load)"
echo "CPU seconds per container during the harvest task (cgroup usage, from its first poll as running to its end):"
join <(sort "$out/cpu-start.txt") <(sort "$out/cpu-end.txt") \
    | awk -v d="$(awk "BEGIN {print $end - $start}")" '{c = ($3 - $2) / 1e6; t += c; if (c >= 0.5) printf "  %-26s %7.1f s  %4.0f%% of a core\n", $1, c, 100 * c / d}
                END {printf "  %-26s %7.1f s  %4.0f%% of a core\n", "all", t, 100 * t / d}'
python3 "$here/harvest-report.py" "$out"
