# Review of the change `subtree-crawl` (2026-11-12)

Scope: the planning artifacts of `openspec/changes/subtree-crawl/` (proposal, design, tasks, four spec deltas) at e5e670d, before any code. Reviewed by an agent that did not write them, against @weber's request of 2026-11-12, `design/requirements.md`, the decision log, the main specs, the open changes `em-formats-and-extraction` and `parallel-walk`, and the code the change touches (`cli.py`, `walk.py`, `store.py`, `extraction.py`, `records.py`, `selection.py`, `python/search-chain`, the warehouse's DAG and `db_methods.py`, the search stack's compose files). D7 (request 2) is open and is reviewed for facts only. Nothing in the other artifacts has been changed; the *Decision* column is for @weber.

Each finding was checked against the code. **CONFIRMED** means read in the code (or run, where marked "ran"); **PLAUSIBLE** means it follows from the code and from documented behaviour of a tool that I did not run here (Docker, Airflow).

Severity: **H** deletes or corrupts index data, or breaks a stated contract with data consequences; **M** a reachable defect, or a contradiction between artifacts that an implementer would have to resolve by guessing; **L** cleanliness, wording, small risks.

Tally: 16 findings: 3 H, 8 M, 5 L (L5 collects several small points). 15 confirmed, 1 plausible (M8).

| # | Finding | Sev | Verdict | Decision |
|---|---|---|---|---|
| H1 | The subtree delete as written matches siblings (`a/b` also matches `a/bc`) | H | CONFIRMED (ran) | |
| H2 | PATH that cannot be listed during the walk gives an empty result, and the store deletes everything under PATH | H | CONFIRMED | |
| H3 | A forced re-extraction is stored under an unchanged extractor identity and reused by every later crawl | H | CONFIRMED | |
| M1 | Spec and design disagree on a collapsed PATH | M | CONFIRMED | |
| M2 | The open change's `extraction` requirements say SHALL take over / reuse; no delta exempts subtree crawls | M | CONFIRMED | |
| M3 | The data root as PATH is undefined, and the agreed rule "a file stands for its directory" reaches it | M | CONFIRMED | |
| M4 | Other rules (`--select`, `--ignore`, `--config`) make records that a full crawl would not make, the case D2 exists to prevent | M | CONFIRMED | |
| M5 | Fast turn-around through the warehouse: the harvest waits behind a running DAG run, and F17 can block it | M | CONFIRMED | |
| M6 | A PATH that is not UTF-8 crashes the store instead of exiting with 2; the design says it is already handled | M | CONFIRMED (ran) | |
| M7 | Missing scenarios for the data-safety cases | M | CONFIRMED | |
| M8 | On staging, a code change needs an image rebuild that recreates `crawl-timer` | M | PLAUSIBLE | |
| L1 | The start time of a run is no longer taken before the first listing (crawl-runs spec) | L | CONFIRMED | |
| L2 | `ADD COLUMN IF NOT EXISTS` takes an ACCESS EXCLUSIVE lock on every call | L | CONFIRMED (ran) | |
| L3 | `--path` with a `--root` other than the last full crawl's | L | CONFIRMED | |
| L4 | Rollback understates the effect on T | L | CONFIRMED | |
| L5 | Small points (tests cited, path forms, per-path ignores, docs) | L | CONFIRMED | |

## H. Data safety

### H1. The subtree delete as written also matches sibling directories

- **What.** D4 deletes "the datasets whose `directory` is PATH or below" and "the stored listings (`directories`) of PATH and below", and says "A prefix test on `directory` uses `starts_with()`". It does not say that the prefix ends at a path separator. `starts_with(directory, '/adhoc/a/b')` is also true for `/adhoc/a/bc` and `/adhoc/a/b_old`.
- **Where.** `design.md:29`, `:31`, `:33`; code it replaces: `store.py:425-428` (datasets), `:437-439` (listings), `:458-461` (records). Directory values carry a leading `/` and no trailing one (`walk.py:214`, `formats/__init__.py:273`).
- **Scenario.** The index holds `/adhoc/libertem/libertem-test-data/…` and `/adhoc/libertem/libertem-test-data-old/…`. `crawl --path adhoc/libertem/libertem-test-data` deletes every dataset of `…-old` (not in the result) and, by D4's second bullet, their records. The `…-old` records are re-created by the next full crawl with new datestamps; meanwhile the warehouse still has them, so no harm shows in the search, which hides the defect from the e2e test. It breaks "the index SHALL be unchanged outside it" (spec `crawl:6`, `:19`).
- **Verdict.** CONFIRMED: ran `SELECT starts_with('/adhoc/a/bc','/adhoc/a/b')` on PostgreSQL 17, which returns true. The design text allows the faulty reading. Task 2.4 tests `%` and `_`, not a sibling.
- **Fix.** Write the predicate in the design: `directory = PATH OR starts_with(directory, PATH || '/')`, with PATH normalised to a leading `/` and no trailing `/`. Use the same predicate for `directories.path`. Add a spec scenario "A sibling with the same prefix stays" (`a/b` and `a/bc`, also `a/b_` and `a/b%`) and cite it in task 2.4. The root needs its own rule (M3).

