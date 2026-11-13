# Design

## Context

What the code does today (`crawler` at 3684d362), and what shapes the approach:

- **A folder that cannot be listed.** `visit()` in `walk.py` catches the `OSError` of `_entries()` for every folder but the walk's start (the root, `top`, or the subtree crawl's path, which raise). It appends `(rel, "cannot list directory: …")` to `result.skipped`, logs an info line, stores the listing as `UNLISTABLE`, and returns no datasets. It returns "unchanged" when the stored listing was `UNLISTABLE` too, so that a folder that stays unreadable does not make its parent recognised again every night. The error's errno is not looked at.
- **The store deletes what the result lacks.** A full crawl's `store()` deletes every dataset (`anchor <> ALL(…)`), listing and record not in the result; a subtree crawl the same under its path (`subtree-crawl` D4). A dataset row carries its extraction, so a deleted dataset loses it, and the next crawl extracts it again.
- **Other places where an `OSError` reaches the walk.** (a) `_stat()` of an entry: a warning `cannot stat: …`, the entry left out of the listing. (b) `os.lstat(dirpath)` after the listing (`visit`): not caught; it ends the crawl as `failed`. (c) MIME detection of a file (`detect` in `_walk`): the file becomes `application/octet-stream`, a warning `cannot read: …`, and the listing is stored with `retry`. (d) `Directory.cannot_read`, from `not_of_type`: the file keeps its type, a warning, `retry` (spec `recognition`, "A read error on one file leaves the rest of the result", change `recognition-checks-content`). (e) A format call that raises (`_call` in `formats/__init__.py`, pre- and post-order): the format's result is discarded, a warning `… failed: …`, and `retry` when the exception is an `OSError`. (c) and (e) change the stored result: a type becomes `octet-stream`, or a format's datasets fall apart into single files; in the pre-order call (e), a Zarr store or an environment that is not collapsed is walked file by file. `retry` makes the next crawl recognise the folder again, but tonight's result is stored, its records changed, and harvested.
- **Extraction** catches every exception in the worker and keeps `repr(e)` as text (`extraction._run`); a failure is stored and tried again on every crawl (decision log 2026-11-12, `extractor-identity` D9). The errno is not kept.
- **NFS.** On a `hard` mount (the default) a request that gets no answer is retried for ever: the crawl waits, it does not fail. On a `soft` mount it fails with `EIO` after the retransmissions, with `softerr` with `ETIMEDOUT` (nfs(5)). The production compose file mounts the data share `soft,timeo=60` (`deploy/docker-compose.prod.yml`, volume `nfsdata`); how the crawler will mount it in production is not decided. `ESTALE` follows a server failover or a folder replaced on the server.
- **Runs.** `crawl_runs.outcome` is `finished` or `failed`; `last_finished()` (the timer's catch-up), `last_full_crawl()` (the subtree crawl's comparison) and `modama-chain` (`chain.py`: the freshness time T, `trace`) read `outcome = 'finished'`. Exit statuses of `crawl`: 0, 1 (another crawl runs), 2 (configuration, a refused `--path`, the root or the path unreadable), 3 (finished, but the harvest could not be started), 130, 143.

## Goals / Non-Goals

**Goals:** a folder the file system did not answer keeps what the index had for it, the admin is told which folders and why, and the next crawl tries again. A folder the file system says is not visible goes, as today.

**Non-Goals:** making NFS calls time out; extraction errors by errno; a guard against mass deletions; showing the kept folders in `modama-chain`.

## Decisions

