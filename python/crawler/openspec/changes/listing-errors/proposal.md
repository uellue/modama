# Proposal

## Why

A folder below the crawl's start that cannot be listed loses its datasets and records today, whatever the reason (`BACKLOG.md`, "a folder that fails to list loses its records"; code review of `subtree-crawl`, finding 5). The walk skips it with "cannot list directory" (`walk.py`, `visit`), the result has no datasets under it, and `store()` deletes every dataset, extraction and record under it; the run ends `finished` with status 0. That is right when the file system says the folder is not visible to the crawler (permission denied, gone), and wrong when the file system did not answer (an I/O error, a stale handle, a time-out): the data is still there, and the next crawl adds it back.

Example: the NFS share drops for 30 s during the 19:00 crawl. The production compose file mounts the data share `soft,timeo=60` (`deploy/docker-compose.prod.yml`, volume `nfsdata`), and on a soft mount a request that times out returns `EIO` to the program (nfs(5), "soft / softerr / hard"); after a server failover the error is `ESTALE`. *Today:* every folder whose listing was in flight during those 30 s is skipped, with everything below it; thousands of records are deleted from the endpoint, their stored extractions with them; the run says `finished`, status 0, and nothing tells the admin. The next night the same datasets come back: extracted again (DM4 is the slow one: 18,294 s summed on staging, run 3), with new datestamps, harvested and indexed again. *After this change:* the run ends "finished with errors", exit status 4; those folders keep their stored datasets, extractions and records unchanged, datestamps included; `runs` and the crawl's error lines name the folders and the error; the next crawl tries them again.

Decision 271 (@weber, 2026-11-13): "271 sounds like correct behavior if that came from the file system refusing to list it? Maybe distinguish permission denied or file not found (correct to remove) from I/O errors and timeouts (probably report loudly for the admin to handle, report error and mark for retry)?"

Serves R7 (the file system is in use; recognition reaches a consistent state), R8 and R36 (errors with context, an error where action is likely required, similar items summarised), R35 (what recognition sees; this change narrows its "directories it cannot list are skipped" to the folders the file system says are not visible) and R10 (a re-crawl only does work for what changed: no re-extraction after an outage).

## Assumptions (the leans of decision 271, accepted as the starting point)

- **A1. Two classes of `OSError`, by errno.** *Not visible* (`EACCES`, `EPERM`, `ENOENT`, `ENOTDIR`): the file system answered, and the answer is that the crawler may not see the folder or that it is gone. The folder's datasets and records go, as today. *Did not answer* (every other errno: `EIO`, `ESTALE`, `ETIMEDOUT`, `EAGAIN`, `ENOTCONN`, `EHOSTDOWN`, …): the folder keeps its stored datasets, members, extractions and records unchanged. The default for an unknown errno is "did not answer", because keeping a record one night too long costs less than deleting it and extracting it again.
- **A2. Nothing is taken over as unchanged.** A folder that did not answer is not counted as unchanged, its listing is not stored, and the next crawl lists and recognises it again.
- **A3. The run records it, and the crawl finishes the rest.** The run keeps outcome `finished` and records the folders that did not answer (folder, the path that failed, errno, datasets kept), at most 100 of them with the total; `runs` shows the run as `finished with errors`; every such folder gets an error line; the crawl exits with status 4.
- **A4. The harvest trigger still runs.** The rest of the tree changed and should reach the search; the kept records keep their datestamps, so they are not harvested again.
- **A5. The same for a single file or entry** whose stat, MIME detection or format read fails with an error of the "did not answer" class: its folder keeps its stored datasets for the night. Not for extraction: its failures are stored and tried again on every crawl already (decision log 2026-11-12, `extractor-identity` D9), and its errors are kept as text without an errno (design, "Not now").
- **A6. The root and the folder of `crawl --path` stay errors** (status 2, run `failed`, nothing stored), whatever the errno, as today (spec `crawl`, "The root cannot be read"; `subtree-crawl` D3).

## What Changes

