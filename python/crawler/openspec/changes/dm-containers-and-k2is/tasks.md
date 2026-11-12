# Tasks

## 1. Types

- [x] 1.1 `.dmw` and `.gtg` types (D1: `.dmw` in `dm/dm.xml`, `.gtg` in `k2is/k2is.xml`). Verify: spec `formats/dm` "A .dmw file with the DM4 header" as `test_a_dmw_file_with_the_dm4_header`, "A lone .gtg file" as `test_a_tag_file_without_sectors` (k2is part); the existing DM tests unchanged.
- [x] 1.2 K2IS sector type in `k2is/k2is.xml` (D2). Verify: spec `formats/k2is` "Another .bin file" as `test_another_bin_file`, with a sector block named `sector.dat` typed by content.

## 2. K2IS

- [x] 2.1 The K2IS part: recognizer grouping by stem (D3), in the collection's `PARTS`. Verify: spec `formats/k2is` scenarios as `test_a_capture_with_its_8_sectors`, `test_sector_files_without_their_tag_file`, `test_a_tag_file_without_sectors`, with recorded expected results.
- [x] 2.2 Extractor from the `.gtg` tags (D4). Verify: `test_a_representative_capture` on the reproducer (358 bytes read of 179,112), README table updated; `uvx ruff check python/` clean; crawler suite 267 passed; collection suite 44 passed and 1 failed by design: `k2is` `test_coverage` (the sector magic and the K2IS format have no representative fixture until 3.1).

## 3. Real data

- [x] 3.1 A representative K2IS fixture from staging, replacing the synthetic capture. Agreed 2026-11-12 (73, 79) for `libertem-test-data/Capture52`, @weber's own test data: metadata only (the `.gtg` and each sector's 40-byte block header, no pixel data, cut by `.claude/field-tests/k2is-fixture.sh`), under the package's MIT licence with no copyright line of its own; `k2is/tests/LICENSE.fixtures` says where the files come from and what was cut. Verify: fixture `capture52`; `test_a_capture_with_its_8_sectors` and `test_a_representative_capture` on it (scan 35 × 34, subjects Gatan K2 IS and FEI Tecnai Remote, 27,045 bytes read: the `.gtg` whole); collection suite 45 passed, `test_coverage` included; `uvx ruff check python/` clean.
- [ ] 3.3 A representative `.dmw` fixture from staging, with @weber's agreement for the file. Verify: `test_a_dmw_file_with_the_dm4_header` on it.
- [ ] 3.2 Staging: the next crawl's warnings no longer list `.dmw`/`.gtg` extraction failures; K2IS captures are one record each. Verify: the findings file, with counts.
