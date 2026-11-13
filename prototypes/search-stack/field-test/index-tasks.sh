#!/bin/bash
# The latest indexing run (DAG warehouse_transform_index) as CSV: one row per task and batch,
# with queued, started and ended, from Airflow's own database; then plan_batches' line
# "Harvest run ...: N events in M batches" (N = the records the harvest stored).
# Read-only. Tried on the VM's search stack 2026-11-12.
#
#   bash index-tasks.sh [compose project, default search-staging] > index-tasks.csv
set -euo pipefail
p="${1:-search-staging}"
docker exec "$p-airflow-postgres-1" sh -c 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-airflow}" -c "\copy (
  select task_id, map_index, state, queued_dttm, start_date, end_date, hostname, try_number
  from task_instance
  where dag_id = '"'"'warehouse_transform_index'"'"'
    and run_id = (select run_id from dag_run where dag_id = '"'"'warehouse_transform_index'"'"'
                  order by start_date desc nulls last limit 1)
  order by start_date nulls last, map_index) to stdout with csv header"'
docker exec "$p-airflow-worker-1" sh -c \
  'grep -h "events in" /opt/airflow/logs/dag_id=warehouse_transform_index/run_id=*/task_id=plan_batches/*.log | tail -n 1' >&2
