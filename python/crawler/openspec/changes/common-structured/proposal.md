# Proposal

## Why

The tree holds structured data files that today become single-file datasets without a description (October listing, `.claude/survey/listing-2026-10-15.tsv.gz`): `.xml` 21,610 (19,636 of them Quantum ESPRESSO's `eigenval.xml`; EPU's `FoilHole_*`, `GridSquare_*`, `Atlas_*`; `*.jpg_metadata.xml`), `.json` 1,384 (mostly conda package metadata; Lake Shore measurement logs; traces), `.csv` 1,274, `.yaml` 417 and `.yml` 2, `.cfg` 49, `.toml` 26, `.ini` 18; no `.tsv`, `.jsonl` or `.ndjson`. What these files say is findable only by their path. @weber's request of 2026-11-12 (the night's brief): format libraries for structured data in `modama-formats-common`, with the lessons of the EM formats (`formats/TEMPLATE.md`, checklist), the established readers, public test data, and nothing that could disrupt the crawl. Serves R21 (the common formats), R15 (extract from content), R30 (findable by what the data is), decisions 230 and 234 and the skip-list rule of 2026-11-12.

## Assumptions and leans (from the brief, taken in before the code)

- **Readers**: `json`, `tomllib`, `csv` (with `csv.Sniffer`) and `configparser` from the standard library; PyYAML with a `SafeLoader` (the C one where the wheel has libyaml) and never the full loader; defusedxml's `ElementTree` for XML, as the input is untrusted.
- **What the file says** goes into `original_metadata`, flat: JSON, YAML and TOML as dotted paths to values; XML by EMPAD's rules (`modama_formats_em.empad.entries`: `@name` for attributes, `[n]` from 1 only for repeated siblings, `#text`, `#tail`, a path met twice kept as `#2` with a warning); INI as `section.key`; CSV only the header row's names, never a data row.
- **Lists**: the same idea as XML's repeated siblings. A list of plain values is one value (the shared `textual` check then keeps it up to 16 items); a list that holds objects or lists numbers its items from 1, `a[1].b`, as XPath and EMPAD do. Lean, open for @weber: JSONPath (RFC 9535) counts from 0; one convention across the record seemed worth more.
- **Bounds, with evidence from the listing**: a file larger than 8 MiB is not read at all and the values say so. Of the files of these types, only 5 JSON (89 to 376 MB: traces, a package cache) and 3 XML (10.5 to 26 MB, Quantum ESPRESSO output) are larger; the next largest JSON is 5.7 MB, the largest CSV 4.4 MB, YAML 0.6 MB, INI/cfg/TOML under 30 kB. A streaming parser was not taken: the files above the bound are data dumps, whose first entries would be data, not description. `original_metadata` is cut after 1,000 entries, the crawler's own cut of a stored object (`extraction.MAX_ITEMS`), and the values say so; the walk over a document stops after a bound of values, so that a YAML alias bomb cannot hold a worker. A CSV's rows are counted in the first 8 MiB; beyond, the count is "at least".
- **Recognition by content where names lie**: a `.json` whose first character cannot start JSON, an `.xml` whose first character is not `<`, an `.ini` or `.cfg` whose first line that is not blank or a comment is not a `[section]` header get the type they have without their name rule (change `recognition-checks-content`), so the plain-text area or none describes them. YAML, TOML and CSV have no signature: any text can be one; a file that does not parse fails its extraction, which the crawl reports.
- **Types**: the core's `application/json`, `application/yaml`, `application/toml`, `text/csv` and `application/xml`; for `.ini` and `.cfg`, which the vendored shared-mime-info lacks, Apache Tika's `text/x-ini` and `text/x-config` (Tika's `text/x-config` also has `*.conf` and `*.config`: not taken, not in this area's brief). XML subtypes (EMPAD's header, SVG, XHTML …) keep their own types; this area is the fallback for `application/xml` only. `.ipynb` is the `pydata` area's.
- **JSON Lines and YAML streams**: a file of several documents numbers them like a list, `[1].a`, and `mapped_metadata` says how many.
- **The summary line**: the only positive list, here a rule, as these formats have no known names: the first 8 entries in the file's order that are a text, a number or a boolean and not empty; text bare (surrounding whitespace removed for the line), a number or a boolean after its name (the last part of its path), no word of ours. XML starts with the root element's name and leaves out namespace declarations and `xsi:` attributes; CSV gives the header's column names. No placeholder value is known for these formats, so a 0 stays.

## Found while building (the spec has each)

- **The core cannot drop `application/json`** of a `.json` file that is not JSON: the vendored `application/schema+json` has the glob `*.json` too, so the type comes from a tie, not from one name rule, and `not_of_type` keeps it with a warning; the same for `.xml` once `modama-formats-em` (EMPAD's `*.xml` glob) is installed. The file is then not claimed. A change of the core's rule is for main to decide (hand-over, question).
- **`application/schema+json`** (JSON documents whose first key is `"$schema"`, typed by the core's magic; `*.schema.json` and `metaschema.json` are in the tree) gets the format `common/jsonschema`, read as JSON.
- **YAML tags of applications** (Docker Compose's `!override`, `!reset`): PyYAML's safe loader refuses the whole document; found on this repository's own `deploy/docker-compose.override.yml`. Such a value is kept as the plain value it tags, the tag left out. Not a bug of PyYAML (a safe loader of objects must refuse), so not in BACKLOG's "Sync with upstream".
- **Credentials**: configuration files hold passwords and tokens, and a record reaches more people than the file. A value whose path has `password`, `passwd`, `secret`, `token`, `api_key`, `private_key` or `credential` is on the skip list (`deploy/` of this repository showed the risk).
- **The walk's bound** is 10,000 values, not 100,000: a bomb's 100,000 took 0.85 s.
- **The summary line** writes a text's whitespace as single spaces (INI and YAML values over several lines, XML text around a value).

## What Changes

- New area `structured` of `modama-formats-common` (`src/modama_formats_common/structured/`): formats `common/json`, `common/jsonschema`, `common/yaml`, `common/toml`, `common/csv`, `common/xml`, `common/ini`, `common/cfg`, each a single-file dataset with an extractor; `structured.xml` with the `.ini` and `.cfg` types; fixtures (generated, and public samples from qeschema and toml-lang, MIT) and tests.
- New dependencies of `modama-formats-common`: PyYAML 6.0.3 and defusedxml 0.7.1 (already a dependency of `modama-formats-em`).

Behaviour towards the user: a harvester and a searcher see a description (summary line and the second description with the entries) on records of JSON, YAML, TOML, CSV, XML, INI and `.cfg` files, and their format's name as a subject; their datestamps move once. A `.json`, `.xml`, `.ini` or `.cfg` file whose content is not of that type is typed by its content, with the reason in its basis. A crawl reads these files' first bytes at recognition (64 bytes, 1 KiB for INI and `.cfg`), and each file up to 8 MiB once at extraction.

Out of scope: `.tsv`, `.jsonl`, `.ndjson`, `.conf` (none in the tree or not in this brief); JSON and XML subtypes the core knows (GeoJSON, JSON-LD, SVG …); reading what a schema means (EPU, Quantum ESPRESSO, conda): that is for formats of their own; text encodings other than UTF-8 (and Latin-1 for CSV and INI) and UTF-16 with a BOM where the reader detects it.

## Capabilities

### New Capabilities
- `formats/structured`: recognition and extraction of JSON, YAML, TOML, CSV, XML, INI and `.cfg` files.

### Modified Capabilities
None.

## Impact

- `python/modama-formats-common/`: the subpackage, one import and one `PARTS` entry in `__init__.py`, the README's table, `pyproject.toml`'s dependencies.
- `python/crawler/BACKLOG.md` if a reader needs a workaround.
- No migration; the extractor identity changes with the installation, as with every code change.
