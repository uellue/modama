# Tasks

## 1. The crawler: rejection and fallback

- [ ] 1.1 `NotOfType` in `formats/__init__.py`, `Extraction.rejected`, and the column `extract_rejected` in `store.py`, stored and read back (D1). Verify: a store round-trip test of an extraction with a rejection; `uvx ruff check` and `uvx ruff format --check --diff` from the repo root.
- [ ] 1.2 `mime.by_name(name)`, factored out of `detect_with_tie` with no change of result, and `detect_with_tie(path, exclude=...)` (D2, D3). Verify: `test_mime.py` passes unchanged, plus one test each for `exclude`: a name candidate left, none left (content decides), and the text and octet-stream fallbacks. These use synthetic files of the core's rule-processing tests.
- [ ] 1.3 `_run` reports a rejection as its own outcome, and `extraction.extract` applies D2 and D4. Verify: one test per scenario of spec `extraction` (this change), with a test format in `tests/`. The scenarios are a stray file falling back with no warning, reuse on a re-recognised directory without running the extractor or moving the datestamp, a replaced file getting the type back, a two-member dataset and a content-typed file failing. Also run the existing extraction tests.
- [ ] 1.4 Docs: TEMPLATE "Extracting metadata" (when to raise `NotOfType`, before parsing, on the signature only), README "Extract" (one sentence on rejection and fallback), `BACKLOG.md` (this change in Next; the items in "Not now" below as deferred). Verify: the TEMPLATE example names `NotOfType` and the exception imports as written; the README sentence matches spec `extraction`.

## 2. `modama-formats-em` on branch `dm-containers` (D5)

- [ ] 2.1 Formats `em/dmw` and `em/gtg` with the DM4 header check, and the K2IS grouping as one function both K2IS and `em/gtg` call. Add reproducer fixtures `notes.gtg` (`hello\n`) and `empty.dmw`, with manifest entries `invalid-by-design`. Verify: the collection's tests cover `notes.gtg` → `text/plain` with no warning, `empty.dmw` → `text/plain`, `IDES_DMS_Config.gtg` (DM4 header) → `application/x.dm-gtg`, and Capture52 with its `.gtg` replaced by text → one K2IS dataset with 9 members and a failure warning. No "already claimed" warning on Capture52. The coverage rule passes.
- [ ] 2.2 Amend `dm-containers-and-k2is`: D1, the spec requirement "Tag files and workspaces are not DM images" (D5 wording), the comments in `dm.xml` and `k2is.xml`, and the outcome of review M1. Verify: `openspec validate dm-containers-and-k2is --strict`; `grep -n "subclass of the sniffed type wins"` in `dm/` and `k2is/` finds nothing.

## 3. Integration

- [ ] 3.1 Crawl a test tree twice with the `em` collection enabled: Capture52, `notes.gtg`, `empty.dmw`, `IDES_DMS_Config.gtg`, with one unrelated file in the directory changed between the crawls. Verify: `modama-crawler records` shows the types of task 2.1. The second crawl reports the rejections as reused and runs no `.gtg`/`.dmw` extractor. Records of unchanged datasets keep their datestamps. The crawler suite and the `modama-formats-em` suite pass, with the number skipped given.

## Not now

- Running the fallback type's extractor, or recognising the directory again after a rejection (a DM3 file named `.dmw` would get its type but not its image metadata).
- Rejection for files typed by their content (weak magic collisions).
- A count of rejections in the crawl report, or the rejection named in the `records` note.