**D1. Two classes, by errno (decision 271, A1).** One function in `walk.py`, `not_visible(err) -> bool`: true for `EACCES`, `EPERM`, `ENOENT`, `ENOTDIR`. Everything else, `OSError`s without an errno included, is "did not answer". *Why these four:* they are answers about the path (the crawler may not see it, it is gone, it is no longer a folder); the file system is the truth (AGENTS.md), and an answer that the crawler may not see a folder is what R18 ("whatever the crawl process can read") makes the scope. *Why the rest by default:* the errors that come up in practice on the share are `EIO`, `ESTALE`, `ETIMEDOUT` (Context); an errno nobody listed (`ENOMEM`, `EMFILE`, `EOVERFLOW`, `ELOOP`) is more likely trouble of the crawler or the client than an answer about the data, and keeping a record one night too long is cheaper than deleting it and extracting it again. *Strongest argument against:* an `EACCES` that is not about the data, for example a Kerberos ticket that expired during the crawl (NFS with `sec=krb5`), deletes everything at once. The share is not mounted with Kerberos today (`deploy/docker-compose.prod.yml`); Q4 asks whether to guard anyway.

**D2. A folder that did not answer keeps its stored subtree (A1, A2).** When, for a folder below the walk's start, the listing (`_entries`), its own `lstat` after the listing, the `_stat` of one of its entries, or a format's pre-order call fails with a "did not answer" error, `visit()`:
- returns the stored datasets of the folder and of every folder below it (`datasets.directory` is the folder or continues it after a `/`, the predicate of `subtree-crawl` D4), each with its stored members and extraction, as the folder's result. A dataset's `parent` is kept when it names a kept dataset and set to None otherwise, so that the folders above can adopt it as before (no format returns parts today; `subtree-crawl` D4);
- does not descend into the folder;
- stores no listing for the folder or below it. A full crawl's `store()` then deletes their stored listings, so the next crawl lists and recognises the whole kept subtree again (A2). Its extractions are reused there while the installation is the same. *Alternative:* keep the stored listings below the folder, so that the next crawl can take unchanged subfolders over. Wrong after a change of rule set: `previous()` is None then, the kept listings were made under the old rules, and the next crawl, under the new rules, would take over datasets recognised under the old ones (the same reason as `subtree-crawl` D4). The cost of deleting is one more recognition of the subtree;
- returns "not unchanged", so every folder above it is recognised again with the kept datasets among its children's results;
- records the folder in `result.unanswered`: the folder, the path that failed (the folder itself, or the entry), the errno's name and the number of datasets kept.

*Why the whole folder when one entry's `stat` fails:* the listing is incomplete, so the folder's recognition would run on a part of its files; the entry may be a folder whose subtree we cannot know. *Why the pre-order call:* a Zarr store or an environment whose marker file could not be read would be walked file by file (Context, (e)).

A "not visible" error keeps today's behaviour: the listing that fails is skipped with an info line and stored as `UNLISTABLE`; an entry whose `stat` fails is left out with a warning.

**D3. A file that did not answer during recognition keeps the folder's own stored datasets (A5).** When MIME detection, `Directory.cannot_read` or a format's post-order call meets a "did not answer" error, the folder's subfolders have been walked already (post-order), and their results stand. The folder keeps its *own* stored datasets (`datasets.directory` = the folder), stores no listing (so it is recognised again next crawl), and is recorded in `result.unanswered` with the file's path. A folder with nothing stored (new since the last crawl) keeps nothing: its records come with the next crawl that reads it (Q5). *Mechanism:* `Directory` keeps the first such error it meets (`cannot_read`, and `_call` for an exception that is an `OSError`), beside `retry`; `recognise()` returns it, the detections' errors too. *Alternative:* keep the whole stored subtree, as in D2, dropping the subfolders' fresh results. Simpler to state, but it throws away results that are right, and a persistent `EIO` on one file (a bad block on the server) would freeze the folder's whole subtree, not only its own datasets.

*Relation to `recognition`'s "A read error on one file leaves the rest of the result":* that requirement is about the walk's result, and stays: `records --verbose` and `modama-chain browse`, which walk without the stored state, still show the file with its type kept and the warning. What the crawl stores is the folder's stored datasets instead.

