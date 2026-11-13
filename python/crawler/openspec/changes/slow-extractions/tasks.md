# Tasks

Tests first, in the worktree's own venv (`pytest --basetemp /var/tmp/slow-extractions/pytest`). Before the code: the tests of 1.1 and 2.1 failed (`AttributeError` for `extraction.SLOW`, `IndexError` for the missing report line and review heading). After: they pass. On the review (merge after changes): `test_a_slow_extraction` failed with `assert 3.0998… < 3.0` (the worker's start counted, S3) and `test_the_slowest_extractions` for want of ` (failed)` (S1); after: they pass.

## 1. Crawler

- [x] 1.1 `tests/test_extraction.py`, one test per scenario: `test_a_slow_extraction` (every worker starts 1.5 s late through `STANDIN_IMPORT_SLEEP`), `test_a_reused_slow_extraction_keeps_its_warning`, `test_the_slowest_extractions` (one over the time limit); the stand-in format sleeps on `sleep <seconds>` (`tests/standin.py`), the threshold lowered to 1 s by monkeypatch.
- [x] 1.2 `extraction.py`: `SLOW`, `SLOW_EXTRACTION`, `SLOWEST`; `_timed`, the worker's clock; the warning set anew for every dataset not kept (`_slow`); `Report.slowest` and its line. Verify: 1.1.
- [x] 1.3 Dropped on the review: the run's column (migration `0005_crawl_runs_slowest`) and the part of the `runs` line. Verify: `schema.HEAD` back at `0004_crawl_runs_listing_errors`, the suite.

## 2. modama-chain review

- [x] 2.1 `python/search-chain/tests/test_review.py`: `test_slow_extractions` (spec `chain-browse`, "Slow extractions"); `test_the_markers_are_the_crawlers` compares `extraction.SLOW_EXTRACTION`.
- [x] 2.2 `review.MARKERS` gets `slow extraction`. Verify: 2.1.

## 3. Documentation

- [x] 3.1 README: the report line, "What to look out for"; `python/search-chain/README.md`, "review"; the decision log. Verify: read.
