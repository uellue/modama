# Spec Delta

## ADDED Requirements

### Requirement: Structured files are datasets of their type
A file of type `application/json`, `application/schema+json` (the core's type for a JSON document whose first key is `"$schema"`), `application/yaml`, `application/toml`, `text/csv`, `application/xml`, `text/x-ini` (`*.ini`) or `text/x-config` (`*.cfg`) SHALL be a single-file dataset of the format `common/json`, `common/jsonschema`, `common/yaml`, `common/toml`, `common/csv`, `common/xml`, `common/ini` or `common/cfg`, of that type, with an extractor. These formats run at priority 21: after the domain formats (image 50, EM 60 and up), which may claim these files first, and before every format that reacts to `text/plain` (the text area, 20), which claims a file these formats drop to `text/plain` (recognition-checks-content D3). Any other subtype the core or another collection defines (EMPAD's `application/x.empad+xml`, `image/svg+xml`, `application/x-ipynb+json` …) keeps its own type and is not claimed by these formats.

#### Scenario: Each type is its format's dataset
- **WHEN** the fixtures `conda_index`, `json_schema`, `yaml_config`, `toml_example`, `csv_tables`, `qe_pbtio3`, `ini_setup` and `setup_cfg` are crawled
- **THEN** each file is one dataset of its format and type, `stream.yml` included (`application/yaml`)

#### Scenario: Formats that drop types run before text
- **WHEN** the installed collections have a format that reacts to `text/plain`
- **THEN** its priority is lower than that of every format of this area that checks the first bytes

### Requirement: A name that lies falls back to the content's type
These formats SHALL check a file's first bytes where its format has a signature and, where they cannot start it, give the file the type it has without its name rule (change `recognition-checks-content`): JSON's first character after a byte order mark and whitespace is one of `{ [ " - 0-9 t f n` (64 bytes read); XML's is `<` (64 bytes); an INI or `.cfg` file's first line that is neither blank nor a comment (`#`, `;`) starts with `[` (1 KiB read). An empty JSON or XML file is not of the type; one with only whitespace in the bytes read but larger keeps it. An INI or `.cfg` file without such a line in its first KiB (empty, comments only) keeps its type. YAML, TOML and CSV have no signature: any text can be one. Known limit: the core drops only a type that one name rule gave (`Directory.not_of_type`); the vendored definitions give `*.json` to both `application/json` and `application/schema+json`, and with `modama-formats-em` installed `*.xml` to both `application/xml` and EMPAD's header. Such a tie resolves to `application/json` or `application/xml` without coming from the name alone, so the type is kept, the crawl warns, and the file is not claimed.

#### Scenario: A web page named .json
- **WHEN** `not_of_their_name/page.json` holds an HTML page
- **THEN** it is not a dataset of `common/json`, its type stays `application/json` (the tie above), and a warning says `common/json: page.json is not application/json (no JSON value first), but that type does not come from its name alone; type kept`

#### Scenario: An empty .json
- **WHEN** `not_of_their_name/empty.json` is empty
- **THEN** it is not a dataset of `common/json`, and a warning says why, as for the web page

