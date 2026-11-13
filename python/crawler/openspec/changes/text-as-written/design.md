# Design

Measured on 2026-11-13 in the VM, with throwaway scripts outside the repository (a venv in `/var/tmp/textasis/`, removed after the hand-over). The examples are synthetic files of the shapes of the snapshots in `/.claude/field-tests/browse/` (2026-11-13, 07:52 to 08:04); no value of a user's file is quoted. The trace export and `stem.json` were measured on the copies @weber made available in `/.claude/field-tests/samples/` (private data, deleted after this work); only their shape and counts are written down here.

## D1 What a text longer than N becomes: the options

For a file of at most N characters (L3: 4,096) every option gives the same: the file's text as written. They differ only beyond N, and in how they meet @weber's three concerns: "just truncating may miss the interesting bits", "produces invalid JSON", "parsing a huge file may be expensive".

The example, `sim.json`: a simulation's parameters, of the shape of the Dr. Probe file, with what @weber named: a long array and a base64 string. 115,512 characters, indented by 4 as Python's `json.dump(indent=4)` writes it:

```json
{
    "name": "probe_run_001",
    "scheme": "scan with 4D camera",
    "intensities": [
        0.0013,
        0.0085,
        … 6,000 numbers, one per line …
    ],
    "thumbnail_png": "iVBORw0KGgo… 20,000 base64 characters on one line",
    "source": {
        "name": "SimTool",
        "version": "1.2.0"
    }
}
```

**Today** (the tag lines of `tags-in-the-record`, sorted by name; the array and the base64 string are left out by the shared `values.textual` check):

```
name: probe_run_001
scheme: scan with 4D camera
source.name: SimTool
source.version: 1.2.0
```

**A: as written up to N, cut at a line boundary, a visible marker.** The first 4,072 characters: `name`, `scheme` and the first 260 numbers, one per line, then `… (111,467 more characters)`. `thumbnail_png` and `source` are not shown; the text is not valid JSON.
Strongest argument against: what comes after a long array or string is lost, the "interesting bits" @weber named; and a third of the record's text is numbers.

