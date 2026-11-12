# Design

## Context

The motivation is in the proposal. This is what the code does today (crawler branch at 9c9b32b), and it is what shapes the approach:

- **The crawl root is the whole repository.** `walk()` visits its root as `/` (`walk.py:354`), so anchors, and with them identifiers and browse URLs, are relative to the root it is given (`records.py:27`, `:36`: "relative to the data root"). `store()` deletes every dataset, listing and record that is not in the result (`store.py:425`, `:438`, `:459`). So `crawl --root SUBTREE` renames the subtree's records and deletes all the others. Exclusions keep the names but delete the same records, and they enter the rule set (`selection.py:165`), so the next full crawl takes nothing over (`store.py:391`).
- **Reuse.** A full crawl takes over a directory whose listing, and the listings of everything below it, are unchanged under the same rule set (`walk.py:264`, `:302`). It reuses an extraction while extractor id, `extractor_version` and the dataset's stamp are the same and the failure, if any, was not an environment failure (`extraction.py:114`). Extractions are reused across a change of rule set as well (`cli.py:222`). The rule set covers format versions, MIME XML, selection, exclusions and distribution versions, but not extractor versions (`selection.py:138`). Distribution versions are static (`0.0.1.dev0`), and the search stack's image installs the crawler and `modama-formats-em` editable (`crawler.Dockerfile`). So a code change without a version bump leaves both the rule set and the extractor identity as they are, and nothing runs again.
- **Datestamps** move only when a record's metadata changes (`store.py:463`, `:470`).
- **Harvest.** The crawler starts `warehouse_harvest_and_index` with `harvest_urls` = its endpoint after every finished crawl (`cli.py:340`, `harvest.py:37`). The warehouse opens the harvest run with `from_date` = the `until_date` of the endpoint's last closed run (`metadata-warehouse/src/app/db_methods.py:176`), so the harvest is incremental. The DAG then indexes only the closed runs created since its start (`harvest_and_index.py:57`, `:110`), and `max_active_runs=1` (`:37`) queues a second DAG run behind a running one. A record changed under the same identifier replaces its search document (e2e test, 2026-11-11, `BACKLOG.md`). Deletions do not reach the warehouse (`deletedRecord=no`).
- **Runs.** `last_finished()` (`store.py:271`) drives the timer's catch-up (`cli.py:403`). `modama-chain` takes T from the newest finished crawl (`search-chain/src/modama_chain/chain.py:299`). Neither knows about subtrees.
- **Staging, run 3:** extraction ran 177,166 times in about 52 minutes on 8 processes, DM4 18,294 s and DM3 5,377 s summed over them. The harvest ran at about 77 records/s, and indexing at 26 to 62 records/s (F16).

## Goals / Non-Goals

**Goals:** one subtree is crawled from scratch, with the same identifiers as a full crawl, and the rest of the index stays untouched. The stored state stays consistent for the next full crawl. Requests 1 and 3 get one command, and request 2 gets a documented procedure.

**Non-Goals:** making the warehouse faster. For a format-wide change, the harvest and indexing of the changed records dominate: about 170,000 DM records at F16's rates take about 40 minutes to harvest and one to two hours to index, against a 17-minute walk.

## Decisions

**D1. One option on `crawl`, not a new command: `crawl --path PATH`.** A subtree crawl is a crawl. It has the same lock, run record, SIGTERM handling, store lock, report, harvest trigger, `--config`, `--select` and `--ignore`, so all of that comes for free and stays the same. *Alternatives:* (a) a command of its own (`recrawl PATH`): it would say "from scratch" in its name, but it would duplicate the option handling and the exit statuses; (b) `--root` with exclusions, which staging uses today: it deletes the rest of the index and resets the rule set (Context). *Name:* `--path` rather than `--subtree`, because the requests say "path". `--root` keeps its meaning, the data root, and its help text says so (proposal).

