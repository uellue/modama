# Tasks

Each scenario of `specs/formats/pydata/spec.md` has one test of the same name in `python/modama-formats-common/src/modama_formats_common/pydata/tests/test_extract.py`.

## 1. Types

- [x] 1.1 `pydata/pydata.xml`: the types of the proposal, with their globs, magic and parents. Verify: the type scenarios (`test_a_numpy_array_file`, `test_hdf5_whatever_the_name`, `test_a_nexus_file_and_a_hyperspy_file`); recorded expected results of the fixtures; `test_coverage` (every glob, magic rule and format fires on a representative fixture).
- [x] 1.2 Recognition with the content checks (`.npz`, `.nxs`, `.hspy`, `.mat`, `.ipynb`, `.pkl`). Verify: `test_a_text_file_named_like_an_archive`, `test_a_text_file_named_like_a_nexus_file`, `test_a_text_file_named_like_a_matlab_file`, `test_a_file_named_like_a_notebook_that_is_not_json`, `test_a_protocol_0_pickle`; fixture `misnamed`.

## 2. Extraction

- [x] 2.1 NumPy `.npy` and `.npz`. Verify: `test_the_header_only` (128 bytes read of 8 MB), `test_stored_and_compressed_archives`.
- [x] 2.2 The HDF5 walk (HDF5, NeXus, HyperSpy). Verify: the scenarios of "An HDF5 file is described by a walk of its objects", "The walk of an HDF5 file is bounded" and "A HyperSpy file is described as HyperSpy stores it" (32 MB array: 6,608 bytes read; 32 MB variance signal: 82,120 bytes).
- [x] 2.3 MATLAB 4, 5 and 7.3. Verify: the MATLAB scenarios, `test_a_matlab_5_file` under `TZ=UTC` and `TZ=Europe/Berlin`.
- [x] 2.4 Notebooks. Verify: the notebook scenarios.
- [x] 2.5 Python scripts and pickles. Verify: the script and pickle scenarios (the script's and the pickle's side effects absent).

## 3. Fixtures, package, documentation

- [x] 3.1 Public fixtures with licence and source in `fixtures.toml` and `LICENSE.fixtures` (NeXus definitions LGPL-3.0, RosettaSciIO GPL-3.0-or-later, SciPy, h5py and nbformat BSD-3-Clause), generated ones in `generate.py`. Verify: `test_manifest`, `test_coverage`, `test_fixture` with reviewed `expected/*.json`.
- [x] 3.2 The part in `PARTS`, README rows, dependencies pinned in `pyproject.toml`, `**/tests/fixtures` out of ruff. Verify: `pytest src` in `python/modama-formats-common` (48 passed, also under `TZ=Europe/Berlin`); the crawler suite (425 passed, 0 skipped); `uvx ruff format --check --diff` and `uvx ruff check` from the repo root (the 7 known errors in `prototypes/*.ipynb` only).
- [x] 3.3 BACKLOG: RosettaSciIO's lazy hspy reader under "Sync with upstream" (A1); Zarr attributes as an open point (A3). Verify: the entries.
- [ ] 3.4 Review by an agent that did not write the code; findings applied. Verify: the review's findings and their outcome in the hand-over.
