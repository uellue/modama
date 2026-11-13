## ADDED Requirements

### Requirement: The text of a structured file as written
For a dataset of `common/json`, `common/jsonschema`, `common/yaml`, `common/toml`, `common/ini` or `common/cfg`, the extractor SHALL put the file's text into `values["text"]` as written (decoded as the area decodes it, line ends as line feeds, no byte order mark) when it has at most 4,096 characters and the credential check left out no value. `common/csv` and `common/xml` SHALL NOT give a text. The summary line and `original_metadata` stay as they are.

#### Scenario: A simulation's parameter file
- **WHEN** a JSON file of 1.7 kB holds a simulation's parameters (`name`, `scheme`, `data_dim` [1, 128, 128], `scan` {`dims`, `step`, `units`}, `source` {`name`, `version`}), indented by 2
- **THEN** `values["text"]` is the file as written, and the record's second description is that text, without tag lines

#### Scenario: A YAML file with comments
- **WHEN** a YAML file holds `shared:`, `  project_dir: ./project   # where the model goes`, `  subtomo_size: 96`, `fit_model:` and `  learning_rate: 0.0004`
- **THEN** its text is these lines as written, the comment included

#### Scenario: A small settings file keeps its summary line
- **WHEN** `settings.json` holds `{"editor.tabSize": 4, "python.envManager": "conda"}`
- **THEN** its summary line and `original_metadata` are the same as before this change, and its text is the file as written

#### Scenario: No text of CSV and XML
- **WHEN** `csv_tables/temperature.csv` or `qe_pbtio3/PbTiO3_scf.xml` is extracted
- **THEN** its values hold no `text`

### Requirement: A long document shortened in place
A JSON, YAML or TOML document that parses and whose text has more than 4,096 characters SHALL be shown as its rendering: JSON, one line per document, `, ` and `: ` as separators, keys in the file's order, values as `original_metadata` keeps them, every key; each list of more than 16 items as its first 16 and `"… (N more items)"`; each value the shared check `values.textual` rejects as `"… (N characters left out)"`.

#### Scenario: A long array and a base64 string
- **WHEN** `sim.json` (115,512 characters) holds `name`, `scheme`, `intensities` (6,000 numbers), `thumbnail_png` (20,000 base64 characters) and `source` {`name` `SimTool`, `version` `1.2.0`}
- **THEN** its text is `{"name": "probe_run_001", "scheme": "scan with 4D camera", "intensities": [` its first 16 numbers `, "… (5,984 more items)"], "thumbnail_png": "… (20,000 characters left out)", "source": {"name": "SimTool", "version": "1.2.0"}}`

#### Scenario: A YAML file longer than the limit
- **WHEN** a YAML file of about 6,500 characters has 40 keys with short values and a comment each, and a key `positions` with a list of 1,000 numbers
- **THEN** its text is the JSON rendering of the 40 keys and values and `positions` with its first 16 numbers and `"… (984 more items)"`, without the comments

### Requirement: Shorter steps until it fits
Where the rendering is still longer than 4,096 characters, it SHALL be made again with lists of at most 3 items and texts of at most 200 characters (a longer text cut, `… (N more characters)` appended), then with 1 item and 80 characters; a rendering still too long SHALL be shown by the text area's rule "Head and tail of a long text", N then counting the characters of the rendering left out.

#### Scenario: A trace export
- **WHEN** a generated trace export of 2.7 MB, `{"data": [{"traceID": …, "spans": [2,000 spans, each with tags and logs], "processes": {…}}], "total": 0}`, is extracted
- **THEN** its text shows the first spans as the step that fits keeps them, then `"… (N more items)"` for the rest, and ends with `"total": 0}`, valid JSON of at most 4,096 characters

### Requirement: A credential in a structured document
A JSON, YAML or TOML document in which the shared check `values.credential` left out a value SHALL never be shown as written, whatever its length: it SHALL be shown as its rendering (requirement "A long document shortened in place"), each such value as `"… (left out: may be a credential)"`. An INI or `.cfg` file SHALL have each line the check flags replaced by `… (a line left out: may be a credential)`, its leading whitespace kept.

#### Scenario: A Compose file with a password
- **WHEN** a YAML file has `services.db.environment` [`POSTGRES_PASSWORD=hunter2`, `POSTGRES_USER=u`], `services.db.image` `postgres` and the comment `# test only`
- **THEN** its text is `{"services": {"db": {"environment": "… (left out: may be a credential)", "image": "postgres"}}}` and `hunter2` is nowhere in the record

