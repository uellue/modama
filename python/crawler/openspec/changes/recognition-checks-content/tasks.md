# Tasks

Commands below run from the worktree with `PATH=~/.venv/bin:$PATH` and `PYTHONPATH` set to the worktree's `python/crawler/src` and `python/modama-formats-em/src` (`~/.venv` has both installed editable from the main checkout).

## 1. The crawler: dropping a name's type during recognition

- [x] 1.1 `mime.by_name(name)`, factored out of `detect_with_tie` with no change of result, and `detect_with_tie(path, exclude=..., strict=...)` (D1, D2; spec `mime-database`, "Detection can leave a type out"). Verify: `test_mime.py` passes unchanged, plus one test per scenario of the `mime-database` delta, on files of the core's types. Run `uvx ruff check` and `uvx ruff format --check --diff` from the repo root. Done: `tests/test_mime.py` 16 passed (the 11 existing unchanged, `test_by_name` and 4 for the scenarios). The scenarios use `image/gif`, not `image/png`: `*.png` is also a glob of `image/apng` in the vendored database, which then decides (first run: `('image/apng', None)`).
- [x] 1.2 `Directory.not_of_type(entry, reason)`, and the changes to the runner (D1 to D4): the type check by `by_name`, with the warning otherwise; the new detection's read not charged to the format's budget (decision 166), with `strict`; the entry replaced; `run_post` reading the current types before each format and for the single files; the order warning; the entries and notes put back when `_call` discards a call; the notes appended to the basis. Verify: one test per scenario of spec `recognition` (this change), with the test formats of D7: `test/tags`, `test/png`, `test/contradicts`, and variants of `test/tags` that raise after their drop or drop twice. Also run the existing `test_formats.py` and `test_walk.py`. Done: in a module of their own, `tests/test_content_checks.py` (the scenarios need a MIME database with the `*.tags` rule, built for the module), 12 tests for the 11 scenarios plus the refusals (pre-order, another entry, the old entry after a drop); `test_formats.py` and `test_walk.py` unchanged and passing (59 passed together).
- [x] 1.3 The reuse scenarios of spec `recognition`, "A dropped type lasts until the file or the rules change". Verify: the second crawl of an unchanged tree calls no format and reads no file of the directory, and a replaced file gets its name type back; the datestamps are checked against `conn`. Done: `test_a_second_crawl_of_an_unchanged_directory` and `test_the_file_is_replaced_by_one_of_the_type` in `tests/test_content_checks.py`, through `cli.crawl_tree` (walk with the stored state as `previous`, extraction, store) instead of `walk` and a separate store test: one test covers the taking over (`result.unchanged == 1`, no call of `test/tags`) and the datestamps.
- [ ] 1.4 `records --verbose`: a single file whose basis is not plain `single file` gets a recognition comment (spec `records-cli`, this change). Verify: the scenario's test in `modama-formats-em` (task 2.4), since only an installed collection's format can drop a type in `records`. Check the output by eye in a real terminal with `tools/xterm-shots.py` where the VM has its tools (xvfb, xterm, xdotool, imagemagick); otherwise say so.
- [x] 1.5 `modama-chain trace`: the crawler line shows the dataset's basis (spec `chain-trace`, this change). Update `python/search-chain/README.md`, "What it reads": `datasets (anchor, basis)`. Verify: a test in `python/search-chain/tests/` with canned inputs for the line's detail. The e2e scenario runs in task 3.1. Done: `crawler.dataset_of` returns a `Holding` with the basis, `chain.crawler_detail` builds the line's detail (factored out of `trace` for the canned-input tests `test_a_text_file_named_like_a_k2is_tag_file` and `test_a_plain_file_and_a_member`); README, "Trace" and "What it reads"; the e2e assertion on the EMPAD member's detail (`prototypes/search-stack/test_e2e.py`) takes the basis after it, not run here. `python/search-chain`: 31 passed.
- [ ] 1.6 Docs:
  - TEMPLATE "Rules first, Python second": `not_of_type`, with an example; check the signature only, never parse to decide; decide what is broken by the files around it first; the order rule of D3, its warning and its blind spot (formats reacting to `DIRECTORY`).
  - README "Walk and recognise": one sentence on a format dropping a name's type.
  - `BACKLOG.md`: the items of "Not now" below as deferred; the item "Suspicious results for manual follow-up" renamed to this change, with the DM3 `.dmw` as its first concrete case (decision 174); "filter the `.dmw` description to relevant tags" next to the K2IS description item (decision 173); the walk's own detection that never raises a read error (review finding 4).

  Verify: the TEMPLATE example runs as written (the test of task 1.2 imports it), and the README sentence matches spec `recognition`.

