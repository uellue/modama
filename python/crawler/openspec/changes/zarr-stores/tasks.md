# Tasks

Each scenario of `specs/formats/pydata-zarr/spec.md` has one test of the same name in `python/modama-formats-common/src/modama_formats_common/pydata/tests/test_zarr.py`, written before the code. Held until @weber answers Q1–Q6 (317–320, 322, 323).

## 1. Fixtures and tests first

- [ ] 1.1 The `.zspy` fixture: written once by RosettaSciIO 0.15.0's zspy writer (`rosettasciio[zspy,hspy]==0.15.0`, zarr 2, in a throwaway environment) with `consolidate=False`, from a signal dictionary shaped like pyxem's (4 × 4 × 16 × 16 `uint16`, signal type `electron_diffraction`, made-up original metadata with an entry nobody has seen, `_None_`, and the keys `package_info`, `learning_results`, `attributes`, `models`), committed with its script (`pydata/tests/write-zspy.py`), its command and the sha256 of its files in `fixtures.toml`. Verify: `test_manifest`; the fixture's root `.zattrs` says `file_format ZSpy`; written twice, `diff -r` identical.
- [ ] 1.2 Generated fixtures (`generate.py`, zarr-python): v2 and v3 abTEM-like stores with made-up values (the v3 one with `.ipynb_checkpoints/` inside), a nested store, a broken root. Verify: `test_manifest`, `test_coverage` (both formats fire on a representative fixture), recorded `expected/*.json` reviewed.
- [ ] 1.3 One test per scenario in `test_zarr.py` (failing before 2.x), the reproducers built in the test: an unknown codec and data type, `.zmetadata` (opened never, by inotify as `test_extract.Opened`), a `.zattrs` symlink and a group symlink to outside, a FIFO, both `zarr.json` and `.zgroup`, a ZSpy store named `.zarr`, 6,000 groups, 20 × 1 MiB, 2 MiB files at a group and the root, deep nesting (an object 100,000 levels deep; 150 nested groups), a credential. Verify: `pytest src/modama_formats_common/pydata/tests/test_zarr.py` fails for the missing formats only.

## 2. Code

- [ ] 2.1 `common/zarr` and `common/zspy` in `pydata/__init__.py` (D4). Verify: the scenarios of "A Zarr store is a described collapsed dataset" and "A HyperSpy Zarr store is typed by name and content".
- [ ] 2.2 `pydata/zarrstore.py`: the walk (D1–D3: `lstat` before open, `fstat` after, the room rule, the depth bound, `RecursionError`/`MemoryError` per node), bounds, the skip list (the root's `zarr_format` kept; Q5 as @weber answers), the summary line; HyperSpy's skip list moved to `values.py`. Verify: the remaining scenarios; the `.hspy` tests unchanged.
- [ ] 2.3 Bytes read: the test of "A store of many chunks" compares the `rchar` delta of `/proc/self/io` with the sum of the metadata files' sizes (TEMPLATE.md, "Testing a format"); `strace -f -e trace=openat,newfstatat` of an extraction of the staging sample `AB-graphene.zarr` (its two `zarr.json` read, the 177 MB chunk never opened). Verify: the command and its output in the hand-over.

## 3. Package, documentation, suites

- [ ] 3.1 `zarr` pinned in the package's `[test]` extra (3.4.2, current on PyPI, pure Python); README rows for Zarr and `.zspy`; TEMPLATE.md, "Extracting metadata": the extractor of a collapsed dataset reads below its anchor (A7); BACKLOG "Zarr attributes" replaced by the stamp limit (A7, Q3); with Q6 agreed, a decision-log row and zarr-python's three behaviours under "Sync with upstream". Verify: the diff.
- [ ] 3.2 The crawler's CLI tests that name `zarr/zarr` for a store (`tests/test_cli.py`: five fail with `common` installed, 2026-11-13) name the format independently of what else is installed. Verify: the crawler suite.
- [ ] 3.3 Suites in an own venv, temporary files under `/var/tmp/zarr-stores/`: `pytest src` in `modama-formats-common` (also with `TZ=Europe/Berlin`), `modama-formats-em`, the crawler; `uvx pre-commit run --all-files` after `git add`. Verify: their outputs, with the number of skipped tests.
- [ ] 3.4 `modama-crawler records --verbose` on the fixtures and on the staging sample. Verify: the summary lines in the hand-over.
