# Proposal: the file's text in the record (`text-as-written`)

## In short

Text and structured files say most about themselves in their own words: a note, a parameter file, a training's configuration. Today their record carries what the format picked out of them: for plain text only the encoding and the line count (`ascii, lines 9`), for JSON and YAML every value as a sorted `name: value` line. With this change the record's second `dc:description` is **the file's text as written**, up to 4,096 characters; the summary line stays the first description. A longer file shows a shortened text with visible markers: a JSON or YAML document keeps every key and shortens long lists and strings in place (design D1, option B), any other text shows its first and last lines (option C). A JSON, YAML, TOML or INI file that does not parse is shown as plain text, its parse error noted, instead of failing its extraction. A file too large to read whole (the 140 MB trace export) shows its first and last lines, from at most 80 KiB read.

Example, a note `info.txt` of four lines in a session folder (synthetic, of the shape of the snapshot):

- today: the record's descriptions are `ascii, lines 4; Plain text document, 1 file, 144 B, in …/` and nothing else;
- with this change: the same first description, and a second one with the four lines as the user wrote them (`run 1: tilt series, 1 degree steps` …).

## Why

@weber's remarks in `modama-chain browse` on 2026-11-13 (snapshots in `/.claude/field-tests/browse/`, 07:52 to 08:04):

