# Tasks

@weber accepted the leans on 2026-11-14 (374: Q1; 375: Q2 to Q5); an independent review asked for fixes before the build (M1, M2, S1 to S8, notes), folded into the proposal, design and spec. Archive `common-office` and `text-as-written` first: this change's delta modifies a requirement of `common-office` (`openspec validate` says so as INFO).

## 1. Tests first

- [x] 1.1 Fixtures: Tika's `testComment.docx` (`comment_docx`) and `testPPT_embeddedMP3.pptx` (`powerpoint_mp3`) at the pinned commit, entries in `fixtures.toml` with sha256 and licence; the documents written at test time by python-docx and python-pptx, and the changed copies of Tika's files, in `office/tests/test_text.py`. Verify: `test_fixtures.py` records and checks the two new fixtures.
- [x] 1.2 One test per scenario of the ADDED requirements in `office/tests/test_text.py` (20 test functions, 21 runs: the record's test is parametrised over two fixtures), plus the record's second description; `bytes_read` for the read scenarios. Verify: they pass; written with the code in one stretch, so not each seen failing first (the first run failed two of them on the templates' own descriptions and a too small document, fixed in the tests).
- [x] 1.3 MODIFIED requirement: `test_a_presentation` (`mapped_metadata` holds more than the slide count) and `test_only_the_property_parts_are_read`, now `test_only_the_xml_parts_are_read` (the text, still under 1 MB read). Verify: the office tests.

## 2. Code

- [x] 2.1 `office/rendered.py`: the proxy (OPC content types, Override before Default, case-insensitive, media types never, unknown never), the DTD check by defusedxml's `iterparse`, the soft deadline of 30 s, Word by mammoth and markdownify (review S5's options, links within the document as text), slides by python-pptx (`has_notes_slide`), the author's properties at the head, `written.shown`, `bytes read`, `xml bytes`, `large document text`, `text not rendered`, `credentials_left_out`. Verify: the office tests.
- [x] 2.2 `ooxml.extract(path, computed, render)` and its docstring (review S7); `Docx` and `Docm` (now a subclass of `Docx`) and `Pptx` pass their renderer; `Xlsx`, `Xlsm` unchanged. Verify: the office tests; `excel_*` expected results unchanged.
- [x] 2.3 `pyproject.toml` of `modama-formats-common`: mammoth, markdownify, python-pptx pinned with a comment each, python-docx in `test`. Verify: the venv installed from it.
- [x] 2.4 Expected results re-recorded: `word_docx`, `word_docm`, `powerpoint_pptx` gain `text` and the three numbers in `mapped_metadata`, nothing else changed. Verify: `git diff` of `expected/`.
- [x] 2.5 Not done, on purpose (deviation from Q4, review S2): the crawler's core and `modama-chain review` are unchanged; the warning channel is in BACKLOG.

## 3. Documentation

- [x] 3.1 `modama-formats-common/README.md` (the Office Open XML row), the crawler's `README.md` (the record's descriptions), `BACKLOG.md` (the change's next steps: the warning channel, PDF, `.xlsx`, `.odt` and `.odp`, our own slide walk, an outline; the upstream entry on python-pptx). Verify: by reading.
- [x] 3.2 A decision-log row in `design/architecture.md` after 369. Verify: by reading.

## 4. Checks and review

- [x] 4.1 The suites of `python/crawler`, `modama-formats-common`, `modama-formats-em`, `search-chain`; `uvx pre-commit run --all-files`. Verify: the output in the hand-over.
- [x] 4.2 Records of two fixtures by `modama-crawler records --verbose`. Verify: in the hand-over.
- [ ] 4.3 Review of the code by an agent that did not write it (the proxy reads untrusted packages). Verify: findings and fixes.
- [ ] 4.4 The image build and the staging crawl of 19:00 UTC, main's OK. Verify: @weber looks at decks and documents in `browse`, among them the `.pptx` of page item 367 a; `large document text` and `text not rendered` counted over the office records.
