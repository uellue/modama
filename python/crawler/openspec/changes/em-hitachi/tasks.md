# Tasks

Prerequisites: @weber's answers (2026-11-13: all leans accepted, 313; fixtures generated from the sample's layout, 314); change `text-as-written`'s text module and record rule (its commit 7a08bb01, merged into this branch). Tests first, one per scenario, named after it; then the code.

## 1. The runner: claimed entries

- [x] 1.1 Not needed: bug 311 and decision 344 (on `crawler` before the build) keep claimed files from later formats and give `Directory.claimed` and `claimed_elsewhere` (design D8). The `recognition` delta is removed; `em/hitachi` uses `claimed_elsewhere` (task 3.3). Verify: `test_the_pairs_files_are_not_offered_to_the_formats_after_it`, `test_the_header_claimed_by_another_format`.

## 2. Hitachi's header in a TIFF (spec `formats/image`)

- [x] 2.1 Generator `lone_hitachi_tif` (fixture `hitachi_tif`) in the image area (`image/tests/generate.py`, tifffile): 64 × 96 pixels, tag 270 with the real file's 40 keys in their order and `\r` line ends, values made up (design D10), tag 65500 with the seven items and the glued repeat, tag 65501 of 15,156 hexadecimal characters, no Software tag, 96 per inch; `fixtures.toml` entry (`validity = "parser-only"`). Verify: `test_manifest`; tags read back with tifffile.
- [x] 2.2 Tests for each scenario of "Hitachi's header in a TIFF's description", "Hitachi's tag 65500", "The summary line of a Hitachi TIFF" and "A number written as text in a Hitachi summary phrase"; 7 failed first (the two scenarios of other programs' tags passed: they hold what was there before). Verify: `pytest`, failing for the right reason.
- [x] 2.3 `image/tiff.py`: the parsing of tag 270 (`sections`) and tag 65500 (`tag_items`), the `HEADLINE` entries, numbers written as text. Verify: the tests of 2.2; `pytest src` of `modama-formats-common`; `expected/hitachi_tif.json` reviewed; the other recorded results unchanged. On the real TIFF head: 40 header entries, 7 of tag 65500 (the glued item read right), no 65501, 12 summary phrases.

- [x] 2.4 The shared credential check on a TIFF's tags (coordinator, after text-as-written's merge: Hitachi's header and tag 65500 carry free text; the image area lacked the check): an entry `values.credential` flags is left out and counted as `credentials_left_out`. Verify: `test_a_credential_in_a_tiffs_tags_is_left_out` failed first, then passed; no recorded result changed; the real TIFF head has none flagged.

## 3. The pair (spec `formats/hitachi`)

- [x] 3.1 Area `src/modama_formats_em/hitachi/`: `hitachi.xml` declaring `application/x-hitachi-sem` with a comment only, `PARTS`, the dependency on `modama-formats-common` in `pyproject.toml`; the search stack's `crawler.Dockerfile` installs common before em. Verify: `modama-crawler records --verbose` on the real pair's copy names `em/hitachi` (one record, no warning).
- [x] 3.2 Generators for `pair`, `notes_beside_tif`, `lone_txt`, `lone_tif`, `last_suffix`; `fixtures.toml`. Verify: `test_manifest`, `test_coverage`.
- [x] 3.3 Tests for each scenario of `formats/hitachi`, with the image and text areas' formats where a scenario needs them (TEMPLATE, rule 11). Written after the recognition code for the recognition scenarios (they passed at once; only the fixtures' recordings failed first); for the text, first: `test_the_header_as_written` and `test_a_line_that_may_hold_a_credential` failed (`KeyError: 'text'`), then passed. Verify: `pytest`.
- [x] 3.4 `recognize` (14 bytes, `d.cannot_read` on a read error, `d.claimed_elsewhere` for a claimed `.txt`) and `extract` (the image area's TIFF extraction; the text through `written.of_head`, `credentials_left_out`). Verify: the tests of 3.3; `pytest src` of `modama-formats-em`, also under `TZ=Europe/Berlin`; `expected/*.json` reviewed (the text added to `pair` and `last_suffix`, nothing else changed).
- [x] 3.5 The scenario "A large TIFF": 66,367 bytes read of a 1 GiB sparse TIFF and its header (`modama_crawler.testing.bytes_read`: one 64 KiB buffer of the TIFF and the `.txt`). Verify: `pytest -s`.

## 4. Documents

- [x] 4.1 README rows: `modama-formats-em` (Hitachi; the setup line installs common too), `modama-formats-common` (TIFF: Hitachi's header); `BACKLOG.md`: the text area's open point on Hitachi sidecars settled, the next steps (a `.bmp`/`.jpg` partner, UTF-16, `[TemImageFile]`, a pair whose TIFF has no header, the image area's credential check). Verify: by eye; `git diff --stat`.

## 5. Checks and review

- [x] 5.1 The packages' suites, the crawler's suite, also under `TZ=Europe/Berlin`, `uvx pre-commit run --all-files` from the repository root. Verify: their output in the hand-over.
- [x] 5.2 The real pair: `modama-crawler records --verbose` on a copy of the samples (the TIFF's head named as the `.txt`'s stem) in `/var/tmp/em-hitachi/`: one record `application/x-hitachi-sem` by `em/hitachi`, the summary line of 12 phrases, the `.txt`'s 41 lines as the second description, no warning; the copy removed. Verify: the output, values left out of the hand-over.
- [ ] 5.3 Review by an agent that did not write the code (`/.claude/skills/format-collection/review-brief.md`); findings verified and answered. Verify: the review and the answers.
- [ ] 5.4 @weber looks at the pairs on staging with `modama-chain browse` after main's merge and an image build. Verify: his remarks.
