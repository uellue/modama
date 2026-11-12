# Tasks

## 1. Crawler: extraction and description

- [x] 1.1 `size` on datasets from the walk's `stat`; the MIME type's comment available from the MIME database. Verify: `test_walk.py`, `test_mimedb.py` (a type's comment, a fallback without one).
- [x] 1.2 Extractor interface (`Format.extract`, `extractor_version`, `Extracted`) and the extraction module: process pool, time limit from outside, failure as warning, report counts and time per format (D1, D2). Verify: tests with a stand-in format whose extractor returns, raises, kills its process and hangs (spec `extraction`, scenarios 1 to 3, 6).
- [x] 1.3 Persistent `datasets` (no truncation), the stored listing per directory, the rule-set fingerprint per run, "unchanged" computed bottom-up in post-order, taking over stored datasets, and the extractor's identity per dataset (D3). Verify: spec `extraction`, the scenarios of "Unchanged directories…" (no content read on the second crawl, measured with `/proc/self/io` or the benchmark's NFS counters; a change three levels down) and of "Extraction follows the identified extractor".
- [x] 1.4 `dc:description` on every record and `dc:subject` from extraction (D4). Verify: `test_records.py` per scenario of spec `records`; `oai_dc` still validates (`test_render.py`).
- [x] 1.5 Decided by @weber on 2026-11-11: the subject names the format by its display name (`Format.display_name`, else the MIME type's comment, else the id), set for EMPAD, DM3/DM4, Merlin, Zarr and the collapsed kinds, to be tuned with real-world feedback; the extraction counts are stored in `crawl_runs` (schema change: recreate the database) and shown by `runs`. Verify: `test_records.py` (subjects, display names), `test_extraction.py` (a stored record's subject), `test_runs.py` (counts stored and shown), the em collection's extraction tests.

## 2. The collection `modama-formats-em`

- [x] 2.1 Package skeleton `python/modama-formats-em/` (D5): `pyproject.toml`, entry point, `em.xml`; RosettaSciIO's current release looked up and pinned; flagged as new dependency. Verify: `pip install -e`, `modama-crawler` lists the `em` collection; the collection's tests run with the crawler's pytest plugin.
- [x] 2.2 Move EMPAD from the crawler (code, `empad.xml`, fixtures, tests), format id `em/empad`; update `stagingconf/`, docs and the crawler's entry points. Verify: EMPAD's existing tests pass in the new package; the crawler's own tests pass without it.
- [x] 2.3 EMPAD extractor (scan size, frame size, exposure). Verify: spec `formats/empad` scenario on the representative fixture.
- [x] 2.4 DM3/DM4 recognition by magic and extractor via RosettaSciIO; representative files from the tree, scrubbed or small, with @weber's agreement on each (R27, R29); bytes read per file measured. Verify: spec `formats/dm` scenarios; bytes per file in the test output; fallback D7 decided if it reads image data. Done with RosettaSciIO's test files (2026-11-11); files from the tree still open. The reader skips the image data by seeking; it reads the tags plus Python's 128 KiB buffer (96,513 of 96,400 bytes of the DM3, 143,371 of 611,355 of the DM4), so no fallback.
- [x] 2.5 Merlin recognition (`.hdr` plus frames) and extractor. Verify: spec `formats/merlin` scenarios; on `libertem-test-data/many_mib`'s shape: one dataset.
- [x] 2.6 NanoMegas ASTAR block files (`.blo`, found with `modama-chain browse` on staging, 2026-11-12): recognition by the `IMGBLO` header, extraction with RosettaSciIO's blockfile reader, lazily; scikit-image added, which that module imports (decision 227). Verify: spec `formats/blockfile` scenarios, on RosettaSciIO's `test2.blo`.

## 3. Stack and real data

- [x] 3.1 Crawler image installs `modama-formats-em`; e2e test with an EMPAD fixture shows description and subjects in the search hit. Verify: `./runtest.sh e2e`. Done: `test_extracted_metadata_reaches_the_search`; 17 passed with the chat test (2026-11-11). The keyword test's threshold follows: no record takes the ×0.1 penalty any more.
- [x] 3.2 Review by an agent that did not write the code, given the code, these specs and `design/requirements.md`; findings verified, listed in `review.md` of this change. Verify: the review file, fixes with tests. Done 2026-11-11: nine findings, all fixed.
- [ ] 3.3 Staging on the real tree, @weber at the host: rebuild, reset warehouse and index, full crawl overnight; then extraction counts, failures, bytes per file and time, and the demo queries from `BACKLOG.md` Next. Verify: the findings file, run 3 or later, with numbers.
