"""Starting the warehouse's harvest of this endpoint after a crawl (decision log 2026-11-04 and 2026-11-05).

The harvest runs as the Airflow DAG `warehouse_harvest_and_index` of the EOSC
metadata warehouse (v1.10.0); its conf `harvest_urls` limits it to our
endpoint. Airflow's REST API /api/v2, with an account allowed to trigger DAG
runs (role User).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

DAG = "warehouse_harvest_and_index"
TIMEOUT = 30


class TriggerError(Exception):
    pass


def _post(url: str, data: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, json.dumps(data).encode(), headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise TriggerError(f"{url}: HTTP {e.code} {e.reason}") from e
    except OSError as e:
        raise TriggerError(f"{url}: {getattr(e, 'reason', e)}") from e


def trigger(airflow_url: str, user: str, password: str, harvest_url: str) -> str:
    """Start a harvest of harvest_url; returns the DAG run's id. Raises TriggerError."""
    token = _post(f"{airflow_url}/auth/token", {"username": user, "password": password})
    run = _post(
        f"{airflow_url}/api/v2/dags/{DAG}/dagRuns",
        {"logical_date": None, "conf": {"harvest_urls": [harvest_url]}},
        token["access_token"],
    )
    return run["dag_run_id"]
