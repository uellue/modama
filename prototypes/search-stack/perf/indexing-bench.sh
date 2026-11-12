#!/bin/bash
# Indexing benchmark of the search stack's test deployment: reset the stack, start it with
# the given batch size and transform-worker processes, seed N small text files, crawl
# (which starts the harvest, which starts the indexing), wait until the harvest DAG run has
# ended, and print what it took: records indexed, wall time and records/s, per-batch
# timings, CPU seconds per container, and a py-spy profile of one batch process by phase.
#
#   perf/indexing-bench.sh N CELERY_BATCH_SIZE PROCESSES [OUT]
#   e.g.  export MODAMA_SECRETS_DIR=~/.config/modama/e2e-secrets
#         perf/indexing-bench.sh 16000 250 "" /tmp/bench/b250-budget
#
# PROCESSES sets TRANSFORM_PROCESSES; empty, the worker computes its CPU budget. PERF_THREADS
# sets EMBEDDING_THREADS likewise. PERF_TODAY=1 runs the worker as before the budget
# (perf/docker-compose.today.yml; PROCESSES and PERF_THREADS are then ignored).
#
# DELETES ALL STATE of the test deployment (./downtest.sh --reset) first; never point it at
# staging. Leaves the stack up with the bench's settings and without crawl-timer (so its
# daily crawl does not interfere); afterwards ./downtest.sh --reset && ./uptest.sh for the
# default stack. OUT (default: a new folder under /tmp) gets the raw data; report.py OUT
# prints the summary again.
#
# Environment: PROFILE_NTH (which batch process to profile, default 2), PY_SPY_ARGS (default
# in perf/batch-probe.py), BENCH_TIMEOUT (seconds to wait for the harvest run, default 7200).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
stack=$(dirname "$here")
n=${1:?usage: indexing-bench.sh N CELERY_BATCH_SIZE PROCESSES [OUT]}
batch=${2:?usage: indexing-bench.sh N CELERY_BATCH_SIZE PROCESSES [OUT]}
conc=${3?usage: indexing-bench.sh N CELERY_BATCH_SIZE PROCESSES [OUT]}
out=${4:-$(mktemp -d /tmp/indexing-bench-XXXX)}
mkdir -p "$out"
out=$(cd "$out" && pwd)
: "${MODAMA_SECRETS_DIR:?set MODAMA_SECRETS_DIR (see README.md)}"
export COMPOSE_FILE="$stack/docker-compose.yml:$stack/docker-compose.override.yml:$here/docker-compose.perf.yml"
[ "${PERF_TODAY:-}" = 1 ] && COMPOSE_FILE+=":$here/docker-compose.today.yml"
export CELERY_BATCH_SIZE=$batch PERF_CONCURRENCY=$conc
# the reset below must never reach another project (staging runs as search-staging)
export COMPOSE_PROJECT_NAME=search-stack
cd "$stack"
dc() { docker compose "$@"; }
# on any exit: stop the host sampler and the probe in the worker, which would run on
stop() { touch "$out/.stop"; dc exec -T airflow-worker-transform touch /tmp/perf-probe/stop 2> /dev/null || true; }
trap stop EXIT
sql() { dc exec -T airflow-postgres psql -U airflow -d airflow -At -F'|' -c "$1"; }
say() { echo "[$(date -u +%T)] $*" >&2; }

say "reset and start the stack (CELERY_BATCH_SIZE=$batch, concurrency $conc), without crawl-timer"
./downtest.sh --reset > "$out/down.log" 2>&1
./uptest.sh --scale crawl-timer=0 > "$out/up.log" 2>&1
# the worker's command line, to check the concurrency it got (the image has no ps)
dc exec -T airflow-worker-transform sh -c 'for p in /proc/[0-9]*; do tr "\0" " " < $p/cmdline; echo; done' \
    | grep -m1 -e '--concurrency' > "$out/worker-command.txt" || true
dc logs airflow-worker-transform 2>&1 | grep -m1 'CPU budget:' > "$out/budget.txt" || true

