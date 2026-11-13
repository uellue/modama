# Tasks

Not to start before @weber has answered the questions (design.md, Q1 to Q14) or accepted the leans; then an independent review of this proposal, then apply (`AGENTS.md`, OpenSpec). Archive `common-text`, `common-structured` and `tags-in-the-record` first: this change's deltas modify their requirements (`openspec validate` says so as INFO).

## 1. Tests first (they fail before the code)

- [ ] 1.1 Fixtures, generated in the areas' `generate.py`, synthetic, of the snapshots' shapes (no user's content): `info.txt` (four lines of notes), `notes_secret.txt` (the credential scenario), a note of 166 lines of 60 characters, one line of 100,000 characters, `stem-shape.json` (13 lines, a comma missing), a YAML that does not parse, `sim.json` (115,512 characters: a list of 6,000 numbers, a base64 string of 20,000 characters), a YAML of about 5,000 characters with a list of 500 numbers and a comment, a YAML with comments, a Compose-shaped YAML with a password, an INI with a password, a trace export of 2 MiB (20,000 spans), a pretty-printed JSON of 9 MiB, a JSON Lines file of 9 MiB; the large ones generated at test time, not stored. Provenance in `fixtures.toml`. Verify: `test_manifest`, `test_coverage`.
- [ ] 1.2 One test per scenario of the deltas: `text/tests/test_extract.py` (text as written, HTML and binary, head and tail, the tail read, credentials, the line count's bytes read counted with `/proc/self/io` as today), `structured/tests/test_extract.py` (text as written, the rendering and its steps, credentials, invalid documents, the file over the bound with its bytes read counted, JSON Lines from the head), `python/crawler/tests/test_records.py` (the text as the second description, the same record from a stored extraction). Verify: they fail on `crawler` before 2.x, for the reason the scenario names.

## 2. Code

- [ ] 2.1 `records.py`: the second description is `values["text"]` where it is a non-empty string, else the tag lines. Verify: the records tests of 1.2; the crawler suite.
- [ ] 2.2 A shared module of `modama-formats-common` (one home for the text as shown): head and tail (rule C) with the marker, the line-wise credential check with its marker, `TEXT` = `modama_crawler.extraction.MAX_STRING`. Verify: its unit tests, the scenarios "Head and tail of a long text" and "A credential is left out of the text".
- [ ] 2.3 Text area: `values["text"]` for the seven formats, not HTML; the tail read (16 KiB) of a file larger than the head; the Markdown front matter's credential rule. Verify: the text scenarios.
- [ ] 2.4 Structured area: the text as written; the rendering B and its steps; credentials through the rendering (JSON, YAML, TOML) or line by line (INI, `.cfg`); a document that does not parse as text, the YAML merge-key bound included; a file over 8 MiB: head and tail, `not_parsed_larger_than_bytes` (was `not_read_larger_than_bytes`), JSON Lines from the head. Verify: the structured scenarios.
- [ ] 2.5 Recorded expected results of every fixture of both areas re-recorded (`text` added, `parse error` where an extraction failed before); the diff read and listed in the hand-over. Verify: `pytest src` of `modama-formats-common`, also with `TZ=Europe/Berlin`.

## 3. Documentation

- [ ] 3.1 `python/modama-formats-common/README.md`: the rows of the text and structured formats ("never the text itself" goes; the text, its limit and markers); `python/crawler/README.md` where it describes the record's descriptions; `formats/TEMPLATE.md` checklist: a format may give `values["text"]`, which replaces the tag lines in the record; `BACKLOG.md`: the next steps (Q9's trace format; Q1's HTML, XML, CSV if deferred). Verify: by reading.
- [ ] 3.2 A decision-log row in `design/architecture.md` with @weber's answers. Verify: by reading.

## 4. Checks and review

- [ ] 4.1 The crawler's suite and `modama-formats-common`'s in a venv of their own; `uvx ruff format --check --diff` and `uvx ruff check` from the repository root; skipped tests counted. Verify: the commands' output in the hand-over.
- [ ] 4.2 The records of the fixtures by eye in a real terminal (`modama-crawler records --verbose`, `tools/xterm-shots.py`): a note, `sim.json`, `stem-shape.json`, the trace. Verify: the screenshots.
- [ ] 4.3 Review by an agent that did not write the code (main starts it), given the code and this change; findings verified before they are acted on. Verify: the findings and fixes in the hand-over.
- [ ] 4.4 The search stack's end-to-end test (`./runtest.sh e2e`, main's OK for the image build): a text file's record carries its text through DataCite to the index. Verify: its output.
- [ ] 4.5 @weber looks at the six files of 2026-11-13 again in `modama-chain browse` on staging, and the trace export. Verify: his remarks.