- A folder below the crawl's start (the root, or the folder of `crawl --path`) whose listing, whose own stat after the listing, the stat of one of its entries, or the pre-order call fails with an error of the "did not answer" class keeps its stored datasets and those of every folder below it, with their members, extractions and records unchanged; the walk does not descend into it.
- A folder whose MIME detection or post-order call fails on one of its files with such an error keeps its own stored datasets; the results of its subfolders, walked before it, stand.
- Kept datasets are not extracted again and not spot-checked; their records keep their datestamps.
- "Not visible" errors behave as today: the folder is skipped with an info line and its records go; an unlistable folder that was unlistable last time too still counts as unchanged.
- **The run records the folders that did not answer** in a new column `crawl_runs.unanswered` (migration `0004_crawl_runs_unanswered`): the total, the count per errno, and the first 100 folders by path, each with the path that failed, the errno and the number of datasets kept. The outcome stays `finished`, so the timer's catch-up, the subtree crawl's comparison with the last full crawl and `modama-chain`'s freshness time keep reading it as they do.
- **`modama-crawler runs`** shows such a run as `finished with errors`, with the count per errno and the first folders.
- **`crawl` exits with status 4** when a folder did not answer, after its store and its harvest trigger; one error line per folder (up to 100, then one summary line).
- The `records` command and `modama-chain browse` walk without the stored state: they show such a folder as skipped, with the error, as today.

Behaviour towards the user: an admin sees a new state `finished with errors` in `runs`, new error lines in the crawl's log (the timer's container log) and the exit status 4 (the timer logs `crawl ended with status 4`). A harvester sees no change for the kept records, which keep their datestamps; today it saw them disappear from the endpoint and come back with new datestamps. A searcher sees no change: deletions do not reach the warehouse (`deletedRecord=no`); the kept folders' new files reach the search one night later. No change for a folder the crawler may not read or that is gone, for `serve`, or for `records`.

Out of scope (design, "Not now"): extraction errors by errno; a time limit on file system calls (a hard NFS mount hangs instead of failing); failing a crawl that would delete more than a share of the index (a bound on deletions); `modama-chain status` and `trace` showing the kept folders; the freshness time excluding them; retrying a folder within the same crawl.

Open questions, each with a lean that the design follows: `design.md`, "Questions" (Q1 the outcome, Q2 status 4 over 3, Q3 the `runs` line, Q4 a guard against an `EACCES` that is not about the data, Q5 a new folder, Q6 extraction left out).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `crawl`: the skip requirement is narrowed to the "not visible" errors; a folder or file that did not answer keeps its stored datasets.
- `crawl-runs`: the run records the folders that did not answer; `runs` shows `finished with errors`; `crawl` exits with status 4.
- `harvest-trigger`: a crawl that finished with errors starts the harvest too.

The `subtree-crawl` change, complete but not archived, modifies requirements of `crawl` and `crawl-runs`; this change adds requirements and modifies only "Entries that cannot make a useful record are skipped and logged", which `subtree-crawl` does not touch, so the two archive in either order.

## Impact

- `src/modama_crawler/walk.py`: the errno classes; `visit` and `recognise` keep the stored datasets of a folder that did not answer, from a stored state given to the walk for that purpose; `Result` lists the folders.
- `src/modama_crawler/formats/__init__.py`: `Directory` keeps the first "did not answer" error that a format call or `cannot_read` met, so that the walk can see it.
- `src/modama_crawler/store.py`: `Stored` gives the datasets under a folder; `end_run` and `Run` carry `unanswered`.
- `src/modama_crawler/extraction.py`: kept datasets are left as stored.
- `src/modama_crawler/cli.py`: `crawl_tree` passes the stored state; `cmd_crawl` logs, records and exits with 4; `_run_line` shows the state and the folders.
- `src/modama_crawler/migrations/versions/0004_crawl_runs_unanswered.py`, `schema.HEAD`.
- `README.md` (exit statuses, "What to look out for"), `design/requirements.md` (R35), `design/architecture.md` (decision log row for 271), `BACKLOG.md` (the item closes; "Not now" items move there).
- No new dependency.