### H2. A PATH that cannot be listed during the walk empties the subtree

- **What.** D3 starts the walk at PATH with `rel = PATH`. Today `visit()` raises only when `rel == "/"`. For any other directory that cannot be listed, it records a skip and returns no datasets (`walk.py:245-256`). Started at PATH, a failed listing of PATH therefore gives an empty result. D4 then deletes every dataset under PATH that is not in the result, which is all of them, together with their records.
- **Where.** `design.md:26` (D3), `:29-30` (D4); `walk.py:248` (`if rel == "/": raise`); R35 (`design/requirements.md:55`: "the path the operator named on the command line being unreadable or missing is an error"); main spec `crawl`, scenario "The root cannot be read".
- **Scenario.** D2 lists PATH successfully. Seconds later the walk's `scandir` of PATH fails (`ESTALE` after an NFS server failover, `EACCES` after an ACL change, `EIO`). The run finishes, `records_changed` equals the subtree's record count, and every record under PATH is gone from the endpoint. The deletions do not reach the warehouse (`deletedRecord=no`), so the search looks fine while the crawler's index lost the subtree until the next full crawl.
- **Verdict.** CONFIRMED by reading `walk.py:242-256`. Tasks 2.1 and 2.2 do not mention it, and D2's check before the run does not close the window.
- **Fix.** Make the walk's start directory behave like the root: `if rel == start: raise`. The crawl then fails, the store is never reached, and the exit status is 2 as for an unreadable root (`cli.py:317-319`). Add a scenario "PATH cannot be listed when the walk reaches it" (simulate with a listing hook or permissions) to the requirement "A subtree crawl only covers what a full crawl enters".

### H3. A forced re-extraction is stored under an unchanged extractor identity

- **What.** D3 runs every extractor under PATH even when `extractor_version` is unchanged, which is the point of request 1. The result is stored as `(extractor, extractor_version, stamp)` with the old version label (`extraction.py:135-140`, `store.py:301-305`). From then on every crawl reuses it (`extraction.py:114-121`), and so does the next full crawl, which the spec requires ("The next full crawl takes over the extractions", spec `crawl:44-46`). So:
  1. The index holds, under one extractor identity, the output of two codes: the new code inside PATH and the old code everywhere else. That contradicts the open change's requirement "Each dataset SHALL record which extractor and which extractor version produced its metadata" (`em-formats-and-extraction/specs/extraction/spec.md:38-39`).
  2. A reverted experiment does not revert. A developer tries a change on `crawl --path X`, finds it wrong and reverts the code. The full crawls that follow reuse X's experimental extractions as long as the files are unchanged, and nothing documented undoes it except another `crawl --path X`. The experimental records stay in the warehouse.
  3. D7 alternative (a) is rejected because "the stored results then carry a version label that does not identify the code that produced them" (`design.md:39`). D3 has exactly this property, for a subtree instead of a format.
