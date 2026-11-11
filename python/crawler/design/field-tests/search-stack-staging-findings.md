# Findings: the search stack on real data (staging)

The record of the staging field test (`search-stack-staging-runbook.md`), kept across
runs: each run adds its measurements, each finding keeps its ID, and a later run checks
whether a fix worked as intended in staging. Evidence (recordings, monitor logs) is in
the private `.claude/field-tests/run-<n>/` and is not committed.

Layers: **crawler**, **search-chain** (`modama-chain`), **stack** (the composition,
`prototypes/search-stack/`), **warehouse** (EOSC upstream), **method** (the field test
itself).

## Runs

### Run 1, 2026-11-10: `adhoc/libertem` (`stagingconf/libertem.toml`)

Commit 9bc9efd on `crawler` (rebased onto GitHub `master`). The dev server: 24 cores
(about 45 threads used at once), 251 GB RAM, Docker's root on `/cachedata`.

- **Start:** `./upstaging.sh --build`, all 14 services healthy after 77 s; peak load 11.4.
- **Crawl:** 16:15:11 to 16:18:46 UTC (3 min 35 s): 59 directories, 21,857 files, 21,854
  datasets, 2 warnings; about 100 files/s; one core at about 77 %.
- **Harvest:** started 16:18:46, closed by 16:23:33 (about 4.5 min for 21,854 records).
- **Indexing:** 16:23:33 to 16:37:05 (13.5 min for 21,854 records, about 27/s on
  average; 18/s measured at 16:26). Then `modama-chain status`: fresh as of 16:15:11
  (the crawl's start), every file with a ctime before it in the search.
- **Memory:** search API 2.6 GB (the embedding model), OpenSearch 1.4 GB, the rest
  below 0.7 GB each.
- **Disk:** `/` 84 % (71 GB free), `/cachedata` 84 % (919 GB free), unchanged by the run.

### Run 2, 2026-11-10/11: the whole tree (`stagingconf/full.toml`), overnight

Commit d2bb41d. Changed from run 1: the whole tree; indexing batches of 2,000 instead of
250 and four at once instead of one (F9). Started by the crawl timer at 19:00 UTC, with
`monitor.sh` and `nfs-stats.sh` (`run-1/nfs.log`, the mount's NFS counters, cumulative:
take differences) running. Results: to be added.

Interim, 20:23 UTC (1 h 23 min in): crawl running, 20,432 directories and 74,525 files,
about 1,000 files/min (16/s, run 1: 100/s); load 2 to 8, the crawler at about 5 % CPU:
waiting for NFS, see F12. Harvest and indexing not started yet.

Interim, 2026-11-11 05:25 UTC (10 h 25 min in): crawl still running, 32,768 directories
and 711,973 files; harvest and indexing not started, so the search still shows run 1.
Files per hour vary from about 20,000 to 110,000 (large directories, F6; files a glob
names need no read). About 306 GB received over NFS since 19:00 (30 to 45 GB per hour).
The crawler's container grew from 270 MiB to 1.9 GiB, see F13. Disk unchanged (84 %).
`df -i` of the mount: 2,286,248 inodes used (the server's file system, so at most
that many files and directories in the tree): the crawl is about a third through.

## Findings

**F1 (crawler): a Merlin frame series becomes 19,601 datasets.**
`libertem-test-data/many_mib` holds 19,601 `.mib` frames, each its own dataset: 90 % of
the run's records, and most search hits. Same shape, smaller: the `img/` folders of the
Dr. Probe and muSTEM simulations in `2023-10-23-simulation-dso-4dstem/raw/` (510 to 512
each), `200_20190328_185735` (257), `20200518+165148` (65).
Expected after the fix: `many_mib` is one dataset (or one per acquisition), the
simulation exports one each (the producer type the survey describes). Planned:
"Next formats" in `../../BACKLOG.md` (series directories, Merlin `.hdr`+`.mib`).
Recheck: `counts.py` (the largest directories by records) and the dataset count of the
run.

**F2 (crawler): two broken EMPAD cases from LiberTEM's own test data, handled.**
`EMPAD/Magical_DataSet/acquisition_1/acquisition_1_bad.xml` names a raw file another
header already claims; `EMPAD/acquisition_series_pretty.xml` names a missing
`series_x1000.raw`. Both reported as warnings, as designed. Candidates for reproducers
in the EMPAD collection's tests (requirements R27).

**F3 (crawler): a symlink skipped.** `libertem-test-data/Capture52/Capture52.raw` is a
symlink, skipped with an info line, as decided (backlog, "Symlinks").

**F4 (search-chain): a refused login reads as "cannot reach".** Right after the start,
before `airflow-accounts` had created the accounts, `modama-chain status` printed
"cannot reach the Airflow at …/auth/token: HTTP 401 Unauthorized". The Airflow answered;
it refused the login. Expected: wording that says the login was refused.

**F5 (stack, method): the monitor cannot see NFS reads.** `docker stats` counts block
devices only: the crawler showed 8.6 MB read for 21,857 files on NFS. For the
performance baseline the monitor needs the host's NFS counters (`nfsiostat`,
`/proc/self/mountstats`), before the full run.

