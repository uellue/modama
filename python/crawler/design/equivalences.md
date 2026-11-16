# Equivalences: our problem, the established thing

Before building a matcher, parser, protocol, scheduler, store or configuration syntax, look here, then ask what else the problem is an instance of (`working-with-agents.md`, section 8b, O32 and O33). Each row: a problem of this project in its own words, the established tool, standard or convention that already solves it, where the fit breaks, and where it was decided. Started 2026-11-16 (@weber, W17); every analogy someone names goes in the same day, also the ones not taken.

People find a distant analogy mostly when someone hints at it, and so do models; a shared name for the pattern is the hint written down (section 8b). So the rows are for reading before designing, not for reference afterwards.

## In use

| Our problem | Established thing | Where the fit breaks | Decided |
|---|---|---|---|
| Which paths a crawl skips entirely | `.gitignore` syntax, matched by `pathspec` (gitwildmatch) | defaults come from the format collections and the deployment adds to them; our hand-written matcher deviated "in the corners users copy from real files" until `pathspec` replaced it | `architecture.md`, 2026-10-27 (@weber), 2026-11-03 (review) |
| Which format handlers are active per deployment | ruff's `select`/`ignore` with prefix ids, here `collection/format` | per-path ignores are additive only; handlers come from separately installed packages | `architecture.md`, 2026-10-16 (@weber) |
| Format collections as plug-ins | pip packages and Python entry points | discovery by the `modama-formats-*` prefix plus a curated page | `architecture.md`, 2026-10-16 (@weber) |
| A file's type | shared-mime-info (XDG MIME rules) and its checking order | Python only where an XDG rule cannot express it, extending a rule; our own vendored database, never the host's; ties resolved to a common ancestor | `architecture.md`, decision on the rule language; 2026-10-14 |
| Finding files in a large shared tree, also by natural-language question | treat the tree as a data repository: an OAI-PMH endpoint, harvested by an existing research-data harvester, warehouse and search (EOSC Data Commons) | nightly, not live; deleted files not yet published as deleted records; no per-user access yet; the search's prompts are written for a public catalogue (`requirements-operations.md`) | the project's starting point; `requirements-pipeline.md` |
| How a record describes a dataset | Dublin Core (`oai_dc`) | richer metadata (units, instruments) has no place there yet (`BACKLOG.md`, "Units and meaning") | `records.py`; the OAI-PMH requirement |
| Changing the database's schema in running deployments | Alembic migrations | the crawler checks the version itself before every command (`schema.py`) | code map in `AGENTS.md` |
| Users reading and adding files over the network | WebDAV, SMB (modama's top level: `deploy/wsgidav`, the SMB ingest share) | outside the crawler | modama's top-level `AGENTS.md` |

## Named, not decided

| Our problem | Candidate | Status |
|---|---|---|
| Removing records of files that are gone, from harvester, warehouse and search | OAI-PMH deleted records (tombstones), which harvesters already understand | @weber, 2026-11-15 ("an organic way to purge"); the harvester and warehouse have bugs on that path (`BACKLOG.md`); purge proposal on its branch |
| Reusing an extraction when nothing it depends on changed | a build cache keyed by the inputs and the tool's version (as ccache or a build system's action cache) | noticed 2026-11-16 while writing this file; the extractor identity (`identity.py`) is that key; not compared with build systems yet |
