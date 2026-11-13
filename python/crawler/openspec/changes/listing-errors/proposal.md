# Proposal

## Why

A folder below the crawl's start that cannot be listed loses its datasets and records today, whatever the reason (`BACKLOG.md`, "a folder that fails to list loses its records"; code review of `subtree-crawl`, finding 5). The walk skips it with "cannot list directory" (`walk.py`, `visit`), the result has no datasets under it, and `store()` deletes every dataset, extraction and record under it; the run ends `finished` with status 0. That is right when the file system says the folder is not visible to the crawler (permission denied, gone), and wrong when the file system did not answer (an I/O error, a stale handle, a time-out): the data is still there, and the next crawl adds it back. The same holds, on a smaller scale, for a file whose `access(2)`, MIME detection or format read fails (review of this proposal, findings 1 to 3).

Example (hypothetical: how staging's and production's crawlers mount the share is not known yet, item 291): the NFS share drops for 30 s during the 19:00 crawl, on a `soft` mount, where a request that times out returns `EIO` to the program (nfs(5), "soft / softerr / hard"; on the default `hard` mount the crawl waits instead); after a server failover the error is `ESTALE`. *Today:* every folder whose listing was in flight during those 30 s is skipped, with everything below it; thousands of records are deleted from the endpoint, their stored extractions with them; the run says `finished`, status 0, and nothing tells the admin. The next night the same datasets come back: extracted again (DM4 is the slow one: 18,294 s summed on staging, run 3), with new datestamps, harvested and indexed again. *After this change:* the run ends "finished with errors", exit status 4; those folders keep their stored datasets, extractions and records unchanged, datestamps included; `runs`, `modama-chain status` and the crawl's error lines name the folders, the error and for how many crawls they have been kept; the next crawl tries them again.

Decision 271 (@weber, 2026-11-13): "271 sounds like correct behavior if that came from the file system refusing to list it? Maybe distinguish permission denied or file not found (correct to remove) from I/O errors and timeouts (probably report loudly for the admin to handle, report error and mark for retry)?"

Serves R7 (the file system is in use; recognition reaches a consistent state), R8 and R36 (errors with context, an error where action is likely required, similar items summarised), R35 (what recognition sees; this change narrows its "files it cannot read and directories it cannot list are skipped" to what the file system refuses or says is gone) and R10 (a re-crawl only does work for what changed: no re-extraction after an outage).

## Assumptions (the leans of decision 271 and main's decisions on the review, accepted as the starting point)

