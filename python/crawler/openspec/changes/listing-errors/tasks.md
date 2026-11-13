# Tasks

Tests first: each test of sections 1 and 2 is written and run before the code it covers, and fails then, unless it says it passes before and after. The errors are injected by monkeypatching `walk._names` (listings), `walk._stat` (an entry's stat), `os.lstat` (a folder's own stat), `os.access` and `os.open` (D5), and `mime.open` and `formats.open` (reads; review 1: not `detect_with_tie`), each raising `OSError(errno.X, os.strerror(errno.X), path)` for one path; the stand-in formats of `tests/standin.py` give datasets with extractions. Runs in the worktree's own venv, `pytest --basetemp /var/tmp/listing-errors/pytest`.

## 1. Tests of the crawl that fail today

- [ ] 1.1 `tests/test_unanswered.py`: one test per scenario of `crawl`'s "A folder the file system did not answer keeps its records", "A kept folder is tried again by the next crawl" and "Kept datasets are not extracted again", through `cli.main(["crawl", …])` in this process, comparing records (identifiers, metadata, datestamps) and the extractor's calls before and after. Verified: each fails today with the records gone, except "The folder's own stat does not answer", which fails today with status 2 and the run `failed` (review 4).
- [ ] 1.2 The same file: "A file the file system did not answer keeps its folder's records". Verified: the entry stat, access, detection and format-read cases fail today; "A file that is gone during detection" fails today for want of the warning (review 1); "The walk's result is unchanged" passes before and after.
- [ ] 1.3 The same file: the skip requirement's "Permission denied" by monkeypatch (so that it also runs as root), "Access says no, and open says why", "A folder that is gone", "The root does not answer". Verified: pass before and after (the guard against keeping too much), and "A refused folder that had datasets is named" fails today for want of the warning.

## 2. Tests of the run, `runs`, the harvest and the chain that fail today

- [ ] 2.1 `tests/test_unanswered.py`: the scenarios of `crawl-runs` on the run record, the refused folders, the error lines and status 4, including "The same record whatever the threads" (`MODAMA_CRAWLER_WALK_THREADS` 1 and 16) and "Kept for two crawls". Verified: fail today.
- [ ] 2.2 The same file: `runs | head -1` as the docs type it ("The report line", "Many folders on the line", "Aligned columns"), `runs --follow`, the timer's `overdue(last_finished(…))`, the subtree crawl's comparison after a crawl with errors. Verified: the `runs` ones fail today; the timer's and the comparison pass before and after.
- [ ] 2.3 The same file: the `harvest-trigger` scenarios, with the Airflow stand-in of `tests/test_trigger.py`. Verified: fail today (status 0 and 3), except "A refused folder alone".
- [ ] 2.4 `tests/test_migrations.py`: `0004_crawl_runs_listing_errors` up and down. Verified: fails until the migration exists.
- [ ] 2.5 `python/search-chain/tests/test_rules.py`: "A crawl with kept folders" and "An older crawler" of `chain-trace`. Verified: the first fails today.

## 3. Implementation

- [ ] 3.1 `formats/__init__.py`: `not_visible()`; `Directory.unanswered`, noted by `read()`, `cannot_read()` and `_call()`; `Dataset.kept`; `Result.unanswered`, `Result.refused`. Verified: 1.2's format cases, and `test_content_checks.py` unchanged.
- [ ] 3.2 `walk.py`: `_stat` asks `open(2)` again (D5); `_entries` notes entries that did not answer; `visit` keeps the subtree (D2) or the folder alone (D3), notes refused folders (D10); detection with `strict=True` (D6); the kept datasets loaded after the walk in one call (D4). Verified: 1.1 to 1.3.
- [ ] 3.3 `store.py`: `Stored.stored()`, `Stored.counts()`, lazy listings; `Run`, `end_run` with `unanswered` and `refused`; `history()` for `since` and `crawls`. `extraction.py`: kept datasets left as stored (D7). Verified: the extractor-call counts of 1.1, the failure count of "A kept dataset whose extraction failed".
- [ ] 3.4 `cli.py`: `crawl_tree` passes `kept`; `cmd_crawl` logs, records and returns 4 after the harvest trigger; `_state`, `_run_line`, `runs --follow`. Verified: 2.1 to 2.3.
- [ ] 3.5 Migration `0004_crawl_runs_listing_errors`, `schema.HEAD`. Verified: 2.4.
- [ ] 3.6 `search-chain`: `crawler.Run.unanswered` behind the column probe; `crawl_line`, the freshness line. Verified: 2.5.
- [ ] 3.7 Measure D4's lookup on 1.45 million dataset rows in a throwaway database: the time of `Stored.stored()` for 10 and for 5,000 folders. Verified: the timings in the hand-over.

## 4. Documentation and the backlog

- [ ] 4.1 `README.md`: exit status 4 beside 3; "What to look out for": a run `finished with errors` or with refused folders, what the admin does (repair, or `exclude`, which changes the rule fingerprint and makes the next crawl recognise everything again), errnos about names (`ENAMETOOLONG`) giving status 4 every night; the `runs` example line. `design/requirements.md` R35. `design/architecture.md`: the decision log row. `BACKLOG.md`: the item closes; the "Not now" items go in. Verified: `git diff` of the four files.

## 5. Acceptance

- [ ] 5.1 The crawler suite, `search-chain`'s and `modama-formats-em`'s, and `pre-commit run` (CI's ruff) on the changed files, with the number of skipped tests and how the environment differs from CI's. Verified: the commands' output.
- [ ] 5.2 Code review by an agent that did not write it, given the code, this change's specs and decision 271 (a migration is in it; AGENTS.md). Verified: `review.md` in this change.
- [ ] 5.3 The search stack's `./runtest.sh e2e`, only with the main session's OK (shared images).
