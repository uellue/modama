# Tasks

Written with the leans of the night brief (2026-11-12) as assumptions; the proposal says where they changed (python-docx, python-pptx, odfpy not used, measured).

## 1. Measure and choose

- [x] 1.1 The tree's office files by extension, size and lock-file names (October listing). Verify: counts and sizes in the proposal.
- [x] 1.2 Bytes read by python-docx, python-pptx and `zipfile` for a 27 MB package. Verify: the numbers in the proposal.
- [x] 1.3 Current releases on PyPI, Python 3.14 wheels (pure Python, or abi3 for cryptography). Verify: the hand-over lists them.

## 2. Package

- [ ] 2.1 `office/office.xml` (lock-file types), `office/__init__.py` (formats, recognition by content), `ooxml.py`, `odf.py`, `pdf.py`, `ole.py` (extraction). Verify: 2.2.
- [ ] 2.2 `office/tests/`: fixtures from Apache Tika's test documents with `fixtures.toml` and `LICENSE.fixtures`, `generate.py` for lock files, misnamed files and an AES PDF; `test_office.py` with one test per scenario of `specs/formats/office/spec.md`. Verify: `pytest src` in `python/modama-formats-common`, also with `TZ=Europe/Berlin`, with the number of skipped tests.
- [ ] 2.3 `modama_formats_common/__init__.py` (import, `PARTS`), `README.md` (rows), `pyproject.toml` (dependencies, pinned). Verify: `git diff`.
- [ ] 2.4 `python/crawler/BACKLOG.md`, "Sync with upstream": python-docx, python-pptx, odfpy load whole packages; olefile's user-defined properties. Verify: `git diff`.

## 3. Checks and hand-over

- [ ] 3.1 `uvx ruff format --check --diff` and `uvx ruff check` from the repo root; the crawler's tests. Verify: their output.
- [ ] 3.2 An independent review (main), its findings applied. Verify: the commits after it.
