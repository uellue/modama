# Run in the embedding worker, read from stdin (no quoting to paste):
#   dc exec -T airflow-worker-transform bash < field-test/batch-times.sh
# Batch timings of the transform tasks from their logs, in time order: how many batches
# of each task, and per batch of run_transform_batch the model load and the batch time.
logs=$(grep -rh -e 'Transform resources ready' -e 'Transformed batch' -e 'planned events' /opt/airflow/logs)
for task in run_transform_batch run_filemeta_batch; do
    echo "$task: $(grep -c "\"task_id\":\"$task\"" <<< "$logs") log lines"
done
grep '"task_id":"run_transform_batch"' <<< "$logs" \
    | sed -E 's/.*"timestamp":"[^T]*T([^.]*)[^"]*".*"event":"([^"]*)".*/\1 \2/; s/.*"event":"([^"]*)".*"timestamp":"[^T]*T([^.]*)[^"]*".*/\2 \1/' \
    | sort | tail -n 45