say "load the embedding model once, into the empty cache volume (as staging's, which keeps it)"
prewarm=$(dc exec -T airflow-worker-transform /opt/airflow/transform-venv/bin/python -c '
import os, time
t = time.monotonic()
from fastembed import TextEmbedding
TextEmbedding(model_name=os.environ["EMBEDDING_MODEL"], cache_dir=os.environ["FASTEMBED_CACHE_DIR"])
print(f"{time.monotonic() - t:.1f}")')

say "seed $n files"
dc exec -T crawler python3 - "$n" < "$here/seed.py" > "$out/seed.log"
cat "$out/seed.log" >&2

# CPU per container from the host's cgroups (cgroup v2, systemd driver), every 2 s
dc ps --format '{{.ID}} {{.Service}}' | while read -r id service; do
    echo "$(docker inspect -f '{{.Id}}' "$id") $service"
done > "$out/containers.txt"
rm -f "$out/.stop"
(
    while [ ! -e "$out/.stop" ]; do
        t=$(date +%s.%N)
        while read -r id service; do
            u=$(sed -n 's/^usage_usec //p' "/sys/fs/cgroup/system.slice/docker-$id.scope/cpu.stat" 2>/dev/null) || continue
            printf '%s\t%s\t%s\n' "$t" "$service" "$u"
            # waiting for a CPU: PSI's total stall time in µs (R6, per container)
            p=$(sed -n 's/^some .*total=//p' "/sys/fs/cgroup/system.slice/docker-$id.scope/cpu.pressure" 2>/dev/null) &&
                printf '%s\t%s\t%s\n' "$t" "$service" "$p" >> "$out/pressure.tsv"
        done < "$out/containers.txt"
        printf '%s\t%s\n' "$t" "$(cut -d' ' -f1 /proc/loadavg)" >> "$out/load.tsv"
        sleep 2
    done
) > "$out/cpu.tsv" &
sampler=$!

dc exec -T airflow-worker-transform rm -rf /tmp/perf-probe
# shellcheck disable=SC2086  # PY_SPY_ARGS: several arguments
dc exec -T airflow-worker-transform python3 - /tmp/perf-probe "${PROFILE_NTH:-2}" ${PY_SPY_ARGS:-} \
    < "$here/batch-probe.py" > "$out/probe.log" 2>&1 &
probe=$!
sleep 2

load=$(cut -d' ' -f1-3 /proc/loadavg)
t0=$(date +%s.%N)
say "crawl (load $load); the crawl starts the harvest"
dc exec -T crawler modama-crawler crawl > "$out/crawl.log" 2>&1
crawl_end=$(date +%s.%N)
crawl_summary=$(grep -o '[0-9]* datasets, [0-9]* warnings, [0-9]* records changed' "$out/crawl.log" | tail -1 || true)
say "crawl done: $crawl_summary; waiting for the harvest run to end"
deadline=$(($(date +%s) + ${BENCH_TIMEOUT:-7200}))
while :; do
    state=$(sql "select state from dag_run where dag_id = 'warehouse_harvest_and_index'
                 and start_date >= to_timestamp($t0) order by start_date desc limit 1")
    case "$state" in success | failed) break ;; esac
    if [ "$(date +%s)" -gt "$deadline" ]; then say "timeout, harvest run state: '$state'"; break; fi
    sleep 10
done
say "harvest run: $state"

dc exec -T airflow-worker-transform touch /tmp/perf-probe/stop
wait "$probe" || true
touch "$out/.stop"
wait "$sampler" || true
rm -rf "$out/probe"
dc cp airflow-worker-transform:/tmp/perf-probe "$out/probe" > /dev/null

sql "select dag_id, extract(epoch from start_date), extract(epoch from end_date), state from dag_run
     where start_date >= to_timestamp($t0) order by start_date" > "$out/dagruns.txt"
sql "select ti.dag_id, ti.task_id, ti.map_index, ti.state, extract(epoch from ti.queued_dttm),
     extract(epoch from ti.start_date), extract(epoch from ti.end_date)
     from task_instance ti join dag_run dr on dr.dag_id = ti.dag_id and dr.run_id = ti.run_id
     where dr.start_date >= to_timestamp($t0) order by ti.start_date" > "$out/tasks.txt"
curl -s 'http://127.0.0.1:9200/test_datacite/_count' > "$out/count.json"
# the transform batches' log lines only (the file-metadata batches log "Transformed batch" too)
dc exec -T airflow-worker-transform sh -c "find /opt/airflow/logs -path '*task_id=run_transform_batch*' -type f \
    -exec grep -h -e 'Transform resources ready' -e 'Transformed batch' {} +" > "$out/batch-log.txt" || true
cat > "$out/meta.env" <<EOF
n=$n
batch=$batch
conc=$conc
threads=${PERF_THREADS:-}
today=${PERF_TODAY:-}
t0=$t0
crawl_end=$crawl_end
load=${load// /,}
prewarm_s=$prewarm
crawl_summary=${crawl_summary// /_}
EOF

echo "== summary ($out)"
python3 "$here/report.py" "$out"