**D4. Where: the walk, given the stored state; the store unchanged.** The walk gets the stored datasets through a second argument, `kept` (a `Stored`), separate from `previous` (take-over). `crawl_tree` passes `Stored(conn)` for every crawl: also when the rule set changed (`previous` is None then: the kept datasets were recognised under the old rules, and stay until the folder answers), and also for a subtree crawl, which takes nothing over (`subtree-crawl` D3) but keeps folders below its path. `Stored` gets one method, `datasets_under(rel)`. Without `kept` (`records`, `browse`, tests) the walk behaves as today. *Why in the walk, not the store:* the folders above need the kept datasets among their children's results, the result's counts (datasets, warnings) stay true, and `store()` keeps one rule: what is in the result is stored, what is not is deleted. *Alternative:* the store excludes the unanswered folders from its deletes. Then the parent's recognition misses the children's datasets, and the store needs the anchors of records it did not see.

**D5. Kept datasets are not extracted (A5).** `extraction.extract` leaves a kept dataset with its stored extraction: no run, also not under another identity or after a stored failure, and no spot check. Otherwise a deployment on the night of an outage would try to extract the kept datasets from the folder that did not answer and store the failure, which changes the record. The `Dataset` carries a `kept` flag, set by the walk (not stored).

**D6. The collapsed datasets and the subtree scope.**
- A folder that did not answer and was stored as a collapsed dataset keeps it: the collapsed dataset's `directory` is the folder itself (`subtree-crawl` D4).
- A folder inside a collapsed dataset is never visited, so it cannot fail.
- A pre-order call that did not answer: D2, the folder is not entered.
- A subtree crawl: a folder below its path that did not answer is kept as in a full crawl; the store's delete under the path skips its datasets, since they are in the result. The subtree crawl stores no listings anyway. The path itself stays an error (A6).
- The root and `top` (`browse`) stay errors, as today (A6).

**D7. The run's record: `crawl_runs.unanswered` (A3).** Migration `0004_crawl_runs_unanswered` adds a nullable `JSONB` column; NULL for a run without such folders. Its value:

```json
{"total": 3, "by_errno": {"EIO": 2, "ESTALE": 1},
 "folders": [{"folder": "/adhoc/a", "path": "/adhoc/a", "errno": "EIO", "kept": 1234}, …]}
```

`folders` holds the first 100 by path. *The bound:* when a folder does not answer, nothing below it is visited, so only the top-most folders count; an outage of the whole share at the wrong moment can still give thousands. 100 lists a handful of real problem folders in full and shows the pattern of an outage, and the counts per errno are always complete (R36: "similar items are summarised in one line"). The outcome stays `finished` (Q1). The downgrade drops the column; the older code reads the run as `finished`. `schema.HEAD` becomes `0004_crawl_runs_unanswered`.

**D8. What the admin sees.**
- *Log:* one error line per folder, in path order, up to the same 100: `ERROR /adhoc/a: the file system did not answer (EIO: Input/output error, listing /adhoc/a); 1234 datasets kept from the last crawl, tried again next crawl`; then, above 100, `ERROR and 4321 more folders the file system did not answer (EIO 4000, ESTALE 321)`; after the report, `ERROR finished with errors: 3 folders the file system did not answer (EIO 2, ESTALE 1), their records kept`. The info line "skipped, cannot list directory" stays for the "not visible" class only.
- *`runs`:* the state reads `finished with errors` instead of `finished`, and the counts end with `; did not answer: 3 folders (EIO 2, ESTALE 1): /adhoc/a, /adhoc/b, /c/d` with up to three folders and `and N more` (Q3). One line per run stays (spec `crawl-runs`, `runs | head -1`).
- *Exit status 4*, "finished with errors", after the store and the harvest trigger (A3, Q2). 1 to 3 keep their meaning; 4 is the next free number. When the harvest cannot be started as well, the status is 4 and the harvest's error line stays (Q2). The timer logs `crawl ended with status 4` as for any non-zero status.