**F6 (crawler): the progress line stands still inside a large directory.** The count is
updated when a directory's listing is finished, so it stayed at 42 directories and
21,730 files for over a minute while `many_mib` was processed. Not wrong, but on the full
tree a large directory looks like a hang. A candidate for the crawl's progress (files
classified, not only listed); decide with F1, which removes this case.

**F7 (warehouse, stack): indexing is the slowest stage, and mostly serial.** About 18
records/s; crawl and harvest are light. The embedding worker is not busy throughout: in
the monitor's 33 s samples from 16:25 to 16:33 it sat at about 100 % (one core) most of
the time, with bursts of 400 % to 4,464 % (a first reading of one burst as "the whole
machine throughout" was wrong; @weber asked why the CPU use is all over the place). So
a serial step between the multi-threaded embedding bursts sets the pace. Expected
(@weber): the CPUs busy continuously with the embedding math itself, in optimised
libraries, not with overhead; so the measure is throughput (records and embeddings per
second), and high CPU percentages are not proof of useful work by themselves: the
bursts may include threads that spin while they wait (thread pools of math runtimes can
do that), to be checked by the profile. On the full
tree (about 430,000 records) at this rate: about 6.5 hours. To find the serial step:
where the worker's time goes (a profile, or tracing, see F8), then the worker's
concurrency (`AIRFLOW__CELERY__WORKER_CONCURRENCY`, `CELERY_BATCH_SIZE`).

**F9 (warehouse): a fresh Python process per batch, one batch at a time.** Upstream's
`run_transform_batch` and `run_filemeta_batch` (`airflow/dags/transform_index.py`) run as
`@task.external_python`: each batch (250 records) starts the transform venv's Python,
imports and loads the embedding model again (upstream's own comment says so), on a queue
with `--concurrency 1`. @weber's reading of the short-lived PIDs ("Python startup is
heavy"). The task log of the run shows at least 88 `run_filemeta_batch` batches, each
"Transformed batch in 0.0s, 0 documents indexed": a process start for nothing, as our
records have no file metadata of that kind. The worker's health check (`celery inspect
ping`) starts a full Python too (96 % CPU while it runs). Measured (`.claude/field-tests/batch-times.sh`): 88 transform batches of 250
records and 88 empty file-metadata batches; per transform batch the model load takes
0.2 to 0.3 s (cached), the batch itself 7.2 to 8.6 s, and a new batch starts about every
9 s. So the process start, imports and scheduling cost about 1.5 s of 9 (plus the empty
batches), and most of the time is inside `transform_batch_impl`: about 33 records/s in
one process. The startup is a real cost but not the main one; what the 7.5 s of a batch
are spent on (embedding, conversion, database and index writes) needs a profile of a
batch while it runs (`py-spy`, `perf`, prepared in run 1, on the next indexing). Note:
the three log lines of a batch carry the same second, so their timestamps are when the
task's output was collected, not when it was printed; the durations inside the lines
are the reliable figures. Options with upstream later: a long-lived worker with the
model loaded, concurrency, skipping empty batches, larger batches.

**F10 (crawler, stack): the creator is a number.** The first search
(`q=libertem&resource=datasets`) shows `"creator": "20335"`: the crawler names the
file's owner with `pwd.getpwuid` and falls back to the uid, and the container knows no
users of the server (its accounts come from the directory service, not `/etc/passwd`).
Expected: the owner's user name, as on the server. Options: the server's name service
in the container (for example the `sssd` socket, or a read-only `/etc/passwd` where
that is enough), or the names from the permissions service; decide with the move to
`deploy/`, where the same question comes up.

**F11 (crawler, warehouse): what a hit shows.** The same search: 100 hits, all single
`.mib` frames from `libertem-test-data/20200518 165148/` (F1), scores around 0.06,
`descriptions` and `fileExtensions` empty, `publicationYear` 2022 (from the file's
mtime, backlog "`dc:date`"). The title is the path. Usable for the demo as "the path is
found", not yet as a search for data; recheck after F1.

**F12 (crawler): about 500 kB read over NFS per file the crawler opens.** Run 2, 19:00:21
to 20:23:22 UTC, the mount's counters (`nfs-stats.sh`): 73,080 opens, 594,735 READs of
up to 64 KiB (`rsize`), 37.1 GB received (about 7.5 MB/s), 21 ms round trip per READ.
The crawler asks for a few bytes per file (`mime.py`: `Mime.magic.maxlen`;
`formats/__init__.py`: `n` bytes within a budget), so the rest is the client reading
ahead. Hypothesis: Python's buffered `open(path, "rb")` sizes its buffer by
`st_blksize`, which NFS reports as `wsize`, so `f.read(small)` fetches up to 1 MiB;
kernel readahead may add to it. First half checked (20:40 UTC): `stat -c %o` gives
1048576 for all 19,601 files of `many_mib`. Fixed on `crawler` (2026-11-10): both reads
unbuffered, tested with the bytes the process reads (`/proc/self/io`, Python 3.14 locally
read 128 KiB for 16 bytes before the fix). Recheck in staging: rebuild the crawler image,
crawl `adhoc/libertem` again (cached on the server by now: compare with `nfs-stats.sh`
and the bytes received per open, not with run 1's time), then the next full crawl. Caveat: the counters are the host's, for everyone using the mount;
that the opens match the crawled files (73,080 of 74,525) points to the crawler. At 16
files/s the whole tree takes hours to crawl: the crawl, not the indexing, sets the pace
on cold NFS data. Confirmed overnight: about 1.1 MB received per open from 21:00 to
22:00 UTC (691,289 READs, 39,527 opens) and from 04:00 to 05:00 (17.0 GB, 15,896 opens),
the 1 MiB buffer per file; READ round trips rose from 16 ms to 43 ms during the night.
Expected after a fix: the bytes received per open near the bytes the
crawler asks for. The crawl benchmark (`../../benchmark/`, 2026-11-11) shows the fix on
an emulated mount with production's options: 18 READs and 1.18 MB per file before, 3
READs and 197 kB after; what is left is the client's readahead (128 kB there).
Production's `read_ahead_kb` for the mount is not known yet:
`cat /sys/class/bdi/$(mountpoint -d /storage/er-c-data)/read_ahead_kb` on the server.

**F13 (crawler): the crawl's memory grows with the files crawled.** Run 2: `crawl-timer`
at 270 MiB at 20:00 UTC, 1 GiB at midnight, 1.9 GiB at 05:25, roughly 2.5 kB per file.
Not checked: whether it is the crawl process (something kept per file or directory for
the whole run) or page cache that `docker stats` counts to the container. Check: the
process's RSS (`ps` in the container) against `docker stats`; on the server, a full
tree has millions of files.

**F8 (stack, method): no tracing across the chain** (@weber, 2026-11-10). The stack is
complex and the slow step was found by sampling `docker stats`. Proposed: OpenTelemetry,
with a collector service in the compose file; Airflow can emit metrics and traces
itself. Not decided.
