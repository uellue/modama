# Tasks

Prerequisites: @weber's answers to Q1 to Q11 (design.md), the leans changed where he says so; change `text-as-written` applied (its text module and the record's rule). Tests first, one per scenario, named after it; then the code.

## 1. The runner: claimed entries (spec `recognition`)

- [ ] 1.1 Tests in `python/crawler/tests/` for the scenarios "Higher priority wins a shared file" (the later format finds the file with `Directory.entry`), "A claimed file is not offered by type", "Files nobody claimed are still offered"; they fail. Verify: `pytest` of these tests, failing for the right reason.
- [ ] 1.2 `run_post` hands the claims to the `Directory` after each format; `of_type` leaves out claimed entries. Existing tests that relied on a later format seeing claimed files adapted, each named in the hand-over. Verify: the tests of 1.1 pass; the crawler's suite.
- [ ] 1.3 Whether a directory taken over from the last crawl keeps the old "already claimed" warnings until it is recognised again (the rule set's fingerprint with a new format enabled). Verify: a test or the command and its output in the hand-over.

## 2. Hitachi's header in a TIFF (spec `formats/image`)

- [ ] 2.1 Generator for `lone_tif` in the image area (`image/tests/generate.py`, tifffile): 64 × 96 pixels, tag 270 with the real file's 41 keys in their order and `\r` line ends, values made up (design D10), tag 65500 with the seven items and the glued repeat, tag 65501 of 15,156 hexadecimal characters; `fixtures.toml` entry (`validity = "parser-only"`, `licence = "CC0"`, the source: generated from the layout of a real pair, key names only). Verify: `test_manifest`; the file read back with tifffile shows the tags.
- [ ] 2.2 Tests for each scenario of "Hitachi's header in a TIFF's description", "Hitachi's tag 65500", "The summary line of a Hitachi TIFF" and "A number written as text in a Hitachi summary phrase"; they fail. Verify: `pytest`, failing for the right reason.
- [ ] 2.3 `image/tiff.py`: the parsing of tag 270 and tag 65500, the `HEADLINE` entries, the rule for numbers written as text. Verify: the tests of 2.2; `pytest src` of `modama-formats-common`, also under `TZ=Europe/Berlin`; `expected/lone_tif.json` reviewed; the other recorded results unchanged (`git diff` of `expected/`).

## 3. The pair (spec `formats/hitachi`)

- [ ] 3.1 Area `src/modama_formats_em/hitachi/` from the skeleton: `hitachi.xml` declaring `application/x-hitachi-sem` with a comment only (a comment naming Gwyddion's declaration as the source), `PARTS`, the dependency on `modama-formats-common` in `pyproject.toml` (a path dependency, as the search stack installs both). Verify: `modama-crawler records --verbose` on the fixtures names `em/hitachi`.
- [ ] 3.2 Generators for `pair`, `notes_beside_tif`, `lone_txt`, `lone_tif`, and the two-suffix case of "Only the last suffix is replaced"; `fixtures.toml`. Verify: `test_manifest`, `test_coverage`.
- [ ] 3.3 Tests for each scenario of `formats/hitachi`, with the collection's own formats plus the image and text areas where a scenario needs them (TEMPLATE, rule 11); they fail. Verify: `pytest`, failing for the right reason.
- [ ] 3.4 `recognize` (14 bytes, `d.cannot_read` on a read error) and `extract` (the image area's TIFF extraction, the text module of `text-as-written`). Verify: the tests of 3.3; `pytest src` of `modama-formats-em`, also under `TZ=Europe/Berlin`; `expected/*.json` reviewed; bytes read printed with `pytest -s`.
- [ ] 3.5 The scenario "A large TIFF" with a sparse TIFF of 1 GiB and `rchar`. Verify: the test, with the bytes read in the hand-over.

## 4. Documents

- [ ] 4.1 README rows: `modama-formats-em` (Hitachi), `modama-formats-common` (TIFF: Hitachi's header); TEMPLATE.md, "Priorities" (claimed entries are not offered by type); `common-text` design D4's remark; `BACKLOG.md`: the `em/de` item (the runner's part settled), the text area's open point on Hitachi sidecars, the next steps (a `.bmp`/`.jpg` partner, UTF-16, `[TemImageFile]`, a pair whose TIFF has no header). Verify: by eye; `git diff --stat`.

## 5. Checks and review

- [ ] 5.1 The packages' suites, the crawler's suite, `uvx pre-commit run --all-files` from the repository root after `git add` of new files. Verify: their output and the number of skipped tests in the hand-over.
- [ ] 5.2 The real pair: `modama-crawler records --verbose` on a folder with the copies in `/.claude/field-tests/samples/` (the TIFF's head is enough for its tags), before and after; only shapes and key names in the hand-over. Verify: the output, values left out.
- [ ] 5.3 Review by an agent that did not write the code, given the code and this change, not the author's conclusions (`/.claude/skills/format-collection/review-brief.md`); findings verified and answered. Verify: the review and the answers.
- [ ] 5.4 @weber looks at the pairs on staging with `modama-chain browse` after main's merge and an image build. Verify: his remarks.
