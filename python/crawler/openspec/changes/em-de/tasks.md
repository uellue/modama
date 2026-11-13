# Tasks

Tests first: each task writes the tests of its scenarios, sees them fail, then the code. Worktree of its own from `crawler`, venv and temporary files under `/var/tmp/em-de/` (`python/crawler/AGENTS.md`, "Parallel coding agents"). Starts after @weber's answers to Q1 to Q9, or on the leans if he says so.

## 1. The runner offers only unclaimed entries (D2, spec `recognition`)

- [ ] 1.1 Tests in `python/crawler/tests/test_formats.py`: `test_higher_priority_wins_shared_file` changed to the modified scenario (no warning, the lower format not offered `a.txt`); `test_a_claimed_entry_named_by_a_later_format`; `test_every_entry_of_a_formats_type_is_claimed` (a spy format is not called). Verify: they fail on the current runner.
- [ ] 1.2 `Directory.of_type` leaves out entries claimed so far; `run_post` passes the claims to the directory after each format and computes the present types from unclaimed entries only; `entries`, `entry(name)` and `children` unchanged. Verify: 1.1 passes; the crawler suite passes (`pytest` in `python/crawler`, with the number of skipped tests); the em and common collection suites pass unchanged, recorded results included (`pytest src` in each package): no recorded dataset changes.

## 2. Types and recognition (D3, D5, D6)

- [ ] 2.1 `src/modama_formats_em/de/` from the skeleton: `de.xml` with `application/x.de-acquisition` and `application/x.de-info` (glob of D3, `sub-class-of` `text/plain`), the format `em/de` (priority 62, `reacts_to` the info type), in the package's `PARTS`. Verify: `modama-crawler records --verbose` on a folder with `20241021_00405_info.txt` names `application/x.de-info` before the format exists (the glob alone, built by `update-mime-database` with its `[0-9]` classes), and `em/de` after.
- [ ] 2.2 Fixtures (D8) with `fixtures.toml` and `de/tests/LICENSE.fixtures` (GPL-3.0, RosettaSciIO `v0.15.0`, the renames). Verify: `test_manifest`.
- [ ] 2.3 Tests, one per scenario of spec `formats/de` on recognition: `test_an_acquisition_of_de_server_2_7_4`, `test_a_numbered_movie_and_a_scan_coordinate_file`, `test_a_file_nobody_has_seen_with_the_stem`, `test_a_filename_suffix_set_by_the_user`, `test_stems_that_nest`, `test_another_programs_files_with_a_date_prefix`, `test_a_movie_without_its_info_file` (with `em/mrc` installed, else `application/octet-stream`), `test_an_info_file_of_de_server_2_7_2_alone`. Verify: they fail, then the recognizer (first line, stem, longest stem first, `not_of_type`), then they pass; recorded results `expected/*.json` reviewed.

## 3. Extraction (D4, D7)

- [ ] 3.1 Tests: `test_a_representative_acquisitions_values`, `test_a_representative_acquisition`, `test_an_entry_nobody_has_seen`, `test_option_lists_are_left_out`, `test_the_movie_is_not_read` (`modama_formats_em.testing.rchar`, a 1 GiB sparse movie), `test_a_raster_scan`, `test_a_scan_that_is_not_a_raster`, `test_a_renamed_info_file`. Verify: they fail.
- [ ] 3.2 The extractor: the info file read and parsed (size check, decoding, `key = value`), `de.skipped`, `textual` and `credential`, `de.HEADLINE`, the Dataset Name check, RosettaSciIO's `read_de_metadata_file` for `mapped_metadata` (Q3). Verify: 3.1 passes; `TZ=Europe/Berlin pytest src` passes too; `pytest -s src/modama_formats_em/de` prints each description, subject and the bytes read.

## 4. Documentation and backlog

- [ ] 4.1 A row in `python/modama-formats-em/README.md` (recognised as, extracted, the example summary line); the pin's comment in `pyproject.toml` names `de` (`rsciio.mrc._api.read_de_metadata_file`, a private module).
- [ ] 4.2 `python/crawler/BACKLOG.md`: the `em/de` item closed with this change; under "Sync with upstream", RosettaSciIO's findings of D1 as *found* (scales set to 1, units not in the file, the gain's key, strings, the non-raster `ValueError`, the joined strings of `Scan - Time`, navigators named crosswise, the virtual images read whole); the runner's "already claimed" note gone.
- [ ] 4.3 `README.md` of the crawler or TEMPLATE.md, where they describe what a format is offered: claimed entries are not. Verify: `grep -n "of_type" python/crawler/README.md python/crawler/src/modama_crawler/formats/TEMPLATE.md` reviewed.

## 5. Acceptance

- [ ] 5.1 TEMPLATE.md, "Testing a format", all of it; the crawler's suite; `uvx pre-commit run --all-files` from the repository root after `git add` of new files. Verify: the commands with their output in the hand-over, skipped tests counted.
- [ ] 5.2 Review by an agent that did not write the code (`/.claude/skills/format-collection/review-brief.md`), findings verified and answered.
- [ ] 5.3 With @weber's copy: `modama-crawler records --verbose` on the folder of `20200821_92978` before and after; browse before and after in the search stack (after merge, the main session). Verify: one record of 3 members instead of 3.
- [ ] 5.4 `openspec validate em-de --strict`.
