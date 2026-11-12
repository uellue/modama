# Design

Measured on the DM and K2IS fixtures of `modama-formats-em` (DM/K2IS branch, `worktree-agent-a454075836693a33a`), in the VM, 2026-11-12. The chain's code read is the pinned submodules: metadata-crawlers 9c120f5, metadata-warehouse v1.10.0 (0b461ce), data-commons-search v0.10.2 (6c07bdc), with our patches in `prototypes/search-stack/patches/`.

## D1: sorted by name, not the file's order

A record is built from the dataset's extraction: on the first crawl from the extraction that ran, on later crawls from the stored one (`datasets.extracted`, JSONB), when the dataset is taken over or its extraction reused. JSONB does not keep the order of an object's keys (PostgreSQL's documentation, "JSON Types": "jsonb does not preserve white space, does not preserve the order of object keys"). Lines in the file's order would therefore change between the first and the second crawl of an unchanged file, and every such record would move its datestamp and be harvested and indexed again (records spec, "Unchanged crawl").

Sorted by name (code points) is the same on both paths. It is close to the file's order, which in the three fixtures with tags is nearly sorted but follows no rule we could name: `Acquisition.Device.Camera Number` comes before `Acquisition.Device.CCD.Pixel Size (um)` in the file (as if case did not count), `Microscope Info.STEM Camera Length` before `Microscope Info.Stage Position` (as if it did). Names that share a group keep together when sorted, as strings with a common prefix do.

Alternative, for @weber: the file's order, kept by storing `datasets.extracted` as `json` instead of `jsonb` (a migration; the stored extractions keep JSONB's order until extracted again, which the DM branch's new identity does anyway). Not done: a migration for an order that sorting nearly gives.

## D2: values as JSON text, numbers as the database gives them back

A string stands as it is (`K2-IS-0001`, `inf` for an infinity, as the DM part stores it); any other value as its JSON text: `300000.0`, `[1920, 1792]`, `-2.4043772802208405`, not rounded, no unit added.

JSONB keeps a number's decimal digits, not Python's type: `1.3166796483380824e+17` (Capture52's `Acquisition.Frame.Sequence.Acquisition Start Time (epoch)`, a DM time stamp) comes back from the database as the integer `131667964833808240`, and `-0.0` as `0.0`. Found by the test that crawls Capture52 twice: the second crawl changed the record in exactly these two lines. `as_stored` writes such numbers as the database gives them back, on both paths; the spot check, which compares with `==`, never saw the difference. The stored values are not changed.

## D3: a line longer than the storage's limit for a string is cut

Storage cuts every string of an extraction to 4,096 characters and every list to 1,000 entries (`extraction.MAX_STRING`, `MAX_ITEMS`). A list of 1,000 numbers is still about 20 kB of JSON text on one line; the formats' skip lists leave out large arrays before (TEMPLATE.md, e9fbf9a8), so this is a guard only: a value's text longer than 4,096 characters is cut to that length and ends in `…`. The longest line of the fixtures is 113 characters (Capture52), so nothing is cut there.

## D4: what the chain does with two descriptions

- **The harvester** (`dc_to_datacite.xsl`, `descriptions`): every non-empty `dc:description` becomes a `datacite:description descriptionType="Abstract"` of `normalize-space(.)`, so **the lines are joined with single spaces**: from DataCite on, the tags are one long line, `Acquisition.Device.Active Size (pixels): [1920, 1792] Acquisition.Device.CCD.Pixel Size (um): [10.0, 10.0] …`. Only the crawler's own record (and `modama-crawler records`) keeps one tag per line.
- **The warehouse** (schema and tables): `descriptions[].description` is a JSON-schema string without a length limit; the tables keep the XML and JSON as `XML`, `TEXT` and `JSONB` without limits. No limit is reached.
- **The index** (`opensearch_mapping.json`): `descriptions.description` is `text`, copied to `_all_fields` and `_description`; the search API's keyword leg queries `_description` (our patch `search-api/0001`), so a word of a tag's value is found. `_source` keeps the descriptions and, in `_additional_metadata`, the oai_dc record again.
- **The embedding** (`utils/embedding_utils.py`, `get_embedding_text_from_fields`): titles, subjects and **all** descriptions, joined with spaces; the stack embeds locally with `BAAI/bge-small-en-v1.5` (`EMBED_API_URL: ""`), whose tokenizer fastembed truncates at 512 tokens (`preprocessor_utils.py`, `enable_truncation`), CLS pooling. The summary comes before the tags, so it is never cut; the tags fill the rest of the 512 tokens. Measured with the warehouse's own functions and model (scripts outside the repository, commands in the hand-over): Capture52 97 tokens without tags, 5,106 with (512 embedded); the DM4 test image 84 and 1,265. Cosine between a record's vector without and with tags 0.90 to 0.95; three queries scored 0.785 → 0.800, 0.722 → 0.758, 0.593 → 0.588, 0.793 → 0.805; between different records the vectors grow more alike, 0.686 → 0.725, 0.763 → 0.792, 0.789 → 0.856. Embedding a 512-token text took 427 ms against 46 ms for the summary record (one thread, the VM).
- **The search API's hit** (`models.py`, `description`): the first description with `lang` `en`, else the first; ours have no language, so the summary. **Matchmaker's** cited entry (`CitedDatasets.tsx`, `SearchResultItem.tsx`; the browser's `upstream.cited_entry`) shows the hit's description: the summary, cut at 300 characters. The reranker (`mcp_server.py`, title and `hit.description`) and the chat model's context (`main.py`, `hit.description` cut at 800 characters) use the summary only. `/search` returns all descriptions in each hit's `_source`, so a K2IS hit carries about 19 kB more.

For @weber (not decided here): (a) leave it, the tags shape about 80 % of the embedded tokens of an EM record and make EM records a little more alike; (b) a patch to the warehouse that embeds titles, subjects and the first description only, which keeps today's vectors and cost, the tags staying in the keyword leg; (c) fewer tags in the record. The measurement is of four fixtures and four queries, not of a search's ranking.

## D5: size

Per record, the second description of the fixtures: Capture52 18,888 bytes (296 lines of 307 entries; 11 empty), the DM4 test image 3,704 (98 of 101), the DM3 one 3,287 (87 of 91), the RGBA DM4 none (no tags). In the crawler's `records` table (JSONB, TOAST with pglz, PostgreSQL 17): Capture52 600 → 5,289 bytes, DM4 565 → 1,931, DM3 554 → 1,787.

Staging (run 4: 156,779 DM4 and 19,457 DM3 datasets extracted; K2IS acquisitions were not a format of their own then): at the fixtures' 1.2 to 1.4 kB more per DM record, the `records` table grows by about 210 to 250 MB, the description text by about 580 to 650 MB before compression. The index keeps the text twice in `_source` (the descriptions and the oai_dc record) and three times in inverted fields; an estimate of 1 to 2 GB for the index, not measured: to be measured on staging (`_cat/indices`) after the first harvest. Indexing: at the measured ratio, about 9 times the embedding time for these 176,000 records, about 20 CPU hours more for a full indexing run, against F16's finding that harvest and indexing spend little of their time on the embedding.

The records change once, when the change reaches a deployment: with the DM branch's new extractor identity, which re-extracts and changes these records anyway, there is no second full run.

## D6: nested original metadata (block files)

The rule is generic: any format whose values hold `original_metadata`. It expects a flat mapping (TEMPLATE.md; the DM and K2IS parts). The block-file branch (`worktree-agent-a421eb4919d7c9317`, not merged here) stores `{"blockfile_header": {…}}`, one level deeper: its record would get one line, `blockfile_header: {"Acquisition_time": 42339.654974861114, "Beam_energy": 200000, …}`, the header's 40 fields as JSON text (its `Note`, with `\r\n` inside, escaped). Proposed: the block-file format stores its header flat (`blockfile_header.Beam_energy`), as the DM part does, rather than `records.py` flattening.

A string value with a line break would break the one line per tag; none of the fixtures has one (the block file's `Note` has, but sits in a nested group). Left as it is until a format stores one.
