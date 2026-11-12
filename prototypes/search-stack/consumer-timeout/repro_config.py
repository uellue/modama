# Airflow's own Celery configuration (what the stack's workers run with: acks late,
# prefetch multiplier 1, ...), plus the reproducer's task module and, for trying a fix,
# Celery settings as JSON in REPRO_CELERY. Loaded through Airflow's
# [celery] celery_config_options, as a deployment would customise Celery.
import json
import os

from airflow.providers.celery.executors.default_celery import DEFAULT_CELERY_CONFIG

CONFIG = (
    DEFAULT_CELERY_CONFIG
    | {"imports": ["repro_tasks"]}
    | json.loads(os.environ.get("REPRO_CELERY") or "{}")
)
