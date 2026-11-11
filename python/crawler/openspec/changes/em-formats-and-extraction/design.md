# Design

## Context

Recognition runs per directory in the walk (`walk.py`, `formats/__init__.py`: `Format.recognize`, a 1 MiB read budget and a 5 s limit per call). `store.py` truncates and rewrites `datasets` and `members` on every crawl and rebuilds every record, so as it stands every crawl would read every DM file again. Records reach the search through `dc_to_datacite.xsl`: only title, subject and description are embedded and returned (field mapping, 2026-11-11). Run 2 crawled about 16 files/s on NFS with round trips of 16 to 43 ms (F12).

## Goals / Non-Goals

**Goals:** extraction on production data for the demo (2026-11-17) without slowing the walk; no file read twice across crawls when nothing changed; a collection layout others can copy.
**Non-Goals:** the final concurrency mechanism (an I/O study is running; this change keeps it behind one module); a structured metadata format beyond `oai_dc`.

## Decisions

**D1. Extraction after recognition, through a queue, in worker processes.** The walk hands each dataset with an extractor to a `concurrent.futures.ProcessPoolExecutor` (spawn context) and continues; results are collected before `store()`. Processes because RosettaSciIO parses in Python (the GIL), and a worker that hangs or crashes is replaced without taking the crawl down (R23). The time limit per dataset is enforced from outside (the future's timeout; the pool is recreated after a timeout). Workers: configurable, default the CPU count capped at 8, since NFS latency, not CPU, sets the pace. *Alternatives:* threads (GIL-bound parsing, no isolation); extraction inside `recognize` (would block the walk and blur the two stages, `architecture.md` C); asyncio (file reads end in a thread pool anyway). Provisional: the I/O study may move the walk to threads, io_uring or Rust; the extractor interface does not change with it.

**D2. The extractor interface.** `Format.extract(dataset, root) -> Extracted | None`, with `Extracted` holding `summary: list[str]` (ordered "key value" phrases for the description), `subjects: list[str]`, and `values: dict` (stored with the dataset for later use, not rendered). Pure function of the files, runs in a worker, no database access. `Format.extractor_version` (string) separate from the recognition `version`, so improving an extractor does not look like a recognition change.

**D3. Skip unchanged directories; the state lives in `datasets` (@weber, 2026-11-11).** No cache of its own. `datasets` and `members` are no longer truncated per crawl (review B17 left them free to change); each dataset row stores its format id and recognition version, its extractor id and version, the `Extracted` result as JSONB (or the error), and the extraction's duration. Each crawl run stores a fingerprint of the rule set: the enabled collections with their versions, the per-deployment MIME database, the selection config.
- The walk still lists and stats every directory (directory mtimes do not propagate: a change deeper down or a file rewritten in place leaves the parent's mtime alone, so no subtree is ever skipped from the top).
- In post-order, a directory is *unchanged* when its own listing (names, types, sizes, mtimes, ctimes) equals the stored one **and** all its subdirectories are unchanged; computed bottom-up by us, not trusted to the file system. A directory dataset that adopts subfolders is thereby re-recognised when anything below changes.
- When the directory is unchanged and the rule set's fingerprint equals the last finished crawl's, its datasets are taken over as stored: no content read, no recognition, no extraction.
- Otherwise recognition runs for the directory; for each resulting dataset, a stored extraction is reused when the extractor id and version and the members' sizes and times are the same, else the extractor runs. A stored failure is reused too (a broken file is not retried every night; a new extractor version retries it), but only one of reading the file: a timeout, a dead worker process, an OS or import error say nothing about the file and are retried next crawl; likewise a directory whose recognition met a read error or the time limit is not taken over (review 2026-11-11, `review.md`).
- Collapsed trees (Zarr stores, environments) are not walked inside, as before: a change inside one is seen only when its own top-level listing changes.
- Datasets of directories that vanished are deleted with their records, as today.
*Alternatives:* a separate cache table keyed by a fingerprint of the files (a second copy of the state to keep consistent: "caching is hard"); running recognition every crawl to confirm the identity (costs the header reads on every file, the expensive part on NFS, F12); trusting directory mtimes to skip subtrees (they don't propagate). Later refinement: when only one format's version changes, re-recognise only the directories where it can apply.

**D4. The description.** `records.py` builds one line: the extracted summary phrases first, then "<type name>, <n> file(s), <size>, in <folder>/". The type name is the MIME type's `<comment>` from the per-deployment MIME database (908 types have one in `freedesktop.org.xml`; our own types get one in their XML), falling back to the MIME string. Subjects: the format's name, then the extractor's subjects, de-duplicated. Sizes come from the walk's `stat` (members' `st_size`, already read); the dataset gains a `size` field.

**D5. The collection `modama-formats-em`.** `python/modama-formats-em/` with `pyproject.toml` (depends on `modama-crawler` and `rosettasciio`, pinned to the current release, looked up when installing), `src/modama_formats_em/` with `empad/`, `dm/`, `merlin/`, each with its own MIME XML (`dm/dm.xml`, `merlin/merlin.xml`; not one `em.xml`, so that each format's coverage test stands on its own fixtures, @weber 2026-11-11), each with fixtures and tests in the layout `formats/TEMPLATE.md` describes. Entry point `em = "modama_formats_em:COLLECTION"`. Installed editable in the dev venv and in the crawler image.

**D6. Merlin as a producer type, not the generic series rule.** The `.hdr` names the acquisition; frames match by stem pattern (`<stem>_<n>.mib` or the naming in the representative files). Highest-value case of F1 now; the generic series rule stays a separate change.

**D7. Readers.** DM3/DM4 and Merlin through RosettaSciIO's readers with lazy loading, metadata only; EMPAD's XML header with the existing parser (no reader needed). If RosettaSciIO reads image data to get the tags, extraction reads more than the header; measured in task 2.4 and on staging; fallback for DM: `ncempy`'s tag reader or our own tag walker, decided then.

## Risks / Trade-offs

- [RosettaSciIO reads far more than the tags over NFS] → measure bytes per file (`/proc/self/io`) in the tests and on the benchmark; fallback D7.
- [The first crawl with extraction re-reads all DM, EMPAD and Merlin files on production] → ~28k DM files, headers only; at the measured NFS rates a few hours at worst; skipping unchanged directories (D3) makes it once. Run on staging overnight first.
- [Every record's content changes once (description), so the next harvest re-indexes the whole tree] → one night of indexing (F7: ~6.5 h for 430k records); planned as the re-index before the demo, which also clears the stale `.mib` frame records if the warehouse and index are reset.
- [Worker processes and memory] → spawn context, few workers, readers lazy; peak memory measured on staging (F13 is open).
- [Format id change `empad/empad` → `em/empad`] → selections in `stagingconf/` and docs updated in the same change.

## Migration Plan

Recreate the crawler database (schema change). On staging: rebuild the crawler image with the collection, reset the warehouse and the index, crawl the full tree overnight; the harvest and index follow. Rollback: the previous image and a fresh index.

## Open Questions

- Which DM tags hold the instrument name on ER-C's microscopes (vendor- and version-specific); settled on representative files from the tree.
