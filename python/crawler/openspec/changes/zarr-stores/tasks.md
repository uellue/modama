# Tasks

Each scenario of `specs/formats/pydata-zarr/spec.md` has one test of the same name in `python/modama-formats-common/src/modama_formats_common/pydata/tests/test_zarr.py`, written before the code.

## 1. Fixtures and tests first

- [ ] 1.1 The `.zspy` fixture: written once by RosettaSciIO 0.15.0's zspy writer with zarr 2 in a throwaway venv, from a signal dictionary shaped like pyxem's (4 × 4 × 16 × 16 `uint16`, signal type `electron_diffraction`, made-up original metadata with an entry nobody has seen), committed with its script (`pydata/tests/write-zspy.py`) and its command in `fixtures.toml`. Verify: `test_manifest`; the fixture's `.zattrs` says `file_format HyperSpy`.
- [ ] 1.2 Generated fixtures (`generate.py`, zarr-python): v2 and v3 abTEM-like stores with made-up values, a nested store, a `.zspy`-named store without HyperSpy, a broken root. Verify: `test_manifest`, `test_coverage` (both formats fire on a representative fixture), recorded `expected/*.json` reviewed.
- [ ] 1.3 One test per scenario in `test_zarr.py` (failing before 2.x). Verify: `pytest src/modama_formats_common/pydata/tests/test_zarr.py` fails for the missing formats only.

## 2. Code

- [ ] 2.1 `common/zarr` and `common/zspy` in `pydata/__init__.py` (D4). Verify: the scenarios of "A Zarr store is a described collapsed dataset" and "A HyperSpy Zarr store is typed by name and content".
- [ ] 2.2 `pydata/zarr.py`: the walk (D1–D3), bounds, the skip list, the summary line; HyperSpy's skip list moved to `values.py`. Verify: the remaining scenarios; the `.hspy` tests unchanged.
- [ ] 2.3 Bytes read: `strace -f -e trace=openat` of an extraction of a store of 4,096 chunks, v2 and v3, and of the staging sample `AB-graphene.zarr` (only its two `zarr.json` opened, the 177 MB chunk not); the test of "A store of many chunks" counts the opens under the store with an `os.open` patch. Verify: the command and its output in the hand-over.

## 3. Package, documentation, suites

- [ ] 3.1 `zarr` pinned in the package's `[test]` extra (3.4.2, current on PyPI, pure Python); README rows for Zarr and `.zspy`; BACKLOG "Zarr attributes" replaced by the stamp limit (A7, Q3). Verify: the diff.
- [ ] 3.2 Suites in an own venv, temporary files under `/var/tmp/zarr-stores/`: `pytest src` in `modama-formats-common` (also with `TZ=Europe/Berlin`), `modama-formats-em`, the crawler; `uvx pre-commit run --all-files` after `git add`. Verify: their outputs, with the number of skipped tests.
- [ ] 3.3 `modama-crawler records --verbose` on the fixtures and on the staging sample. Verify: the summary lines in the hand-over.
