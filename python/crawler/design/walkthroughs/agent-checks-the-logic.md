# Walk-through: a coding agent shows that the chain's logic is sound

Persona: a coding agent changing the crawler (deletions, series, scheduling) that must show, stage by stage, that every stage holds what it should, and on a failure find the first stage that diverged. Knows how to read code and run commands; knows nothing about this stack beyond the documents. Works inside the VM, with the e2e stack running.
Confidence: **measured, not simulated** (2026-11-04). Claude injected two faults into the running e2e stack; a fresh sub-agent, told only the symptom and pointed at the documents, diagnosed them read-only. Its report is summarised below; the full text is in the session transcript. Requirements: `../requirements-pipeline.md`.

## The experiment

Faults, both realistic:
1. **A datestamp before the harvest window,** as clock skew or the datestamp-window race would produce (BACKLOG, "Datestamp window"): a new file `notes/late-arrival.txt` was crawled, its record's datestamp set back one hour in the crawler database, then the harvest DAG ran. The crawler serves the record; the incremental harvest skips it.
2. **A lost index document:** the OpenSearch document of `notes/sample-list.csv` deleted directly. The warehouse's `records` row still says `opensearch_synced = t`.

Symptom given to the agent: "searching for the paths `/notes/late-arrival.txt` and `/notes/sample-list.csv` does not find these files". Allowed: reading documents and code, SELECTs, GETs, logs; no writes, no DAG triggers, no crawl.

## Result

Both diagnoses correct, with evidence: 24 tool calls, about 2 minutes, 67,000 tokens; about 22 of the calls were commands against the stack, in 8 steps:
- `late-arrival.txt`: first wrong stage the crawler database (`records.datestamp` an hour before the file's mtime); the harvest window (`from` 15:38:12) skips it correctly; nothing downstream. Caveat: the agent recognised an out-of-band write because the injected datestamp had microseconds, which `store.py` never writes. A real skew would write whole seconds and look plausible; the decisive check is the one the agent proposed: a datestamp before the last harvest's `until` for a dataset whose mtime is newer.
- `sample-list.csv`: first missing stage OpenSearch (`found: false`; `_stats` shows one delete), while the warehouse row says synced, so nothing will re-index it.

## Steps (the agent's log, condensed)

1. **Documents** (2 commands). Had to find: the warehouse database user (`warehouse.env`), the index name, the crawler database's trust login (compose file).
2. **Tree** (1). The data root `/data` is a volume; only the compose file says so.
3. **Crawler database** (3). Table names and the identifier form `oai:er-c-data-mgmt.fz-juelich.de:/path` are not documented; the datestamp anomaly needed `store.py`.
4. **OAI-PMH** (1).
5. **Warehouse database** (4). Undocumented: the endpoint's UUID, that `record_identifier` drops the `oai:…:` prefix, that the record id is `<endpoint uuid>::<path>`; `records_harvested` 0 misleads.
6. **OpenSearch** (5). The first lookup failed: the `_id` is the URL, found by listing documents and then in `transform_core.py`. `docs.count` (70) counts nested documents; `_count` (14) is the real number.
7. **Logs** (4). The crawler's access log has the harvest windows; the transformation's logs only point to Airflow task log files inside the worker.
8. **Search API** (1).

## Product hat

The agent got there, which says the documents and the clear-box access are enough in principle. But each diagnosis cost the agent what it costs an admin (walk-through B), and an agent developing the chain repeats it on every iteration. What it asked for is the same thing as the admin: **a per-path trace**, one row per stage (tree mtime, `datasets.mtime`, `records.datestamp`, OAI datestamp, the harvest run whose window covers it and whether it has an event, the warehouse row and its sync flag, the OpenSearch document, the search rank), flagging a datestamp before the last harvest's `until` and a synced row without a document. Both faults would have shown at once.

## Developer hat

- **The trace and the e2e test should share code:** the e2e test checks counts after each stage today and stops at the first failed assertion; asserting with the trace (per stage, per identifier) gives the failing stage in the test output.
- **Comparisons need set operations, not lookups:** the stage comparison for the e2e test (requirements 2.5) is the trace over all identifiers; at production scale it needs identifier lists per stage, not per-record calls.
- **The mappings are upstream behaviour** (prefix dropped, `endpoint::path` ids, URL as `_id`): the trace encodes them in one place, with a test against the real stack, so that an upstream change shows up as a failing e2e test, not as a wrong trace.
- **Detecting the injected faults is not a test of the trace;** the injections themselves are. They can become e2e scenarios: "a record dated before the harvest window is reported", "a synced record without a document is reported".

## Gaps

The same as walk-throughs A and B, confirmed by measurement: the trace across stages, the stage comparison, documentation of keys and stores. Added here:
- Fault-injection scenarios in the e2e test, so that the trace and the comparison are tested against the faults they are meant to find.

## Acceptance examples

- When a record's datestamp lies before the `until` of the last harvest although its dataset's mtime is newer, then the trace of its path flags it as skipped by the harvest window.
- When a warehouse record is marked synced but OpenSearch has no document for its URL, then the trace flags it, and so does the stage comparison.
- When the e2e test fails, then its output names the first diverging stage per affected identifier, not only a count.
- When a fresh agent gets the symptom of a single-fault case, then one trace command identifies the stage. Baseline today: 24 tool calls, about 2 minutes, 67,000 tokens.
