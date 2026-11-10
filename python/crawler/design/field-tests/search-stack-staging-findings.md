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
- **Indexing:** started 16:23:33; 3,250 records in the warehouse at 16:26 (about 18/s);
  the embedding worker at 4,464 % CPU.
- **Memory:** search API 2.6 GB (the embedding model), OpenSearch 1.4 GB, the rest
  below 0.7 GB each.
- **Disk:** `/` 84 % (71 GB free), `/cachedata` 84 % (919 GB free), unchanged by the run.

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

**F7 (warehouse, stack): embedding is the only heavy stage.** About 18 records/s with
about 45 threads busy; crawl and harvest are light. On the full tree (about 430,000
records) that is about 6.5 hours of the whole machine. Measure on the full run; then
decide on the worker's concurrency and its effect on others using the server.
