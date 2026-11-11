# Crawl benchmark

How the crawl behaves on the production file system, measured in minutes on a machine
without access to production: a test tree served over NFS with production's mount
options, read cold, with a small cache. A unit of its own, apart from the test suite
and the staging field test. Requirements: `../design/requirements-benchmark.md`;
prior art: `../design/prior-art-benchmark.md`.

The benchmark runs the crawler as a program and measures from outside (the mount's NFS
counters, the cgroup's memory counters), so it works for any implementation.

## Setup

Linux with root, cgroup v2 and systemd; the kernel and package list is in the
requirements, 2.7. In the devvm, as root:

```bash
sudo ./nfs-up.sh                    # export /srv/modama-bench, mount it at /mnt/modama-bench
sudo BENCH_DELAY=5ms ./nfs-up.sh    # the same, NFS packets delayed 5 ms each way (10 ms round trip)
sudo ./nfs-down.sh                  # unmount, unexport, no delay
```

`BENCH_EXPORT` and `BENCH_MOUNT` change the two paths. The export is read-only and
reachable from this machine only.

## The test tree

From a listing of the real tree (the survey's, private in `/.claude/survey/`), `shape.py`
takes a sample of directories with their files' sizes, times and name patterns, and
replaces the names: directories by `d<n>`, files by a prefix per pattern with a trailing
number's digits and the extension kept, so that series stay series and globs still
match. Names the formats look for (`site-packages`, `__pycache__`, `.git`, the Zarr
markers) are kept. `generate.py` builds the tree from that shape as sparse files: the
listed sizes, but no data written. It needs only Python 3.6 and its standard library,
writes only into a new or empty directory, and never overwrites or deletes.

```bash
python3 shape.py LISTING.tsv.gz 0.05 1 > SHAPE.tsv.gz    # 5 % of the directories, seed 1
sudo python3 generate.py SHAPE.tsv.gz /srv/modama-bench/tree
```

Files are zeros, so the content checks see no real headers: a format reader that parses
a header (EMPAD XML, Zarr metadata) only warns. The I/O per file is that of the real
tree; what the readers extract is not.

## A run

```bash
sudo ./run.sh ~/.venv/bin/modama-crawler records /mnt/modama-bench/smoke
```

`run.sh` remounts (the client's cache is then cold), runs the command as you in a cgroup
limited to `BENCH_MEMORY` (default `256M`), and prints per NFS operation the count, the
megabytes received and the average round trip, and the cgroup's `anon` and `file`
memory, its peak, and the pages read again after eviction.

## First results (2026-11-11, devvm, no delay)

A smoke tree of 200 files of 4 MiB without a file name extension (sparse, a PNG
signature at the start), so the crawler reads the start of each:

| crawler | READs per file | received per file |
|---|---|---|
| before the F12 fix (5d1787e~1) | 18 | 1.18 MB |
| after the F12 fix | 3 | 197 kB |

The three READs left are the client's readahead (128 kB, `read_ahead_kb` of the
mount). With `BENCH_DELAY=5ms` every operation took 10.2 ms; the 1,200 operations took
7.1 s, not 12 s, so some overlap (readahead runs in parallel).

The generated tree, 5 % of the surveyed directories (seed 1): 3,273 directories, 22,109
files, 664 GB apparent size on 14 MB of disk, generated in under a second. The crawler
(after the F12 fix) in 54.5 s without delay: 12,277 files opened, 32,456 READs, 2.0 GB
received (164 kB per file opened), 21,746 ACCESS, 6,620 LOOKUP, 2,681 READDIR; no page
read again after eviction at 256 MB. Production's readahead is 128 kB as well (`read_ahead_kb`
of the mount on the development server, 2026-11-11).