## 2. modama-formats-em (built here on `crawler`, decision 144)

These need tasks 1.1 and 1.2.

- [ ] 2.1 `dm.version(data)`, the DM3 and DM4 header tests of `dm.xml`, and the tag walker moved from `k2is/` to `dm/` with K2IS's filter as its argument (E1). Verify: K2IS's tests and recorded results unchanged.
- [ ] 2.2 The format `em/dmw` in `dm/` with its extractor (E1, decisions 173, 174). Fixtures: `dmw_file` (the DM4 stand-in, its provenance kept honest: an image, not a workspace), `dm3_dmw` (`old_workspace.dmw`, a copy of `stem_image_dm3`'s file, also a stand-in), `text_dmw` (`notes.dmw` holding `hello\n`, `invalid-by-design`), `empty_dmw` (an empty `empty.dmw`, `invalid-by-design`). Verify: one test per scenario of the `formats/dm` delta; the coverage rule passes (`em/dmw` has a dataset on the representative `dmw_file`, review finding 2).
- [ ] 2.3 K2IS: groups whatever the `.gtg` holds, checks a lone `.gtg` (E2): priority 61, recognition version 2. Fixtures: `text_tags` (`notes.gtg` holding `hello\n`), `empty_tags` (an empty `empty.gtg`), `empty_capture` (an empty `Capture7_.gtg` with 8 sector blocks), `broken_next_to_complete` (`scan_.gtg`, Capture52's tag file, with 8 sector blocks, and `scan_2_.gtg` holding `hello\n` with 8). Verify: one test per scenario of the `formats/k2is` delta, the extraction failures through `extraction.extract` as a crawl runs it; the recorded results of the existing fixtures unchanged.
- [ ] 2.4 The `records-cli` scenario of this change: `python -m modama_crawler records --verbose` on a tree holding `notes.gtg`. Verify: a test in the k2is part's tests that runs the command as typed and finds the comment directly before the record.
- [ ] 2.5 The XML comments of `dm.xml` and `k2is.xml` (E3); `dm-containers-and-k2is` task 4.1 points here; the README of `modama-formats-em` names `em/dmw`. Verify: `grep -rn "subclass of the sniffed type wins" python/modama-formats-em/src` finds nothing; `openspec validate dm-containers-and-k2is --strict`.

## 3. Integration

- [ ] 3.1 Crawl a test tree twice in the search stack, with the `em` collection enabled. The tree holds Capture52, `notes.gtg`, `notes.dmw`, `empty.dmw`, `conditions_00C.dmw` and `IDES_DMS_Config.gtg`. Between the crawls, change one unrelated file in the directory. Verify:
  - `modama-crawler records` shows the types of tasks 2.2 and 2.3.
  - The second crawl recognises that directory again and gives the same types and bases. Records of unchanged datasets keep their datestamps.
  - `modama-chain trace` on `notes.gtg` shows the basis of spec `chain-trace`.
  - `./runtest.sh e2e` in `/prototypes/search-stack/`, the crawler suite and the `modama-formats-em` suite pass, with the number skipped given.

## Not now

- A fallback for files typed by their content (weak magic collisions, flow F): a warning only.
- Checking the fallback type again (one drop per file per crawl).
- Calling formats that already ran on a directory again after a drop, or a check stage before recognition (D1's alternative). Revisit if the order rule bites; the order warning shows when.
- A count of rejections in the crawl report (decision 148).
- The DM3 header for a lone `.gtg` (decision 147; design.md, "Open questions").
- Filtering the `.dmw` description to the relevant tags (decision 173, backlog).
- A read error in the walk's own detection, which gives `application/octet-stream` today (review finding 4, second paragraph).