#### Scenario: Text named .xml
- **WHEN** `not_of_their_name/notes.xml` is plain text, with `modama-formats-em` installed, as in every deployment
- **THEN** it is not a dataset of `common/xml`, its type stays `application/xml` (EMPAD's `*.xml` glob ties with it), and a warning says `common/xml: notes.xml is not application/xml (no < first), but that type does not come from its name alone; type kept`; with only this area's and the core's definitions it is a dataset of type `text/plain` whose basis says `common/xml: not application/xml, no < first` (BACKLOG, "A name type that a glob tie resolves to cannot be dropped")

#### Scenario: A .cfg that is not INI
- **WHEN** `not_of_their_name/turtle.cfg` has `key = value` lines without a section, as Python's `turtle.cfg`, and `keys.ini` a comment and such lines
- **THEN** each is a dataset of type `text/plain` and its basis says `common/cfg: not text/x-config, no [section] first` or `common/ini: not text/x-ini, no [section] first`

#### Scenario: An empty .cfg
- **WHEN** `setup_cfg/empty.cfg` is empty, as three `setup.cfg` in the tree are
- **THEN** it is a dataset of `common/cfg` with no entries

### Requirement: Every entry of a JSON, YAML or TOML document is kept
The extractor SHALL keep every value of the document in `original_metadata`, flat, under its path: keys joined with dots, as the file writes them; a list of plain values (texts, numbers, booleans, nulls) is one value; a list that holds an object or a list numbers its items from 1 (`a[2].b`), as XPath numbers siblings; an empty object or list and an empty text or null are kept as such (decision 161); a document that is a plain value or a list of plain values is kept under `$`. A path met twice (a key with a dot beside the same path by nesting) keeps both, the second as `<path>#2`, with a warning. No list of wanted entries (@weber, 2026-11-12).

#### Scenario: A JSON object as conda writes it
- **WHEN** `conda_index/index.json` is extracted
- **THEN** `original_metadata` has `name` `numpy`, `version` `1.26.4`, `build_number` 0 and `depends` as the list of its 4 texts, and `mapped_metadata` is `documents` 1

#### Scenario: Empty values are kept
- **WHEN** a JSON document is `{"a": {}, "b": [], "c": "", "d": null}`
- **THEN** `original_metadata` is `a` {}, `b` [], `c` empty text and `d` null

#### Scenario: Lists of objects are numbered from 1
- **WHEN** a JSON document is `{"runs": [{"id": 1}, {"id": 2, "tags": []}], "shape": [4, 4]}`
- **THEN** `original_metadata` is `runs[1].id` 1, `runs[2].id` 2, `runs[2].tags` [] and `shape` [4, 4]

#### Scenario: An entry nobody has seen before
- **WHEN** a JSON document has `{"made_up_group": {"made_up_value": "42 zz", "made_up_empty": ""}}`
- **THEN** `original_metadata` has `made_up_group.made_up_value` `42 zz` and `made_up_group.made_up_empty` as empty text

#### Scenario: A path met twice
- **WHEN** a JSON document is `{"a": {"b": 1}, "a.b": 2}`
- **THEN** `original_metadata` has `a.b` 1 and `a.b#2` 2, and a warning names `a.b`

#### Scenario: A plain value as the document
- **WHEN** a JSON document is `[1, 2, 3]`
- **THEN** `original_metadata` is `$` [1, 2, 3]

### Requirement: Several documents in one file are numbered
A YAML stream of several documents and a JSON Lines file named `.json` SHALL be kept as a list of documents: each document's paths start with `[n]`, from 1, and `mapped_metadata` has `documents`, their number. A file of one document has `documents` 1 and no `[1]`.

#### Scenario: A YAML stream
- **WHEN** `yaml_config/stream.yml` with three documents is extracted
- **THEN** `original_metadata` has `[1].kind` `run`, `[3].kind` `end`, and `mapped_metadata` `documents` 3

#### Scenario: JSON Lines named .json
- **WHEN** `json_lines/log.json` with 5 lines of JSON objects is extracted
- **THEN** it is a `common/json` dataset, `original_metadata` has `[1].event` `start` and `[5].event` `stop`, and `mapped_metadata` `documents` 5

### Requirement: Values as the file writes them
Values SHALL be kept as the file writes them. YAML (one loader for the package, `modama_formats_common.yamldoc`, which the text area uses too): a plain value keeps its written text wherever the value YAML 1.1 reads prints differently (JSON's spelling): `10:30` (not 630), `1.10`, `012`, `0x1F`, `0.00001`, `NO` (not False), `~` and an empty value (as `~` and empty text); `12`, `1.5`, `true` and `null` stay a number, a boolean and null; a key is its text (`on:`, `yes:`, `null:`, `1.0:`); a timestamp is its text. JSON and TOML: a float is a number where Python prints it as written, else its text (`1.0E-3`, `0.00001`, `1e999`); JSON's `NaN`, `Infinity` and `-Infinity` are these words; TOML integers come as tomllib gives them (`0x1F` as 31: tomllib has no hook for them). A TOML date-time is ISO 8601 with its offset as written (`1979-05-27T07:32:00-08:00`), a TOML infinity `inf`. Nothing is converted to another time zone; the output is the same in any local time zone.

#### Scenario: YAML values as written
- **WHEN** a YAML document has `time: 10:30`, `version: 1.10`, `code: 012`, `country: NO`, `mask: 0x1F`, `small: 0.00001`, `tilde: ~`, `empty:`, `n: 12`, `x: 1.5`, `ok: true`, `nothing: null`
- **THEN** `original_metadata` has the texts `10:30`, `1.10`, `012`, `NO`, `0x1F`, `0.00001`, `~` and empty text, and 12, 1.5, true and null

#### Scenario: YAML keys as written
- **WHEN** a YAML document has the keys `on:`, `yes:`, `null:`, `~:`, `1.0:` and `2026-11-12:`
- **THEN** `original_metadata` has them as these texts (`on.push`, `yes`, `null`, `~`, `1.0`, `2026-11-12`)

#### Scenario: JSON numbers as written
- **WHEN** a JSON document is `{"a": 1.0E-3, "b": 0.00001, "c": 1.5, "d": 1.0, "e": 12}`, or a TOML document has `a = 1.0E-3`
- **THEN** `original_metadata` has `a` `1.0E-3` and `b` `0.00001` as text, `c` 1.5, `d` 1.0 and `e` 12 as numbers

#### Scenario: A TOML date-time with an offset
- **WHEN** `toml_example/example.toml` is extracted, under `TZ=UTC` and `TZ=Europe/Berlin`
- **THEN** `original_metadata` has `owner.dob` `1979-05-27T07:32:00-08:00` both times

#### Scenario: A YAML timestamp
- **WHEN** `yaml_config/config.yaml` has `started: 2026-11-12 21:04:05.500000+01:00`, as PyYAML wrote it, or a file has `started: 2026-11-12 21:04:05.5 +01:00`
- **THEN** `original_metadata` has `started` with that text

#### Scenario: A YAML tag of an application
- **WHEN** a YAML document has tags no YAML loader knows, as Docker Compose files have (`ports: !override ["8080:80"]`, `command: !reset null`, `image: !custom nginx`), which PyYAML's safe loader refuses as a whole
- **THEN** the extraction does not fail: each tagged value is kept as the plain text, list or mapping it tags (`services.web.ports` ["8080:80"], `services.web.command` `null`, `services.web.image` `nginx`), without the tag

#### Scenario: Not a number
- **WHEN** a JSON document is `{"a": NaN, "b": 1e999}`, or a YAML document `a: .inf` and `b: .NaN`
- **THEN** `original_metadata` has `a` `NaN` and `b` `1e999`, or `a` `.inf` and `b` `.NaN`

### Requirement: Every element and attribute of an XML document is kept
The XML extractor SHALL keep every attribute and text of the document in `original_metadata` by the rules of `formats/empad`, "Every element and attribute is kept" (paths below the root element, `@name` for attributes, `[n]` from 1 for repeated siblings only, `#text` and `#tail`, `#2` for a path met twice, the same skip list), with names as the file writes them: an element or attribute in a namespace with the prefix the file declares for it (`qes:espresso`, `@xsi:schemaLocation`), one in the default namespace without one. A namespace declaration is kept as an attribute of the element that declares it, `@xmlns` or `@xmlns:<prefix>`. `mapped_metadata` has the root element's name as written (`root`) and its namespace (`namespace`), if any. Comments, processing instructions and the document type declaration are skipped; a document that declares entities is refused by defusedxml, and its extraction fails.

#### Scenario: A namespaced document
- **WHEN** `qe_pbtio3/PbTiO3_scf.xml` is extracted
- **THEN** `original_metadata` has `@xmlns:qes` `http://www.quantum-espresso.org/ns/qes/qes-1.0`, `input.control_variables.title` `PBTiO3_scf`, `input.atomic_species.@ntyp` `3` and `input.atomic_species.species[2].@name` `Ti`, and `mapped_metadata` has `root` `qes:espresso` and `namespace` `http://www.quantum-espresso.org/ns/qes/qes-1.0`

#### Scenario: A default namespace and a prefixed attribute
- **WHEN** a document is `<MicroscopeImage xmlns="urn:a" xmlns:i="urn:i"><x i:type="b">1</x></MicroscopeImage>`
- **THEN** `original_metadata` is `@xmlns` `urn:a`, `@xmlns:i` `urn:i`, `x.@i:type` `b` and `x` `1`

#### Scenario: An XML element nobody has seen before
- **WHEN** a document has `<made_up_group made_up_attribute="a"><made_up_value>42 zz</made_up_value><made_up_empty/></made_up_group>` below its root
- **THEN** `original_metadata` has `made_up_group.@made_up_attribute` `a`, `made_up_group.made_up_value` `42 zz` and `made_up_group.made_up_empty` as empty text

### Requirement: A CSV file is described by its header, never its data
The CSV extractor SHALL give the dialect `csv.Sniffer` finds in the first 64 KiB (`delimiter`, among `,`, `;`, tab and `|`; none where it finds none, and then the file is read as comma-separated), whether `csv.Sniffer` sees a header row (`header`), the number of fields of the first row (`columns`), the number of rows after the header (`rows`; `rows_at_least` where the file is larger than 8 MiB and only its first 8 MiB were counted) and the text encoding (`encoding`: UTF-8, else Latin-1) in `mapped_metadata`; and, where there is a header row, its names as found in `original_metadata` as `column[n]` (`column` alone for a single column). No data row goes into the values or the description.

#### Scenario: A semicolon-separated file with a header
- **WHEN** `csv_tables/temperature.csv`, Latin-1, `;`-separated, with the header `Zeit;Temperatur (°C);Strom (A)` and 20 rows, is extracted
- **THEN** `original_metadata` is `column[1]` `Zeit`, `column[2]` `Temperatur (°C)`, `column[3]` `Strom (A)`; `mapped_metadata` has `delimiter` `;`, `header` true, `columns` 3, `rows` 20, `encoding` `latin-1`; the description has no value of a data row

#### Scenario: Numbers without a header
- **WHEN** `csv_tables/numbers.csv` has 50 rows of 4 numbers, comma-separated
- **THEN** `original_metadata` is empty, `mapped_metadata` has `header` false, `columns` 4, `rows` 50

#### Scenario: A CSV file larger than the bound
- **WHEN** a CSV file is larger than 8 MiB
- **THEN** at most 8 MiB of it are read and `mapped_metadata` has `rows_at_least` instead of `rows`

### Requirement: Every key of an INI or .cfg file is kept
The INI extractor SHALL keep every key of every section in `original_metadata` as `section.key`, both as the file writes them (case kept, no interpolation of `%(…)s`, a value over several lines as one text with its line breaks, a key without `=` as null), a section without keys as an empty object, and the `[DEFAULT]` section as any other section, without adding its keys to the others. A key that appears twice in a section keeps the last value, as `configparser` reads it; a section that appears twice is one section. `mapped_metadata` has `encoding` (UTF-8, else Latin-1).

#### Scenario: Sections and keys as found
- **WHEN** `ini_setup/setup.ini` is extracted
- **THEN** `original_metadata` has `Laser.Wavelength_nm` `532`, `Laser.Comment` `%(not interpolated)s`, `Stage.Axes` `X Y Z`, `Stage.Limits` `-1.5` and `1.5` on two lines, `DEFAULT.Operator` `ER-C` and the empty section `Spare` as {}

### Requirement: Bounded reading
An extractor of these formats SHALL NOT read a file larger than 8 MiB (the size from the open file's `fstat`); the dataset then has `mapped_metadata` `not_read_larger_than_bytes` 8388608 and nothing else, and the summary line is empty. A CSV file is read up to 8 MiB (requirement above). `original_metadata` holds at most 1,000 entries, the first in the file's order; where there were more, `mapped_metadata` has `cut_at_entries` 1000. The walk over a document stops after 10,000 values, kept or skipped, with the same `cut_at_entries` (the number kept).

#### Scenario: A JSON file over the bound
- **WHEN** a JSON file of 9 MiB is extracted
- **THEN** no byte of it is read and `mapped_metadata` is `not_read_larger_than_bytes` 8388608

#### Scenario: More entries than the bound
- **WHEN** a JSON document has 1,500 objects in a list
- **THEN** `original_metadata` has the first 1,000 entries and `mapped_metadata` `cut_at_entries` 1000

#### Scenario: A YAML alias bomb
- **WHEN** a YAML document nests aliases to 9 levels of 10 lists each (10⁹ values), of short texts or of texts too long to keep
- **THEN** the extraction ends within a second with `cut_at_entries` 1000, or 0

#### Scenario: A YAML merge-key bomb
- **WHEN** a YAML document nests merge keys (`<<: [*l0, *l0, …]`) to 9 levels of 10 each (10⁹ pairs)
- **THEN** the extraction fails within a second with `merge keys give more than 10000 pairs` (a mapping's pairs after merging are bounded at 10,000), and a merge as YAML files use it (`d: {<<: *b, y: 2}`) is kept

### Requirement: The summary line
The description SHALL start with the first 8 entries of `original_metadata`, in the file's order, that are a text, a number or a boolean and not empty, a phrase repeated once: text bare, its whitespace (line breaks too) as single spaces, so that the line stays one line; a number or a boolean (also a text that is one, as XML and INI write them: `0.1E-03`, `false`) after its name, the last part of its path without `@` and `[n]`, as JSON writes it (`true`). No word or unit of ours; a 0 stays, as these formats know no placeholder. XML: the root element's name first, then the entries but namespace declarations and attributes in the XML Schema instance namespace (`xsi:`). CSV: its entries are the header's column names.

#### Scenario: The summary line of a JSON document
- **WHEN** `conda_index/index.json` is crawled
- **THEN** its description starts with `x86_64, py312h0d1d6f8_0, build_number 0, BSD-3-Clause, numpy, linux, linux-64, timestamp 1707225498123; `

#### Scenario: The summary line of an XML document
- **WHEN** `qe_pbtio3/PbTiO3_scf.xml` is crawled
- **THEN** its description starts with `qes:espresso, PBTiO3_scf, scf, from_scratch, pwscf, /scratch/pdelugas/espresso-xsd/pseudo/, /scratch/pdelugas/espresso-xsd/tempdir/, stress false, forces false; `

#### Scenario: The summary line of a CSV file
- **WHEN** `csv_tables/temperature.csv` is crawled
- **THEN** its description starts with `Zeit, Temperatur (°C), Strom (A); `

### Requirement: What is left out
The skip list of these formats SHALL be, and only be: a value not suitable for text (`modama_crawler.formats.values.textual`: a text over 1,000 characters or with control characters, a list of more than 16 values, bytes such as YAML's `!!binary`); a value that may be a credential, by the shared check `modama_crawler.formats.values.credential(path, value)`, best effort: a path with `password`, `passwd`, `pwd`, `passphrase`, `secret`, `token`, `api_key`, `private_key`, `credential`, `authorization` or `auth` (not `author`), in any case; a text (or a text in a list) with such a word followed by `=` or `:` and a value, a command line option with such a word or `pass` and a value, a URL with a password, or an HTTP authorization's `Basic`/`Bearer` token; as configuration files hold credentials and a record is seen by more people than the file. Such values are counted in `mapped_metadata` as `credentials_left_out` and never enter the summary line; for XML the parts `formats/empad` skips (whitespace around elements, the empty text of an element whose attributes or children carry its content) and comments, processing instructions and the document type declaration; entries after the bounds above; the tag of a YAML value of an application's tag. No user-interface setting is known for these generic formats.

#### Scenario: A value whose name says it is secret
- **WHEN** a JSON document has `db.user`, `db.Password`, `db.db_passwd`, `api_token`, `client_secret`, `apiKey`, `private-key` and `credentials.id`, or an INI file `[db]` with `password` and `host`
- **THEN** `original_metadata` is `db.user` alone, or `db.host` alone, and `mapped_metadata` has `credentials_left_out` 7, or 1

#### Scenario: A credential in a value
- **WHEN** a Compose file has `environment: [POSTGRES_PASSWORD=hunter2, POSTGRES_USER=u]`, `command: --requirepass hunter2`, `url: postgres://admin:hunter2@db/x`, `auth: Basic aHVudGVyMg==` and `image: redis`
- **THEN** `original_metadata` is `services.db.image` `redis` alone, `credentials_left_out` is 4, and `hunter2` is nowhere in the description

#### Scenario: A long text and a long list
- **WHEN** a JSON document has a text of 1,001 characters and a list of 17 numbers next to `{"kept": 1}`
- **THEN** `original_metadata` is `kept` 1
