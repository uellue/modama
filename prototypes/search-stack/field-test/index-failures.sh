#!/bin/bash
# Why the latest indexing run (DAG warehouse_transform_index) failed: the count of its tasks
# per state, then for each failed task its id, batch (map index), tries and times, and the
# last lines of its latest log. Read-only.
#
#   bash index-failures.sh [compose project, default search-staging] > index-failures.txt 2>&1
set -uo pipefail
p="${1:-search-staging}"
run=$(docker exec "$p-airflow-postgres-1" sh -c 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-airflow}" -At -c "
  select run_id from dag_run where dag_id = '"'"'warehouse_transform_index'"'"'
  order by start_date desc nulls last limit 1"')
echo "== run $run"
docker exec "$p-airflow-postgres-1" sh -c 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-airflow}" -c "
  select task_id, state, count(*) from task_instance
  where dag_id = '"'"'warehouse_transform_index'"'"' and run_id = '"'"'"$1"'"'"'
  group by 1, 2 order by 1, 2"' sh "$run"
echo "== failed tasks"
docker exec "$p-airflow-postgres-1" sh -c 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-airflow}" -At -F " " -c "
  select task_id, map_index, try_number, start_date, end_date from task_instance
  where dag_id = '"'"'warehouse_transform_index'"'"' and run_id = '"'"'"$1"'"'"'
    and state in ('"'"'failed'"'"', '"'"'upstream_failed'"'"')
  order by start_date nulls last"' sh "$run" > /tmp/index-failures.$$
cat /tmp/index-failures.$$
head -n 5 /tmp/index-failures.$$ |
while read -r task map try _; do
    [ "$map" = "-1" ] && m="" || m="/map_index=$map"
    echo "== log of $task$m, try $try (last 40 lines)"
    # the log is on the worker that ran the task: the transform worker for batches, else the default one
    for w in airflow-worker-transform airflow-worker; do
        docker exec "$p-$w-1" sh -c \
            'f="/opt/airflow/logs/dag_id=warehouse_transform_index/run_id=$1/task_id=$2$3/attempt=$4.log"
             [ -e "$f" ] && { echo "($0)"; tail -n 40 "$f"; }' \
            "$w" "$run" "$task" "$m" "$try" 2>&1 | cut -c1-400
    done
done
rm -f "/tmp/index-failures.$$"
echo "== records in the warehouse index, against the crawler's"
docker exec "$p-opensearch-1" curl -s "localhost:9200/_cat/count/test_datacite?h=count"
docker exec "$p-crawler-db-1" psql -U postgres -d modama_crawler -At -c "select count(*) from records"
