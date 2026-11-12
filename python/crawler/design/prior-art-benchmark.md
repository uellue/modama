# Crawl benchmark: prior art

Status: research notes for `requirements-benchmark.md` (1.2, item 74). Made 2026-11-11 by a research agent from official docs, man pages, kernel sources and project repositories; every claim carries a link. Claims marked **(unverified)** are inference or come from secondary sources; claims marked **(not researched)** were asked about but not checked in this pass.

## Short version

- **F12 needed two things to show, and neither was latency:** a file system that reports a 1 MiB `st_blksize`, and a counter of bytes moved per file opened. Python's buffer is `max(min(blocksize, 8 MiB), DEFAULT_BUFFER_SIZE)` ([Python docs](https://docs.python.org/3/library/functions.html#open)), and the Linux NFS client sets the block size from `wsize` unless the mount gives `bsize` ([`fs/nfs/super.c`, v6.12](https://github.com/torvalds/linux/blob/v6.12/fs/nfs/super.c)). A loopback NFS mount with `wsize=1048576` has that 1 MiB block size without any delay, and a FUSE file system can report any block size per file ([`fs/fuse/dir.c`, v6.12](https://github.com/torvalds/linux/blob/v6.12/fs/fuse/dir.c)).
- **Counters are the stable result, wall time is the projection.** Counts of NFS operations and bytes per crawled file (`/proc/self/mountstats`, `nfsiostat`), syscalls and bytes per process (`/proc/self/io`, `strace -c`) and page-cache refaults per cgroup (`memory.stat`) come out the same on every run. Wall time with injected latency varies from run to run and depends on the host. A projection is our proposal, not prior art: time ≈ Σ (operation count × production round-trip time) / concurrency, using the round-trip times measured in the field test.
- **A small page cache:** run the crawler in a cgroup v2 with a small `memory.max` (Docker `--memory`). The kernel charges page cache to the cgroup that first reads a page ([cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)), so a tree several times larger than the limit is read mostly cold, and `workingset_refault_file` counts the re-reads. `drop_caches` before each run gives a cold start, but it needs root and clears the whole host.
- **What others do:** filebench, smallfile and mdtest generate trees and time metadata operations. mdtest can read a fixed number of bytes from each file (`-e`), which is close to our access pattern. fd's benchmarks use hyperfine with a `--prepare` command that drops caches for cold runs. Impressions (Agrawal et al., FAST '09) is the published method for statistically realistic file-system images. We have something better than its model: our own listing of the tree (`survey.md`).
- **CI:** GitHub-hosted Linux runners have passwordless sudo ([GitHub docs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)), so mounting there may be possible. Wall time on shared runners is noisy; the counters are what a CI job can check.

Ranked setups (details at the end):

1. **Loopback NFS in the devvm with `tc netem`, the crawler in a memory-limited container.** Needs root on the VM and the kernel's `nfsd`. Effort: about a day. It uses the real NFS client: `st_blksize`, `rsize` and readahead, the attribute cache, the RPC counters `nfs-stats.sh` already reads, and round-trip delay. It cannot emulate the production server's load or its variation over a day.
2. **A counters test, no privileges:** a small FUSE passthrough that reports 1 MiB `st_blksize`, or a check with the buffer size forced in the test, asserting bytes read per file opened from `/proc/self/io`. Effort: hours. Runs in CI. It catches F12-type regressions but has no NFS client, readahead or latency.
3. **A FUSE latency injector** (google/slowfs, nirs/slowfs, fusestream) between the crawler and a local tree. Needs `/dev/fuse`, usually `SYS_ADMIN` in Docker **(unverified)**. Per-operation delays, but no NFS client behaviour; the tools are small and partly archived.

## 1. Emulating NFS latency and bandwidth locally

### Loopback NFS mount plus `tc netem`

