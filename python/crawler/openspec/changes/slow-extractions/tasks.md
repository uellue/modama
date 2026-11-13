# Tasks

Tests first, in the worktree's own venv (`pytest --basetemp /var/tmp/slow-extractions/pytest`). Before the code: the four tests of 1.1 and the one of 2.1 failed (`AttributeError` for `extraction.SLOW`, `IndexError` for the missing report line and review heading). After: they pass.

## 1. Crawler

- [x] 1.1 `tests/test_extraction.py`, one test per scenario: `test_a_slow_extraction`, `test_a_reused_slow_extraction_keeps_its_warning`, `test_the_slowest_extractions`, `test_the_slowest_extractions_stay_with_the_run`; the stand-in format sleeps on `sleep <seconds>` (`tests/standin.py`), the threshold lowered to 1 s by monkeypatch.
- [x] 1.2 `extraction.py`: `SLOW`, `SLOW_EXTRACTION`, `SLOWEST`; the warning set anew for every dataset not kept (`_slow`); `Report.slowest`, its line and `slowest_json`. Verify: 1.1.
- [x] 1.3 Migration `0005_crawl_runs_slowest` (one nullable JSONB column), `schema.HEAD`, `end_run`, `Run`, the `runs` line. Verify: 1.1, `tests/test_migrations.py` (every revision up and down; `test_a_database_made_before_migrations` counts the new column).

## 2. modama-chain review

- [x] 2.1 `python/search-chain/tests/test_review.py`: `test_slow_extractions` (spec `chain-browse`, "Slow extractions"); `test_the_markers_are_the_crawlers` compares `extraction.SLOW_EXTRACTION`.
- [x] 2.2 `review.MARKERS` gets `slow extraction`. Verify: 2.1.

## 3. Documentation

- [x] 3.1 README: the report line, the `runs` part, "What to look out for"; `python/search-chain/README.md`, "review"; the decision log. Verify: read.
