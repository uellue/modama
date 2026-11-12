#!/bin/bash
# Re-run the hallway test's experiments of 2026-11-12 (cpu-budget task 5.3) against the running
# test deployment: ./cpu-budget.sh with each override file of this folder, and with a few
# AIRFLOW_TASK_LIMIT values. Read-only (throwaway containers only). Output: one *.out per case,
# in a folder given as the first argument (default: a new one under /tmp).
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
stack=$here/../../../../../prototypes/search-stack
out=${1:-$(mktemp -d /tmp/hallway-cpu-XXXX)}
mkdir -p "$out"
cd "$stack" || exit 2
./cpu-budget.sh > "$out/default.out" 2>&1; echo "exit=$?" >> "$out/default.out"
for f in "$here"/*.yml; do
    name=$(basename "$f" .yml)
    COMPOSE_FILE="docker-compose.yml:docker-compose.override.yml:$f" ./cpu-budget.sh > "$out/$name.out" 2>&1
    echo "exit=$?" >> "$out/$name.out"
done
for limit in 3 16 0 abc; do
    AIRFLOW_TASK_LIMIT=$limit ./cpu-budget.sh > "$out/task-limit-$limit.out" 2>&1
    echo "exit=$?" >> "$out/task-limit-$limit.out"
done
echo "results in $out"
