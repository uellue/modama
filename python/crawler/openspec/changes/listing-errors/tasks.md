# Tasks

Tests first: each test of sections 1 and 2 is written and run before the code it covers, and fails then (record the failing line in the hand-over). The errors are made by monkeypatching `walk._names`, `walk._stat`, `os.lstat` in `walk`, `mime.detect_with_tie` or `mime.open` to raise `OSError(errno.X, os.strerror(errno.X), path)` for one path, as the review's reproducer did (`BACKLOG.md`); the stand-in formats of `tests/standin.py` give datasets with extractions. Runs in the worktree's own venv, `pytest --basetemp /var/tmp/listing-errors/pytest`.

## 1. Tests that fail today

- [ ] 1.1 `tests/test_walk.py` or a new `tests/test_unanswered.py`: one test per scenario of "A folder the file system did not answer keeps its records" (ESTALE, EIO, ENOMEM, folders below, stat of an entry, collapsed folder, pre-order call, changed rule set), "A kept folder is tried again by the next crawl" and "Kept datasets are not extracted again", each comparing the records' identifiers, metadata and datestamps before and after, and the extractor's calls (`calls` file). Verified: each fails on `crawler` at 3684d362 with the records gone.
- [ ] 1.2 The same file: the scenarios of "A file the file system did not answer keeps its folder's records" (type read EIO, format read ESTALE, ENOENT as before, the walk's result unchanged). Verified: the first two fail today (the type becomes `application/octet-stream`, the format's dataset falls apart); the last two pass before and after.
- [ ] 1.3 `tests/test_walk.py`: "A folder that is gone" (ENOENT) and "Permission denied" (EACCES, by monkeypatch, so that it also runs as root, unlike the `chmod` tests) still delete. Verified: pass before and after (the guard against over-keeping).
- [ ] 1.4 `tests/test_subtree.py`: "A folder below the path of a subtree crawl", on the review's reproducer tree. Verified: fails today.
- [ ] 1.5 `tests/test_cli.py` or `tests/test_runs.py`: "The root does not answer" (EIO on the root: status 2, `failed`, records kept). Verified: passes today (A6 kept).

## 2. Tests of the run record, `runs` and the harvest that fail today

- [ ] 2.1 `tests/test_runs.py`: "The run records the folder", "A file in recognition", "More than 100 folders", "Not visible is no error", "A subtree crawl", through `cli.main(["crawl", …])` with `caplog` and the exit status. Verified: fail today (status 0, no column).
- [ ] 2.2 `tests/test_runs.py`: "The report line" and "Many folders on the line" through `runs | head -1` as the docs type it; "The timer counts it as finished" through `overdue(last_finished(…))`. Verified: the first two fail today.
- [ ] 2.3 `tests/test_trigger.py`: "The harvest starts after errors" and "Errors and a harvest that cannot be started", with the Airflow stand-in of the existing trigger tests. Verified: fail today (status 0 and 3).
- [ ] 2.4 `tests/test_migrations.py`: `0004_crawl_runs_unanswered` up and down on a database with runs; after the downgrade the older code's `runs` reads them. Verified: fails until the migration exists.

## 3. Implementation

- [ ] 3.1 `walk.py`: `not_visible(err)` (D1); in `visit`, a "did not answer" error of the listing, the folder's `lstat`, an entry's `_stat` or the pre-order call keeps the stored subtree from `kept.datasets_under(rel)` with the parents set as in D2, no listing below, "not unchanged", an entry in `result.unanswered`; `recognise` returns the first such error of detection, `cannot_read` or a format call, and `visit` keeps the folder's own stored datasets then (D3). Without `kept`, as today. Verified: 1.1 to 1.3 pass.
- [ ] 3.2 `formats/__init__.py`: `Directory` keeps the first "did not answer" `OSError` of `cannot_read` and `_call`; `Dataset.kept` (not stored); `Result.unanswered`. Verified: 1.2 passes, and the `recognition` tests of `test_content_checks.py` still pass unchanged.
- [ ] 3.3 `store.py`: `Stored.datasets_under(rel)`; `Run.unanswered`, `end_run(unanswered=…)`. `extraction.py`: kept datasets are not run or spot-checked (D5). Verified: the extractor-call counts of 1.1.
- [ ] 3.4 `cli.py`: `crawl_tree` passes `kept=Stored(conn)` for full and subtree crawls (D4); `cmd_crawl` logs the lines of D8, records the run and returns 4 after the harvest trigger; `_state`/`_run_line` show `finished with errors` and the folders. Verified: 1.4, 2.1 to 2.3 pass.
- [ ] 3.5 Migration `0004_crawl_runs_unanswered` (nullable JSONB, downgrade drops it), `schema.HEAD`. Verified: 2.4 passes; `modama-chain`'s tests pass unchanged (it does not read the column).

## 4. Documentation and the backlog

- [ ] 4.1 `README.md`: the exit statuses (4 beside 3), "What to look out for" (a run `finished with errors`: what the admin does), the reading of `runs`. `design/requirements.md` R35: directories the file system says are not visible are skipped; one that did not answer keeps its records. `design/architecture.md`: the decision log row for 271 with A1 to A6 and the answers to Q1 to Q6. `BACKLOG.md`: the item "a folder that fails to list loses its records" closes; the "Not now" items of the design go in. Verified: `git diff` of the four files in the hand-over.

## 5. Acceptance

- [ ] 5.1 The whole crawler suite and `uvx ruff format --check --diff` and `uvx ruff check` from the repository root, with the number of skipped tests and how the environment differs from CI's (root or not: the `chmod` tests skip as root). Verified: the commands' output.
- [ ] 5.2 Code review by an agent that did not write it, given the code, this change's specs and decision 271, not the author's conclusions (a migration is in it; AGENTS.md). Verified: `review.md` in this change, findings verified before they are acted on.
- [ ] 5.3 The search stack's `./runtest.sh e2e` in `/prototypes/search-stack/`, only with the main session's OK (shared images). Verified: its PASS/FAIL count.
