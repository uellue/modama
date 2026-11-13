# Tasks

Tests first: each task writes the tests of its scenarios, sees them fail, then the code. Worktree of its own from `crawler`, venv and temporary files under `/var/tmp/em-de/` (`python/crawler/AGENTS.md`, "Parallel coding agents"). Built 2026-11-13 on the leans @weber accepted (312).

## 1. The runner offers only unclaimed entries (D2)

- [x] 1.1 and 1.2 Built as bug 311 (merge 58bea00e) before this change was applied, with decision 344 (`Directory.claimed`, `claimed_elsewhere`); this change's `recognition` delta dropped. Verify: `test_formats.py` of that change; here `test_the_members_are_not_offered_to_later_formats` (the whole em collection on `acquisition_274`: one `em/de` dataset, no warning).

## 2. Types and recognition (D3, D5, D6)

- [x] 2.1 `src/modama_formats_em/de/` with `de.xml` (`application/x.de-acquisition`; `application/x.de-info`, the glob `[0-9]…[0-9]_*_info.txt`, `sub-class-of` `text/plain`), the format `em/de` (priority 62, `reacts_to` the info type), in the package's `PARTS`. Verify: `modama-crawler records --verbose` on `acquisition_274` names `application/x.de-acquisition by em/de` (the glob with its `[0-9]` classes, built by `update-mime-database`).
- [x] 2.2 Fixtures (D8): `acquisition_274`, `lone_info_272`, `xy_scan_275` from RosettaSciIO v0.15.0, with sha256 in `fixtures.toml`; reproducers from `generate.py`; `de/tests/LICENSE.fixtures` (GPL-3.0-or-later). Verify: `test_manifest`, `test_coverage`.
- [x] 2.3 Tests, one per scenario: `test_an_acquisition_of_de_server_2_7_4`, `test_a_numbered_movie_and_a_scan_coordinate_file`, `test_a_file_nobody_has_seen_with_the_stem`, `test_a_filename_suffix_set_by_the_user`, `test_stems_that_nest`, `test_the_sum_claimed_by_another_format` (decision 344), `test_another_programs_files_with_a_date_prefix`, `test_a_movie_without_its_info_file` (with the whole em collection: `em/mrc`), `test_an_info_file_of_de_server_2_7_2_alone`. Verify: all but the lone movie failed on a stub format, then pass; recorded results `expected/*.json` reviewed.

## 3. Extraction (D4, D7)

- [x] 3.1 Tests: `test_a_representative_acquisitions_values`, `test_a_representative_acquisition`, `test_an_entry_nobody_has_seen`, `test_option_lists_are_left_out`, `test_the_movie_is_not_read` (a 1 GiB sparse movie), `test_a_raster_scan`, `test_a_scan_that_is_not_a_raster`, `test_a_renamed_info_file`, `test_an_info_file_of_de_server_2_7_2`. Verify: they failed on the stub.
- [x] 3.2 The extractor (`read_info`, `skipped`, `headline`, `mapping`). Verify: 3.1 passes; also with `TZ=Europe/Berlin`; `pytest -s` shows 80,742 bytes read for the 1 GiB acquisition, twice its 40,309-byte info file plus 124.

## 4. Documentation and backlog

- [x] 4.1 A row in `python/modama-formats-em/README.md`; the pin's comment in `pyproject.toml` names `de` (`rsciio.mrc._api.read_de_metadata_file`).
- [x] 4.2 `python/crawler/BACKLOG.md`: the `em/de` item now says what is left (the 2020 acquisition); RosettaSciIO's findings of D1 under "Sync with upstream", as *found*.
- [x] 4.3 What a format is offered: described by bug 311's change in README and TEMPLATE.md; nothing to add here.

## 5. Acceptance

- [x] 5.1 The em, common and crawler suites, also with `TZ=Europe/Berlin` for em and common; `uvx pre-commit run --all-files` after `git add`. Verify: the counts in the hand-over.
- [ ] 5.2 Review by an agent that did not write the code (`/.claude/skills/format-collection/review-brief.md`), findings verified and answered: for the main session to start.
- [ ] 5.3 With @weber's copy of `20200821_92978`: `modama-crawler records --verbose` on its folder before and after; browse before and after in the search stack (after merge). Verify: one record of 3 members instead of 3.
- [x] 5.4 `openspec validate em-de --strict`.
