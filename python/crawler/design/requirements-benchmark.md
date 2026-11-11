# Demand and requirements: a crawl benchmark that behaves like the production file system

Author: Claude (interview). Principal: @weber. Date: 2026-11-11. Interviewed: the principal in person, in rounds; drafted first from the record (the staging field test, `field-tests/search-stack-staging-findings.md`; `survey.md`; `requirements-pipeline.md` 2.6).
Markers per item: [answered] said or confirmed by the principal; [record] taken from the source named, not yet confirmed; [assumed] proposed by the author; [unknown] listed in 2.2 with what would resolve it; [deferred] listed under open questions with stage and owner.

## 1. Demand

### 1.1 Problem and context

- [answered] In @weber's words (2026-11-11): "a more controlled benchmark with faster turn-around where we can emulate the characteristics of the NFS file system without access to production, and also the fact that we will be reading most files cold. We should emulate a much smaller file system cache because e.g. it will be efficient to immediately extract metadata from a file that was read recently and is 'hot'."
- [record] What happened: the crawler reads about 1 MiB over NFS for every file it opens to look at a few bytes (F12). Run 1 (a 22,000-file subtree) did not show it: 100 files/s. Run 2 (the whole tree) found it after an hour: 16 files/s, about a third of the tree after 10 hours (field test, run 2). Neither the test suite nor the VM could have shown it: on a local disk the same mistake costs 128 KiB (Python 3.14's buffer), and a small tree stays in the page cache.
- [record] The production file system varies by itself: 60 files/s for 428,000 files on 2026-10-27 (`requirements-pipeline.md` 2.6), 16 files/s on 2026-11-10; READ round trips rose from 16 ms to 43 ms during one night. A measurement there is not repeatable, so it cannot tell whether a change made the crawl faster.
- [answered] (2026-11-11, accepting items 68 to 73) The need behind it: to know within minutes, before a change reaches staging, how the crawl will behave on the production tree (time and I/O per file), and to compare two versions of the crawler under the same conditions.

### 1.2 Current solutions
- [record] Prior art: `prior-art-benchmark.md` (research agent, 2026-11-11; not yet reviewed by a person). Checked by me against the sources: Python's buffer size `max(min(st_blksize, 8 MiB), DEFAULT_BUFFER_SIZE)` (`_pyio.py` of Python 3.14, line 247); mdtest's `-e bytes`, "Set the number of Bytes to read from each file"; cgroup v2, "A memory area is charged to the cgroup which instantiated it", and `workingset_refault_file`, "Number of refaults of previously evicted file pages". Its ranked setups: loopback NFS in the VM with `tc netem` and a memory-limited crawler container; a counters test without privileges; a FUSE latency injector.

### 1.3 Benefits
- [record] A field-test round on the whole tree takes a night or longer (run 2: over 10 hours for a third of the tree) and ties up @weber's attention on the server.

### 1.4 Users
- [assumed] @weber and the colleagues developing the crawler (one of them profiles performance with `perf`); coding agents iterating on the crawler (they have no access to the server). Later perhaps CI.

## 2. Requirements

### 2.1 Use scenarios
- [answered] Scope (68): first the crawler alone: the walk, the format check, the format readers. Harvest and indexing later, in a benchmark of their own.
- [answered] Agnostic to the crawler's language (@weber): the benchmark runs the crawler as a program and measures from outside, so that a rewrite (for example in Rust) is measured the same way. No measurement through the crawler's own code or imports (75, confirmed): the crawler is started from a command line with the tree's path, and everything is measured from outside (the mount's counters, the cgroup, `perf`).
- [answered] Emulated: a test tree served with the production file system's characteristics (2.4), on a machine without access to production; reads mostly cold, with a cache much smaller than the tree (@weber: reading a file again soon after, while it is hot, must show up as cheap, and later, once evicted, as expensive).
- [answered] Real (@weber): the same test tree also on the actual storage (there is space to spare), and the same benchmark run against it there, to see what is actually going on and to check that the emulation behaves like the real thing. The tree on the storage also serves a planned test suite that monitors production.
- [answered] Profiled (@weber): any run can be done with a full system profile (`perf`), so that what happens in the kernel, NFS client and the crawler shows up together.
- [answered] Where (72): first the VM; the development server with the real storage; CI decided later.
- [answered] A unit of its own (@weber, 2026-11-11): separate from the functional tests (the crawler's test suite, the search stack's e2e test) and from the staging field test on production data. The unit tests of F12 (`bytes_read`) stay functional tests of the Python crawler.
- [answered] The setup (80, @weber): an NFS server and client in a VM, with the production mount options, network delay (`tc netem`) and the crawler in a memory-limited cgroup. Closest to production, and it shows what NFS actually does instead of guessing it from production's counters. The benchmark collects events (operations, bytes, re-reads) and predicts the production time from them with the round-trip times measured there, instead of running at production's pace; that keeps it fast.
- [answered] Reproducible elsewhere (@weber): a complete list of what the setup needs (2.7), so that another machine can be set up the same way.
- [answered] Test tree (71): generated from the survey's figures (file sizes, types, large frame-series directories, environments to collapse), scaled down, still much larger than the emulated cache.

### 2.2 Demand uncertainties
- [unknown] The production NFS server's behaviour under load (round-trip times over a day, other users' load). Resolves with: the `nfs-stats.sh` logs over several days.

### 2.3 Interfaces with existing systems
- [record] The crawler's file access: `os.scandir`/`stat` for the walk, `open` and read for the format check (`mime.py`) and the format readers (`Directory.read`).

