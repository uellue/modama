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

## 5. The review's follow-ups

- [x] 5.1 `em/de`: an info file not read (an error, or over the read limit) still owns its stem's files, so that they don't join a shorter stem's acquisition; it makes no dataset and no "two formats want it" warning. Verify: `test_an_unread_info_file_of_a_longer_stem` (failed before: the `_x_` files were members of `20241021_00405`).
- [x] 5.2 `common/zspy` reads a v3 store's `zarr.json` once: the core's `zarr/zarr` hands its parsed document to `Zarr.described`, which `common/zspy` overrides. Verify: `test_the_zarr_json_of_a_zspy_store_is_read_once` (failed before: `read more than 64 KiB of zarr.json` for 40 KiB of attributes); BACKLOG item removed.
- [x] 5.3 `em/empad`: a refusal gives the core's warning only. Verify: `test_a_header_over_the_read_limit_is_warned_once` (failed before: a second warning, `cannot read the raw file name from the header: BudgetExceeded(…)`).
- [x] 5.4 `READ_MUCH` derived from `FLAG_PER_FILE`; `review.py` keeps the text (it needs no crawler installed), compared by `test_the_markers_are_the_crawlers`. "Byte budget" in `inspection.py` and `files.py` in the new wording. Verify: the suites.
- [ ] 5.5 Archive after `hdf5-links` and `recognition-checks-content`: all three modify "Plain data in, no reach outside the directory", and this change's version of it holds the other two's (their description sentences and scenarios), so archived last it leaves the requirement whole; archived earlier, a later one would put back the old wording. Likewise after `parallel-walk`, which adds "A byte budget bounds every format call" (and `recognition-checks-content` modifies it), which this change removes.
