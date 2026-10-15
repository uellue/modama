# Backlog

Deferred items, roughly in the order they are likely to come up.

- **Deleted records:** support `deletedRecord` (`transient` or `persistent`) with tombstones for removed or renamed datasets. Currently `no`.
- **Collapsing trees:** treat large uninteresting trees (`node_modules`, Python/conda environments, known source trees such as a Linux kernel checkout) as one dataset, adding their members in bulk or ignoring them.
- **Sniffing cost:** files without a decisive name cost about 5 ms each in pure-Python magic matching, plus reading 18 KB. Measure on real data; options are skipping or deferring them, parallelism, or libmagic.
- **Curated MIME definitions:** import the full range of freedesktop shared-mime-info types into our own curated packages, so the crawler depends on nothing from the host. Large, well-defined, with lots of context: a work item for an AI agent.
- **Revisit-later stash:** keep incomplete datasets (for example an EMPAD XML without its raw file) for a retry, and report them as broken after a deadline. For now they are only reported.
- **Agent skill:** find an existing or propose a new MIME type for a format, in discussion with the user, as part of adding a handler.
- **Agent workflow, unclaimed review (R22):** from the crawl's report of unclaimed and generic-only files (by extension, location, and change over time), inspect likely candidates for a missing handler, then search for, activate or create one, or extend an existing handler's rules for an unknown variant. Sub-handlers for schema-specific XML, YAML and JSON (`docker-compose.yml`, Dublin Core XML) are the generic-only case.
- **Per-user views** of the index, as a deferred requirement; crawl-time access checks stay out of scope.
- **EMPAD detection:** `application/x.empad+xml` registers `*.xml` only to make every XML file ambiguous and force sniffing. This belongs in dataset recognition (XML plus raw file), driven by the raw files' weight-80 globs.
- **Metadata extraction** per file format.
- **`dc:date`** currently uses `max(mtime, ctime)` from the crawl, which becomes the copy time for files copied from instruments. The plain mtime, or a date from the file's own metadata, is probably closer to the acquisition time.
- **Non-UTF-8 and control characters in file names:** decide how to store them and how to render them in XML.
- **Per-user access checks** through the modama permission APIs.
- **DataCite output,** if `oai_dc` turns out too lossy. The warehouse's DC→DataCite XSLT drops `dc:format`. The warehouse also accepts DataCite with `identifierType="URL"`, even though the DataCite schema documentation requires a DOI.
- **Crawl scaling:**
  - The walk is single-threaded and has no checkpointing, so a failure restarts it from scratch.
  - `DELETE … WHERE path NOT IN (SELECT path FROM crawl)` is an anti-join over the whole table.
  - Paths are stored as absolute text, and keys are `SERIAL` (int4).
  - `publish_records` recomputes the metadata of every dataset on every crawl, not only of changed ones.
- **Datestamp window:** a harvest running in the same seconds as a publishing batch can miss that batch. Batching keeps the window small, but not zero.
- **Symlinks and directories** never become datasets. Directories should wait for dataset grouping; symlinks to files are an open question.
- **Schema migrations:** there are none, so every schema change means recreating the database. Needed before deployment.
- **`recognition.py` defects,** relevant if parts of it are kept in step 2:
  - The members query never returns other members, and `files_in_datasets` is never populated.
  - `matches()` and EMPAD glob the file system.
- **Local EOSC snapshot:** `prototypes/EOSC-Data-Commons/` is about three months behind upstream (v1.9.0, 2026-10-08) and has uncommitted local changes, including the `localhost:7654` endpoint in `seed.sql`.
- **Deployment:** a container in `deploy/` behind the gateway, with a read-only data mount and a crawl schedule.
- **Drop the pyxdg fork** once https://gitlab.freedesktop.org/xdg/pyxdg/-/merge_requests/18 is merged.
- **Report or fix upstream** (pyxdg): `get_type2()` lacks the longest-pattern rule (`a.tar.gz` becomes `application/gzip`), and `MagicDB.match_data(possible=...)` checks the lowest priority first (an SVG checked against `[xml, svg]` becomes `application/xml`).
- **Report upstream** (EOSC `metadata-crawlers`):
  - Deletion detection reads `header.status`, but oaipmh-scythe exposes `header.deleted`, so deletions are never propagated.
  - A `noRecordsMatch` response on an incremental harvest marks the run as failed.
  - A single failed record blocks indexing of the whole run.
  - OAI identifiers are cut at the last `:` and stored as `VARCHAR(255)`.
