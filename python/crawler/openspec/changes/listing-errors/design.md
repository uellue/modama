# Design

## Context

What the code does today (`crawler` at 89e16a57), and what shapes the approach:

- **A folder that cannot be listed.** `visit()` in `walk.py` catches the `OSError` of `_entries()` for every folder but the walk's start (the root, `top`, or the subtree crawl's path, which raise). It appends `(rel, "cannot list directory: …")` to `result.skipped`, logs an info line, stores the listing as `UNLISTABLE`, and returns no datasets. It returns "unchanged" when the stored listing was `UNLISTABLE` too, so that a folder that stays unreadable does not make its parent recognised again every night. The errno is not looked at.
- **The store deletes what the result lacks.** A full crawl's `store()` deletes every dataset (`anchor <> ALL(…)`), listing and record not in the result; a subtree crawl the same under its path (`subtree-crawl` D4). A dataset row carries its extraction, so a deleted dataset loses it, and the next crawl extracts it again.
- **Other places where an `OSError` reaches the walk.** (a) `_stat()` of an entry: a warning `cannot stat: …`, the entry left out. (b) `os.access()` in `_stat()` returns False on any failure, so a transient `EIO` skips a file as "not readable" and its record goes (review 2). (c) `os.lstat(dirpath)` after the listing: not caught; it ends the crawl `failed`, status 2. (d) MIME detection in the walk calls `mime.detect_with_tie` without `strict`, which falls back to the name's candidates or `application/octet-stream` on any read error: no warning, no retry; the walk's `isinstance(got, OSError)` branch is dead (review 1, the reviewer's probe). (e) `Directory.cannot_read`, from `not_of_type`: the file keeps its type, a warning, `retry` (spec `recognition`, "A read error on one file leaves the rest of the result"). (f) A format call that raises (`_call`): the format's result is discarded, a warning, `retry` for an `OSError`. (g) A format that catches the error itself (EMPAD wraps `d.read` in `except Exception`): no trace at all, its dataset falls apart into single files (review 3). In the pre-order call, (f) and (g) can leave a Zarr store or an environment uncollapsed, and it is walked file by file.
- **Extraction** catches every exception in the worker and keeps `repr(e)` as text; a failure is stored and tried again on every crawl (`extractor-identity` D9). The errno is not kept.
- **NFS.** On a `hard` mount (the default) a request that gets no answer is retried for ever: the crawl waits. On a `soft` mount it fails with `EIO` after the retransmissions, with `softerr` with `ETIMEDOUT` (nfs(5)). `nfsdata` in `deploy/docker-compose.prod.yml` is the WebDAV backend's loopback mount, not the crawler's (review 9); staging bind-mounts a host mount whose options are not known (item 291).
- **Runs.** `crawl_runs.outcome` is `finished` or `failed`; `last_finished()` (the timer's catch-up), `last_full_crawl()` (the subtree crawl's comparison) and `modama-chain` (the freshness time T) read `outcome = 'finished'`. Exit statuses of `crawl`: 0, 1, 2, 3 (the harvest could not be started), 130, 143.

## Goals / Non-Goals

**Goals:** what the file system did not answer keeps what the index had for it, the admin is told which folders, why and since when, and the next crawl tries again. What the file system refuses or says is gone goes, as today, and a refused folder that had datasets is named.

**Non-Goals:** making NFS calls time out; extraction errors by errno; a guard against mass deletions.

## Decisions

**D1. Two classes, by errno (decision 271, A1).** `not_visible(err) -> bool` in `formats/__init__.py` (the walk and `Directory` both need it; `walk` imports `formats`): true for `EACCES`, `EPERM`, `ENOENT`, `ENOTDIR`. Everything else, an `OSError` without an errno included, "did not answer". *Why these four:* they are answers about the path (the crawler may not see it, it is gone, it is no longer a folder); the file system is the truth (AGENTS.md), and what the crawler may not see is out of scope (R18). *Why the rest by default:* the errors that come up on a share are `EIO`, `ESTALE`, `ETIMEDOUT`; an errno nobody listed is more likely trouble of the client than an answer about the data, and keeping a record one night too long is cheaper than deleting it and extracting it again. *Strongest argument against:* an `EACCES` that is not about the data (a wrong supplementary group, an expired Kerberos ticket) deletes everything under it. A7 makes that loud instead of guarding (D10).

**D2. A folder that did not answer keeps its stored subtree.** When, for a folder below the walk's start, the listing, its own `lstat` after the listing, an entry's `stat` or `access` (D5), or the pre-order call meets a "did not answer" error, `visit()` does not enter it, stores no listing for it, returns "not unchanged" (so every folder above is recognised again) and notes the folder as kept *with its subtree*. After the walk, its stored datasets and those of every folder below it are added to the result (D4), each with its stored members and extraction. A dataset's `parent` is kept when it names a kept dataset, else None (no format returns parts today; `subtree-crawl` D4). The stored listings below the folder are not carried over, so a full crawl's `store()` deletes them and the next crawl recognises the subtree again (A2): keeping them would let the next crawl take over datasets recognised under an older rule set (`previous()` is None after a change of rules, `subtree-crawl` D4). The cost is one more recognition of the subtree; extractions are reused.

*The pre-order call:* `Directory` notes the first "did not answer" error of `read()` (before it re-raises), of `not_of_type`'s detection, or of a format call that raises one. When the pre-order call noted one, the folder is kept with its subtree, whatever any format answered: a lower-priority format that collapsed the folder after a higher one failed to read (review 12) is the same night's guess as a format that did not collapse it.

*The folder's own `lstat` "not visible"* (`ENOENT`: removed between its listing and the `lstat`): skipped like a folder that cannot be listed, no longer the end of the crawl.

*An entry's `stat` or `access`* (code review 1, main's decision): the listing is incomplete, so the pre-order call's answer on it is a guess; the code review's S5 showed a new Zarr store whose `zarr.json` did not answer, walked file by file one night (a chunk record, harvested, left in the warehouse) and collapsed the next. So the folder is kept whole and not entered, before the pre-order call. A folder with nothing stored keeps nothing (Q5): a new store's records come the night it answers.