**D9. The harvest still starts (A4).** The rest of the tree changed and should reach the search; the kept records keep their datestamps, so the incremental harvest does not take them again. The run is `finished`, so `modama-chain`'s freshness time moves past it, although new files in a kept folder are not in the index yet (Risks).

## Risks / Trade-offs

- [A folder that never answers again (a bad block, a broken export)] → its records stay as they were, and every crawl ends with status 4 and names it. Intended: the admin decides (decision 271, "report loudly for the admin to handle").
- [An `EACCES` that is not about the data] → as today, everything under it is deleted (D1, Q4).
- [The freshness time overstates for kept folders] → `modama-chain status` claims that files older than T are in the search; for a kept folder that holds only until its last good crawl. `runs` names the folders; `modama-chain` showing them is "Not now".
- [A hard mount hangs] → the crawl waits, its run stays `running` (the heartbeat is a thread of its own), and the timer's next crawl is refused by the crawl lock. Unchanged by this change.
- [A kept dataset under new rules] → after a change of rule set, a kept folder's datasets stay as recognised under the old rules until it answers (D4).
- [The `recognition` requirement and the store disagree for one night] → `records --verbose` shows the fresh result with the type kept, the index the stored one (D3). The warning names the error in both.

## Migration Plan

Deploy by rebuilding the crawler image; `modama-crawler migrate` (the service `crawler-migrate`) applies `0004_crawl_runs_unanswered`. Rollback: its downgrade drops the column, run with the newer code before going back (README, "Upgrade").

## Not now

- Extraction errors by errno (A5): a "did not answer" failure under a new identity replaces a stored success with a failure for one night (`extraction.extract`); needs the errno kept from the worker. Backlog, with the example: a deployment and an outage on the same night.
- A time limit on file system calls, or retrying a folder within the same crawl.
- A guard that fails a crawl which would delete more than a share of the index (Q4).
- `modama-chain status` and `trace` naming the kept folders; T excluding them.
- `records` exiting non-zero for a folder that did not answer.

## Questions

Each with a lean; the leans are the design above.

- **Q1 A new outcome, or `finished` with a column?** *Lean: outcome `finished`, the folders in `unanswered`, `runs` shows `finished with errors`.* The timer's catch-up, the subtree crawl's comparison and `modama-chain` (T, `trace`) read `outcome = 'finished'`; a new outcome would need each of them, and `modama-chain` across crawler versions, to learn it. *Against:* a reader of `crawl_runs` that is not ours sees `finished` and nothing else.
- **Q2 Exit status 4, and 4 over 3?** *Lean: 4 for "finished with errors"; when the harvest could not be started too, still 4,* since the data is the admin's first concern and both error lines are in the log. *Against:* 3 is the more urgent to act on (the search stops moving until the next crawl), and a script that checks for 3 misses it.
- **Q3 The `runs` line.** *Lean: the state `finished with errors`, the counts per errno and up to three folders on the run's line.* *Against:* the full list (100) needs SQL (`crawl_runs.unanswered`), which the rule "own instruments first" counts as a gap; a `runs --errors` or a line per folder below the run would close it, as a next step if asked.
- **Q4 A guard against an `EACCES` that is not about the data?** *Lean: no, not now* (D1): no case hit, the share is not mounted with Kerberos. *Against:* one expired credential deletes the whole index from the endpoint and its extractions.
- **Q5 A new folder with one file that did not answer.** *Lean: it keeps what is stored, which is nothing,* so its records come one night later. *Against:* the fresh result, with the file typed `application/octet-stream`, would give the other files their records tonight; but then a folder's result would depend on whether it is new.
- **Q6 Extraction errors stay out (A5).** *Lean: yes,* "Not now" with a backlog item; the brief's "where the code distinguishes these cases today" does not hold for extraction (the errno is lost in `repr(e)`).