- **What netem does:** a queueing discipline for "emulating the properties of real-world networks": delay with jitter and correlation, delay distributions, loss and a rate limit ([tc-netem(8)](https://man7.org/linux/man-pages/man8/tc-netem.8.html)). Its examples apply delay to outgoing packets. On `lo` both the request and the reply leave through the same device, so one `delay D` probably adds about 2·D to each round trip **(unverified, inference)**. Delay applies per packet, not per NFS operation, so a large READ reply that is split into several packets is delayed per packet **(unverified)**.
- **The NFS client side is real:** `rsize`/`wsize` are capped at 1 MiB and negotiated, attribute cache `acregmin` 3 s / `acregmax` 60 s by default, plus `lookupcache`, `nconnect` and `fsc` ([nfs(5)](https://man7.org/linux/man-pages/man5/nfs.5.html)). Mounting with `vers=4.1,rsize=65536,wsize=1048576` reproduces production's settings; `st_blksize` then follows `wsize` ([`fs/nfs/super.c`](https://github.com/torvalds/linux/blob/v6.12/fs/nfs/super.c)). For directories, `stat` reports `dtsize` instead ([`fs/nfs/inode.c`](https://github.com/torvalds/linux/blob/v6.12/fs/nfs/inode.c)). Readahead per NFS mount is `read_ahead_kb`, set by `nfsrahead` from `/etc/nfs.conf`; the man page's example uses 128 ([nfsrahead(5)](https://man7.org/linux/man-pages/man5/nfsrahead.5.html)). The production host's value is not known; it should be read there.
- **Counters:** `nfsiostat` reports ops/s, kB/op, RTT and execution time per operation from `/proc/self/mountstats` ([nfsiostat(8)](https://man7.org/linux/man-pages/man8/nfsiostat.8.html)), the same source as `nfs-stats.sh`.
- **Caveat, loopback:** mounting an export on the host that serves it can deadlock under memory pressure. A 2014 patch set removed "most, and hopefully all" such deadlocks; the article does not say whether it was merged ([LWN, Neil Brown, 2014](https://lwn.net/Articles/595652/)). This matters because we want memory pressure on purpose. Limiting only the crawler's cgroup, not the host, should avoid it **(unverified)**.
- **Sparse files:** a tree with production sizes can be made cheaply from sparse files. On NFS 4.1 a READ returns the holes as zeros over the wire, so the bytes per open still count; NFS 4.2's READ_PLUS can send holes compactly, so pin `vers=4.1` **(unverified, no source fetched)**.

### Server choice: kernel `nfsd` or nfs-ganesha

| | kernel nfsd | nfs-ganesha |
|---|---|---|
| Runs | in the kernel; a container only configures it | user space, "an NFSv3,v4,v4.1 fileserver that runs in user mode" ([repo](https://github.com/nfs-ganesha/nfs-ganesha)) |
| In Docker | the host kernel must have `nfs`/`nfsd`; `--cap-add SYS_ADMIN` or `--privileged` ([ehough/docker-nfs-server](https://github.com/ehough/docker-nfs-server), GPL-3.0) | FSAL_VFS uses `open_by_handle_at`, which needs `CAP_DAC_READ_SEARCH` ([open_by_handle_at(2)](https://man7.org/linux/man-pages/man2/open_by_handle_at.2.html)); community images add `SYS_ADMIN` and `DAC_READ_SEARCH` **(unverified, community READMEs)** |
| Licence | GPL-2.0 (Linux) | LGPL-3.0 ([LICENSE.txt](https://raw.githubusercontent.com/nfs-ganesha/nfs-ganesha/next/src/LICENSE.txt)) |
| Note | simplest in a VM we own (devvm) | has an in-memory FSAL (`src/FSAL/FSAL_MEM`, seen in the source) but no delay option there |

In the devvm both work, since we are root on the VM. On the dev server, kernel nfsd changes the host. Either way the server side reads from the VM's page cache, which is not charged to the crawler's cgroup: server-side cache hits are fast, as they can be in production.

### FUSE latency injection

| Tool | What | Licence, status |
|---|---|---|
| [google/slowfs](https://github.com/google/slowfs) | Go, mirrors a directory; `SeekTime`, `ReadBytesPerSecond`, `MetadataOpTime` | Apache-2.0, archived 2022 |
| [nirs/slowfs](https://github.com/nirs/slowfs) | Python, per-operation delays (`unlink = 60`), changed at run time with `slowfsctl` | BSD-2-Clause, tox targets py27 |
| [zperf/fusestream](https://github.com/zperf/fusestream) | Go, `inject-latency` per glob, operation and probability | MIT |
| [scylladb/charybdefs](https://github.com/scylladb/charybdefs) | C++, fault injection with a Thrift interface; delays per [ScyllaDB blog](https://www.scylladb.com/2016/02/16/fault-injection-filesystem-software-testing/) | archived January 2026; licence not checked |

Pros: per-operation control (a LOOKUP 0.5 ms, a READ 20 ms), and a FUSE file system can set `st_blksize` per file ([`fs/fuse/dir.c`](https://github.com/torvalds/linux/blob/v6.12/fs/fuse/dir.c): `attr->blksize` if non-zero). Cons: no NFS client, so no `rsize` splitting, NFS readahead or attribute cache; the FUSE mount has its own page cache and readahead; one more cache in the daemon's backing file system. Unprivileged mounts go through the setuid `fusermount` ([kernel FUSE docs](https://docs.kernel.org/filesystems/fuse/fuse.html)); in Docker, `/dev/fuse` plus `SYS_ADMIN` is the usual recipe **(unverified)**.

### dm-delay

dm-delay "delays reads and/or writes and/or flushes" of a block device, in milliseconds per target ([kernel docs](https://docs.kernel.org/admin-guide/device-mapper/delay.html)). It delays block I/O under a local file system, so metadata in the dentry/inode cache is not delayed and block size stays local. Needs root and `dmsetup`. Not a model of NFS; not recommended.

## 2. A small page cache and cold reads

- **cgroup v2:** the memory controller tracks "page cache and anonymous memory"; over `memory.high` the cgroup is throttled and reclaimed, at `memory.max` direct reclaim and then OOM. Pages are charged to the cgroup that first used them, and stay there until released ([cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)). `memory.stat` splits `anon` from `file` and counts `workingset_refault_file` (refaults of evicted file pages). `memory.peak` gives the peak, `memory.reclaim` reclaims on demand (same page). For F13 this split is the answer to "process or page cache": compare `anon` with `file`. Docker's `--memory` sets the limit; its docs do not mention page cache ([Docker](https://docs.docker.com/engine/containers/resource_constraints/)). That NFS client pages are charged like local ones follows from the ownership rule **(unverified for NFS specifically)**.
- **drop_caches:** 1 = page cache, 2 = dentries and inodes, 3 = both; non-destructive; "use outside of a testing or debugging environment is not recommended" ([vm sysctl](https://docs.kernel.org/admin-guide/sysctl/vm.html)). Root, whole host. Dropping dentries and inodes (2) matters for us: a cold walk on NFS is LOOKUP and GETATTR traffic.
- **posix_fadvise:** `POSIX_FADV_DONTNEED` frees cached pages of a range; `POSIX_FADV_RANDOM` "disables file readahead entirely" ([posix_fadvise(2)](https://man7.org/linux/man-pages/man2/posix_fadvise.2.html)). No root needed. vmtouch `-e` uses it on Linux ([vmtouch.pod](https://raw.githubusercontent.com/hoytech/vmtouch/master/vmtouch.pod); [repo](https://github.com/hoytech/vmtouch), BSD-3-Clause).
- **Residency:** `cachestat(2)` (Linux 6.5) reports cached, dirty, writeback, evicted and recently evicted pages for a range: residency, not hits and misses ([cachestat(2)](https://man7.org/linux/man-pages/man2/cachestat.2.html)). `fincore` (util-linux) uses it and falls back to `mincore` ([fincore(1)](https://man7.org/linux/man-pages/man1/fincore.1.html)).
- **Hits and misses:** BCC's `cachestat` counts page-cache hits and misses through kprobes on `filemap_add_folio`, `folio_mark_accessed` and others; system-wide, root, Apache-2.0 ([source](https://github.com/iovisor/bcc/blob/master/tools/cachestat.py), [example](https://github.com/iovisor/bcc/blob/master/tools/cachestat_example.txt)).
- **Per process:** `/proc/<pid>/io`: `rchar` is "bytes returned by successful read(2) and similar system calls", `syscr` the number of read calls, `read_bytes` "bytes really fetched from the storage layer", "accurate for block-backed filesystems" ([proc_pid_io(5)](https://man7.org/linux/man-pages/man5/proc_pid_io.5.html)). `rchar` sees Python's oversized buffer reads (F12), not kernel readahead; whether `read_bytes` counts NFS is not documented. For NFS readahead, use the mount counters.
- **Syscalls:** `strace -c` counts calls, errors and time per syscall; `-e trace=%file` covers every call that takes a path ([strace(1)](https://man7.org/linux/man-pages/man1/strace.1.html)). strace slows the traced process, so use it for counts, not for timing.

## 3. How others benchmark tree walks and crawlers

- **mdtest** (in [hpc/ior](https://github.com/hpc/ior), GPL-2.0): "a file system metadata performance test designed to run in a cluster MPI environment"; each task creates, stats and removes files and directories in a tree with a branching factor (`-b`), items per directory (`-I`), and `-e bytes` "to read from each file" ([mdtest.1](https://github.com/hpc/ior/blob/main/doc/mdtest.1)).
- **filebench** (CDDL-1.0, [repo](https://github.com/filebench/filebench)): a workload language; `define fileset ... entries=$nfiles,dirwidth=$meandirwidth` ([fileserver.f](https://github.com/filebench/filebench/blob/master/workloads/fileserver.f)); file sizes and directory widths can follow a gamma distribution ([fileset.c](https://github.com/filebench/filebench/blob/master/fileset.c)).
- **smallfile** (Apache-2.0, [repo](https://github.com/distributed-system-analysis/smallfile)): "distributed metadata-intensive workload generator"; operations `stat`, `read`, `ls-l`, `readdir`; `--files-per-dir`, `--dirs-per-dir`; exponential file-size distribution; the README drops caches with `echo 1 > /proc/sys/vm/drop_caches` on every host and mentions NFS mounts.
- **fd** ([fd-benchmarks](https://github.com/sharkdp/fd-benchmarks)): warm-cache scripts with `WARMUP_COUNT=5`, one cold-cache script with `--prepare "sync; echo 3 | sudo tee /proc/sys/vm/drop_caches"`, and a check that `fd` and `find` give the same output. The tree is the user's `$HOME`, so results are not comparable between machines.
- **plocate** uses io_uring for nearly all I/O to reduce "the impact of seek latency"; the page gives one timing with no cache state ([plocate](https://plocate.sesse.net/)). No method to borrow.
- **Robinhood** (CeCILL-C, [repo](https://github.com/cea-hpc/robinhood)): keeps "a replicate of filesystem metadata in a database", parallel scans, and Lustre MDT changelogs to avoid rescans. No benchmark or NFS figures published there.
- **tika-eval** compares extraction output between tools or versions (exceptions, MIME detection, content quality), not throughput ([Tika wiki](https://cwiki.apache.org/confluence/display/TIKA/TikaEval)). A model for comparing two crawler versions' *records*, not their speed.
- **Not researched:** fio, fs_mark, rsync, restic, borg, Everything, mlocate, Elastic fscrawler, ripgrep. No claims about them here.
- **Realistic trees:** Agrawal, Arpaci-Dusseau and Arpaci-Dusseau, "Generating Realistic Impressions for File-System Benchmarking", FAST '09 ([USENIX](https://usenix.org/conference/fast-09/generating-realistic-impressions-file-system-benchmarking), [PDF](https://www.usenix.org/event/fast09/tech/full_papers/agrawal/agrawal.pdf)); journal version ACM TOS 5(4), 2009 ([ADSL PDF](https://research.cs.wisc.edu/adsl/Publications/impressions-tos09.pdf)). Its distributions come from Agrawal, Bolosky, Douceur and Lorch, "A Five-Year Study of File-System Metadata", FAST '07 ([USENIX](https://www.usenix.org/conference/fast-07/five-year-study-file-system-metadata)), on Windows desktops. For us the listing behind `survey.md` (names, sizes, directory shapes of the visible quarter) is closer than any model. A replay could reuse it: same directories and names, sparse files of the listed sizes, a real header per format copied from public samples (LiberTEM test data). The production tree has about four times as many files as the listing saw.

## 4. Reproducible benchmarks

- **hyperfine** (MIT/Apache-2.0, [repo](https://github.com/sharkdp/hyperfine)): `--warmup N` for warm runs, `--prepare CMD` before every run for cold runs (the README's example drops caches), `--runs`, exports including JSON with every run.
- **pytest-benchmark**: `--benchmark-autosave`, `--benchmark-compare`, `--benchmark-compare-fail min:5%` ([usage](https://pytest-benchmark.readthedocs.io/en/latest/usage.html)); in pedantic mode, `setup` is called "right before calling the target function in the first iteration of every round", so a cold-cache step fits there ([pedantic](https://pytest-benchmark.readthedocs.io/en/latest/pedantic.html)). Licence not checked.
- **Noise in CI:** GitHub-hosted Linux runners have passwordless sudo and 4 cores, 16 GB RAM; `ubuntu-slim` is unprivileged and cannot mount ([GitHub docs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)). Whether the runner kernel ships `nfsd` was not checked. CodSpeed's documentation calls wall time on standard hosted runners inconsistent and counts simulated CPU work instead ([CodSpeed](https://codspeed.io/docs/instruments/cpu)). The same idea for us: assert on counts (bytes per open, RPCs per file, refaults), report time as information.
- **Practice the sources share:** state the cache condition of each run (fd: separate warm and cold scripts), warm runs before measuring, several runs with a spread, the same tree for both versions, and an output check alongside the timing (fd compares outputs; tika-eval compares records).

## 5. Candidate setups, ranked

| | 1. Loopback NFS + netem + cgroup | 2. Counters in the test suite | 3. FUSE latency injector |
|---|---|---|---|
| Privileges | root on the devvm; kernel nfsd; `tc` on `lo` | none (FUSE variant: `/dev/fuse`) | `/dev/fuse`, `SYS_ADMIN` in Docker **(unverified)** |
| Effort | about a day: export, mount options, netem, a generated tree, a memory-limited crawler container | hours | half a day plus maintaining an outside tool |
| Emulates | `st_blksize` 1 MiB, `rsize` 64 KiB splitting, NFS readahead, attribute and lookup caches, RPC counters as on the server, round-trip delay, a cache smaller than the tree | `st_blksize` (FUSE variant) or a forced buffer size; bytes and syscalls per open | per-operation delay; `st_blksize` if the tool passes it through (not checked) |
| Cannot | the server's load and variation over the day; production's network | NFS client behaviour, latency, cache pressure | NFS client, readahead as on NFS, RPC counters |
| CI | possibly on GitHub-hosted runners (sudo), not checked | yes | possibly |

Suggested combination: 2 in the test suite (a regression net for F12-type bugs), 1 in the devvm for the time and memory questions (F12 recheck, F13), and the projection from counters times production round-trip times to compare with the field test.

## Sources

Every link above was fetched on 2026-11-11, except the Impressions PDFs and the Five-Year Study, whose bibliographic data was checked on the USENIX pages and search results only.
