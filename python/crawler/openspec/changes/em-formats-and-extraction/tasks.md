# Tasks

## 1. Crawler: extraction and description

- [ ] 1.1 `size` on datasets from the walk's `stat`; the MIME type's comment available from the MIME database. Verify: `test_walk.py`, `test_mimedb.py` (a type's comment, a fallback without one).
- [ ] 1.2 Extractor interface (`Format.extract`, `extractor_version`, `Extracted`) and the extraction module: process pool, time limit from outside, failure as warning, report counts and time per format (D1, D2). Verify: tests with a stand-in format whose extractor returns, raises, kills its process and hangs (spec `extraction`, scenarios 1 to 3, 6).
- [ ] 1.3 Persistent `datasets` (no truncation), the stored listing per directory, the rule-set fingerprint per run, "unchanged" computed bottom-up in post-order, taking over stored datasets, and the extractor's identity per dataset (D3). Verify: spec `extraction`, the scenarios of "Unchanged directories…" (no content read on the second crawl, measured with `/proc/self/io` or the benchmark's NFS counters; a change three levels down) and of "Extraction follows the identified extractor".
- [ ] 1.4 `dc:description` on every record and `dc:subject` from extraction (D4). Verify: `test_records.py` per scenario of spec `records`; `oai_dc` still validates (`test_render.py`).

## 2. The collection `modama-formats-em`

- [ ] 2.1 Package skeleton `python/modama-formats-em/` (D5): `pyproject.toml`, entry point, `em.xml`; RosettaSciIO's current release looked up and pinned; flagged as new dependency. Verify: `pip install -e`, `modama-crawler` lists the `em` collection; the collection's tests run with the crawler's pytest plugin.
- [ ] 2.2 Move EMPAD from the crawler (code, `empad.xml`, fixtures, tests), format id `em/empad`; update `stagingconf/`, docs and the crawler's entry points. Verify: EMPAD's existing tests pass in the new package; the crawler's own tests pass without it.
- [ ] 2.3 EMPAD extractor (scan size, frame size, exposure). Verify: spec `formats/empad` scenario on the representative fixture.
- [ ] 2.4 DM3/DM4 recognition by magic and extractor via RosettaSciIO; representative files from the tree, scrubbed or small, with @weber's agreement on each (R27, R29); bytes read per file measured. Verify: spec `formats/dm` scenarios; bytes per file in the test output; fallback D7 decided if it reads image data.
- [ ] 2.5 Merlin recognition (`.hdr` plus frames) and extractor. Verify: spec `formats/merlin` scenarios; on `libertem-test-data/many_mib`'s shape: one dataset.

## 3. Stack and real data

- [ ] 3.1 Crawler image installs `modama-formats-em`; e2e test with an EMPAD fixture shows description and subjects in the search hit. Verify: `./runtest.sh e2e`.
- [ ] 3.2 Review by an agent that did not write the code, given the code, these specs and `design/requirements.md`; findings verified, listed in `review.md` of this change. Verify: the review file, fixes with tests.
- [ ] 3.3 Staging on the real tree, @weber at the host: rebuild, reset warehouse and index, full crawl overnight; then extraction counts, failures, bytes per file and time, and the demo queries from `BACKLOG.md` Next. Verify: the findings file, run 3 or later, with numbers.
