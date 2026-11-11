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
sudo python3 generate.py shapes/shape-0.05-seed1.tsv.gz /srv/modama-bench/tree
```

`shapes/shape-0.05-seed1.tsv.gz` is the reference tree: 5 % of the directories of the
listing of 2026-10-15, seed 1, checked by @weber for publication (2026-11-11). The same
tree is on the real storage at `/storage/er-c-data/adhoc/datamanagement/testdata/` on
the development server (@weber manages it).

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

## The emulation against the real storage (2026-11-11)

The same tree (seed 1, 5 %), generated on the storage server's XFS and crawled from the
development server through the production mount, by the staging crawler (same code),
measured with `measure.sh`; first cold (nothing had read the tree), then warm:

| NFS operation | VM, cold | real storage, cold | real storage, warm |
|---|---|---|---|
| READ | 32,456 | 32,456 | 0 |
| MB received by READ | 2,011.8 | 2,011.8 | 0 |
| OPEN_NOATTR, CLOSE | 12,277 each | 12,277 each | 12,277 each |
| READDIR | 2,682 | 2,681 | 2,681 |
| ACCESS | 21,746 | 24,087 (+11 %) | 21,748 |
| GETATTR | 5,346 | 2,681 (−50 %) | 8,796 |
| LOOKUP | 6,620 | 21,769 (×3.3) | 3,374 |
| DELEGRETURN | 7,278 | 11,817 (+62 %) | 7,738 |
| READ round trip | 0.07 ms | 0.47 ms | |
| wall time | 54 s | 79 s | 74 s |

- The data path agrees exactly: READs, bytes, opens, directory reads.
- Metadata operations differ: on the real storage the client looked up almost every
  entry (21,769 LOOKUPs for 25,382 entries), in the VM about one in four. Not explained
  yet. Not the timing: with a 0.2 ms delay each way (0.47 ms round trip, as on the real
  storage) the VM's counts stay the same, and its wall time is 82 s. The client kernels
  are the same version (6.12.115, Debian); the storage server runs a Red Hat 9.6 kernel
  (5.14.0-570), the VM's NFS server 6.12. The server is the likely cause.
- The test tree's READs took 0.47 ms on the real storage, against 16 to 43 ms for real
  data in the field test: sparse files are holes, so the server reads no disk. Times on
  the test tree therefore say nothing about production; a time is projected from the
  counters and production's round trips instead.
- Warm, the development server's page cache served every READ; opens still go to the
  server.

## The parallel walk (2026-11-11, devvm, 20 ms round trip)

Change `parallel-walk` (`../openspec/changes/parallel-walk/`), `records` on the reference
tree (3,273 directories, 22,109 files), `BENCH_DELAY=10ms`, `BENCH_MEMORY=1G`, 8 CPUs;
CPU time of the command and its worker processes. Before: the crawler at 8d1dec8, after:
dd508fa (32 threads, 8 matching processes), each run on a frozen copy of the code.

| | before | after |
|---|---|---|
| wall time | 1,275 s | 40.5 s (40.0 s on a second run) |
| files/s | 17.3 | 546 |
| NFS operations | 94,663 (4.3 per file) | 54,346 (2.5 per file) |
| READ | 26,489 | 10,269 |
| ACCESS | 21,746 | 2,673 (directories only) |
| GETATTR | 7,279 | 6,238 |
| DELEGRETURN | 9,272 | 5,289 |
| OPEN, CLOSE, LOOKUP, READDIR | 10,288, 10,288, 6,620, 2,681 | the same |
| MB received per file opened | 0.157 | 0.018 |
| CPU user, sys | 44.3 s, 2.9 s | 50.6 s, 4.7 s |
| largest RSS of one process | 210 MB | 219 MB |
| cgroup memory.peak (with page cache) | 1,074 MB (at the limit; 824 MB cache) | 596 MB |
| load average at the start | 2.68 | 1.38 (14.29 on the second run) |

Every round trip took 20.2 ms in both. The output of `records --verbose` without the
delay is byte for byte the same before, after, and after with one thread and one process
(apart from `responseDate`): 18,719 records, 39 warnings. The mean number of requests in
flight after: 54,346 × 20.2 ms / 40.5 s ≈ 27, near the server's 30 session slots.