*The walk's start* (code review 2, A6): kept whole, the root or the folder of `crawl --path` would keep every stored dataset and drop every stored listing, and the next crawl would take nothing over (S3: listings 13 → 0). So a "did not answer" error of its pre-order read or of one of its entries' `stat` ends the crawl, as its listing does: status 2, the run `failed`, nothing stored. A file read in its post-order call (D3) keeps only its own datasets and does not end the crawl.

**D3. A file that did not answer in the post-order call keeps the folder's own stored datasets.** When a file's MIME detection (D6) or a format's read in the post-order call meets a "did not answer" error, the folder's subfolders have been walked (post-order: their results come first), were entered on a complete listing, and stand. The folder is noted as kept *alone*: after the walk, its own stored datasets (`datasets.directory` = the folder) are added. The folder stores no listing; its fresh datasets are dropped. *Why not the whole subtree* (the first version of this design): it throws away subfolder results that are right, and a persistent `EIO` on one file (a bad block on the server) would freeze the folder's whole subtree (review 5). *A folder stored as collapsed* whose own recognition did not answer: its stored collapsed dataset contains the subfolders, so the folder is kept with its subtree instead, and the fresh results below it are dropped. A folder with nothing stored (new since the last crawl) keeps nothing: its records come with the next crawl that reads it (Q5).

*Relation to `recognition`'s "A read error on one file leaves the rest of the result":* that requirement is about the walk's result, and stays: `records --verbose` and `modama-chain browse`, which walk without the stored state, show the file with its type kept and the warning. What the crawl stores is the folder's stored datasets instead.

**D4. Where: the walk notes, one query loads.** The walk gets the stored state through a second argument, `kept` (a `Stored`), separate from `previous` (take-over). `crawl_tree` passes `previous` when the rule set is the same, else a new `Stored(conn)`, for every crawl, also a subtree crawl, which takes nothing over (`subtree-crawl` D3) but keeps folders below its path. Without `kept` (`records`, `browse`, tests) the walk behaves as today. During the walk, kept folders are only noted; at its end, one call `kept.stored(subtrees, folders)` loads them (review 11): one `SELECT DISTINCT directory FROM datasets` (an index-only scan of `datasets_directory`), the directories at or below each folder found in Python by walking each directory's ancestors, then one `WHERE directory = ANY(…)` with the members. A `starts_with` per folder would scan the table once per folder: thousands of scans in an outage. `Stored` loads its listings on first use, so that a subtree crawl does not read them for nothing. *Why in the walk, not the store:* the result's counts stay true, the extraction sees the kept datasets, and `store()` keeps one rule: what is in the result is stored, what is not is deleted. *Limit:* the folders above a kept folder do not see its datasets among their children's results; no format adopts children's datasets today ("Not now").