**B: shortened in place, every key kept, valid JSON** (as `reprlib` limits a representation, here with the shared check's limits: lists to 16 items, values not suitable for text as a marker with their size). 325 characters:

```json
{"name": "probe_run_001", "scheme": "scan with 4D camera", "intensities": [0.0013, 0.0085, 0.0076, 0.0026, 0.005, 0.0045, 0.0065, 0.0079, 0.0009, 0.0003, 0.0084, 0.0043, 0.0076, 0.0, 0.0045, 0.0072, "… (5,984 more items)"], "thumbnail_png": "… (20,000 characters left out)", "source": {"name": "SimTool", "version": "1.2.0"}}
```

Where the result is still longer than N, the next step keeps 3 items per list and texts of at most 200 characters, then 1 item and 80 characters (the levels `reprlib`'s `maxlist`, `maxstring` stand for); what does not fit even then is shown by C. Strongest argument against: it is not the file as written but our rendering of it: the file's layout, a YAML file's comments and the spelling of a number that Python prints otherwise are gone, and a marker string sits where the file has numbers (a reader that loads it gets `"… (5,984 more items)"` as an item). It needs the whole document parsed, which the 8 MiB bound allows today; and a rule of ours (the levels) decides what is shown.

**C: head and tail, at line boundaries.** The first 1,994 characters (`name`, `scheme`, the first 190 numbers), a line `… 113,441 bytes left out …`, and the last lines that start within the last 2,000 characters: here only the `source` block, since the base64 line starts before them. Strongest argument against: the middle is gone, keys included (`thumbnail_png` is not named), and the text is not valid JSON; nothing says how many items were left out. For a log it is what people look at first: how it started and how it ended.

**D: binary-looking values replaced by a marker with their length.** Applied to A, the base64 line becomes `"thumbnail_png": "… (20,000 characters left out)"`, but A's cut still falls inside the array, so `source` is still lost. Strongest argument against D on its own: no file in the snapshots has a base64 value, and telling base64 from a long identifier or a path by its characters is a guess; the shared check already says "not suitable for text" by size and control characters, which is what B uses.

**Combinations, the lean (L4):** B for a JSON, YAML or TOML document that parses (D comes with it, as the shared check's markers), C for everything else and for what B cannot fit. All six of @weber's files but the trace fit in N and are shown as written.

Prior art (checked 2026-11-13):

| Tool | How it shows large structured data or text | Source |
|---|---|---|
| Python `reprlib.Repr` | "size limits for different object types are added to avoid the generation of representations which are excessively long": `maxlist` 6, `maxdict` 4, `maxstring` 30, `maxlevel` 6 by default; `fillvalue` `...` for recursion; an `indent` since 3.12. The model for B's levels | [docs.python.org, reprlib](https://docs.python.org/3/library/reprlib.html) |
| jq 1.8 | `limit(n; expr)` "extracts up to `n` outputs"; `first(expr)`, `last(expr)`; `paths` "outputs the paths to all the elements"; `--stream` parses "in streaming fashion, outputting arrays of path and leaf values", "useful for processing very large inputs". No built-in shortening of a document in place | [jq manual 1.8](https://jqlang.org/manual/) |
| `python -m json.tool` | pretty-prints and validates; options for indentation, `--compact`, `--sort-keys`, `--json-lines`; no option to shorten | [docs.python.org, json](https://docs.python.org/3/library/json.html) |
| Elasticsearch, ingest attachment processor (Tika) | `indexed_chars`: "The number of chars being used for extraction to prevent huge fields", default 100,000; A, at a far larger N | [Elastic docs, attachment processor](https://www.elastic.co/docs/reference/enrich-processor/attachment) |
| Apache Tika | `WriteOutContentHandler`'s write limit: the maximum number of characters, `-1` to disable; reaching it raises `WriteLimitReachedException` (A). Its default I could not confirm from the docs | [Tika 4.0.0 API](https://tika.apache.org/4.0.0/api/org/apache/tika/sax/WriteOutContentHandler.html) |
| GitLab job log | shows the last 500 KiB of a long log with a notice, "Showing last … KiB of log", and loads more on demand (the tail of C). From GitLab's issues, not its current documentation | [gitlab#338705](https://gitlab.com/gitlab-org/gitlab/-/issues/338705), [gitlab!73572](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/73572) |
| `head`, `tail` | the first or last lines of a file, the established look at a log (C) | GNU coreutils |

Not found: a documented size limit of GitHub's file view for github.com (only GitHub Enterprise Server pages for single file kinds); not used.

## D2 The text alone, not the text and the tag lines

The record's second description is the text where the format gives one, the tag lines otherwise (L2). For a document that fits N the text holds every key and value of the tag lines, in the file's order rather than sorted (`tags-in-the-record` D1 sorted them only because JSONB keeps no order; a string keeps it), with a YAML file's comments, and in the words the user wrote. Both would double what the chain stores and indexes, and the embedding, which reads titles, subjects and all descriptions up to 512 tokens (`tags-in-the-record` D4), would see the same content twice and the second copy not at all. What the first description reaches stays as it is: the search API's hit, Matchmaker's cited entry (cut at 300 characters), the reranker and the chat model's context (cut at 800) use the summary line only. So the text serves the keyword search, the embedding (its first part) and whoever reads the record (`modama-chain browse`, `records`, an OAI client).

Strongest argument against: for a document B shortened, a value the levels left out (the 4th item of a list) is in the tag lines but not in the text. The tag lines are bounded too (1,000 entries, lists of at most 16 values), and the values stay in the stored extraction.

The alternative, the text as the first description for plain text (where the summary line says only `ascii, lines 4`), would put the note into Matchmaker's entry and the chat's context; it changes what every hit shows and is not asked for (Q2).

## D3 N and the limits

- **The crawler's storage**: every string of an extraction is cut to 4,096 characters (`extraction.MAX_STRING`, `_storable`), every list to 1,000 entries. N = 4,096 lets the text be one string, `values["text"]`, with no change there. A larger N needs the text as a list of lines (1,000 × 4,096) or a larger `MAX_STRING` for every format.
- **Dublin Core and OAI-PMH** set no length for `dc:description`; the harvester's XSLT makes each description one `datacite:description` of `normalize-space(.)` (line breaks become spaces); the warehouse's schema and tables and the index's `text` fields have no limit that 4,096 characters reaches (`tags-in-the-record` D4).
- **The embedding** reads the first 512 tokens of titles, subjects and descriptions. With the path (about 30 tokens) and the summary (20 to 100) before it, about 350 to 450 tokens of the text count, about 1,000 to 2,000 characters of English prose, fewer of JSON. Beyond that the text serves the keyword search and readers only.
- **What fits**: @weber's six files are 170 B, 235 B, 270 B, 1.3 kB, 1.7 kB, 2.8 kB and 3.3 kB, and the 140 MB trace. In the October listing (a quarter of the tree), of the 9,977 files of these formats 3,867 (39 %) are at most 4 kB; 4,000 of the 7,287 `.txt` are numeric `*_triplets.txt` tables of 16 to 64 kB; without them 65 %. JSON 973 of 1,384, YAML 331 of 419, Markdown 159 of 194, BibTeX 174 of 189 are at most 4 kB.
- **Size**: at most 28.7 MB of text for those 9,977 files (98.9 MB at 16 KiB), against 1.2 to 1.4 GB of DM tag text on staging (`tags-in-the-record` D5).

Lean: N = 4,096 characters (Q3).

## D4 A document that does not parse

`stem.json` (1,263 bytes, CRLF): line 13 closes an object and line 14 starts the next member without the comma between them. Python's `json` says `Expecting ',' delimiter: line 14 column 5 (char 254)`; a JSON5 reader would refuse it too (main's check). It is a broken file, not a reader issue. Its shape, rebuilt (`stem-shape.json`, 13 lines, 263 bytes):

```json
{
    "camera_length" : {
        "value" : 115,
        "unit" : "mm"
    }
    "detectors" : {
        "HAADF" : {
            "type" : "annular",
            "plane" : "detector",
            "inner_angle" : { "value" : 60, "unit" : "mrad" }
        }
    }
}
```

Today: the extraction fails with `JSONDecodeError("Expecting ',' delimiter: line 6 column 5 (char 81)")`, the record has only the basic description, and the failure is tried again on every crawl (decision 185). With L6: summary line `ascii, lines 13`, `mapped_metadata` `parse error` `Expecting ',' delimiter: line 6 column 5 (char 81)`, and the second description is the text as written: it "reads perfectly as is".

How to tell a reader issue from a broken file: the message names line and column, and the text, now in the record, shows them. Python's `json` is strict where JSON is (comments, trailing commas, single quotes and unquoted names are refused; with comments the message is the same `Expecting ',' delimiter` or `Expecting value`) and lenient where JavaScript is (`NaN`, `Infinity`, repeated names, the last one kept: "This module does not comply with the RFC in a strict fashion", docs.python.org, json). A comment (`//`, `#`) or a trailing comma at the named place is JSONC or JSON5, which a lenient reader would take (a choice of reader, Q14); a missing or doubled delimiter is a broken file. PyYAML, `tomllib` and `configparser` name line and column likewise. The YAML loader's own bound (`merge keys give more than 10000 pairs`, `common-structured`) is treated as a refusal too: the bomb's text is small and harmless to show. XML is not changed: defusedxml's refusal of a document that declares entities is a safety rule (`common-structured`).

## D5 Large files: the 140 MB trace export

The file (140,170,201 bytes): a trace exported from the Jaeger UI ("Download JSON"), written through the OpenTelemetry SDK: one pretty-printed JSON object, `{"data": [{"traceID", "spans": [{…}, …], "processes": {…}, "warnings"}], "total", "limit", "offset", "errors"}`. 16,403 spans, 30 operation names, 23 processes, 83 distinct paths. Not JSON Lines: of the 1,515 complete lines in its first 64 KiB, none is a JSON value on its own.

| Option | Read | Time (VM, local disk, file in the page cache) | Memory | Shows |
|---|---|---|---|---|
| C: head 64 KiB, tail 16 KiB | 81,920 B | 6 ms | – | the first span's first 2,000 characters; the last processes and the closing keys; nothing about counts |
| C with head 1 MiB, tail 64 KiB | 1,114,112 B | 2 ms | – | the same (the text shown is 4,096 characters either way) |
| E1: `json.load` whole, then B | 140 MB | 0.9 to 1.05 s, B 0.00 s | 357 MiB peak | B at its last level (1 item per list, 80 characters) is 4,179 characters compact, 5,984 indented: the whole skeleton, `"… (16,402 more items)"` for the spans, every process; over N, so C cuts it once more |
| E2: ijson 3.6.0 (yajl2_c), first 1 MiB | 1 MiB | 0.02 s | 15 MiB | 317 spans, 17 of 30 operations ("at least") |
| E2: ijson, first 8 MiB | 8 MiB | 0.14 s | 16 MiB | 1,354 spans, 27 of 30 operations |
| E2: ijson, whole file | 140 MB | 1.85 s | 16 MiB | 16,403 spans, all 30 operations, the time span, all 83 paths |

On staging the file is on NFS: reading it whole costs its transfer as well (16 to 43 ms per round trip, decision log 2026-11-11), and every change of the extractor identity re-extracts it (decision of `extractor-identity`). The listing has 5 JSON files over 8 MiB (89 to 376 MB, "traces, a package cache"); E1 on the largest would need about 1 GB (2.5 times the file, as measured here), under the workers' 4 GiB.

- **C** (the lean, L7): bounded (80 KiB), no dependency, no parse; the same rule as for logs. Against: it shows two corners of the file and no counts.
- **E1**: whole-file parse with the standard library up to a larger bound (say 512 MiB), then B: the skeleton with counts. Against: reads the whole file on every re-extraction; memory grows with the file; "parsing a huge file may be expensive".
- **E2**: a streaming parser, ijson (BSD-3-Clause AND ISC, 3.6.0 current on PyPI on 2026-11-13; a new dependency), within a byte budget: constant memory, counts "at least" within the budget, or exact for 1.85 s per 140 MB. Against: a new dependency, and B would have to be built on its events (a second renderer).
- **F**: a format of its own for Jaeger trace exports, recognised from the head (`{"data": [{"traceID": …, "spans": [`), with a summary such as `trace <traceID>, spans 16403, operations 30, services …, from … to …`. It would need E1 or E2 for its counts. Against: Jaeger documents the UI's JSON as "Internal": "This JSON API is intentionally undocumented and subject to change" ([Jaeger 2.23, APIs](https://www.jaegertracing.io/docs/2.23/architecture/apis/)); OTLP JSON is the stable export. A next change, after a look at the listing's other large JSON files (Q9).

JSON Lines from the head (L7): the head's complete lines (the last, cut one left out), blank lines skipped; at least two, each a JSON object or array on its own (a pretty-printed document has lines such as `0,` or `3` that parse as numbers). Then `mapped_metadata` has `json lines` true and `documents at least` (the complete lines in the head), and the summary line comes from the first document's entries by the area's summary rule.

## D6 Credentials

A record reaches everyone who can search; the file only those who can read it (R18: the crawl reads what it can; per-user views are deferred). Today the structured formats leave a value the shared check `values.credential` flags out of `original_metadata` and count it; the text area shows no body. The text as written would carry such values, so:

- a JSON, YAML or TOML document in which the check flagged a value (by its path or its text) is never shown as written: it is rendered by B from the parsed document, the value replaced by `"… (left out: may be a credential)"`, whatever its length. The parsed document knows where the value is, also for a value on the line after its name (a YAML block scalar);
- an INI or `.cfg` file, an invalid document and any other text: a line in which the check finds a credential (`credential("", line)`: a name such as `password` followed by `=` or `:` and a value, an option such as `--requirepass x`, a URL with a password, `Basic …`) is replaced by `… (a line left out: may be a credential)`, its indentation kept. Best effort, as the check is: a value on the line after its name is not caught there (a Markdown front matter's block scalar); for Markdown, a front matter in which the check flagged a value is left out of the text as a whole, a line `… (front matter left out: it may hold a credential)` in its place.

## D7 Encoding, line ends, cutting

- The text is decoded as the area decides today: the text area by the bytes (BOM, ASCII, UTF-8, else Windows-1252; `common-text` D1); the structured area UTF-8, else Latin-1. A text that is not text (a NUL byte) has no `text`.
- Line ends become line feeds, as Python reads text files (`newline=None`): a CRLF file would otherwise carry `&#13;` in the XML of every line, and DataCite joins lines with spaces anyway. A BOM is not part of the text.
- C cuts at line breaks: the head's last complete line within its half, the tail's first line that starts within its half; a line longer than a half is cut at a character. The marker between them counts the bytes of the file not shown, computed from the file's size and the byte offsets of the cuts, so it is right also for the unread middle of a large file. The tail of a large file is read from `size − 16 KiB` and its first, partial line dropped, so that a UTF-8 sequence cut by the read is never decoded.
- Markers use `…` and thousands separators, as `records.py` cuts a long value with `…`: `… (111,467 more characters)` (B, a text shortened), `"… (5,984 more items)"`, `"… (20,000 characters left out)"`, `… 113,441 bytes left out …`, the credential markers of D6. No other word of ours enters the text.

## Questions to @weber, with leans

- **Q1** Formats: text for plain text, logs, READMEs, Markdown, reStructuredText, LaTeX, BibTeX, JSON, JSON Schema, YAML, TOML, INI and `.cfg`. HTML, XML and CSV too? Lean: not now. HTML and XML are mostly markup (21,610 XML files in the listing, 19,636 of them Quantum ESPRESSO's `eigenval.xml`, for formats of their own); CSV is data rows, which its spec keeps out ("never a data row").
- **Q2** Only the text in the record, the tag lines no longer (lean, D2); or both; or the text as the first description for plain text, in Matchmaker's entry.
- **Q3** N = 4,096 characters, the storage's limit of one string (lean, D3); or 16 KiB as a list of lines (98.9 MB instead of 28.7 MB for the listing's files).
- **Q4** Beyond N: B for parsed JSON, YAML and TOML, C for the rest (lean); or C everywhere (simpler, no renderer, keys in the middle lost); or the tag lines as today beyond N (no new code, sorted, all keys, no file order).
- **Q5** B's rendering: compact, one line per document, as `jq -c` with a space after `,` and `:` (lean: more of the document fits; DataCite joins lines anyway); or indented as `jq` prints by default (readable in `browse` and `records`; 5,984 against 4,179 characters for the trace's skeleton).
- **Q6** A YAML or TOML file beyond N rendered by B as JSON (lean: one renderer, every key kept; its comments are lost); or shown by C as its own text.
- **Q7** An invalid document: plain text with the text area's summary line (`ascii, lines 13`) and the parse error in `mapped_metadata` only (lean, no word of ours in the summary); or a summary phrase such as `(not valid JSON)`, as `(encrypted)` is one.
- **Q8** Files over 8 MiB: head and tail, 80 KiB read (lean, C); or the whole file parsed up to a larger bound and shortened by B (E1, 1 s and 357 MiB for 140 MB); or ijson within a byte budget (E2, a new dependency).
- **Q9** A format for Jaeger or OpenTelemetry trace exports (F), as a next change once the listing's other JSON files over 8 MiB are looked at? Lean: yes, then.
- **Q10** Files typed by their content (45,123 `.dat` and 33,251 names without a dot in the listing, those that look like text) and numeric tables (4,000 `*_triplets.txt`) get the text like any text (lean: one rule; their first 4,096 characters are numbers in the keyword index and the embedding); or a rule that leaves them out, from examples.
- **Q11** Line ends as line feeds (lean, D7); or as written.
- **Q12** Credentials (D6): structured documents through the parsed document, other text line by line, best effort (lean). The text of users' notes then reaches everyone who can search, as values do today (R18).
- **Q13** Wording: I call it "the file's text" (`values["text"]`). The glossary's **Description** (`/CONTEXT.md`) is a project's or session's `README.md`, whose text this change puts into its record; the record's `dc:description` is another thing. A glossary entry for "the file's text in the record"?
- **Q14** `stem.json` is broken (a missing comma), not a reader issue. Who writes such files (a script of the group, an instrument's software)? A lenient reader (JSON5) only if a file with comments or trailing commas turns up. Lean: no lenient reader now.