- **Where.** `design.md:26`, `:39`; `proposal.md:21`, `:25`; spec `crawl:33-46`; `extraction.py:114-121`; `cli.py:222` (extractions are reused across rule sets as well).
- **Scenario.** Staging: the DM extractor is edited in the image and `crawl --path adhoc/libertem/libertem-test-data` runs. The edit is reverted and the image rebuilt. The 19:00 crawl recognises the subtree again (no listings) and reuses the reverted-away extractions, because `(em/dm4, "2", stamp)` matches. The search keeps the experimental descriptions indefinitely.
- **Verdict.** CONFIRMED by reading. This is a fact about D3, which was agreed, not an objection to doing request 1 from scratch.
- **Fix (options for @weber).** (a) Keep D3 and document the consequence and the undo step (`crawl --path X` again after reverting) in the README procedure of task 4.2. (b) Store the subtree's forced extractions with `extract_retry = true`, so that the next full crawl runs them again with the deployment's code. That is cheap (one flag in `store`), but it replaces the scenario "The next full crawl takes over the extractions" with "…extracts them again". (c) Settle the extractor identity first (@weber's D7 remark: a hash unique to the code). With a code-derived identity, reuse never crosses a code change, so the forced run of D3 is no longer needed for correctness. In any case, add a scenario for the revert case.

## M. Contradictions, gaps and reachable defects

### M1. Spec and design disagree on a collapsed PATH

- **What.** D2: "PATH itself may be collapsed: it then becomes one dataset, as in a full crawl" (`design.md:24`). Spec: status 2 "when … it or a directory above it is a symlink, is excluded …, cannot be listed, or is a directory that a format collapses" (`specs/crawl/spec.md:49`). Read literally, the spec refuses `crawl --path some/store.zarr`. That is request 1 for a Zarr store, a `.git` or an environment. There is no scenario for a collapsed PATH.
- **Verdict.** CONFIRMED by reading.
- **Fix.** Reword the spec to "a directory above it is collapsed", and add the scenario "A collapsed directory as PATH" (one dataset, the same as in a full crawl).

### M2. The `extraction` requirements of the open change still say every crawl takes over and reuses

- **What.** `em-formats-and-extraction/specs/extraction/spec.md:27-28` says "A crawl SHALL take over the stored datasets of a directory … when … unchanged", and `:38-…` says "otherwise its stored result SHALL be reused". A subtree crawl is a crawl (D1) and does neither. This change has no delta for the `extraction` capability, so after both changes are archived the main specs contradict each other. Tasks only say "Archive … together with or after `em-formats-and-extraction`" (`tasks.md:41`).
- **Verdict.** CONFIRMED by reading.
- **Fix.** Add `specs/extraction/spec.md` with the two requirements MODIFIED to "a crawl of the whole tree", and point to "A subtree crawl recognises and extracts its subtree again". Settle the archive order in tasks.

### M3. The data root as PATH is undefined

- **What.** D2 and the spec speak of "a directory below the data root". Nothing says what `--path /`, `--path .` or an empty PATH do. The agreed rule "a file as PATH stands for its directory" makes the root reachable without anyone asking for it: `crawl --path README.txt`, for a file at the top level, has the data root as its subtree. With the predicate of H1, `'/' || '/'` matches only the top level's own datasets, so datasets that disappeared deeper down would never be deleted. With a special case, it is a full crawl recorded with a `scope` and without a rule set, which deletes every stored listing, so the next full crawl takes nothing over (1 h 17 min on staging instead of a take-over).
- **Where.** `design.md:24`, `:67`; `proposal.md:21-22`; spec `crawl:19`, `:29-31`, `:49`.
- **Verdict.** CONFIRMED by reading.
- **Fix.** Decide and specify one behaviour: either status 2 with "the data root is crawled by `crawl` without `--path`", or a full crawl (scope NULL, rule set recorded, nothing deleted from the listings). Add a scenario for it, including the file at the top level.

### M4. Other rules make exactly the records that D2 is there to prevent

- **What.** D1 offers `--config`, `--select` and `--ignore` "for free" with `--path`. D2 justifies its checks: "The check prevents records that a full crawl would not make, which would be harvested and never purged" (`design.md:24`). A subtree crawl under another selection makes such records. For example, `--select em/dm4` (the natural combination for request 1) turns every EMPAD, Merlin or other dataset under PATH into single-file datasets with other anchors. They get new identifiers and are harvested, and the next full crawl deletes them in the crawler only. Every such iteration leaves stale entries in the warehouse. The D2 checks also use the exclusions of the subtree crawl's own configuration, not the deployment's (a forgotten `--config`, `design.md:45`). The Risks section says that "D4 keeps the stored state consistent". That holds for the crawler, not for the warehouse.
- **Where.** `design.md:22`, `:24`, `:45`, `:60` ("Not now": a warning); `selection.py:138-166` (the fingerprint covers selection, exclusions and per-path ignores, and also format versions and distributions); `store.py:391-396`.
- **Verdict.** CONFIRMED by reading.
- **Fix (options).** (a) Refuse `--select`/`--ignore` with `--path`, and refuse a subtree crawl whose configuration (selection, exclusions, per-path ignores) differs from the last full crawl's. That needs the configuration stored apart from the code part of the fingerprint: comparing the whole fingerprint would also refuse the legitimate case of a bumped format version. (b) At least the warning from "Not now", now, with the consequence for the warehouse stated in the README. (a) costs a second digest column or a JSON of the configuration on the run.

### M5. The turn-around through the warehouse is not "one incremental harvest" while the warehouse is busy

- **What.** The claim that the harvest is incremental and covers the subtree's records holds (see "Right" below). The time claim does not always hold. The proposal says "A searcher sees those records re-indexed within the time of one incremental harvest" (`proposal.md:29`), and D6 that a running harvest "queues the new one". But the DAG run that is already active includes the indexing waits: `index_run` is a `TriggerDagRunOperator` with `wait_for_completion=True` and a one-day `execution_timeout` (`harvest_and_index.py:138-145`). With `max_active_runs=1` (`:37`), the subtree's DAG run starts only after the previous run's harvest and all its indexing. After a full crawl that changed much, that is hours (run 3: 5 h 14 min of harvest, then hours of indexing). Separately, F17 (on the `crawler` branch, commit b18a40a2, not yet in e5e670d): the default worker loses its broker connection after a task of more than 30 minutes and does not come back. The queued harvest "would wait in `default` with nobody to run it".
- **Facts for D7 (open).** D7's own estimate, about 40 minutes of harvest and one to two hours of indexing for about 170,000 DM records (`design.md:18`), is above F17's 30 minutes for both the harvest task and the wait for indexing. The format-wide procedure would therefore meet F17 on staging until F17 is fixed. At F16's 62 records/s the indexing is about 46 minutes, at 26 records/s about 1 h 50 min, so "45 minutes to two hours".
- **Verdict.** CONFIRMED by reading the DAG and F17. The e2e test (task 4.1) cannot show it: in the VM, harvests and indexing take minutes (F17: "Not seen in the VM").
- **Fix.** State the precondition in the proposal's behaviour paragraph and in D6 (no harvest DAG run active, the default worker alive). Make the staging measurement in "Workflow follow-up" check it first (Airflow's DAG runs, or `modama-chain status`), and list F17's fix as a prerequisite for the turn-around on staging. No crawler change is needed.