- a simulation's parameter file (`.json`, 1.7 kB): "To be honest, we can also just return the JSON document verbatim. Unless it is super large or contains stuff like base64 strings, it pretty much speaks for itself. Let's think about ways that handle such documents well! Just truncating may miss the interesting bits and produces invalid JSON, but parsing a huge file may be expensive."
- a `stem.json` whose extraction failed (`Expecting ',' delimiter: line 14 column 5`): "I guess we should fall back to plain text format if it is really invalid? Or is it a reader issue?" Main checked the file (1,263 bytes, CRLF): a comma is missing between two members, so it is invalid JSON, not a reader issue; a JSON5 reader would refuse it too.
- a trace export `long-log-….json` of 140 MB, not read (over 8 MiB): "aaah here we have an actual large file. Let's work on that, keep this as an example!"
- two YAML files (a training's `hparams.yaml`, a `config.yaml`): "Same like JSON, the file stands for itself".
- three `.txt` notes: "I think .txt we can just reproduce verbatim up to a size limit?"; "reproduce text verbatim"; a folder's `info.txt`: "notes by the user, so treat as separate file. Makes sense to reproduce verbatim!"
- a VS Code `settings.json`: "Perfect!" (it keeps its summary line, and gains its text, 170 B).

I read the six files as examples of a rule, "a text file stands for itself: show it as written, within a size limit, and handle large and invalid ones well", not as the whole ask (standing rule on named cases). The research the remark on `20200821_92978_info.txt` asks for (whether `_info.txt`, `_movie.mrc` and `_processing.log` are one cryo-EM dataset) is a separate request, not part of this change.

Serves R30 ("not finding something although the file tree and file contents held enough information to match the query"), R15 (extract from content), decision 230 (represent what is in the file without editorializing), decision 234 (the second description), the skip-list rule of 2026-11-12 (values not suitable for text, credentials).

## Assumptions and leans (accepted by @weber on 2026-11-13: 299 "Sounds good to me!", 303 N "Ok!", 304 "Yes, shorten in place", 307 "Let's go with that and review with examples"; 306: the wording settles in the glossary pull request after the demo; the questions are in design.md, Q1 to Q14)

- **L1 Which formats** (Q1): the text area's `common/text`, `common/log`, `common/readme`, `common/markdown`, `common/rst`, `common/tex`, `common/bibtex`, and the structured area's `common/json`, `common/jsonschema`, `common/yaml`, `common/toml`, `common/ini`, `common/cfg`. Not HTML, XML and CSV: their text is mostly markup or data rows; they keep what they show today.
- **L2 Only the text** (Q2): where a dataset has the text, the record's second description is the text, not the tag lines; `original_metadata` stays in the values (summary line, `browse`, later use). Both would put the same content into the record twice and fill the embedding's 512 tokens with it twice (design D2).
- **L3 N = 4,096 characters** (Q3), the storage's limit of one string (`extraction.MAX_STRING`): the text is one string in the values, `values["text"]`, and no limit of the crawler changes. All six of @weber's files but the trace fit whole (170 B to 3.3 kB); in the October listing 39 % of these formats' files are at most 4 kB, 65 % without 4,000 numeric `*_triplets.txt` tables (design D3).
- **L4 Longer than N** (Q4): a JSON, YAML or TOML document that parses is shortened in place (option B): every key kept, a list shortened to its first items with `"… (5,984 more items)"`, a value not suitable for text (the shared `values.textual` check: over 1,000 characters, control characters) replaced by `"… (20,000 characters left out)"` (option D comes with B), in steps until it fits, as `reprlib`'s limits do; what still does not fit is shown as head and tail. Any other text: its first and last lines, about 2,000 characters each, with a line `… 123,456 bytes left out …` between them (option C).
- **L5 B renders JSON** (Q5, Q6): compact, one line per document as `jq -c` prints it (with a space after `,` and `:`), for JSON, YAML and TOML alike (one renderer); a YAML file's comments are then not shown. Only a document longer than N, or one with a credential (L8), is rendered; everything else is shown as written.
- **L6 Invalid documents** (Q7): a JSON, YAML, TOML, INI or `.cfg` file that its reader refuses is shown as plain text (L4's rule C), with the reader's message in `mapped_metadata` as `parse error`; its summary line is the text area's (`ascii, lines 13`); the extraction does not fail, so it is not run again on every crawl (decision 185). XML keeps failing (defusedxml's refusal of entities is a safety rule).
- **L7 Large files** (Q8, Q9): a structured file over the 8 MiB read bound is not parsed, as today; its first 64 KiB and last 16 KiB are read (two reads, never the whole file) and shown by rule C. JSON Lines are recognised from the head: at least two complete lines, each a JSON object or array on its own. A text file over the text area's head (1 MiB) gets its last 16 KiB read too. The trace export: 81,920 bytes read in 6 ms, against 0.9 s and 357 MiB to parse it whole (design D5). A format of its own for trace exports is a next step (Q9).
- **L8 Credentials, best effort** (Q12): a structured document in which the shared check `values.credential` found a value is rendered by B with that value replaced by `"… (left out: may be a credential)"`, never shown as written; in any other text a line the check flags is replaced by `… (a line left out: may be a credential)`. A record reaches more people than the file (review of `common-structured`).
- **L9 Encoding and line ends** (Q11): the text decoded as the text area decides today (BOM, ASCII, UTF-8, else Windows-1252; HTML not affected), for the structured files too (while applying: their readers keep UTF-8, else Latin-1; the text area's rule also reads a UTF-16 file with a BOM, and Windows-1252 differs from Latin-1 only in 0x80 to 0x9F); line ends as line feeds, as Python reads text files. A file typed by its content gets no tail read (while applying: the 64 KiB bound of such files, `common-text` D2, stays).
- **L10 Files typed by their content** (Q10) get the text like any other text file, under the same N.

## What Changes

- Records (`records.py`): a dataset whose values hold `text` gets it as its second `dc:description`, in place of the tag lines (change `tags-in-the-record`); otherwise nothing changes.
- A shared module of `modama-formats-common` for the text as shown: the head-and-tail rule C, the markers, the line-wise credential check.
- Text area: `values["text"]` for the formats of L1; the tail read for a file larger than the head.
- Structured area: `values["text"]`; the shortened rendering B; the fallback to plain text for a document that does not parse (a YAML merge-key bomb too, which failed its extraction before); head and tail of a file over 8 MiB, JSON Lines from the head; `mapped_metadata.not_read_larger_than_bytes` becomes `not_parsed_larger_than_bytes`, as the head and tail are now read.
- No new dependency (ijson, measured in design D5, is not taken; Q8).

Behaviour towards the user: the record of every plain text, log, README, Markdown, reStructuredText, LaTeX, BibTeX, JSON, YAML, TOML, INI and `.cfg` file carries the file's text as its second `dc:description` (as written up to 4,096 characters, else shortened with visible markers), in place of the sorted `name: value` lines that JSON, YAML, TOML, INI and Markdown front matter carried; the summary line stays first, so Matchmaker's cited entry, the search API's hit, the reranker and the chat model's context are unchanged (they use the first description only, `tags-in-the-record` D4). The text reaches DataCite (lines joined by spaces there), the warehouse, the keyword search and the embedding text, of which the first 512 tokens count. A JSON, YAML, TOML, INI or `.cfg` file that does not parse gets a description instead of a failed extraction. A file over 8 MiB gets its first and last lines in its record. Every record of these formats changes once, so the next harvest and indexing are a full run for them. A crawl reads at most 16 KiB more of a text file larger than 1 MiB, and 80 KiB of a structured file over 8 MiB, which it did not read before.

## Out of scope

- HTML, XML and CSV text (Q1); notebooks and Python scripts (area `pydata`); grouping `_info.txt` with its `.mrc` and `.log` (separate request).
- A format for Jaeger or OpenTelemetry trace exports (Q9); a streaming parser; parsing files over 8 MiB.
- A lenient JSON reader (comments, trailing commas, JSON5): no file in the snapshots needs one (Q14).
- A rule that leaves out numeric tables (Q10); the warehouse's embedding text (`tags-in-the-record` D4, for @weber).

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `records`: the file's text as the second description.
- `formats/text`: the text as written (from the unarchived change `common-text`).
- `formats/structured`: the text as written, the shortened rendering, invalid documents, large files (from the unarchived change `common-structured`).

## Impact

- `python/crawler/src/modama_crawler/records.py`, the records spec; `python/modama-formats-common/src/modama_formats_common/` (`text/`, `structured/`, one shared module); their tests, fixtures and recorded expected results (every fixture of these formats gains `text`); the package's README rows ("never the text itself" goes); the crawler's README (the record's descriptions), `formats/TEMPLATE.md` (checklist: a format may give `text`), `BACKLOG.md`; a decision-log row once @weber agrees.
- Order of archiving: `common-text`, `common-structured` and `tags-in-the-record` before this change, whose deltas modify their requirements.
- Size and cost (design D3): in the October listing about 10,000 files of these formats, at most 28.7 MB of text at 4,096 characters each. Each such record's embedding text grows from about 50 to 100 tokens to up to 512, about 0.4 s more per record on one CPU (`tags-in-the-record` D5), about one CPU hour for those 10,000.
