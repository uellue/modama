# Tasks

Written with the leans of the night brief (2026-11-12) as assumptions; the proposal says where they changed (python-docx, python-pptx, odfpy not used, measured).

## 1. Measure and choose

- [x] 1.1 The tree's office files by extension, size and lock-file names (October listing). Verify: counts and sizes in the proposal.
- [x] 1.2 Bytes read by python-docx, python-pptx and `zipfile` for a 27 MB package. Verify: the numbers in the proposal.
- [x] 1.3 Current releases on PyPI, Python 3.14 wheels (pure Python, or abi3 for cryptography). Verify: the hand-over lists them.

## 2. Package

- [x] 2.1 `office/office.xml` (lock-file types), `office/__init__.py` (formats, recognition by content), `ooxml.py`, `odf.py`, `pdf.py`, `ole.py` (extraction). Verify: 2.2.
- [x] 2.2 `office/tests/`: fixtures from Apache Tika's test documents with `fixtures.toml` and `LICENSE.fixtures`, `generate.py` for lock files, misnamed files and an AES PDF; `test_office.py` with one test per scenario of `specs/formats/office/spec.md`. Verify: `pytest src` in `python/modama-formats-common`, also with `TZ=Europe/Berlin`, with the number of skipped tests.
- [x] 2.3 `modama_formats_common/__init__.py` (import, `PARTS`), `README.md` (rows), `pyproject.toml` (dependencies, pinned). Verify: `git diff`.
- [x] 2.4 `python/crawler/BACKLOG.md`, "Sync with upstream": python-docx, python-pptx, odfpy load whole packages; olefile's user-defined properties. Verify: `git diff`.

## 3. Checks and hand-over

- [x] 3.1 `uvx ruff format --check --diff` and `uvx ruff check` from the repo root; the crawler's tests. Verify: their output.
- [x] 3.2 An independent review (main) of 60a5f619..7f8a17cd, its findings applied with main's decisions: pypdf only with `%%EOF` at the end and a read budget of 32 MiB, the header from where `%PDF-` is (1); openpyxl only when no part of cell data is over 16 MiB (2); the code page as unsigned (3); references inside an Info value not followed (4); BACKLOG details (5); the brief cited as the coordinator's (6); XMP flattened by our code, said (7); OLE times with `Z` (8). Verify: the tests of the new scenarios, the re-recorded `word_doc`, `powerpoint_ppt`, `excel_xls` (times with `Z` only).
