# Tasks

## 1. Types

- [x] 1.1 `.dmw` and `.gtg` types (D1: `.dmw` in `dm/dm.xml`, `.gtg` in `k2is/k2is.xml`). Verify: spec `formats/dm` "A .dmw file with the DM4 header" as `test_a_dmw_file_with_the_dm4_header`, "A lone .gtg file" as `test_a_tag_file_without_sectors` (k2is part); the existing DM tests unchanged.
- [x] 1.2 K2IS sector type in `k2is/k2is.xml` (D2). Verify: spec `formats/k2is` "Another .bin file" as `test_another_bin_file`, with a sector block named `sector.dat` typed by content.

## 2. K2IS

- [x] 2.1 The K2IS part: recognizer grouping by stem (D3), in the collection's `PARTS`. Verify: spec `formats/k2is` scenarios as `test_a_capture_with_its_8_sectors`, `test_sector_files_without_their_tag_file`, `test_a_tag_file_without_sectors`, with recorded expected results.
- [x] 2.2 Extractor from the `.gtg` tags (D4). Verify: `test_a_representative_capture`, README table updated; `uvx ruff check python/` clean; crawler suite passed. (First on a synthetic capture, replaced in 3.1; the description changed in 4.2.)

## 3. Real data

- [x] 3.1 A representative K2IS fixture from staging, replacing the synthetic capture. Agreed 2026-11-12 (73, 79) for `libertem-test-data/Capture52`, @weber's own test data: metadata only (the `.gtg` and each sector's 40-byte block header, no pixel data, cut by `k2is/tests/cut-capture.sh`, then in `.claude/field-tests/k2is-fixture.sh`), under the package's MIT licence with no copyright line of its own; `k2is/tests/LICENSE.fixtures` says where the files come from and what was cut. Verify: fixture `capture52`; `test_a_capture_with_its_8_sectors` and `test_a_representative_capture` on it (scan 35 × 34, subjects Gatan K2 IS and FEI Tecnai Remote, the `.gtg` read whole); collection suite 45 passed, `test_coverage` included; `uvx ruff check python/` clean.
- [ ] 3.2 Staging: the next crawl's warnings no longer list `.dmw`/`.gtg` extraction failures; K2IS captures are one record each. Verify: the findings file, with counts.
- [ ] 3.3 A representative `.dmw` fixture from staging, with @weber's agreement for the file. Verify: `test_a_dmw_file_with_the_dm4_header` on it.

## 4. Review (`review.md`, decisions 129 and 130 of 2026-11-12)

- [x] 4.1 Finding 1 (M, `.dmw`/`.gtg` typed by name whatever the content): decided by @weber (2026-11-12, decisions 149, 172 to 174) and built in the change `recognition-checks-content`, instead of the octet-stream globs: the format checks the header during recognition (`em/dmw` for `.dmw`, K2IS for a `.gtg` without sector files), and a file without it gets the type it has without the name. That change's deltas `formats/dm` and `formats/k2is` modify this change's requirements, so it is archived after this one.
- [x] 4.2 Finding 2 (M), decision 129: the K2IS description gives every tag of the `.gtg` but GMS's user-interface settings, an explicit list in D4 (the image viewer's tag group, `Session Info.Items`), the root's `SI Dimensions` and `Microscope Info` first; tags without a value kept (decision 161, after the merge); K2IS `extractor_version` 3. Verify: `test_a_representative_capture` (307 phrases of Capture52's 359 tags, 11 of them without a value), `test_user_interface_settings_are_left_out`; recorded results unchanged by `--regen-expected` (recognition only). Backlog: "K2IS description", trimming on human feedback.
- [x] 4.3 Finding 3, grouping: a warning at a `.gtg` with other than 8 sector files, naming the number; a sector file belongs to the longest stem it starts with; `.bin` in any case, as `.gtg` (D3). Verify: `test_a_tag_file_with_7_or_9_sector_files`, `test_an_incomplete_capture_next_to_a_complete_one`, `test_extensions_in_upper_case` (each failed before the fix), reproducers `wrong_count`, `nested_incomplete`, `upper_case` with recorded results; `other_bin` and `sectors_without_tags` re-recorded for the orphan warning's new wording.
- [x] 4.4 Finding 4: `SI Dimensions` and `Microscope Info` from the root. Verify: `test_the_groups_at_the_root_whatever_the_tag_order` (failed before).
- [x] 4.5 Finding 5: no rounding (`:g`, `:.3g` gone); DM `extractor_version` 4; README, "Values and units". Verify: `test_a_representative_dm4_image` and `_dm3_image` (`18.325349807739258 µm/pixel`).
- [x] 4.6 Finding 6: `posix_fadvise` guarded. Verify: `test_without_the_readahead_advice` (refused, missing; failed before).
- [x] 4.7 Finding 7: `first_image` against `file_reader(lazy=True)`; `ImageList` moved to the end as `file_reader` does; the pin's comment names dm and k2is. Verify: `test_first_image_is_what_file_reader_gives` on the three DM fixtures (the key order failed before; RGBA: `file_reader` still refuses).
- [x] 4.8 Finding 8: the README's pitfall names the 64 KiB buffer for readers of tiny pieces; TEMPLATE points to it.
- [x] 4.9 Finding 9: `lone_tags` is Capture52's `.gtg` (MIT); `dmw_file` labelled a stand-in until 3.3; `capture52` labelled "vendor-written, cut", allowed in TEMPLATE; the cut script in the repository. Verify: `test_a_tag_file_without_sectors`, `test_manifest`, `test_coverage`; the script run on `capture52` gives identical files.
- [x] 4.10 Finding 10: the `.dmw` and lone `.gtg` records asserted; reads recorded per file (`testing.described`). Verify: `test_a_dmw_file_with_the_dm4_header`, `test_a_tag_file_without_sectors`, each DM read at most 64 KiB and of the file only, the K2IS extractor reads the `.gtg` only.
- [x] 4.11 Finding 11: proposal (no deletion records, the cut fixture), design (risks), this file. Verify: `openspec validate dm-containers-and-k2is --strict`.

Verify 4.2 to 4.11 together: collection suite 58 passed; crawler suite 267 passed, 0 skipped (both with `PYTHONPATH` set to the worktree's `src` directories); `uvx ruff check python/` and `uvx ruff format --check python/` clean.
