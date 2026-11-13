# Tasks

Each scenario of `specs/formats/pydata-zarr/spec.md` has one test of the same name in `python/modama-formats-common/src/modama_formats_common/pydata/tests/test_zarr.py`; the scenario of `specs/crawl/spec.md` one in `python/crawler/tests/test_walk.py`. Q1–Q6 (317–320, 322, 323) answered by @weber on 2026-11-13.

## 1. Fixtures and tests first

- [x] 1.1 The `.zspy` fixture: written once by RosettaSciIO 0.15.0's zspy writer (`rosettasciio[zspy,hdf5]==0.15.0`, zarr 2.18.7, in a throwaway environment) with `consolidate=False`, from a signal dictionary shaped like pyxem's (4 × 4 × 16 × 16 `uint16`, signal type `electron_diffraction`, made-up original metadata with an entry nobody has seen, `_None_`, and the keys `package_info`, `learning_results`, `attributes`, `models`), committed with its script (`pydata/tests/write_zspy.py`), its command and the sha256 of its tree in `fixtures.toml`. Verify: `test_manifest`; the root `.zattrs` says `file_format ZSpy`; written three times, `diff -r` identical.
- [x] 1.2 Generated fixtures (`generate.py`, zarr-python 3.4.2): v2 and v3 abTEM-like stores with made-up values (the v3 one with `.ipynb_checkpoints/` inside), a nested store, a broken root. Verify: `test_manifest`, `test_coverage`, reviewed `expected/*.json`.
- [x] 1.3 One test per scenario in `test_zarr.py`, the reproducers built in the test. Verify: 29 tests (one parametrised over v2 and v3).

## 2. Code

- [x] 2.1 `common/zarr` and `common/zspy` in `pydata/__init__.py` (D4). Verify: the scenarios of "A Zarr store is a described collapsed dataset" and "A HyperSpy Zarr store is typed by name and content".
- [x] 2.2 `pydata/zarrstore.py`: the walk (D1–D3: `lstat` before open, `fstat` after, the room rule, the depth bound, `RecursionError`/`MemoryError` per node), bounds, the skip list (the root's `zarr_format` kept; a `.zspy` array's storage parameters kept, 322), the summary line (318); the reasons for reading the JSON ourselves in the module's docstring (323); HyperSpy's skip list moved to `values.py`. Verify: the remaining scenarios; the `.hspy` tests unchanged.
- [x] 2.3 The stamp (D5, 319): `Format.collapsed_state` and `walk._stamped` in the crawler, `zarrstore.state` and `Zarr.collapsed_state` here. Verify: `test_a_file_deep_below_a_collapsed_directory_changes` (taken over, stamp changed), `test_a_metadata_file_below_the_first_level_changes` (a chunk changes nothing).
- [x] 2.4 Bytes read: `test_a_store_of_many_chunks` compares the `rchar` delta with the sum of the metadata files' sizes; `strace -f -e trace=openat,newfstatat` of an extraction of the staging sample `AB-graphene.zarr`. Verify: the hand-over.

## 3. Package, documentation, suites

- [x] 3.1 `zarr` pinned in the package's `[test]` extra (3.4.2); README rows for Zarr and `.zspy`; TEMPLATE.md and the crawler's README on the extractor and the stamp of a collapsed dataset; BACKLOG "Zarr attributes" replaced by "Zarr subtypes beyond ZSpy" (318). Verify: the diff.
- [x] 3.1a Decision-log rows for 319, 322 and 323 in `design/architecture.md`; zarr-python under BACKLOG "Sync with upstream", not reported (@weber). Verify: the diff.
- [x] 3.2 The crawler's CLI tests that assumed the core's `zarr/zarr` claims a store (`tests/test_cli.py`: five failed with `common/zarr` installed, 2026-11-13) are independent of the installed format packages: the selection tests (`test_per_path_ignores_from_the_config`, `test_ignore_overrides_selection`, `test_comma_separated_ids`) and `test_dataset_warnings_are_reported_without_verbose` select only the crawler's collections they need (`--select core,zarr`, `core,collapse,zarr`); `test_verbose_diagnostics_travel_with_the_records` names any installed Zarr format (`application/x-zarr by …/zarr`) and counts the warnings from the warning comments. Only these tests changed. Verify: `pytest tests/test_cli.py` with `common/zarr` installed and without it.
- [x] 3.3 Suites in an own venv, temporary files under `/var/tmp/zarr-stores/`: `pytest src` in `modama-formats-common` (also with `TZ=Europe/Berlin`), `modama-formats-em`, the crawler; `uvx pre-commit run --all-files` after `git add`. Verify: their outputs, with the number of skipped tests.
- [x] 3.4 `modama-crawler records --verbose` on the fixtures and on the staging sample. Verify: the summary lines in the hand-over.