### M6. A PATH that is not UTF-8 crashes the store

- **What.** The design says that names which are not valid UTF-8 are "already skipped by the walk (R35). PATH comes from the command line as text" (`design.md:47`). Python decodes `argv` with `surrogateescape`, so such a PATH arrives as a string with lone surrogates. The walk checks only the names of entries it lists (`walk.py:199-206`), never the start directory or the directories above it. Every anchor under such a PATH contains the surrogate, and `oai_identifier` raises in the store.
- **Verdict.** CONFIRMED: ran `oai_identifier(os.fsdecode(b'/adhoc/caf\xe9/x'))`, which raises `UnicodeEncodeError: … surrogates not allowed` (`records.py:43`). The result is a failed run with a traceback. The transaction rolls back, so no data is lost, but the spec's "status 2 … no run recorded" for a path that a full crawl does not enter is not met (a full crawl skips that name with a warning).
- **Fix.** Refuse a PATH that does not encode as UTF-8 in the D2 checks, with status 2, naming it with `!r`. Add it to the requirement's list and a scenario. Correct the Risks line.

### M7. Missing scenarios for the data-safety cases

Every scenario in the deltas is testable and is cited by a task (2.2 to 2.5, 3.1 to 3.3; checked one by one). Missing, each a case that the design describes or that a finding above shows:
- a sibling with the same prefix stays (H1);
- PATH cannot be listed when the walk reaches it (H2);
- a reverted extractor change (H3);
- a collapsed directory as PATH (M1);
- the data root and a file at the top level (M3);
- a subtree crawl under other rules, followed by a full crawl (D4 claims consistency "whatever rules either crawl ran under"; M4);
- a symlink on the way, and a directory on the way that cannot be listed (both in the requirement text at `specs/crawl/spec.md:49`, no scenario);
- a PATH that is not UTF-8 (M6);
- `..` that stays inside the root (`adhoc/../other`, accepted after normalisation) and a trailing `/`.

**Fix.** Add them to the deltas and cite them in tasks 2.1 to 2.4.

### M8. On staging, a code change needs an image rebuild that recreates `crawl-timer`

