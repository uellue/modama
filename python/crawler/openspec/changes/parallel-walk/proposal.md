# Proposal

## Why

On NFS the walk waits for one round trip after another: run 2 of the staging field test crawled about 16 files/s at 16 to 43 ms per round trip, so the whole tree takes days (F12), and the benchmark's emulated mount with a 20 ms round trip gives the current crawler 11 files/s. The I/O study of 2026-11-11 (`benchmark/`, the playground `pywalk.py` and its log) measured 440 to 515 files/s on the same mount with the per-file work in a thread pool, subdirectories listed in parallel, no `os.access` per file, `posix_fadvise(POSIX_FADV_RANDOM)` after open, and the MIME magic matching in a few processes; io_uring and Direct I/O did not help. @weber decided on 2026-11-11 to make the walk fast on NFS on that basis (decision 53 of the study). Serves R10 (a full crawl stays feasible), R12 (should: recognition fast and light), the provisional decision-log row of 2026-11-11 (throughput from external I/O; NFS round trips make the requests in flight a main lever), and F12.

## What Changes

- The walk runs its I/O in a thread pool: listing a directory, the `lstat` of each entry, the content sniffing of each file, and the format calls (they may read). Subdirectories are walked at the same time; a directory's recognition still waits for all of its subdirectories (post-order), and nothing below a collapsed directory is listed, as now.
- The result is the same whatever the number of threads: the same datasets, records, warnings and skipped entries, in the same order as the walk with one thread, which does what today's walk does. The stored state of commit 3eff7e2 (unchanged directories taken over without opening files, computed bottom-up) is kept as it is.
- **New setting `MODAMA_CRAWLER_WALK_THREADS`**, default 32; 1 walks one step at a time.
- MIME magic matching (pyxdg, pure Python, about 4.2 ms CPU per sniffed file, holding the GIL) runs in worker processes, as many as `MODAMA_CRAWLER_EXTRACT_WORKERS` gives (default: the CPUs, up to 8); that setting then counts the crawler's worker processes for both, matching during the walk and extraction after it.
- Readability (R35) without one `ACCESS` round trip per file: where the file's mode bits grant read access to the crawler's user or group, the file counts as readable; otherwise the kernel is asked (`os.access`), as now.
- A sniffed file is opened with `posix_fadvise(POSIX_FADV_RANDOM)`, so that the client does not read ahead (196 kB to 20.5 kB per sniffed file in the study).

Behaviour towards the user: a harvester and a searcher see no change (same records). An operator sees a faster crawl, a new setting, `MODAMA_CRAWLER_EXTRACT_WORKERS` also used during the walk, more threads and processes in the crawler's container, and different NFS load: many requests in flight instead of one.

Out of scope: Rust, io_uring, Direct I/O, a new dependency; `fstat` after open and the file type from `d_type` (the stored state needs every entry's `lstat` before the directory's recognition, design D3); bounding memory beyond what the benchmark shows is needed; extraction's own concurrency (unchanged); checkpointing; formats' own reads (`Directory.read`, unchanged).

## Prediction for the next staging run

On the real tree, cold, with this change and nothing else changed in the crawl: the walk's rate is files/s ≈ min(32, S) / (RTT × k), where S is the NFS session slots production grants, RTT the mean round trip and k the NFS operations per file, all three read from the same run (`nfs-stats.sh`, the `nfs4_sequence_done` tracepoint for S). The prediction holds if the measured rate is within a factor of 2 of that. In numbers: with S ≥ 30 and RTT ≤ 25 ms, at least 150 files/s averaged over the first hour of the walk, against 16 in run 2; bytes received per file opened at most 40 kB, against 1.1 MB in run 2. It fails if the rate is below 100 files/s under those conditions while the crawler uses less than one core.

Caveats from the study: the test tree's files are zeros (no real headers: formats that parse a header only warn, magic matching may cost differently on real data); the real storage reads data from disk (16 to 43 ms per READ in run 2, 0.47 ms for the sparse test tree), and many requests in flight may raise that; production's slot count is unknown (`BACKLOG.md`), and on the emulated server about 30 slots cap the crawl at about 1,450 operations/s; the real storage looked up almost every entry (21,769 LOOKUPs against 6,620 in the VM), so k is likely higher there than in the benchmark; extraction after the walk is not covered.

## Capabilities

### New Capabilities

### Modified Capabilities
- `crawl`: the walk's result does not depend on the number of threads; the number is a setting.

## Impact

- `walk.py` (the walk as asyncio tasks over a thread pool; readability by mode bits), `mime.py` (fadvise; magic matching through a given function, worker-process matcher), `cli.py` (the setting, the processes), tests (`test_walk.py`: one thread against many on the fixture trees, the setting).
- `README.md` (settings), `BACKLOG.md`, the benchmark's README (results).
- No new dependency; standard library only (`asyncio`, `concurrent.futures`).
