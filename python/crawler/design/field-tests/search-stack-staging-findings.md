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

### Run 3, 2026-11-11/12: the whole tree, parallel walk and EM extraction

Commit 3251cad (`crawler`: parallel walk with its review fixes, EM formats and
extraction, `os.access` per file). Fresh state (`./downstaging.sh --reset`), crawl started
by the timer at once at 17:49:07 UTC. Recording in `.claude/field-tests/run-2/`
(`monitor.log`, `nfs.log`, `indexing-probe.log`, py-spy records `crawl-*.txt`; the folder
is named for the second recording session, the run is the third).

Result, crawl: finished at 19:06:02 UTC, 1 h 17 min: 51,306 directories, 1,511,890 files,
1,451,848 datasets, 3,191 warnings, 1,451,848 records changed. Walk about 17 minutes;
extraction from about 18:06 to 18:58 (177,166 run, 2,871 failed; time per format: DM4
18,294 s, DM3 5,377 s, Merlin 88 s, EMPAD 10 s, summed over 8 processes); storing until
19:06. The prediction of `parallel-walk` holds: at least 150 files/s over the first hour
(the walk listed and sniffed 1.5 million files in about 17 minutes) and at most 40 kB per
file opened (8 to 20 kB), with the caveat of warm caches (round trips 1 to 10 ms). The
crawler's memory peaked at about 3.2 GiB. Extraction failures by cause, from the crawl's
log: 2,036 `.dmw` and 33 `.gtg` files recognised as DM4 without an image (F15), 604
RGBA images (F14, fixed on `dm-handle`), 104 Merlin headers (97 not UTF-8, 5 dates with
AM/PM), 94 other DM errors (for example `DM3TagIDError`, unsupported tag types). Harvest
started at 19:06:10.

Interim, 18:20 UTC:
- **Walk:** listing done at 18:06, 17 minutes in: 51,306 directories, 1,511,890 files
  (run 2: 38,596 directories and 1.0 million files in 11 hours, unfinished). Up to
  3,000 files/s listed; content sniffing 550 to 900 files/s at 8 to 20 kB received per
  file opened (prediction: at most 40 kB). The heartbeat counts files listed, not done
  (`BACKLOG.md`). Round trips 1 to 10 ms, against 16 to 43 ms in run 2: caches likely
  warm from the last two nights. 45 files not readable and 19 directories not listable in
  the recorded log, in a few folders.
- **Extraction, from 18:06:** about 72 files/s (4,200 to 4,450 opens per minute), 1,168 kB
  received per file opened, 16 requests in flight, crawl container at 1 to 5 cores and
  3.2 GiB. py-spy (`crawl-gil-60s.txt`): the main process holds the GIL in 36 of 3,000
  samples, so it is not the limit. py-spy with `--subprocesses` (`crawl-sub-60s.txt`):
  90 % of the workers' samples in RosettaSciIO's DM reader, over half on the first 4-byte
  read of a file (`parse_header`, `_api.py:76`), 14 % on the first byte after a seek:
  waits for NFS, not parsing (6 ms CPU per file on the DM4 fixture). See F14.

## Findings

**F14 (crawler, formats): extraction read about 1 MiB per DM file.** Run 3: 1,168 kB
received per file opened during extraction, the same every minute; RosettaSciIO's DM
reader needs the tags (96 to 143 kB on the fixtures). First read as the NFS readahead;
reproduced in the VM on the benchmark's NFS mount (20 ms round trip, a DM4 fixture padded
to 16 MB): 1,154 kB and 176 ms per file with `file_reader`, and readahead off changed
nothing. The cause is Python's file buffer: `open()` sizes it from `st_blksize`, 1 MiB on
NFS, and the reader seeks through the tag tree, so every seek refills up to 1 MiB.
Levers (@weber, 2026-11-11: (a) first, in the VM): (a) read less: RosettaSciIO's reader
classes (`DigitalMicrographReader`, `ImageObject`, the steps of `file_reader` without
`get_data`) on a handle we open with a 64 KiB buffer and readahead off: 132 kB and 93 ms
per file; 8 KiB reads 36 kB but takes 129 ms (more round trips). Identical metadata, axes,
tags and mapping on RosettaSciIO's 98 DM test files that `file_reader` reads; its 12 RGBA
files, which `file_reader(lazy=True)` refuses, are now read too. Branch `dm-handle`
(4f0a6ec), for review. (b) more requests in flight: more extraction processes than CPUs,
since they mostly wait (`MODAMA_CRAWLER_EXTRACT_WORKERS`, 8 by default; decision 59).
Both measured on the next crawl, not tonight (a restart would lose the extraction done).
Merlin's extractor has the same buffer per acquisition (RosettaSciIO's
`MIBProperties.parse_file` opens the first frame file to read 384 bytes); it accepts bytes,
but for a Quad detector it then opens `self.path`, which is `None` for bytes
(`quantumdetector/_api.py:164`, 0.15.0): an upstream bug, not worked around.

**F15 (crawler, formats): DM workspaces and tag files are recognised as DM4 images.** Run 3:
2,036 `.dmw` (Gatan workspace) and 33 `.gtg` files have the DM4 header, so the crawler
types them `application/x.dm4`, names them "Gatan Digital Micrograph (DM4)", and their
extraction fails with `TypeError("'NoneType' object is not iterable")` (no image in them):
72 % of run 3's extraction failures. Recognition by content, whatever the name, is what
spec `formats/dm` asks for; whether workspaces and tag files get types of their own (and
which metadata their tags give) is open (@weber). Decided 2026-11-11 (71): types of their
own; @weber asked whether `.gtg` files belong to K2IS captures, and LiberTEM's K2IS
reader says so (one `.gtg` and 8 `.bin` sector files; 32 of the 33 are named `<stem>_.gtg`,
two in `libertem-test-data`). OpenSpec change `dm-containers-and-k2is`, branch
`dm-containers` (f9b3c9d), for review.

