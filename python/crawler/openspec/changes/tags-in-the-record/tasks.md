# Tasks

Written with the leans of the brief (decision 234, 2026-11-12) as assumptions; where they changed, design.md says why (D1 the order, D2 the numbers). Built on the DM/K2IS branch (`worktree-agent-a454075836693a33a`), which defines `values["original_metadata"]` for DM3, DM4 and K2IS.

## 1. Measure first

- [x] 1.1 The second description's size for Capture52 and the DM fixtures, in the record, in the oai_dc XML and stored in PostgreSQL; the growth for staging's 176,000 DM datasets (design D5). Verify: the commands and their output in the hand-over.
- [x] 1.2 The chain's limits and what it does with two descriptions: the harvester's XSLT, the warehouse's schema and tables, the index mapping, the embedding text and model, the search API's hit, Matchmaker's entry (design D4). Verify: file and line of each in design D4; the embedding measured with the warehouse's functions and model.

## 2. Crawler

- [x] 2.1 `records.py`: `tags()` and `as_stored()`; `dc_metadata` appends the second description. Verify: 2.2.
- [x] 2.2 `tests/test_records.py`, one test per scenario of "The file's tags go into a second description": with tags (a made-up tag included), without, empty values, sorted, values as stored, numbers as the database gives them back (through the real store), a very long value, and Capture52 crawled twice as typed and served (datestamp kept, two descriptions). `tests/test_cli.py`: `records --verbose` on Capture52. Verify: `pytest` in `python/crawler` and `python/modama-formats-em`, with the number of skipped tests.
- [x] 2.3 `README.md` (the record's descriptions), `BACKLOG.md` ("DM and K2IS tags"), `design/architecture.md` (rows for 234 and D1), the unarchived `em-formats-and-extraction` delta ("one" becomes "a first"). Verify: `git diff`.

## 3. Search stack

- [x] 3.1 `test_e2e.py`: Capture52 in the tree; `test_the_file_s_tags_reach_the_index` (two descriptions in the index document, the lines joined by the XSLT, a word of a tag's value found in `_description` for this record only, the hit's description the summary); the browser's live index document against the stored one for Capture52 too. Verify: `./downtest.sh --reset && ./uptest.sh && ./runtest.sh e2e` when the VM's stack is free, with the number of skipped tests.

## 4. Checks and hand-over

- [x] 4.1 `uvx ruff format --check --diff` and `uvx ruff check` from the repo root. Verify: their output.
- [x] 4.2 An independent review of ac1104cf (the coordinator's, 2026-11-12: fine for tonight). Its items, after merging `crawler` 4cef5532: D5 re-measured; a string with line breaks as JSON text (D6), tested on the block file Stingray16bit_7_11.blo; an object's keys sorted (D2); the reviewer's round trip as `test_a_stored_extraction_gives_the_same_lines_whatever_the_values`; the `…` for non-string values only in the spec. Verify: `pytest` in `python/crawler`, `python/modama-formats-em`, `python/search-chain`; the e2e.