**D5. `access(2)` asked again.** `os.access()` returns False on every failure. When it says no for a regular file, `_stat()` asks `open(2)` for the errno, with `O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_NOCTTY` (code review 3: a file that became a FIFO in between would block the thread; one that became a symlink is not followed): `EACCES`, `EPERM` and `ELOOP` (now a symlink, which a crawl skips) make the file "not readable" (skipped, as today); success makes it readable; `ENOENT`, `ENOTDIR` (gone in between) a `cannot stat` warning, as for a failing `lstat`; any other error is an entry that did not answer (D2).

**D6. The walk's MIME detection reports read errors** (review 1; same data, same result or a failure). The walk calls `detect_with_tie(…, strict=True)`. A "not visible" error falls back as today (the name's candidates or `application/octet-stream`, `mime.without_content`, without reading the file again: code review 6), now with the warning `cannot read: …` and `retry`; a "did not answer" error keeps the folder (D3), or, without `kept`, falls back with the same warning.

**D7. Kept datasets are left as stored** (reviews 10, 13). `Dataset.kept` (set by the walk, not stored). `extraction.extract` does not run, reuse or spot-check them, leaves their extraction also when their format has no extractor any more, and does not count a stored failure of theirs in `failed` or warn about it. Their records are built from the stored dataset, so their metadata and datestamps stay, with one exception (code review 8): a kept dataset whose format is no longer enabled (the rule set changed in the same night) is named in its record by its format id instead of the display name (`records.subjects`), so its record changes and is harvested again; so does a change of a display name, as for any record.

**D8. The run's record: two columns** (A3, A7). Migration `0004_crawl_runs_listing_errors` adds `unanswered JSONB` and `refused JSONB`, nullable; NULL for a run without such folders.

```json
"unanswered": {"total": 3, "kept": 1236, "by_errno": {"EIO": 2, "ESTALE": 1},
  "folders": [{"folder": "/adhoc/a", "path": "/adhoc/a", "errno": "EIO", "kept": 1234,
               "whole": true, "since": "2026-11-11T19:00:00Z", "crawls": 3}, …]}
"refused": {"total": 2, "removed": 340,
  "folders": [{"folder": "/groups/x", "errno": "EACCES", "removed": 300}, …]}
```

`folders` holds the first 100 by path. *The bound:* when a folder does not answer, nothing below it is visited, so only the top-most folders count; an outage of the whole share can still give thousands. 100 lists a handful of real problem folders in full and shows the pattern of an outage, and the totals are always complete (R36). *`since` and `crawls`* (review 5): from the newest earlier finished run that covered the folder (a crawl of the whole tree, or a subtree crawl whose path holds it; one query per recorded folder, so that subtree crawls elsewhere do not push it out, code review 4): when it listed the folder, or a folder above it kept whole (`whole`), its `since` and `crawls + 1`, else this run's start and 1; a folder beyond that run's first 100 starts again at 1. The outcome stays `finished` (Q1). The downgrade drops both columns; older code reads such a run as `finished`. `schema.HEAD` becomes `0004_crawl_runs_listing_errors`.

**D9. What the admin sees.**
- *Log:* in path order, up to 100 error lines `ERROR /adhoc/a: the file system did not answer (EIO: Input/output error, at /adhoc/a/x.dm4); 1234 datasets kept, for 3 crawls since 2026-11-11T19:00:00Z; tried again next crawl`, then `ERROR and 4321 more folders the file system did not answer (EIO 4000, ESTALE 321)`; after the report, `ERROR finished with errors: 3 folders the file system did not answer (EIO 2, ESTALE 1), 1236 datasets kept`. A refused folder that had datasets: `WARNING /groups/x: refused (EACCES); its 300 datasets are removed from the index`, up to 100, then one summary line.
- *`runs`:* the state `finished with errors`, the counts as for `finished`, then `; did not answer: 3 folders (EIO 2, ESTALE 1): /adhoc/a (3 crawls), /adhoc/b, /c/d` with up to three folders and `and N more`, and `; refused: 2 folders, 340 datasets removed: /groups/x, /groups/y`. The state column is as wide as `finished with errors` for every line, so that the columns stay aligned (review 8). One line per run stays. `runs --follow` ends with status 4 for such a run (review 8, lean).
- *Exit status 4*, "finished with errors", after the store and the harvest trigger; 4 also when the harvest could not be started (Q2), with the harvest's error line. A refused folder alone leaves the status 0 (A7).
- *`modama-chain status`* (review 7): the crawl line shows `finished with errors` and the same `did not answer` part (behind the existing column probe, so it works against an older crawler); when the crawl that gives T kept folders, the freshness line adds `, except where that crawl kept the stored state: 1 folder (EIO 1): /adhoc/a`. The state column of the crawl, harvest and indexing lines is as wide as `finished with errors` (code review 5).

