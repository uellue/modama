# Run in the embedding worker, read from stdin (no quoting to paste):
#   dc exec -T airflow-worker-transform bash < field-test/batch-times.sh
# (`bash -s DIR < field-test/batch-times.sh` reads the task logs in DIR instead of
# /opt/airflow/logs.)
# Batch timings of the transform tasks from their logs: how many log lines of each task,
# then per batch of run_transform_batch, in time order, the model load, the batch time, the
# documents indexed and how its texts were embedded: `service` (the embedding service),
# `fallback` (the service failed, embedded locally), `local` (no service configured) or `-`
# (no embedding, vectors reused); from upstream's lines in embedding_utils.py
# (change embedding-service-grace). Last, the count of each.
logs_dir="${1:-/opt/airflow/logs}"
logs=$(grep -rh -e 'Transform resources ready' -e 'Transformed batch' -e 'planned events' "$logs_dir")
for task in run_transform_batch run_filemeta_batch; do
    echo "$task: $(grep -c "\"task_id\":\"$task\"" <<< "$logs") log lines"
done
rows=$(find "$logs_dir" -path '*task_id=run_transform_batch/*' -name '*.log' -print0 \
    | xargs -0 -r awk '
        function event() { return match($0, /"event":"[^"]*"/) ? substr($0, RSTART + 9, RLENGTH - 10) : "" }
        function flush() {
            if (ended != "") printf "%s  load %6s  batch %7s  indexed %5s  %s\n", ended, load, took, indexed, kind
            ended = ""; load = "-"; took = "-"; indexed = "-"; kind = "-"
        }
        FNR == 1 { flush() }
        { e = event() }
        e ~ /^Transform resources ready after / { load = $0; sub(/.*ready after /, "", load); sub(/".*/, "", load) }
        e ~ /^Transformed batch in / {
            split(e, w, " "); took = w[4]; sub(/,$/, "", took); indexed = w[5]
            # date and time, so that the sort below is in time order across days
            ended = $0; sub(/.*"timestamp":"/, "", ended); sub(/[.Z"].*/, "", ended)
        }
        e ~ /from with API$/ { kind = "service" }
        e ~ /falling back to local model\.$/ { kind = "fallback" }
        e ~ /calculating embeddings locally$/ { kind = "local" }
        END { flush() }' \
    | sort)
[ -n "$rows" ] || { echo "no batch of run_transform_batch in $logs_dir"; exit 0; }
tail -n 45 <<< "$rows"
awk '{ n[$NF]++ } END { printf "batches %d: service %d, fallback %d of %d, local %d, none %d\n", NR, n["service"], n["fallback"], NR, n["local"], n["-"] }' <<< "$rows"
