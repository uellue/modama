# Backlog

Deferred items, roughly in the order they are likely to come up.

- **Deleted records:** support `deletedRecord` (`transient` or `persistent`) with tombstones for removed or renamed datasets. Currently `no`.
- **Collapsing trees:** treat large uninteresting trees (`node_modules`, Python/conda environments, known source trees such as a Linux kernel checkout) as one dataset, adding their members in bulk or ignoring them.
- **Sniffing cost:** files without a decisive name cost about 5 ms each in pure-Python magic matching, plus reading 18 KB. Measure on real data; options are skipping or deferring them, parallelism, or libmagic.
- **EMPAD detection:** `application/x.empad+xml` registers `*.xml` only to make every XML file ambiguous and force sniffing. This belongs in dataset recognition (XML plus raw file), driven by the raw files' weight-80 globs.
- **Metadata extraction** per file format.
- **`dc:date`** currently uses `max(mtime, ctime)` from the crawl, which becomes the copy time for files copied from instruments. The plain mtime, or a date from the file's own metadata, is probably closer to the acquisition time.
- **Non-UTF-8 and control characters in file names:** decide how to store them and how to render them in XML.
- **Per-user access checks** through the modama permission APIs.
- **DataCite output,** if `oai_dc` turns out too lossy. The warehouse's DC→DataCite XSLT drops `dc:format`. The warehouse also accepts DataCite with `identifierType="URL"`, even though the DataCite schema documentation requires a DOI.
- **Deployment:** a container in `deploy/` behind the gateway, with a read-only data mount and a crawl schedule.
- **Drop the pyxdg fork** once https://gitlab.freedesktop.org/xdg/pyxdg/-/merge_requests/18 is merged.
- **Report or fix upstream** (pyxdg): `get_type2()` lacks the longest-pattern rule (`a.tar.gz` becomes `application/gzip`), and `MagicDB.match_data(possible=...)` checks the lowest priority first (an SVG checked against `[xml, svg]` becomes `application/xml`).
- **Report upstream** (EOSC `metadata-crawlers`):
  - Deletion detection reads `header.status`, but oaipmh-scythe exposes `header.deleted`, so deletions are never propagated.
  - A `noRecordsMatch` response on an incremental harvest marks the run as failed.
  - A single failed record blocks indexing of the whole run.
  - OAI identifiers are cut at the last `:` and stored as `VARCHAR(255)`.
