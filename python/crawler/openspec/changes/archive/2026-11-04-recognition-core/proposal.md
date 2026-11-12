# Proposal

## Why

The crawler's middle (the walk, the schema, `recognition.py`) is a proof of concept that recognises one dataset per file, touches the file system at request time, and cannot group files into the multi-file datasets that make up 71% of the visible ER-C tree (`design/survey.md`). The design for dataset recognition is now decided (`design/architecture.md`, decision log through 2026-10-16) and needs a core that proves it on real shapes before hundreds of formats are written against it (R2, R14).

## What Changes

- **Post-order walk with a pre-order collapse check** replaces the flat `os.walk` crawl: a directory is recognised after its children, with their results; boring trees are recognised from their listing and not entered (architecture A, R11).
- **Format interface**: a format is a class with `type`, `priority`, `reacts_to`, `collection` and `recognize(directory)`, called pre-order and post-order with plain data and a budgeted `read`; it claims its own entries and whole child datasets (architecture B, D).
- **Recognition result** as the single oracle: datasets (type, anchor, members, format and version, basis, warnings, parent, collapsed) plus tree-level warnings; stored in the index, rendered as `oai_dc`, recorded for fixtures (architecture H). Every file gets a record by default.
- **Curated MIME database** built per deployment from the enabled collections, with `freedesktop.org.xml` vendored into the core collection; nothing from the host (Q12). Ties between types resolve to their common `sub-class-of` ancestor (C).
- **Format selection** in the deployment configuration, ruff-style `select`/`ignore` by `collection/format` id with additive per-path ignores (E).
- **`records [PATH]` command**: prints the `oai_dc` `ListRecords` rendering for a path after the walk, diagnostics on stderr, `from`/`until`, `--select`/`--ignore`, `--verbose` (H).
- **Fixture test plugin**: fixtures as directories of wild files, one manifest per collection, recorded expected results, coverage of our own rules (`design/testing.md` T-B).
- **Four in-package collections** with the standard layout: `core` (single files, vendored upstream definitions), `collapse` (environments, `.git`, `__pycache__`, `.ipynb_checkpoints`), `zarr` (v3, nested), `empad` (XML plus raw, generated cheat fixture).
- **BREAKING**: the `datasets`, `files` and `records` tables change shape (no migrations; the development database is recreated); `recognition.py`, `tests/test_recognition.py` and `tests/test_crawl.py` are removed; the crawl stores mtime and ctime separately.
- Kept as they are: `mime.py` (XDG checking order), `server.py` and the OAI-PMH protocol tests, the identifier and browse-URL code, the client interoperability tests.

Out of scope, each its own later change: the series format and the grouping thresholds (R31), DM4, notebooks, TIA pairs, the `survey` command, the deployment expectation file (T-D), crawl scheduling, process isolation (G), separate distributions for collections, metadata extraction (R15) and relations (R32).

Requirements served: R1, R2, R3, R5, R6, R7 (reporting only), R9, R11, R12 (time limit), R13, R14 (the template and plugin), R17, R21, R22, R25, R29, R30; decisions Q1, Q2, Q4, Q5, Q6, Q9, Q11, Q12, Q16, Q17.

## Capabilities

### New Capabilities
- `crawl`: walking a tree post-order with a pre-order collapse check, recording entries with mtime and ctime, skipping what cannot be stored, storing results in the index.
- `recognition`: the format interface and how the core runs formats: priorities and ties, candidate pre-filtering, the recognition result, nesting and membership, warnings and budgets.
- `mime-database`: building the per-deployment MIME database from enabled collections only, with vendored upstream definitions, and classifying single files by the XDG checking order (today's `mime.py` behaviour, now specified).
- `format-selection`: selecting formats from installed collections by id, with `select`, `ignore` and per-path ignores, and the discovery of collections through entry points.
- `records`: building the Dublin Core record of a dataset from the recognition result (identifier, browse URL, DC mapping including relations for collection members) and rendering `oai_dc`.
- `records-cli`: the `records [PATH]` command.
- `formats-testing`: the fixture layout, manifest, recorded expected results, the coverage rule, and the pytest plugin that runs them for any collection.
- `formats/core`: single-file types from the curated upstream definitions.
- `formats/collapse`: directories recognised as one dataset from their listing, not entered.
- `formats/zarr`: Zarr v3 stores, including stores nested in stores.
- `formats/empad`: EMPAD XML plus raw pairs.

### Modified Capabilities
None exist yet; the OAI-PMH server's behaviour is unchanged and gets no spec in this change.

## Impact

- Code: `database.py` (walk, schema, storage) rewritten; `records.py` split into record building and rendering; `recognition.py` removed; new modules for the walk, the format interface, the result, selection, the MIME database build, the CLI, the pytest plugin; `formats/` directory with four collections; `pyproject.toml` gains the entry-point group `modama.formats` and a pytest plugin entry point.
- Database: schema change without migration (development only); the `records` table keeps its role for the server.
- Dependencies: none new at runtime; `freedesktop.org.xml` vendored with its GPL-2.0-or-later notice (decided 2026-10-16); zarr-python as a test dependency to generate Zarr fixtures; LiberTEM used once, outside the test suite, to validate the EMPAD cheat fixture.
- Tests: `test_mime.py`, `test_records.py`, `test_server.py`, `test_clients.py` kept; `test_crawl.py` and `test_recognition.py` replaced by core engine tests on synthetic trees and by each collection's fixtures.
- Documentation: `AGENTS.md` updated for the new layout and commands.