**D2. PATH is a canonical path, checked against what a full crawl enters.** PATH is relative to the data root, and a leading `/` is accepted (the form of anchors and `dc:title`). It is normalised, and a `..` that leaves the root is an error. Before anything is recorded, the crawl goes from the root down to PATH. For each directory on the way, and for PATH itself, it asks the file system: an `lstat`, which refuses symlinks, and a listing, which refuses a directory it cannot list (AGENTS.md: the file system is the truth). It then applies the exclusions and the enabled formats' pre-order check to that listing. The first directory that is excluded, collapsed (an environment, `.git`, a Zarr store) or not listable ends the crawl with status 2 and names that directory (spec `crawl`, "A subtree crawl only covers what a full crawl enters"). PATH itself may be collapsed: it then becomes one dataset, as in a full crawl. The check prevents records that a full crawl would not make, which would be harvested and never purged. The pre-order check runs on the listings rather than on the stored datasets, so it also holds for a tree that was never crawled. *A file as PATH* stands for its directory, because recognition works per directory (question below).

**D3. From scratch inside the subtree.** The walk starts at PATH with rel = PATH, without the stored state (`previous=None`), and extraction runs without the stored extractions. So every directory under PATH is recognised and every extractor runs, with or without a version bump. This does not contradict "the same data gives the same result or a failure" (change `parallel-walk`, spec `crawl`). Only the cache is skipped, not the rules: the same code on the same files gives the same records, and no datestamp moves. Only changed code changes records, which is the point. *Alternative:* the normal take-over and reuse in the subtree, with a `--force` flag. Request 3 (new data, unchanged code) would then do less work, but request 1 needs the forced run, and a subtree is small enough that one behaviour beats a flag (question below).

**D4. The store, restricted to the subtree.** In one transaction, as today:
- delete the datasets whose `directory` is PATH or below and whose anchor is not in the result (members go by cascade), and upsert the result's datasets;
- delete the records of the deleted datasets, by the identifiers of their anchors, since records have no anchor column and long identifiers are hashed. Upsert the result's records under the store lock, with one datestamp, as today;
- delete the stored listings (`directories`) of PATH and below, and store none for the subtree. The next full crawl then recognises the subtree again and reuses its extractions (spec scenario "The next full crawl takes over the extractions"), whatever rules either crawl ran under. *Alternative:* store fresh listings, so that the next full crawl takes the subtree over. That is wrong when the subtree crawl ran under other rules (a forgotten `--config` in `docker compose exec`, a format bumped in the image): the full crawl would then take over datasets recognised under those other rules. The cost of deleting is one more recognition of the subtree;
- record no rule set on the run. `previous()` then still compares against the last full crawl.
A prefix test on `directory` uses `starts_with()`, not `LIKE`, because paths may contain `%` and `_`. Parents are set only by formats that adopt datasets of subdirectories, and none does today (`collection = True` nowhere). So the datasets at the top of the subtree get no parent, as at the top of a full crawl ("Not now").

**D5. The run records its subtree.** A column `crawl_runs.scope TEXT` holds the canonical path without a leading `/`, and NULL for a full crawl. `runs` prints it after the root. `last_finished()` and `modama-chain`'s T use `scope IS NULL` only. There are no migrations, so the column is added by `ALTER TABLE crawl_runs ADD COLUMN IF NOT EXISTS scope TEXT` in `ensure_tables`. That is the first such step: recreating the database would cost staging a full crawl, harvest and indexing, about a night (question below). `modama-chain` checks that the column exists, as it already does for the table (`crawler.py:102`), so that it also works against a crawler from before this change. *Alternative:* encode the subtree in `root` (root + path). Readers would then have to know the data root to tell the two kinds apart.

**D6. Lock, SIGTERM and harvest: no new mechanism.** The same crawl lock: a subtree crawl and a full crawl refuse each other with status 1. SIGTERM records the run as `failed` and exits with 143, and the store's single transaction guarantees that no record changed. After a finished subtree crawl the harvest starts as after any crawl. Only records changed under PATH have a datestamp after the last harvest window, so only they are harvested and indexed. A harvest already running queues the new one (`max_active_runs=1`), and its window still starts at the end of the last closed run, so it includes the subtree's records. In production only `crawl-timer` has the Airflow account, so a subtree crawl that should start the harvest runs there: `docker compose exec crawl-timer modama-crawler --config … crawl --path …`.

