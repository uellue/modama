# Tasks

## 1. The crawler: dropping a name's type during recognition

- [ ] 1.1 `mime.by_name(name)`, factored out of `detect_with_tie` with no change of result, and `detect_with_tie(path, exclude=...)` (D1, D2). Verify: `test_mime.py` passes unchanged, plus one test each for `exclude`: another name candidate left, none left with a content match, and none left with the text and the octet-stream fallbacks. These use synthetic files of the core's rule-processing tests. Run `uvx ruff check` and `uvx ruff format --check --diff` from the repo root.
- [ ] 1.2 `Directory.not_of_type(entry, reason)`, and the changes to the runner (D1 to D4). These are: the type check by `by_name`, with the warning otherwise; the budget charge for the new detection; the entry replaced; `run_post` reading the current types before each format and for the single files; the entries put back when `_call` discards a call; the note appended to the basis. Verify: one test per scenario of spec `recognition` (this change) in `tests/test_formats.py`, with two test formats. `test/tags` is for files named `*.tags`: type `application/x.test-tags`, a name rule only, files starting with the 4 bytes `TAGS`. It reads those 4 bytes and says that a file without them is not of its type, with the reason "no TAGS header". `test/png` claims files of type `image/png`. Also run the existing `test_formats.py` and `test_walk.py`.
- [ ] 1.3 The reuse scenarios of spec `recognition`, "A dropped type lasts until the file or the rules change". Verify: tests in `tests/test_walk.py` with `previous` set: the second walk of an unchanged tree calls no format and reads no file of the directory, and a replaced file gets its name type back. The datestamp check runs in a store test against `conn`.
- [ ] 1.4 `records --verbose`: a single file whose basis is not plain `single file` gets a recognition comment (spec `records-cli`, this change). Verify: the scenario's test in `modama-formats-em`, since only an installed collection's format can drop a type in `records` (task E.4). Check the output by eye in a real terminal with `tools/xterm-shots.py`, as for every `records` output change.
- [ ] 1.5 `modama-chain trace`: the crawler line shows the dataset's basis (spec `chain-trace`, this change). Update `python/search-chain/README.md`, "What it reads": `datasets (anchor, basis)`. Verify: a test in `python/search-chain/tests/` with canned inputs for the line's detail. The e2e scenario runs in task 2.1.
- [ ] 1.6 Docs:
  - TEMPLATE "Rules first, Python second": `not_of_type`, with an example; check the signature only, never parse to decide; the order rule of D3.
  - README "Walk and recognise": one sentence on a format dropping a name's type.
  - `BACKLOG.md`: this change in Next; the items of "Not now" below as deferred; @weber's idea of tagging suspicious results for follow-up.

  Verify: the TEMPLATE example runs as written (a doctest or the test of task 1.2 imports it), and the README sentence matches spec `recognition`.

## To fold into dm-containers-and-k2is

These tasks move with design.md's section of the same name into `dm-containers-and-k2is` on branch `dm-containers` (decision 144). They need tasks 1.1 and 1.2.

- [ ] E.1 The format `em/dmw` in `dm/` (E1). Fixtures: `notes.dmw` (`hello\n`) and an empty `empty.dmw` as reproducers, `invalid-by-design`, and `stem_image.dmw`, a copy of the DM3 fixture `stem_image_dm3`. Verify: the `formats/dm` scenarios of the section, one test each. `conditions_00C.dmw` (DM4 header) keeps the `.dmw` type with no extraction. `stem_image.dmw` gives the same extracted values as `stem_image_dm3`. The coverage rule passes.
- [ ] E.2 K2IS checks its tag files before grouping (E2): the priority 61, the recognition version, the warning's wording. Fixtures: `notes.gtg` (`hello\n`), a capture `X_` whose `.gtg` holds `hello\n` next to sector files cut as Capture52's are, and Capture52 with its `.gtg` cut after 1,000 bytes. Verify: the `formats/k2is` scenarios of the section, one test each. Capture52 unchanged is still one dataset of 9 members, with no "already claimed" warning.
- [ ] E.3 Amend `dm-containers-and-k2is` (E3): D1, the requirement "Tag files and workspaces are not DM images" (the section's text), the new K2IS requirement, the comments in `dm.xml` and `k2is.xml`, and the outcome of review finding 1. Verify: `openspec validate dm-containers-and-k2is --strict`. `grep -rn "being its subclass, wins\|subclass of the sniffed type wins" python/modama-formats-em/src/modama_formats_em/dm python/modama-formats-em/src/modama_formats_em/k2is` finds nothing.
- [ ] E.4 The `records-cli` scenario of this change: `python -m modama_crawler records --verbose` on a tree holding `notes.gtg`. Verify: a test in the k2is part's tests that runs the command as typed and finds the comment directly before the record.

## 2. Integration

- [ ] 2.1 Crawl a test tree twice in the search stack, with the `em` collection enabled. The tree holds Capture52, `notes.gtg`, `notes.dmw`, `empty.dmw`, `stem_image.dmw` and `IDES_DMS_Config.gtg`. Between the crawls, change one unrelated file in the directory. Verify:
  - `modama-crawler records` shows the types of tasks E.1 and E.2.
  - The second crawl recognises that directory again and gives the same types and bases. Records of unchanged datasets keep their datestamps.
  - `modama-chain trace` on `notes.gtg` shows the basis of spec `chain-trace`.
  - `./runtest.sh e2e` in `/prototypes/search-stack/`, the crawler suite and the `modama-formats-em` suite pass, with the number skipped given.

## Not now

- A fallback for files typed by their content (weak magic collisions, flow D): a warning only.
- Checking the fallback type again (one drop per file per crawl).
- Calling formats that already ran on a directory again after a drop, or a check stage before recognition (D1's alternative). Revisit if the order rule bites.
- A count of rejections in the crawl report (decision 148).
- The DM3 header for `.dmw` and `.gtg` (decision 147, @weber's fresh `.dmw` files, open item 155).
- Metadata from `.dmw` files.
