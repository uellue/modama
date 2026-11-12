# Proposal

## Why

Improving a format's recognition or extraction and seeing the result in the search takes a whole crawl today: on staging (run 3, 2026-11-11) the walk took 17 minutes, the crawl 1 h 17 min, the harvest 5 h 14 min, the indexing hours more. @weber asked on 2026-11-12 for commands that give fast turn-around instead, without waiting for the whole re-crawl:

1. re-run extraction, harvest and indexing for a specific path (to test an updated extractor);
2. the same for all files of a specific kind (to make an improved format available everywhere);
3. crawl, recognise, extract, harvest and index a whole subtree on demand, for example `adhoc/libertem/libertem-test-data`.

I read the three as rules, not as single cases. In (1) and (3), "path" is a canonical path in the glossary's sense (`/CONTEXT.md`: the same on every way of access, `adhoc/testproject/session2`), which is also how the crawler names datasets: an anchor such as `/adhoc/libertem/libertem-test-data/dm/a.dm4` is relative to `MODAMA_DATA_ROOT`. In (2), "kind" is a format, named by its id as in `--select` (`em/dm4`; there is no `em/dm`: DM3 and DM4 are `em/dm3` and `em/dm4`, and they share one extractor).

Today's `crawl --root PATH` does not help with (1) or (3), and it is a trap. It treats PATH as the whole repository: anchors become relative to PATH, so the identifiers change (`walk.py:354`), and the store deletes every dataset, listing and record it did not see (`store.py:425`, `:438`, `:459`). Staging's other workaround, `--root` on the data root with exclusions (`stagingconf/libertem.toml`), keeps the identifiers but deletes everything outside the subtree too. It also changes the rule set (`selection.fingerprint` includes the exclusions), so the next full crawl recognises the whole tree again and gives every record a new datestamp, which means a full re-harvest.

Request (2) already works without a new command: bumping a format's `extractor_version` makes the next crawl extract that format's datasets again and nothing else, and only records whose content changed get a new datestamp. That behaviour is the scenario "A new extractor version" in the open change `em-formats-and-extraction`. What is missing there is the documentation and a way to run it now rather than at 19:00 (design D7).

Serves R14 (developing a format is easy for humans and agents), R10 (a re-crawl only does work for what changed), R9 (inspect the outcome for one directory, now with harvest and search included) and the request of 2026-11-12, to be recorded as R41 (task 1.1).

## What Changes

- **New option `modama-crawler crawl --path PATH`**: a *subtree crawl* of the directory PATH (a canonical path; a leading `/` is accepted). It walks only that subtree and recognises and extracts it from scratch: nothing is taken over from the stored state, and no extraction is reused, so an extractor changed without a version bump runs again. Within the subtree it brings datasets, members and records up to date, and records of datasets that disappeared are deleted. Outside the subtree, nothing changes, datestamps included. Identifiers are the same as a full crawl's. A file as PATH stands for its directory.
- PATH must be a directory that a full crawl would enter: below the data root, with no symlink on the way, not excluded by `[crawl] exclude`, not inside a collapsed directory (environment, `.git`, Zarr store), and every directory above it listable. Otherwise the crawl exits with status 2 and an error naming the reason, and records nothing.
- A subtree crawl takes the same crawl lock, reacts to SIGTERM in the same way (run `failed`, status 143, no record changed) and starts the same harvest when it finishes. Only the records it changed are harvested and indexed, because the harvest is incremental (`from` = the end of the last closed harvest) and the harvest DAG indexes only the runs it harvested.
- **Runs record their subtree.** `crawl_runs` gets a `scope` column (NULL for a full crawl), and `runs` shows it. Only full crawls count for the timer's catch-up and for `modama-chain`'s freshness time T. A subtree crawl says nothing about the rest of the tree.
- The next full crawl recognises a crawled subtree again: the subtree crawl leaves no stored listings for it. Its extractions are reused, so this costs one more recognition of the subtree, and the state stays consistent even when the subtree crawl ran under other rules (another `--config`, a changed format).
- **Format-wide re-extraction (request 2) is documented, not built**: bump `extractor_version`, rebuild, run `crawl` (design D7, with the alternative `crawl --format ID`).
- `--root`'s help text and the README say that it sets the data root and that a crawl treats it as the whole tree.

Behaviour towards the user: an operator or developer gets `crawl --path`, a `scope` on run lines in `runs` (`… /data  adhoc/libertem/libertem-test-data`), and new exit-2 errors for a path that a full crawl would not enter. A harvester sees new datestamps only on records under the path whose content changed. A searcher sees those records re-indexed within the time of one incremental harvest, and records under the path whose datasets disappeared drop out of the crawler's endpoint (the warehouse keeps them, as after a full crawl, until the purge). `modama-chain status` shows subtree crawls but does not move T for them. No change for full crawls, `serve` or `records`.

Out of scope (see "Not now" in `design.md`): several paths in one crawl; a subtree crawl that keeps the stored state (no forced re-run); re-extraction without a walk; tombstones (`deletedRecord`) and the purge; the timer retrying when a subtree crawl holds the lock; the inotify watcher; subtree crawls below a format that adopts datasets of subdirectories (none exists yet).

## Capabilities

### New Capabilities

### Modified Capabilities
- `crawl`: the index after a crawl is defined for a subtree crawl as well, plus new requirements for the subtree crawl: what it changes, that it recognises and extracts from scratch, which paths it accepts, and the lock and SIGTERM.
- `crawl-runs`: a run records its subtree, and `runs` shows it.
- `harvest-trigger`: a subtree crawl starts the harvest, and the timer's catch-up counts full crawls only.
- `chain-trace`: the freshness time T counts full crawls only.

## Impact

- Crawler: `cli.py` (the option, path checks, the run's scope, `--root`'s help), `walk.py` (start the walk at a directory below the root, with anchors relative to the root; the checks on the directories above it), `store.py` (store restricted to a subtree; `scope` column added with `ADD COLUMN IF NOT EXISTS`, so the database need not be recreated, design D5; `last_finished` for full crawls only), tests (`test_cli.py`, `test_store.py`, `test_trigger.py`, `test_walk.py`).
- `python/search-chain`: T from full crawls only; `scope` read as part of the `crawl_runs` interface.
- Docs: `README.md` (running the crawler, the format-wide procedure), `BACKLOG.md`, `design/requirements.md` (R41), the decision log, `/prototypes/search-stack/README.md` (the command in `crawl-timer`, which alone has the Airflow account in production).
- No new dependency.