#### Scenario: An INI file with a password
- **WHEN** `[db]` has `host = db.example` and `password = hunter2`
- **THEN** its text is `[db]`, `host = db.example` and `… (a line left out: may be a credential)`

### Requirement: A document that does not parse is shown as text
A JSON, YAML, TOML, INI or `.cfg` file that its reader refuses SHALL NOT fail its extraction: `original_metadata` is empty; `mapped_metadata` has `parse error`, the reader's message, and `encoding` and `lines` as the text area counts them; the summary line is the encoding and the line count; `values["text"]` is its text by the text area's rules (whole, or head and tail; lines that may hold a credential left out).

#### Scenario: A comma missing between two members
- **WHEN** `stem-shape.json` (13 lines, 263 bytes) closes `"camera_length" : { … }` on line 5 and starts `"detectors" : {` on line 6 without a comma between them
- **THEN** the extraction does not fail; `mapped_metadata` has `parse error` `Expecting ',' delimiter: line 6 column 5 (char 81)`, `encoding` `ascii` and `lines` 13; the summary line is `ascii, lines 13`; and its text is the file as written

#### Scenario: YAML that does not parse
- **WHEN** a YAML file holds `title: [unclosed`
- **THEN** the extraction does not fail, `mapped_metadata` has `parse error` with PyYAML's message, and its text is `title: [unclosed`

### Requirement: A file over the bound
Of a file larger than 8 MiB the extractor SHALL read the first 64 KiB and the last 16 KiB, without readahead, and parse nothing: `mapped_metadata` has `not_parsed_larger_than_bytes` 8388608, and `values["text"]` is its head and tail by the text area's rule, the tail's first, partial line dropped.

#### Scenario: A trace export of 9 MiB
- **WHEN** a pretty-printed JSON file of 9 MiB is extracted
- **THEN** the extractor read at most 65,536 + 16,384 bytes of it, `mapped_metadata` has `not_parsed_larger_than_bytes` 8388608, and its text is its first lines, a line `… N bytes left out …` and its last lines

### Requirement: JSON Lines recognised from the head
For a JSON file over the bound, when the head's complete lines (blank lines skipped, the last, cut one left out) are at least two and each is a JSON object or array on its own, `mapped_metadata` SHALL have `json lines` true and `documents at least`, their number, and the summary line SHALL be made from the first document's entries by the area's rule.

#### Scenario: A large JSON Lines log
- **WHEN** a file `events.json` of 9 MiB holds one JSON object per line, the first `{"event": "start", "program": "acquire", "version": "2.1"}`
- **THEN** `mapped_metadata` has `json lines` true and `documents at least` the number of complete lines in its first 64 KiB, and its summary line is `start, acquire, version 2.1` (a text that is a number after its name, the area's rule)

#### Scenario: A pretty-printed document is not JSON Lines
- **WHEN** a pretty-printed JSON array of numbers of 9 MiB is extracted, some of whose lines are numbers alone
- **THEN** its `mapped_metadata` has no `json lines`

## MODIFIED Requirements

### Requirement: Bounded reading
An extractor of these formats SHALL parse a file only up to 8 MiB (the size from the open file's `fstat`); of a larger one it reads its head and tail only (requirement "A file over the bound"). A CSV file is read up to 8 MiB. `original_metadata` holds at most 1,000 entries, the first in the file's order, with `cut_at_entries` 1000 where there were more; the walk over a document stops after 10,000 values, kept or skipped, with the same `cut_at_entries`.

#### Scenario: More entries than the bound
- **WHEN** a JSON document has 1,500 objects in a list
- **THEN** `original_metadata` has the first 1,000 entries and `mapped_metadata` `cut_at_entries` 1000

#### Scenario: A YAML alias bomb
- **WHEN** a YAML document nests aliases to 9 levels of 10 lists each (10⁹ values), of short texts or of texts too long to keep
- **THEN** the extraction ends within a second with `cut_at_entries` 1000, or 0

#### Scenario: A YAML merge-key bomb
- **WHEN** a YAML document nests merge keys (`<<: [*l0, *l0, …]`) to 9 levels of 10 each (10⁹ pairs)
- **THEN** the extraction ends within a second without failing, with `parse error` `merge keys give more than 10000 pairs` (a mapping's pairs after merging are bounded at 10,000) and the file's text, as for a document that does not parse; and a merge as YAML files use it (`d: {<<: *b, y: 2}`) is kept