**D10. Refused folders are loud, not guarded** (A7, review 6). When a folder's listing or own `lstat`, or an entry's `stat` from its parent's listing (code review 7), fails with `EACCES` or `EPERM`, the walk notes it; after the walk, one count query (D4's directory lookup) gives the stored datasets under each. Those with datasets become `result.refused` and the warning of D9; the store removes their datasets as today. `ENOENT` is not counted: a folder that is gone is an ordinary deletion.

**D11. The collapsed datasets and the subtree scope.**
- A folder that did not answer and was stored as one collapsed dataset keeps it: its `directory` is the folder itself (`subtree-crawl` D4).
- A folder inside a collapsed dataset is never visited, so it cannot fail.
- A subtree crawl: a folder below its path that did not answer is kept as in a full crawl; the store's delete under the path spares its datasets, since they are in the result; the subtree crawl stores no listings anyway. The path itself stays an error (A6).
- The root and `top` (`browse`) stay errors (A6).

## Risks / Trade-offs

- [A folder that never answers again (a bad block, a broken export, a name the client rejects)] → its datasets stay as they were, and every crawl ends with status 4 and names it, with the number of crawls. The admin's options are in the README: repair it, or exclude it with `[crawl] exclude`, which changes the rule set's fingerprint, so the next crawl recognises the whole tree again (1.5 million files on staging) and removes the folder's records.
- [An `EACCES` that is not about the data] → as today, everything under it is deleted, now with a warning per folder and a count in the run (D10, Q4).
- [The freshness time overstates for kept folders] → `modama-chain status` says so (D9).
- [A hard mount hangs] → the crawl waits, its run stays `running`, and the timer's next crawl is refused by the crawl lock. Unchanged by this change.
- [A kept dataset under new rules] → after a change of rule set, a kept folder's datasets stay as recognised under the old rules until it answers (D4); one whose format is no longer enabled gets the format id in its record's subject (D7).
- [One entry's `stat` keeps a whole folder] → a persistent `EIO` on one entry's `stat` freezes the folder's subtree, and new files below it wait for the folder to answer (D2, code review 1); the error line names the entry.
- [`modama-chain trace` does not say that a file sits in a kept folder] → a new file there shows "missing" without the reason; a backlog item.
- [`records` and the index disagree for one night] → `records --verbose` shows the fresh result with the warning, the index the stored one (D3).

## Migration Plan

Deploy by rebuilding the crawler image; `modama-crawler migrate` (the service `crawler-migrate`) applies `0004_crawl_runs_listing_errors`. Rollback: its downgrade drops the columns, run with the newer code before going back (README, "Upgrade").

## Not now

- Extraction errors by errno (A5): a "did not answer" failure under a new identity replaces a stored success with a failure for one night (`extraction.extract`); it needs the errno kept from the worker. Backlog, with the example: a deployment and an outage on the same night.
- A time limit on file system calls, or retrying a folder within the same crawl.
- A guard that fails a crawl which would delete more than a share of the index (Q4).
- Formats that adopt datasets of subfolders seeing kept datasets among their children (D4).
- `records` exiting non-zero for a folder that did not answer.

## Questions

Each with a lean; the leans are the design above. @weber's items 284 to 289 are open.

- **Q1 A new outcome, or `finished` with a column?** *Lean: outcome `finished`, the folders in `unanswered`, `runs` and `modama-chain status` show `finished with errors`.* The timer's catch-up, the subtree crawl's comparison and `modama-chain` read `outcome = 'finished'`. *Against:* a reader of `crawl_runs` that is not ours sees `finished` and nothing else.
- **Q2 Exit status 4, and 4 over 3?** *Lean: 4; still 4 when the harvest could not be started too,* since the data is the admin's first concern and both error lines are in the log. *Against:* 3 is the more urgent to act on, and a script that checks for 3 misses it.
- **Q3 The `runs` line.** *Lean: the state, the counts per errno and up to three folders on the run's line.* *Against:* the full list (100) needs SQL; a `runs --errors` would close it, as a next step if asked.
- **Q4 A guard against an `EACCES` that is not about the data?** *Lean (the reviewer's, adopted by main): no guard; refused folders that had datasets are warned about and counted (D10).* *Against:* a guard would keep the records through one bad night; the warning only says what was lost.
- **Q5 A new folder with one file that did not answer.** *Lean: it keeps what is stored, which is nothing,* so its records come one night later. *Against:* the fresh result would give the other files their records tonight; but a folder's result would then depend on whether it is new.
- **Q6 Extraction errors stay out (A5).** *Lean: yes,* "Not now" with a backlog item; the errno is lost in `repr(e)`.