- **What.** The image copies the sources and installs them editable from the copy (`crawler.Dockerfile`: `COPY . /src`, `pip install -e /src`). Every extractor edit for request 1 therefore needs a rebuild. `docker compose up --build` recreates `crawl-timer`. A crawl the timer is running gets SIGTERM and is recorded as `failed`. The new timer checks for catch-up at its start (`cli.py:401-403`). If the last full crawl ended more than a day ago, for example after the accepted skipped night (`design.md:43`, `:69`), it crawls the whole tree at once. Every `crawl --path` is then refused with status 1 for the length of a full crawl (1 h 17 min in run 3). D6 sends subtree crawls through `docker compose exec crawl-timer`, which ties them to that container's lifecycle. A process started with `docker compose exec` is also not the one that `docker stop` signals, so on a stop it is killed without a chance to record `failed`, and its run shows as stale (data safe: the transaction rolls back).
- **Verdict.** PLAUSIBLE: the Dockerfile and the timer's start are read in the code; Compose's recreate on `--build` and the way exec'd processes are stopped are documented Docker behaviour that I did not run here.
- **Fix.** Describe the development loop in task 4.2 and in the search stack's README: build the image, then run the subtree crawl as a one-off container of the same service, `docker compose run --rm crawl-timer modama-crawler --config … crawl --path …`. It gets the service's environment, including the Airflow account, the user and the mounts, from the new image, without recreating the timer, and `run` forwards signals to the crawl. Check that command in the e2e stack as task 4.2 asks.

## L. Small risks and cleanliness

### L1. The run's start time is no longer taken before the first listing

The crawl-runs delta keeps "The start time SHALL be taken before the first directory is listed" (`specs/crawl-runs/spec.md:6`). D2 lists the directories from the root down to PATH, and runs pre-order format calls on them, before any run is recorded (`design.md:24`). The run and its time are inserted together (`store.py:160-173`). For T this does not matter, since subtree crawls do not count for it, but the requirement as written is broken. **Fix:** "before the walk lists its first directory", or take the time before the checks and insert the run after them. CONFIRMED.

### L2. `ALTER TABLE … ADD COLUMN IF NOT EXISTS` locks the table on every call

Ran on PostgreSQL 17: the statement takes an ACCESS EXCLUSIVE lock on the table even when the column exists (NOTICE "already exists, skipping"). `ensure_tables` runs at every `crawl` (also a refused one), every `runs`, and at the start of `timer` and `serve` (`cli.py:270`, `:402`, `:454`, `:484`). While the lock is queued behind an open transaction on `crawl_runs`, the heartbeat's updates queue behind it. It stays short as long as the statement is the last one before the commit. Side observation, existing and not this change's: `CREATE INDEX IF NOT EXISTS` takes a SHARE lock on its table even when the index exists (ran), so `modama-crawler runs` already waits for a crawl's store transaction. **Fix:** check `information_schema.columns` first, or put the `ALTER` last; update the `ensure_tables` docstring ("There are no migrations: recreate the database after a change", `store.py:63`), which this step makes untrue. Recording the start of migrations (task 6.1) is right.

### L3. `--path` with a different `--root`

`--root` stays, and `--path` is relative to it. `crawl --root /data/adhoc --path libertem` on an index whose full crawls used `/data` makes anchors `/libertem/…`. The delete finds nothing to remove, the new records get identifiers of another root, they are harvested, and the next full crawl deletes them in the crawler only. **Fix:** refuse `--path` when the root differs from the last full crawl's `crawl_runs.root`, or document it with the `--root` help text of task 2.6. CONFIRMED (`cli.py:267`, `walk.py:354`).

### L4. Rollback understates the effect on T

"Its `runs` and `modama-chain` would count earlier subtree runs as full crawls, which only affects the timer's catch-up and T" (`design.md:51`). For T this is a false freshness claim: T jumps to a subtree crawl's start and states that every file older than that is in the search. **Fix:** say so, or delete the subtree runs' rows (or set their outcome aside) before a rollback. CONFIRMED (`search-chain/src/modama_chain/chain.py:299`).

### L5. Small points

- Task 2.4 and the proposal's Impact cite `test_store.py`, which does not exist. Task 2.5 puts the lock scenario in `test_trigger.py`, while the lock tests live in `tests/test_locks.py`. Say whether a new file is intended.
- `scope` is stored without a leading `/` (`design.md:35`), while anchors, `datasets.directory` and `directories.path` carry one. That is two forms in one database, which the chain reads as an interface. The form without the slash follows the glossary for display; consider storing what the other columns store and stripping it only for display.
- The pre-order check on the directories above PATH must use the formats active there after per-path ignores (`walk.py:186-187`, `formats_for`). Otherwise a per-path ignore of a collapse format gives a refusal that a full crawl would not give, or the opposite. Say so in D2.
- A PATH typed as the container's absolute path (`/data/adhoc/…`) is read as canonical and fails as "not found". The error line should name the data root it is relative to.
- `docker-compose.staging.yml:11-12` says "a first crawl of a subtree uses exclusions". Add it to task 4.2's documentation list, with the runbook.
- "Parents are set only by formats that adopt …, and none does today (`collection = True` nowhere)" (`design.md:33`): adoption is guarded by `parts`, not by `collection` (`formats/__init__.py:346-349`). It only warns when a non-collection format adopts. The fact holds today (no format returns `parts`), but the guard to name is "no dataset with parts".

