"""Reading the warehouse's indexing runs from Airflow (warehouse.py)."""

from modama_chain import warehouse


def run(state, harvest, run_after, start=None, end=None):
    """A DAG run as Airflow 3's REST API returns it (the fields index_runs reads)."""
    return {
        "state": state,
        "run_after": run_after,
        "start_date": start,
        "end_date": end,
        "conf": {"harvest_run_id": harvest},
    }


def test_a_run_cancelled_before_it_started_does_not_hide_newer_runs(monkeypatch):
    """Staging, 2026-11-15: a run queued and then cancelled yesterday has no start
    date; ordered by start date (nulls first) it stayed on top, and status showed
    it instead of the night's successful run."""
    pages = [
        {"access_token": "t"},
        {
            "dag_runs": [
                run(
                    "failed", "de02", "2026-11-14T05:20:00Z", end="2026-11-14T05:32:20Z"
                ),
                run(
                    "success",
                    "58cb",
                    "2026-11-14T21:49:30Z",
                    "2026-11-14T21:49:31Z",
                    "2026-11-14T21:51:20Z",
                ),
                run(
                    "failed",
                    "de02",
                    "2026-11-14T01:46:30Z",
                    "2026-11-14T01:46:33Z",
                    "2026-11-14T04:11:58Z",
                ),
            ]
        },
    ]
    monkeypatch.setattr(warehouse, "get_json", lambda *a, **k: pages.pop(0))

    runs = warehouse.index_runs("http://airflow", "user", "password")

    assert [(r.state, r.harvest_run_id) for r in runs] == [
        ("success", "58cb"),
        ("failed", "de02"),
        ("failed", "de02"),
    ]
    assert runs[1].start is None
