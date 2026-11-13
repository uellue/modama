# Tasks

@weber accepted the leans on 2026-11-13 (299, 303, 304, 307); 306: the wording in the glossary pull request after the demo. Archive `common-text`, `common-structured` and `tags-in-the-record` first: this change's deltas modify their requirements (`openspec validate` says so as INFO).

## 1. Tests first (they fail before the code)

- [x] 1.1 Test files, written by the tests themselves (synthetic, of the snapshots' shapes, no user's content; the large ones generated at test time, not stored): a session note, a note with a password, a note of 166 lines of 60 characters, one line of 100,000 characters, `stem-shape.json` (a comma missing), a YAML that does not parse, `sim.json` (6,000 numbers, 20,000 base64 characters), a YAML of 40 keys with comments and 1,000 numbers, a YAML with comments, a Compose-shaped YAML with a password, an INI with a password, trace exports of 2.7 MB and 10 MB, a JSON Lines file and a pretty-printed array over 8 MiB; the existing fixtures for the rest. Verify: the fixture tests with the re-recorded results.
- [x] 1.2 One test per scenario of the deltas: `text/tests/test_extract.py` (10, of which 9 failed before the code; "HTML and binary content" passed, as today), `structured/tests/test_extract.py` (16, of which 14 failed; "no text of CSV and XML" and "a pretty-printed document is not JSON Lines" passed, as today), `crawler/tests/test_records.py` (4 tests, 5 cases, of which 3 failed; the two cases of "no text, the tag lines as before" passed, as today). Changed: the bytes-read bounds of "A log larger than the bound" and "A JSON file over the bound", and "A YAML merge-key bomb" (no failure any more).

## 2. Code

- [x] 2.1 `records.py`: `text(dataset)`; the second description is `values["text"]` where it is a non-empty string, else the tag lines. Verify: the records tests.
- [x] 2.2 `modama_formats_common/written.py`: head and tail with the marker, the line-wise credential check, the front matter rule, the tail read, `TEXT` = `extraction.MAX_STRING`. Verify: the text tests.
- [x] 2.3 Text area: `values["text"]` for the seven formats, not HTML; `head.Head.size`; the tail of a file typed by its name only. Verify: the text tests.
- [x] 2.4 Structured area: the text as written; `structured/shortened.py` (B and its steps, credentials, a bound of 10,000 values for an alias bomb); a document its reader refuses as text; a file over 8 MiB as head and tail, `not_parsed_larger_than_bytes`, JSON Lines from the head. Verify: the structured tests.
- [x] 2.5 Recorded expected results re-recorded: `values.text` added, nothing else changed (`git diff` of `expected/`).

## 3. Documentation

- [x] 3.1 `python/modama-formats-common/README.md` ("never the text itself" gone; the paragraph "The file's text"); `python/crawler/README.md` (the record's descriptions); `formats/TEMPLATE.md` (checklist); `BACKLOG.md` (the next steps). Verify: by reading.
- [x] 3.2 A decision-log row in `design/architecture.md`.

## 4. Checks and review

- [x] 4.1 The crawler's, `modama-formats-common`'s and `modama-formats-em`'s suites, also under `TZ=Europe/Berlin`; `uvx pre-commit run --all-files`. Verify: the commands' output in the hand-over.
- [x] 4.2 Before/after examples for @weber's review (synthetic, of the snapshots' shapes), through `records.build`. Verify: in the hand-over.
- [ ] 4.3 Review by an agent that did not write the code (main starts it), given the code and this change.
- [ ] 4.4 The search stack's end-to-end test (`./runtest.sh e2e`, main's OK for the image build).
- [ ] 4.5 @weber looks at the six files of 2026-11-13 again in `modama-chain browse` on staging, and the trace export (307).