**D7. Request 2 (all files of a kind): bump the version and crawl now.** No new command. Bump the format's `extractor_version` (DM3 and DM4 share one, `modama_formats_em/dm/__init__.py:19`), rebuild the image, and run `crawl` instead of waiting for the timer. The full crawl takes every unchanged directory over, extracts only that format's datasets again (`extraction.py:118`), and gives a new datestamp only to records whose content changed. So the harvest is incremental. A recognition change (format `version`, MIME XML) changes the rule set: every directory is recognised again, and extractions are still reused. This is the decision of 2026-10-16 ("after a format change, re-crawl; no selective invalidation") and the open change `em-formats-and-extraction`'s scenario "A new extractor version". The bump is also what carries the improvement to every other deployment. Cost on staging: the walk (17 minutes with warm caches) and the store (about 8 minutes in run 3) on top of the format's extraction, and then the warehouse (Non-Goals). The README gets the procedure. *Alternatives:* (a) `crawl --format ID[,ID…]`: a full crawl that does not reuse the given formats' extractions. It is small (one set passed to `extract`) and needs no bump while iterating, but the stored results then carry a version label that does not identify the code that produced them, so another deployment with that version would give different results. (b) Re-extraction from the stored datasets without a walk: it saves about 25 minutes out of about three hours, at the price of a second store path and of extracting files that changed or disappeared since the last crawl.

## Risks / Trade-offs

- [A subtree crawl holds the lock at the timer's time] → the nightly crawl exits with status 1, and the timer waits until the next day (`cli.py`, `cmd_timer`). Subtree crawls are short, and `runs` shows the conflict. A retry in the timer goes to "Not now" (question below).
- [A large PATH (`adhoc`)] → everything under it is extracted again. The operator chose the path, and the report shows the counts.
- [A forgotten `--config` in `docker compose exec`] → the subtree is recognised under the default rules until the next full crawl. D4 keeps the stored state consistent, and the records under PATH show it. In the search stack's README, the commands always pass `--config`.
- [The warehouse keeps records of datasets that disappeared under PATH] → as after a full crawl. The purge of stale entries is in the backlog.
- [Paths that are not valid UTF-8] → already skipped by the walk (R35). PATH comes from the command line as text.

## Migration Plan

No database recreation (D5). Deploy by rebuilding the crawler image. Rollback: the old crawler ignores the `scope` column. Its `runs` and `modama-chain` would count earlier subtree runs as full crawls, which only affects the timer's catch-up and T.

## Not now

- Several paths in one crawl (`--path` repeated).
- A subtree crawl that takes over and reuses (`--force` off), for new data with unchanged code (D3).
- `crawl --format` or re-extraction without a walk (D7).
- The timer retrying later when a subtree crawl holds the lock.
- Subtree crawls below a format that adopts datasets of subdirectories (series, when it comes): keep or recompute the parent.
- A warning when a subtree crawl runs under rules other than the last full crawl's.
- Tombstones (`deletedRecord`) and the purge; the inotify watcher feeding subtree crawls (the decision log's "later, a watcher").

## Questions for @weber

- Request 2: is "bump `extractor_version` and run `crawl`" enough (lean, D7), or do you want `crawl --format em/dm4`, which re-extracts without a bump?
- Subtree crawls always run from scratch (lean, D3), or reuse what is stored unless `--force` is given?
- A file as PATH: does it stand for its directory (lean), is it an error, or should it mean "extract only this dataset, without recognition"?
- The `scope` column added in place (`ADD COLUMN IF NOT EXISTS`, lean, D5), the first schema step without recreating the database, or recreate it as the README says (on staging, a night of crawl, harvest and indexing)?
- If a subtree crawl blocks the nightly crawl, is skipping that night acceptable for now (lean), or should the timer retry?
- Glossary: "subtree crawl" and "crawl of the whole tree" as the terms. Should they go into `/CONTEXT.md` with the other crawler terms when those move there?
