#!/bin/bash
# Reproducer of F17, in its own compose project (f17-repro, no published ports), torn
# down at the end. A task longer than the broker's consumer_timeout, then a second task
# once the timeout has passed. Exit 0 if the second task ran while the long one was
# still running and the long one ran once; 1 if not (the failure of F17, or the broker
# redelivered the long task and the worker ran it again).
#
#   ./run.sh                     the failure: consumer_timeout 60 s, a task of 180 s
#   REPRO_BROKER_CONF=../broker.conf ./run.sh
#                                the stack's broker setting (the fix)
#   REPRO_CELERY='{"broker_channel_error_retry": true}' ./run.sh
#                                a Celery setting on top of Airflow's
#
# REPRO_LONG (seconds, 180) is the long task's duration; REPRO_PROJECT the project name,
# for runs side by side. About 4 minutes. Needs the stack's Airflow image
# (search-stack-airflow:3.3.2, built by ../uptest.sh).
set -uo pipefail
cd "$(dirname "$0")"
long=${REPRO_LONG:-180}
dc() { docker compose -p "${REPRO_PROJECT:-f17-repro}" "$@"; }
t0=$(date +%s)
say() { echo "[t+$(($(date +%s) - t0))s] $*"; }
send() { dc exec -T worker python -c "import repro_tasks as t; t.sleep.apply_async(args=[$1, '$2'], queue='default')"; }
worker_state() {
    docker inspect -f 'worker: {{.State.Status}}, health {{.State.Health.Status}}, restarts {{.RestartCount}}' "$(dc ps -aq worker)"
}
queues() { dc exec -T broker rabbitmqctl list_queues -q name messages messages_unacknowledged consumers; }
ran() { dc logs worker 2>/dev/null | grep -c "REPRO $1 finished"; }
trap 'dc down -v --remove-orphans >/dev/null 2>&1' EXIT

dc up -d --wait >/dev/null 2>&1 || { echo "the reproducer did not come up"; dc logs; exit 2; }
t0=$(date +%s)
say "broker: $(dc exec -T broker rabbitmq-diagnostics -q environment | grep -o '{consumer_timeout,[^}]*}')"
say "$(worker_state)"
send "$long" long && say "sent the long task ($long s)"
# the broker checks the timeout about once a minute; wait for it, or 130 s
for _ in $(seq 26); do
    dc logs worker 2>/dev/null | grep -q "PRECONDITION_FAILED" && break
    sleep 5
done
dc logs worker 2>/dev/null | grep -o "Unrecoverable error: PreconditionFailed.\{0,90\}" | head -n1 | sed 's/^/        /'
send 5 second && say "sent the second task (5 s)"
sleep 25
say "second task finished: $(ran second)"
say "$(worker_state)"
queues | sed 's/^/        /'
while [ $(($(date +%s) - t0)) -lt $((long - 5)) ]; do sleep 1; done
second_early=$(ran second)
say "just before the long task ends: second task finished: $second_early; $(worker_state)"
sleep 20
say "long task finished: $(ran long)"
sleep 30
say "after the long task: second task finished: $(ran second); $(worker_state)"
queues | sed 's/^/        /'
echo "worker log, the lines that tell:"
dc logs --no-log-prefix -t worker 2>/dev/null \
    | grep -E "REPRO|critical|ready\.|Connected to" | grep -vE '^\S+ {2}' \
    | cut -c1-200 | sed 's/^/        /'
long_runs=$(dc logs worker 2>/dev/null | grep -c "REPRO long started")
if [ "$second_early" -lt 1 ]; then
    say "RESULT: the second task did not run while the long task was running (F17)"
    exit 1
fi
if [ "$long_runs" -ne 1 ]; then
    say "RESULT: the second task ran, but the long task started $long_runs times (redelivered)"
    exit 1
fi
say "RESULT: the second task ran while the long task was running, the long task once"
exit 0