**F16 (warehouse): harvest and indexing spend little of their time on the embedding.**
Run 3: the harvest of 1,451,848 records, from 19:06 UTC, ran for hours at about 1.2 cores
on 24: `transform` 42 %, warehouse `postgres` 58 to 60 %, the harvest worker 21 %, the
crawler's OAI-PMH server near idle. At 22:08 UTC (3 h in) still open, the same CPU, while
the warehouse database's writes per 16.5 minutes grew from 2.5 GB (19:27) to 4.3 GB
(21:56): more bytes per interval at the same CPU, not explained yet (no record count:
the monitor does not reach the warehouse). Reproduced in the VM's test deployment (8 CPUs,
16,000 synthetic records, `prototypes/search-stack/perf/`, untracked; raw data in the
session's scratchpad `indexing-perf/`):
- **Harvest:** 68 records/s, serial: one task, one record per `POST /harvest_event`
  (12.5 ms each: a new PostgreSQL connection 6.6 ms, mostly SCRAM authentication; the
  insert 3.2 ms on a fresh backend against 0.31 ms on an open one; commit 0.6 ms), the
  `oai_dc` XSLT compiled again per record (1 ms). The OAI-PMH pages are about 1 % of
  the time. At that rate staging's 1.45 million records take about 6 hours
  (extrapolated). Upstream already has `POST /harvest_event_bulk` (`routes.py:74`), used
  by its import script, not by the harvester (`db_api_functions.py:106`).
- **Indexing:** batches of 250, one at a time (F9's settings) 26 records/s; batches of
  2,000, four at once (staging's) 62 records/s, the same CPU spent in parallel. Inside a
  batch of 250, `jsonschema.validate` per record (`transform_core.py:179`) takes 21 ms,
  because it checks the schema itself on every call (0.18 ms with one validator): about
  60 % of the batch. The embedding: ONNX pins 7 pool threads per process to the same
  cores, so 4 processes oversubscribe them (load 27 on 8 CPUs); 4 × 2 threads give 194
  texts/s against 118 with the default.
- **Options, by expected gain (estimates from component timings):** the harvester on the
  bulk route (about 8×); one validator per process (2.5× at batch 250); pooled database
  connections in the warehouse API (about 3× for the harvest, a new dependency or one
  connection per thread); ONNX threads ≈ cores / concurrency (with the validator, 3 to 4×
  over staging's settings). Not worth it: a long-lived worker, skipping the empty
  file-metadata batches. All are changes upstream (EOSC Data Commons), as patches like
  the search API's first; not decided.

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

## Review of the staging changes, 2026-11-11

By an agent that did not write them (f2171b6..1bc2bc5: the staging override and scripts,
the batch size, F12), given the code, the runbook and the requirements; verified with
`docker compose … config` before acting.

**R1 (stack): Docker could create the data path on `/storage`.** The short mount syntax
`${STAGING_DATA}:/data:ro` resolves to `create_host_path: true`: a typo in `STAGING_DATA`
would make dockerd create a directory under `/storage` (which the runbook forbids), and an
unmounted share would give the crawl an empty tree. Fixed: long syntax without
`create_host_path` (false), so a missing path fails.

**R2 (stack): containers reachable from the LAN despite `127.0.0.1`.** On Docker Engine
before 28.0, hosts on the same subnet could route to container IPs on the bridge
(OpenSearch without security, Airflow with the test password). Not verified (the
reviewer's recollection); the host runs 29.9.3 (@weber, 2026-11-11), so likely moot.
Check again for `deploy/`.

**R3 (stack): `:ro` not recursive for nested mounts** on older Docker or kernels, and the
crawler runs with @weber's uid and groups. Fixed with R1: `recursive: readonly`, which
fails loudly where it can't be honoured.

**R4–R8 (minor), for the move to `deploy/`:** shell variables override `--env-file
staging.env` (R4); `monitor.sh` resolves a relative log path after `cd` and doesn't check
for `staging.env` (R5); unbuffered `read(n)` may return fewer than n bytes on soft NFS,
FUSE or CIFS (R6, F12); readahead may dominate F12's remaining reads, `posix_fadvise`
would turn it off per file (R7); the staging timer repeats `--at 19:00` and the base
file's "one at a time" comment no longer holds for staging (R8).

## Demo queries: before and after

Queries for the demo of 2026-11-17, each with its answer before the metadata extraction
(index of run 1: `adhoc/libertem` only, titles are paths, no descriptions) and, after the
re-index with `modama-formats-em`, the answer to compare.

**Q1, chat: "Find Merlin acquisitions"** (@weber, 2026-11-11, `POST /chat`, Blablador
`alias-large`). Before: 3 search tool calls, then an answer listing the
`merlin_scan_header` `.mib` and its `.hdr` as two hits, four single frames of `many_mib`
as "a large set of numbered raw frame acquisitions", and the MDMC 2024 slides; its values
("200 kV", "1 ms") read off the file name; "LibreTEM" for LiberTEM (the model's slip);
then a question whether MERLIN the radio interferometer or the lidar was meant (the model
knows no context). The text stream began with stray `{\{\{\n`. Expected after: one hit
per Merlin acquisition (`.hdr` with its frames, `many_mib` as one), values from the
header (frames, frame size, bit depth, time).