### 2.4 Operating conditions
- [record] Production as measured (field test, run 2, the host's mount counters): NFS 4.1, `rsize` 64 KiB, `wsize` 1 MiB, `st_blksize` 1 MiB, attribute cache 3 to 60 s; READ round trip 16 to 43 ms, LOOKUP and OPEN about 0.1 to 0.8 ms; 2.29 million inodes in use, 73 TB of 109 TB; a page cache far smaller than the tree (251 GB RAM on the server), so almost every file is read cold.
- [record] The tree's shape: `survey.md` (file sizes, extensions, directories with tens of thousands of files, collapsible trees).

### 2.5 Availability and reliability
- [answered] The emulation is good enough when the counters per file (NFS READs, bytes received per open, re-reads) of the same test tree agree within 10 % between the emulation and the actual storage (77). Wall times are recorded on both, not compared: the actual storage varies.
- [assumed] A wrong result shows up as a disagreement in that comparison; it is repeated after a change of the setup or the storage, and when production's counters (`nfs-stats.sh`) change noticeably.
- [answered] First comparison (2026-11-11, `../benchmark/README.md`): READs, bytes, opens and directory reads agree exactly; LOOKUP (×3.3), GETATTR (−50 %) and DELEGRETURN (+62 %) do not, probably because of the storage server's NFS server (Red Hat 9.6, kernel 5.14). Accepted for the data path; the metadata counters stay marked "differs, reason unknown" until explained (96).
- [answered] The reference tree's shape is public (`../benchmark/shapes/`), checked by @weber (93).
- [deferred] Real bytes at the start of each test file instead of holes, so that the server reads disk as with real data (97): "we only do these things when necessary. That may come soon when we start extracting metadata!" (@weber). Until then, times are projected from the counters and production's round trips.

### 2.6 Performance
- [answered] Turnaround (69): one run under 5 minutes in the VM, so that every change can be tried.
- [answered] What it measures (70): first counters (bytes read, NFS operations per file, files read more than once and whether from cache), as they repeat; second wall time under the emulated latency.

### 2.7 Testing, installation and service
- [answered] Root: in the VM the agent may be root; on the development server @weber runs everything, `perf` included (78). No private information on the server except some tokens and SSH keys, which `perf` does not leak as far as @weber knows.
- [record] What the setup needs, as installed in the devvm on 2026-11-11 (Debian 13, kernel 6.12.115+deb13.1-cloud-amd64, 8 CPUs, 23 GiB):
  - Kernel (all present in Debian's cloud kernel): `CONFIG_NFSD=m`, `CONFIG_NFS_FS=m`, `CONFIG_NFS_V4_1=y`, `CONFIG_NET_SCH_NETEM=m`, `CONFIG_FUSE_FS=y`, `CONFIG_PERF_EVENTS=y`, `CONFIG_BPF_EVENTS=y`; cgroup v2.
  - Debian packages: `nfs-kernel-server` and `nfs-common` 2.8.3 (server, `mount.nfs`, `nfsiostat`), `iproute2` 6.15 (`tc`), `linux-perf` 6.12.116, `bpftrace` 0.23.2, `bpfcc-tools` 0.31.0 (`cachestat-bpfcc`), `strace` 6.13, `hyperfine` 1.19.0, `vmtouch` 1.3.1, `util-linux-extra` 2.41.5 (`fincore`), `fio` 3.39, `sysstat` 12.7.5. To go into `.devvm/provision.sh` once the setup works.
  - `perf`: `kernel.perf_event_paranoid` is 3 on Debian, so `sudo`; `perf stat -G <cgroup>` counts for one container only; `perf trace -s` summarises system calls per thread; tracepoints `sunrpc:*`, `nfs:*`, `filemap:*` (143 present before NFS v4 was loaded), `nfs4:*` once `nfsv4` is loaded. Python 3.14 shows its own functions in `perf` with `-X perf` (checked: `sys.is_stack_trampoline_active()` is true).

### 2.8 Portability and distribution
- [answered] In `python/crawler/benchmark/` for now (81); a repository of its own is being considered, to be decided by the maintainers.
- [assumed] Linux only (NFS client and server, cgroup v2, `perf`); any machine where one is root, set up from the list in 2.7.

### 2.9 Jurisdictions
- [assumed] Nothing applies: the test tree is generated, without real data or personal data; the tools are free software (licences in `prior-art-benchmark.md`).

### 2.10 Lifetime and decommissioning
- [assumed] As long as the crawler is developed. The test tree on the storage is @weber's to manage and remove (76).

### 2.11 Safety and risks
- [answered] In the VM the agent may be root; on the development server @weber runs every command (78).
- [assumed] The emulation runs inside the devvm only: an NFS server there, exporting only the generated tree, on the VM's loopback; no export reachable from outside the VM.
- [assumed] Risk: a loopback NFS mount under memory pressure can deadlock (`prior-art-benchmark.md`, LWN 2014); the memory limit applies to the crawler's cgroup only, not to the server.

### 2.12 Applicable standards
- Not asked: none known for a benchmark of this kind.

## Release
Decides: @weber. Builds: Claude with @weber. Owns the shared system it acts on: the emulation, none; the test tree on the actual storage: @weber (76: Claude prepares the tree, @weber copies it to the storage, says where, and manages it, like the LiberTEM test tree).

## Open questions
- 73 Vocabulary: common terms from the performance literature (cold and hot cache, working set) for now; glossary entries for `/CONTEXT.md` proposed once the prior art shows which are established. @weber, after the research.
- Production monitoring (79): a requirements document of its own later, sharing the test tree on the storage. @weber.
- Own repository for the benchmark (81): the maintainers decide.
- Real bytes in the test files (97): deferred to the extraction of metadata. @weber.
- Why the storage server's NFS causes three times the LOOKUPs (96): reproduce with a Red Hat 9 NFS server, for example a second VM. @weber decides when.
