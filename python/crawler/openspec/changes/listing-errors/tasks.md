# Tasks

Tests first: each test of sections 1 and 2 is written and run before the code it covers, and fails then, unless it says it passes before and after. The errors are injected by monkeypatching `walk._names` (listings), `walk._stat` (an entry's stat), `os.lstat` (a folder's own stat), `os.access` and `os.open` (D5), and `mime.open` and `formats.open` (reads; review 1: not `detect_with_tie`), each raising `OSError(errno.X, os.strerror(errno.X), path)` for one path; the stand-in formats of `tests/standin.py` give datasets with extractions. Runs in the worktree's own venv, `pytest --basetemp /var/tmp/listing-errors/pytest`.

Before the fix (`crawler` at 89e16a57 merged, the tests of `tests/test_unanswered.py` written, the code unchanged): 40 failed, 5 passed, the five being "Permission denied", "A folder that is gone", "Access says no, and open says why", "The root does not answer" and "A refused folder alone", which pass before and after by design. "The folder's own stat does not answer" failed with `assert 2 == 4` (the crawl ended `failed`, review 4); the pre-order cases with `assert 0 == 4` after `zarr/zarr failed: OSError(5, …)` and `le/marked failed: …` (walked file by file); the format that catches the error with `assert 0 == 4` after `cannot read the header: OSError(116, …)`; "A file that is gone during detection" and "The walk's result is unchanged" for want of the `cannot read` warning (review 1). After the fix: 45 passed.

## 1. Tests of the crawl that fail today

- [x] 1.1 `tests/test_unanswered.py`: one test per scenario of `crawl`'s "A folder the file system did not answer keeps its records" (ESTALE, EIO, ENOMEM, folders below, the folder's own stat, collapsed folder, pre-order read, a lower-priority format, below a subtree crawl's path, changed rule set), "A kept folder is tried again by the next crawl" and "Kept datasets are not extracted again", through `cli.main(["crawl", …])` in this process, comparing records (identifiers, metadata, datestamps moved back a day first, so that a rewrite shows) and the extractor's calls.
- [x] 1.2 The same file: "A file the file system did not answer keeps its folder's records" (an entry's stat, a subfolder's stat, access, detection, a format that catches the error, gone during detection, the walk's result).
- [x] 1.3 The same file: "Permission denied" by monkeypatch (so that it also runs as root), "Access says no, and open says why", "A folder that is gone", "The root does not answer"; "A refused folder that had datasets is named" (fails today for want of the warning and the column).

## 2. Tests of the run, `runs`, the harvest and the chain that fail today

- [x] 2.1 `tests/test_unanswered.py`: the run record, the refused folders, the error lines and status 4, "The same record whatever the threads" (`MODAMA_CRAWLER_WALK_THREADS` 1 and 16, 150 folders, the first 100 the same), "Kept for two crawls".
- [x] 2.2 The same file: `runs | head -1` as the docs type it ("The report line", "Many folders on the line"), "Aligned columns", `runs --follow` (status 4), the timer's `overdue(last_finished(…))`, the subtree crawl's comparison after a crawl with errors.
- [x] 2.3 The same file: the `harvest-trigger` scenarios, with the Airflow stand-in of `tests/test_trigger.py`.
- [x] 2.4 `0004_crawl_runs_listing_errors` up and down: covered by the existing generic tests, which walk every revision (`test_every_downgrade_undoes_its_revision_or_refuses`, `test_a_single_head_equal_to_schema_head`); no test of its own, since the migration only adds two nullable columns. `test_a_database_made_before_migrations` counts the two new columns.
- [x] 2.5 `python/search-chain/tests/test_rules.py`: "A crawl with kept folders", "An older crawler" (and the column probe of `test_runs_of_a_crawler_without_scope`). Against `crawler`'s search-chain code: 2 failed; after: 38 passed.

## 3. Implementation

- [x] 3.1 `formats/__init__.py`: `not_visible()`, `errno_name()`; `Directory.unanswered`, noted by `read()` before it re-raises, `cannot_read()` and `_call()`; `Dataset.kept`; `Unanswered`; `Result.unanswered`, `Result.refused`.
- [x] 3.2 `walk.py`: `_stat` asks `open(2)` again (D5); `_entries` notes entries that did not answer; `visit` keeps the subtree (D2) or the folder alone (D3), notes refused folders (D10); detection with `strict=True` and the fallback after a "not visible" error (D6); `_restore` loads the kept datasets after the walk (D4).
- [x] 3.3 `store.py`: `Stored.stored()`, `Stored.counts()`, `_directories_under()`, lazy listings; `Run`, `end_run` with `unanswered` and `refused`; `unanswered_before()` for `since` and `crawls`. `extraction.py`: kept datasets left as stored (D7).
- [x] 3.4 `cli.py`: `crawl_tree` passes `kept`; `cmd_crawl` logs, records and returns 4 after the harvest trigger; `_state`, `_run_line` (the state column as wide as `finished with errors`), `runs --follow`.
- [x] 3.5 Migration `0004_crawl_runs_listing_errors`, `schema.HEAD`.
- [x] 3.6 `search-chain`: `crawler.Run.unanswered` behind the column probe; `crawl_state`, `crawl_line`, the freshness line.
- [x] 3.7 D4's lookup on 1,440,000 dataset rows (120,000 directories, one member each) in a throwaway PostgreSQL 17: `stored()` 0.70 s for 10 folders (120 datasets), 1.89 s for 5,000 folders (60,000), 2.21 s for one top folder of 72,000; `counts()` 0.72 to 0.77 s for each. Script: the scratchpad's `measure_kept.py` (not committed).

## 4. Documentation and the backlog

- [x] 4.1 `README.md`: status 4 beside 3, a paragraph on what the file system did not answer, the states and the `runs` example (rendered by `_run_line`), "What to look out for" (what the admin does, `exclude` and its full re-recognition, errnos about names). `design/requirements.md` R35. `design/architecture.md`: the decision log row. `BACKLOG.md`: the item closes, its open points and the "Not now" items.

## 5. Acceptance

- [x] 5.1 The crawler suite, `search-chain`'s, `modama-formats-em`'s and `modama-formats-common`'s, and CI's ruff (`uvx ruff format --check`, `uvx ruff check`) on the changed packages, with the number of skipped tests and how the environment differs from CI's. Crawler (`pytest tests src`): 542 passed, 0 skipped, 8 min; search-chain 78 passed; em 135 passed; common 276 passed; ruff: "All checks passed!", "267 files already formatted". As user `dev`, not root, so the `chmod` tests ran; the worktree's own venv; the first full run had 4 failures, three older tests that injected the error in `detect_with_tie` or denied only `access(2)` (now the read, and `open(2)` too) and the column count of `test_a_database_made_before_migrations`.
- [ ] 5.2 Code review by an agent that did not write it, given the code, this change's specs and decision 271 (a migration is in it; AGENTS.md). Verified: `review.md` in this change.
- [ ] 5.3 The search stack's `./runtest.sh e2e`, only with the main session's OK (shared images).
