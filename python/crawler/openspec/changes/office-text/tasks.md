# Tasks

Before the build: @weber's answers to Q1 to Q5 (design.md); Q1 (the dependencies) blocks everything. Archive `common-office`, `text-as-written` and `slow-extractions` first, or keep the deltas as ADDED (they are).

## 1. Tests first (they fail before the code)

- [ ] 1.1 Fixtures: Tika's `testComment.docx` and `testPPT_embeddedMP3.pptx` at the pinned commit, with their entries in `fixtures.toml` (sha256, licence); written at test time: the `.docx` with title, headings, list, bold, table (python-docx), the deck with notes (python-pptx), both with a 20 MB picture, the tracked-changes reproducer, the 300-paragraph document, the DOCTYPE document, the 1.5 MiB document. Verify: the fixture tests list them.
- [ ] 1.2 One test per scenario of `specs/formats/office/spec.md` in `office/tests/test_office.py` (13) and of `specs/extraction/spec.md` in the crawler's extraction tests (3); `bytes_read` for the two read scenarios. Verify: each fails before the code, with the count in the hand-over.

## 2. Code

- [ ] 2.1 `office/rendered.py`: the proxy (D2: content types, `ZIP_STORED`, the DOCTYPE stop, bytes read from `Budgeted.read_so_far`), Word by mammoth (`external_file_access=False`, `convert_image` that reads nothing and gives no `img`, the Title style map) and markdownify, PowerPoint by python-pptx and the slide walk, `written.shown_text`, the flag. Verify: the office tests.
- [ ] 2.2 `ooxml.extract` and `Docx`, `Docm`, `Pptx`: `values["text"]`, `text not rendered`, `values["warnings"]`; not `Xlsx`, `Xlsm`. Verify: the office tests; `Xlsx` expected results unchanged.
- [ ] 2.3 `pyproject.toml` of `modama-formats-common`: mammoth, markdownify, python-pptx pinned with a comment each (release, licence, why), python-docx in `test`. Verify: a fresh venv installs it.
- [ ] 2.4 `extraction.py`: `values["warnings"]` warned at the dataset beside `_slow`; `review.py`: the marker `large document text`. Verify: the extraction tests, `search-chain`'s review tests.
- [ ] 2.5 Re-record the expected results of `word_docx`, `word_docm`, `powerpoint_pptx`: `values.text` added, nothing else changed. Verify: `git diff` of `expected/`.

## 3. Documentation

- [ ] 3.1 `modama-formats-common/README.md` (office rows: the text; the new dependencies), the crawler's `README.md` (the record's descriptions), `formats/TEMPLATE.md` (`values["warnings"]`), `BACKLOG.md` (PDF, `.xlsx`, `.odt`, `.odp` next; an outline for long documents; bytes read for every extraction), `common-office`'s BACKLOG entry on python-pptx (now used, on the proxy). Verify: by reading.
- [ ] 3.2 A decision-log row in `design/architecture.md` once @weber agrees. Verify: the row names Q1 to Q5's answers.

## 4. Checks and review

- [ ] 4.1 `modama-formats-common`'s office tests, the crawler's extraction tests, `search-chain`'s review tests; then the three suites whole; `uvx pre-commit run --all-files`. Verify: the commands' output in the hand-over.
- [ ] 4.2 Before/after records of the self-made `.docx` and `.pptx` through `records.build`, and in `modama-chain browse`. Verify: in the hand-over.
- [ ] 4.3 Review by an agent that did not write the code (the proxy reads untrusted packages: D2's safety points first). Verify: findings and fixes in the hand-over.
- [ ] 4.4 The image build and the staging crawl of 19:00 UTC, main's OK. Verify: `modama-chain review` lists the `large document text` flags; @weber looks at decks and documents in `browse`, among them the `.pptx` of page item 367 a.
