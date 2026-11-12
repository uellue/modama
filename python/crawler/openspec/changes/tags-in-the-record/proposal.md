# Proposal

## Why

Since decision 230 the formats read through RosettaSciIO keep the file's own tags as `values["original_metadata"]`: flat, dotted names to values, every entry the file has minus a skip list per format (TEMPLATE.md, "Extracting metadata"). They are stored with the dataset, but the record carries only the summary line and the subjects (`records.py`), so nothing of the tags is searchable (BACKLOG, "DM and K2IS tags": "the search stack does not see them yet").

Decided by @weber, 2026-11-12, item 234: "yes, go with your lean (A)". (A): the record's `oai_dc` gets a second `dc:description` with the dataset's tags as `name: value` lines, as found in the file; the summary line stays the first `dc:description`. This also answers decision 231 (summary line or `name: value` as found) by showing both, so that @weber can compare them in `modama-chain browse`.

Leans of the brief, taken in as assumptions (design says where they were changed and why):

- one line per tag, `name: value`, in the file's order or the stored order, the choice said: **sorted by name** (D1: neither the file's nor JSONB's order survives a reused extraction);
- values as stored, no rounding, no units added, lists and arrays as their stored text (D2: as JSON text, numbers as the database gives them back);
- empty values (`[]`, `""`) left out;
- no list of wanted tags in `records.py` (@weber, 2026-11-12: "we don't keep a positive list, but a negative 'skip these' list"): every entry the format kept;
- a guard against a pathological value (the coordinator, 2026-11-12), with a limit that has evidence (D3: the storage's 4,096 characters per string);
- the size measured first, the effect on the embedding reported for @weber to decide (D4, D5).

## What Changes

- `records.py`: `tags(dataset)` makes the second description from `values["original_metadata"]` of any format that has it (DM3, DM4, K2IS, block file, Merlin, EMPAD, D6); `dc_metadata` appends it after the summary. `as_stored(value)` writes numbers as the database gives them back (D2); a string with line breaks and an object are written as JSON text, the object's keys sorted (D2, D6; the review of 2026-11-12).
- Records spec: a new requirement "The file's tags go into a second description" with its scenarios. The unarchived change `em-formats-and-extraction` said "one `dc:description`"; its delta now says the summary is the first.
- `README.md` (the record's description), `BACKLOG.md` (DM and K2IS tags), `design/architecture.md` (a decision-log row for 234 and D1).
- Search stack: the end-to-end tree gets the K2IS fixture Capture52; one test checks where its tags end up (index document, keyword leg, the hit's description), and the browser's live index document is compared with the stored one for it too.

Behaviour towards the user: the record of every DM3, DM4, K2IS, block file, Merlin and EMPAD dataset (the formats that store `original_metadata` since `crawler` 4cef5532) carries a second `dc:description` with its tags, one `name: value` per line, sorted by name; it reaches DataCite, the warehouse and the index, so the tags are found by the search's keyword leg and go into the embedding text. The summary stays first: the search API's hit, Matchmaker's cited entry, the reranker and the chat model's context show or use the first description only (D4). Harvesters see every extracted DM and K2IS record change once (about 176,000 on staging), so the next harvest and indexing after the upgrade are a full run for them (D5). `modama-crawler records` shows the second description.

Out of scope: a separator other than a line break (the harvester's XSLT joins the lines with spaces, D4); a change to the warehouse's embedding text (D4, for @weber); a cap on the number of lines (D5: no limit of the chain is reached); flattening nested `original_metadata` (D6: every format stores it flat); the summary line's future (231 stays answered by showing both).

Serves: decision 234 (and 231), decision 230 and the skip-list rule of 2026-11-12, R25 (Dublin Core from the file system and the files), the records spec's "The datestamp moves when the record changes".

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `records`: a second `dc:description` with the file's tags.

## Impact

- `python/crawler/`: `src/modama_crawler/records.py`, `tests/test_records.py`, `tests/test_cli.py`, `README.md`, `BACKLOG.md`, `design/architecture.md`, `openspec/changes/em-formats-and-extraction/specs/records/spec.md` (one word).
- `prototypes/search-stack/test_e2e.py`.
- No migration, no new dependency, no change of the stored values.
