# A task on Airflow's Celery app that only sleeps: the stand-in for the harvest DAG's
# wait for the indexing run (TriggerDagRunOperator with wait_for_completion), whose
# message stays unacknowledged while it runs.
import time

from airflow.providers.celery.executors.celery_executor import app


@app.task(name="repro.sleep")
def sleep(seconds, tag):
    print(f"REPRO {tag} started, {seconds} s", flush=True)
    time.sleep(seconds)
    print(f"REPRO {tag} finished", flush=True)
