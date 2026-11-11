# Proposal

## Why

Search hits today carry the path and little else: no `dc:description`, so the search API multiplies their score by 0.1, and nothing about the data itself (F11). The demo on 2026-11-17 is to show metadata extraction at work on production data in formats relevant for electron microscopy. Measured on 2026-11-11: only title, subject and description reach the embedded text and the hit; a record changed under the same identifier replaces its search document (e2e test). Serves R15 (extract from tags and content, now), R26 (first step), R21 (domain formats outside the core), R14 (a collection as a template for more), R30 (findable by what the data is).

## What Changes

- **New collection `modama-formats-em`** in `python/modama-formats-em/` (package `modama_formats_em`, entry-point group `modama.formats`), a separate repository later (decision log, 2026-11-11). **BREAKING (ids):** EMPAD moves there from the crawler; its format id becomes `em/empad` (was `empad/empad`), so a selection that names it must be updated.
- **Recognition of DM3/DM4** (Gatan Digital Micrograph, by magic) and **Merlin** acquisitions (one `.hdr` with its `.mib` frames as one dataset; F1's `many_mib` becomes one record per acquisition).
- **Metadata extraction**: a format may have an extractor; extraction runs after recognition, apart from the walk, through a work queue in worker processes with a time limit per dataset. A crawl skips recognition and extraction for directories whose listing, and everything below them, is unchanged while the formats are unchanged; the stored datasets in the crawler's database carry over, with the identity of the extractor that produced their metadata, so a new extractor version re-extracts (no cache of its own; R10: a re-crawl only does work for what changed). The mechanism is provisional (decision log, 2026-11-11); an I/O study running now informs it.
- **First extractors**, with the upstream reader RosettaSciIO (new dependency of `modama-formats-em` only, version pinned after looking up the current release): DM3/DM4 (voltage, magnification, pixel size, detector, instrument, acquisition time where present), EMPAD (scan size, frame size, exposure), Merlin (frame count, frame size, bit depth).
- **Every record gets a `dc:description`**: a readable summary, extracted values first; for datasets without an extractor a basic one (the MIME type's description, number of files and size, the folder). Short terms (format, technique, instrument) go into `dc:subject`.

Behaviour towards the user: a harvester sees `dc:description` on every record and `dc:subject` on extracted ones; their datestamps move once (content changed), so the next harvest re-indexes everything. A searcher sees descriptions in hits, no ×0.1 penalty, and EM metadata that the embedding can match; Merlin frames no longer flood results. An admin sees extraction counts, failures and time in the crawl's report, and `em/*` format ids.

Out of scope: Velox EMD, TIA, TENSOR and Dr. Probe exports, the generic series rule (F1 beyond Merlin), the purge of stale entries (the old `.mib` frame records stay until the purge or a fresh index), subtree crawls, keyword search in the search API (a separate patch), parallel walk, Rust, vision-language models (R16), `dc:date` from file metadata.

## Capabilities

### New Capabilities
- `extraction`: running extractors after recognition: the work queue, time limit and failure isolation, skipping unchanged directories and re-extracting on a new extractor, how results become `dc:description` and `dc:subject`.
- `formats/dm`: DM3/DM4 recognition and extraction.
- `formats/merlin`: Merlin `.hdr` plus `.mib` frames as one dataset, and extraction.

### Modified Capabilities
- `records`: every record carries a `dc:description`; extracted metadata goes into description and subject.
- `formats/empad`: the format id is `em/empad`, and EMPAD datasets get extracted metadata.

## Impact

- New package `python/modama-formats-em/` (`pyproject.toml`, MIME XML for DM and Merlin, recognizers, extractors, fixtures and tests); `src/modama_crawler/formats/empad/` moves there.
- Crawler: `formats/__init__.py` (an optional extractor per format), a new module for the extraction queue, `walk.py` (the unchanged check), `store.py` (persistent `datasets`, the stored listings, the rule-set fingerprint; schema change: recreate the database, as for every schema change so far), `records.py` (description, subject), `cli.py` (report), `pyproject.toml` (EMPAD's entry point removed).
- Dependency: `rosettasciio` (and what it pulls in, e.g. numpy) in `modama-formats-em` only; flagged in the hand-over.
- The search stack's crawler image installs `modama-formats-em`. A full re-harvest and re-index after the first crawl with it (one night on staging).