- **A1. Two classes of `OSError`, by errno.** *Not visible* (`EACCES`, `EPERM`, `ENOENT`, `ENOTDIR`): the file system answered, and the answer is that the crawler may not see the path or that it is gone. Its datasets and records go, as today. *Did not answer* (every other errno, or none: `EIO`, `ESTALE`, `ETIMEDOUT`, `EAGAIN`, `ENOTCONN`, `EHOSTDOWN`, but also `ENAMETOOLONG`, `EOVERFLOW`, …): the stored datasets stay. Keeping a record one night too long costs less than deleting it and extracting it again; an errno that is about the name rather than the server (`ENAMETOOLONG`) then gives status 4 every night, which the README says (review 14).
- **A2. Nothing is taken over as unchanged.** A folder that did not answer is not counted as unchanged, its listing is not stored, and the next crawl lists and recognises it again.
- **A3. The run records it, and the crawl finishes the rest.** The run keeps outcome `finished` and records the folders that did not answer (folder, the path that failed, errno, datasets kept, since when and for how many crawls), at most 100 with the totals; `runs` and `modama-chain status` show `finished with errors`; every such folder gets an error line; the crawl exits with status 4.
- **A4. The harvest trigger still runs**, and the status stays 4 when it fails too.
- **A5. Files too:** an entry whose `stat` or `access` did not answer, a file whose MIME detection or format read did not answer (also when the format catches the error itself, as EMPAD does): the folder keeps its own stored datasets and the failed entry's stored subtree; its other subfolders are walked as usual. Not extraction: its failures are stored and tried again on every crawl already (`extractor-identity` D9), and its errors are kept as text without an errno (design, "Not now").
- **A6. The root and the folder of `crawl --path` stay errors** (status 2, run `failed`, nothing stored), whatever the errno, as today.
- **A7. Removals by "not visible" are loud** (review 6, @weber's item 287 re-asked; replaces the earlier lean of Q4, "nothing"): when a folder that has stored datasets is refused (`EACCES`, `EPERM`), a warning names it with the number of datasets removed; the run counts them and `runs` shows them. No guard: the crawl still removes them and exits 0. Example: staging's `group_add: STAGING_GROUP` (`docker-compose.staging.yml`) set wrong deletes the group's parts with status 0 today, without a word.

## What Changes

- A folder below the crawl's start whose listing, own `lstat` or pre-order call fails with an error of the "did not answer" class keeps its stored datasets and those of every folder below it, with their members, extractions and records unchanged; the walk does not enter it. Today a failing own `lstat` ends the whole crawl `failed` with status 2.
- A folder where an entry's `stat` or `access`, a file's MIME detection, or a format's read of a file fails with such an error keeps its own stored datasets and the failed entry's stored subtree; its other subfolders are walked and stored as usual.
- `access(2)` saying "no" is asked again with an `open(2)` for the errno: only `EACCES`/`EPERM` make a file "not readable" (review 2). The walk's MIME detection reports read errors instead of falling back silently (review 1): "not visible" keeps the fallback and gets a warning, "did not answer" keeps the folder.
- Kept datasets are not extracted again, not spot-checked, not counted as failed extractions, and keep their extraction also when their format has no extractor any more (review 10, 13); their records keep their datestamps.
- **The run records** the folders that did not answer, and the refused folders that had datasets, in two new columns of `crawl_runs` (migration `0004_crawl_runs_listing_errors`): totals, counts per errno, the first 100 folders by path. A folder kept again by the next crawl carries the time of the first crawl that kept it and the number of crawls. The outcome stays `finished`.
- **`modama-crawler runs`** shows `finished with errors` with the counts, the folders that did not answer and the refused folders; the state column is widened for it; `runs --follow` ends with status 4 for such a run.
- **`modama-chain status`** names the kept folders on its crawl line, and its freshness line says that T does not hold for them (review 7).
- **`crawl` exits with status 4** when a folder did not answer, after its store and its harvest trigger; one error line per folder (up to 100, then one summary line) and a closing error line; one warning per refused folder that had datasets.
- `records` and `modama-chain browse` walk without the stored state: a folder that did not answer is skipped as today, a file read that fails now gets a warning.

Behaviour towards the user: an admin sees a new state `finished with errors` in `runs` and `modama-chain status`, new error and warning lines in the crawl's log (the timer's container log), and the exit status 4 (the timer logs `crawl ended with status 4`). A harvester sees no change for the kept records, which keep their datestamps; today it saw them disappear from the endpoint and come back with new datestamps. A searcher sees no change: deletions do not reach the warehouse (`deletedRecord=no`); new files in a kept folder reach the search when the folder answers again. `records` shows a warning for a file it cannot read. No change for a folder the crawler may not read or that is gone, other than the warning when it had datasets.

Out of scope (design, "Not now"): extraction errors by errno; a time limit on file system calls; a guard that fails a crawl which would delete much; retrying a folder within the same crawl; formats adopting kept datasets of subfolders.

Open questions, each with a lean that the design follows: `design.md`, "Questions".

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `crawl`: the skip requirement is narrowed to the "not visible" errors; a folder or file that did not answer keeps its stored datasets; refused folders with datasets are warned about.
- `crawl-runs`: the run records the folders that did not answer and the refused ones; `runs` shows `finished with errors`; `crawl` exits with status 4.
- `harvest-trigger`: a crawl that finished with errors starts the harvest too.
- `chain-trace`: `modama-chain status` names the kept folders and qualifies T.

The `subtree-crawl` change, complete but not archived, modifies requirements of `crawl`, `crawl-runs` and `chain-trace`; this change adds requirements and modifies only "Entries that cannot make a useful record are skipped and logged", which `subtree-crawl` does not touch, so the two archive in either order.

## Impact

- `src/modama_crawler/walk.py`: the errno classes in use; `visit`, `_entries`, `_stat` and `recognise` keep the stored datasets of what did not answer, loaded after the walk in one query; `Result` lists the folders.
- `src/modama_crawler/formats/__init__.py`: `not_visible()`; `Directory` keeps the first "did not answer" error of a read, a detection or a format call; `Dataset.kept`; `Result.unanswered`, `Result.refused`.
- `src/modama_crawler/store.py`: `Stored` gives the stored datasets under folders and their counts, and loads its listings lazily; `end_run` and `Run` carry the two columns; the history of a kept folder.
- `src/modama_crawler/extraction.py`: kept datasets are left as stored.
- `src/modama_crawler/cli.py`: `crawl_tree` passes the stored state; `cmd_crawl` logs, records and exits with 4; `runs` shows the state and the folders.
- `src/modama_crawler/migrations/versions/0004_crawl_runs_listing_errors.py`, `schema.HEAD`.
- `python/search-chain`: reads `unanswered` behind the existing column probe; the status's crawl and freshness lines.
- `README.md` (exit statuses, "What to look out for"), `design/requirements.md` (R35), `design/architecture.md` (decision log), `BACKLOG.md`.
- No new dependency.