## D7, facts only

- The references hold: `extraction.py:118` (reuse by extractor id, version and stamp), `modama_formats_em/dm/__init__.py:19` (`Dm.extractor_version`, shared by `Dm3` and `Dm4`, lines 83 and 89), and the 2026-10-16 decision "re-crawl rather than invalidate selectively" (`design/architecture.md:58`).
- The objection to (a) applies to D3 as well (H3). A code-derived extractor identity, as in @weber's remark, would also remove the need for D3's forced run for correctness. This is a fact about how the two interact, not a recommendation.
- The warehouse numbers meet F17 (M5): a harvest of about 40 minutes and an indexing wait of 45 minutes or more both exceed RabbitMQ's 30-minute `consumer_timeout`.
- `design/architecture.md:19` (2026-10-16) asks that "re-running recognition … for a path subset … must stay possible without a re-walk" (stage 3 from the index alone). This bears on alternative (b), and nothing in this change works against it.

## Right, and should stay

- **One option on `crawl` (D1).** The lock, run record, SIGTERM handling, report and harvest trigger come with it, and `--root` keeps its meaning with an honest help text.
- **Identifiers relative to the data root.** Starting the walk at PATH with `rel = PATH` keeps anchors, exclusions and per-path ignores relative to the root (`walk.py:214`, `:220`, `:187`), and the extractors get the data root (`extraction.py:177`, `root + dataset.anchor` in the DM reader).
- **One transaction, safe on SIGTERM.** `store()` checks before the commit, and the caller closes the connection on any failure, so the server rolls back (`store.py:481`, `cli.py:302`). Nothing in D4 needs a second transaction.
- **Records deleted by the identifiers computed from the deleted anchors** (`records.oai_identifier`), not by title or by `LIKE`. This handles hashed identifiers deterministically (SHA-256 of the anchor, `records.py:50`).
- **`starts_with()` instead of `LIKE`** for `%` and `_` (ran: correct for both), once the separator is fixed (H1).
- **No listings stored for the subtree, and no rule set on the run.** `previous()` keeps comparing against the last full crawl (`store.py:393-396`). The directories above PATH keep their listings, are recognised again (their subtree is not unchanged), and siblings are taken over. That costs little and is consistent whatever rules the subtree crawl used, for the crawler's own state.
- **The checks ask the file system** (`lstat`, an actual listing) rather than mode bits, as AGENTS.md requires.
- **The incremental harvest claim, verified in the warehouse code.** A new run's `from` is the `until` of the endpoint's last closed run (`db_methods.py:173-187`). `until` is the run's creation time (`tables.sql:96`), cut to seconds by the harvester (`harvester_oaipmh.py:343-348`). The crawler's `from`/`until` are inclusive (`server.py:270-273`), and the datestamp is taken after the store lock with 503 during the write (`store.py:457-463`). So a subtree crawl that commits during a running harvest is in that harvest or in the next window, never lost. The DAG indexes only runs closed since its own start (`harvest_and_index.py:57`, `:110`).
- **`scope` NULL for full crawls, with `last_finished()` and T on full crawls only.** That is the smallest change that keeps the timer and T honest, and the chain's check for the column follows its existing check for the table (`crawler.py:102`).
- **Scope.** Nothing beyond the three requests. Request 2 is left open instead of built, and the "Not now" list keeps the generality out. Every code reference in the design's Context section was checked and is correct for e5e670d.

## Not verified

- F17 is read from `design/field-tests/search-stack-staging-findings.md` on the `crawler` branch (commit b18a40a2), which is newer than this change's base and not in this worktree.
- That Airflow starts a triggered DAG run beyond `max_active_runs` once the active one ends (queued, not rejected): documented Airflow behaviour, not run here.
- Docker Compose's recreate on `up --build` and the signals that `exec`'d processes get (M8): documented behaviour, not run here.
- The count of about 170,000 DM records (D7, Non-Goals) is the design's own. Run 3 reports 177,166 extractions over all formats.
