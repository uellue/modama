# Tasks

## 1. Tests first

- [x] 1.1 `tests/test_read_limit.py`, one test per scenario, failing on the folder budget: `test_many_files_each_within_the_limit`, `test_a_file_read_past_64_KiB_is_flagged`, `test_a_file_over_the_read_limit_is_skipped`, `test_a_format_that_declares_a_larger_limit`, `test_a_refusal_the_format_does_not_catch` (passes before and after: the rule kept). Verify: the four failed before the core change (`'' == 't/heads'`, no flag warning).
- [x] 1.2 `em/mrc`: `test_a_flat_folder_and_the_same_files_in_100_subfolders` (10,000 files; failed: every file a single file) and `test_an_mrc_file_over_the_read_limit_is_skipped`. Verify: failed before.

## 2. The core

- [x] 2.1 `formats/__init__.py`: `LIMIT_PER_FILE`, `FLAG_PER_FILE`, the markers `READ_MUCH` and `OVER_LIMIT`; `Format.read_limit`; `Directory.read` counts per file and call, flags, refuses (D1); `cannot_read` and `did_not_answer` treat a refusal as warned and final (D2); `inspect` takes the format's limit (D3); `_call` sets the limit and resets the counts; `run_pre`/`run_post` without `byte_budget`; `BYTE_BUDGET` gone. Verify: 1.1.
- [x] 2.2 `files.BudgetExceeded` an `OSError`. Verify: 1.1, `test_inspection.py`.
- [x] 2.3 `walk.py`, the crawler's and `em/de`'s tests on the new signatures; `test_formats.py`'s budget tests on the limit (`test_read_limit`; the folder test moved to 1.1). Verify: the crawler suite.

## 3. Formats

- [x] 3.1 `em/mrc` and the skeleton catch an `OSError` around their read and skip the file (D4). Verify: 1.2, `test_a_header_over_the_read_limit_is_skipped`.
- [x] 3.2 `common/hdf5links` declares `read_limit = 4 << 20`; `links.BUDGET` goes. Verify: `test_a_file_over_its_budget` with the new wording, the rest of `test_links.py` unchanged.
- [x] 3.3 Each format's reads listed (design D4).

## 4. Review and docs

- [x] 4.1 `modama-chain review`: the two markers as kinds. Verify: `test_files_recognition_read_much_of`, `test_the_markers_are_the_crawlers`.
- [x] 4.2 TEMPLATE.md (the code sample's comment, the readers, catching per file, a checklist item), README ("What recognition reads of one file", the hdf5links wording), search-chain README, decision log row, BACKLOG. Verify: read.
- [x] 4.3 Suites: crawler, em, common (also `TZ=Europe/Berlin`), search-chain; `uvx pre-commit run --all-files`; `openspec validate read-limit-per-file --strict`.
