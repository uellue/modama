# Design

## Context

`walk.py` visits the tree depth first, one system call after the other: per directory a `scandir`, an `lstat` and an `os.access` per entry, an `lstat` of the directory, the pre-order call (collapse check), the subdirectories, then per file the MIME detection (a glob, and for files without a decisive name an open and a read of `Mime.magic.maxlen` bytes plus pyxdg's magic matching) and the post-order call. Since 3eff7e2 a directory whose listing and whole subtree are unchanged takes over its stored datasets without opening a file (D3 of `em-formats-and-extraction`). On NFS each of these calls can be a round trip (16 to 43 ms on production in run 2), and nothing overlaps.

The I/O study (2026-11-11, `/python/crawler/benchmark/pywalk.py` on the `crawler` branch and its log; benchmark tree `shapes/shape-0.05-seed1`: 3,274 directories, 22,109 files; `BENCH_DELAY=10ms`, so 20 ms per round trip):

| variant | files/s | note |
|---|---|---|
| current crawler | 11 | |
| Python, 64 threads, `lstat` in the file's task, no `os.access`, fadvise | 332 | 52.9 s user CPU in one process: magic matching holds the GIL |
| the same, magic matching in 4 processes | 438 | 4.0 s user CPU in the main process; 74,438 NFS operations, 3.4 per file |
| Rust, 64 threads, io_uring (8 or 128) | no gain over threads | |

About 30 NFSv4.1 session slots on the emulated server cap the crawl at about 1,450 operations/s; at 3.4 operations per file that is the 438 files/s measured.

## Goals / Non-Goals

**Goals:** many NFS requests in flight during the walk; the same result as the serial walk, also with the stored state; the code still reads as the post-order walk the `crawl` spec describes.
**Non-Goals:** the last factor (Rust, io_uring); bounding memory before a measurement asks for it; changing what formats see or how they read.

## Decisions

**D1. The walk as asyncio tasks, the I/O in a thread pool.** Each directory is a coroutine: it awaits its listing, its pre-order call, then starts one task per subdirectory and awaits them in name order, then awaits its files' detections and its post-order call. Every call that may block (a listing, an `lstat`, a detection, a format call, a stored-state query) goes to a `ThreadPoolExecutor` with `MODAMA_CRAWLER_WALK_THREADS` threads through `run_in_executor`. The coroutines run in the calling thread; only they touch the `Result`. The post-order dependency (a parent after its children) is an `await`, so no thread waits for another task and a bounded pool cannot deadlock. The listing's `lstat`s are one task per entry, gathered, so a directory of 20,000 files (F6) is not 20,000 round trips in a row.
*Alternatives:* (a) one pool task per directory that waits for its children's tasks: deadlocks once the tree is deeper than the pool is wide; (b) a serial walker in the main thread that prefetches I/O ahead of itself: simplest to keep in order, but it waits for each directory's listing on the critical path (about 3,300 directories × 2 to 3 round trips, over 150 s on the benchmark), unless it prefetches speculatively, which would list inside collapsed trees; (c) futures chained by callbacks: the same as D1, written by hand; (d) a pool of processes for everything: pickling of entries and formats, and the stored-state connection, for no gain on I/O. The decision log lists asyncio as not chosen for extraction "because file reads end in a thread pool anyway"; here asyncio only orders the work, and the reads do end in the thread pool.

**D2. Determinism by construction and by sorting.** Format calls get the same inputs as before (entries sorted by name, children's datasets in name order, since the subdirectory tasks are awaited in name order). Warnings and skipped entries are sorted at the end, as now; datasets are sorted by anchor, as now; the stored listings are sorted by path at the end (before: post-order insertion; the store does not depend on it). The order of log lines may differ between runs; the result does not. Verified by a test that walks every installed collection's fixture trees and the test trees of `test_walk.py` with one thread and with many and compares the whole result (D7).

**D3. `lstat` per entry, kind from it; no `d_type`, no `fstat` after open.** The study's best variant took a file's kind from `d_type` and its attributes from `fstat` after the open. The crawler needs every entry's size, times and owner before the directory's pre-order call (the stored-state digest, the formats' `Entry`), and a file with a decisive name is never opened, so both would save nothing here; the `lstat`s run in parallel instead (D1).

**D4. Readability from the file system: `os.access` per file, in the thread pool.** R35 skips files the crawler cannot read. `os.access` costs an `ACCESS` round trip per file on NFS (21,746 on the benchmark tree, a quarter of all operations); it runs in the entry's task, so it overlaps with the other calls. The file system is the truth: the storage enforces rules that no client sees in the mode bits (immutable flags, which NFS does not even carry; ACLs; identity mapping), and they are used on purpose (@weber, 2026-11-11).
*Alternatives:* readability from the mode bits, `os.access` only where they deny (built first; rejected by @weber 2026-11-11, since it infers who sees what from what the client sees); drop the check and rely on the sniffing open, which breaks R35 for files with a decisive name, since they are never opened.

**D5. Magic matching in worker processes.** pyxdg's `Mime.magic.match_data` costs about 4.2 ms CPU per sniffed file and holds the GIL; with 64 threads it used one core and capped the walk at 332 files/s. `mime.detect_with_tie` gets an optional `match` function; the walk passes one that sends the bytes read to a `ProcessPoolExecutor` (spawn context, as extraction; each worker activates the same compiled MIME database) and looks the returned type name up in the parent's database, so the rest of the detection is unchanged. The number of processes is `MODAMA_CRAWLER_EXTRACT_WORKERS` (default: the CPUs up to 8): one setting for the crawler's CPU-bound worker processes, used one after the other (the walk, then extraction). Processes start on first use, so a crawl whose files all have decisive names starts none. `walk()` matches in its own threads unless it is given a number of processes; `crawl` and `records` pass the setting's.
*Alternatives:* libmagic or the `xdg-mime` crate (a new dependency, possibly different results); a separate setting for the matching processes (no need yet).

**D6. `posix_fadvise(POSIX_FADV_RANDOM)` on the sniffing open.** Turns off the client's readahead for that file descriptor: 196 kB to 20.5 kB received per sniffed file in the study, same bytes returned. Only in `mime.py`; `Directory.read` (formats, up to the 1 MiB budget) keeps readahead, which helps reads of that size.

**D7. Verification.** The comparison test of D2; the existing tests run with the default number of threads, so the stored-state tests of `test_extraction.py` and `test_walk.py` cover the parallel walk; one test runs the walk with matching processes. The benchmark (`benchmark/run.sh`, `BENCH_DELAY=10ms`) before and after on the reference tree: files/s, NFS operations and bytes per file, CPU, peak memory, with the load average.

## Risks / Trade-offs

- [Memory: all directories in progress at once hold their entries; F13 already measured about 2.5 kB per file] → peak memory measured on the benchmark before and after; a bound (a semaphore on directories in progress) only if the measurement asks for it.
- [Format calls run in threads] → formats are stateless (checked: no instance or module state is written in the core or `modama-formats-em`); each call gets its own `Directory`. A call's wall time now depends on the other threads (the GIL, requests in flight), so the time limit checked after the call, which discarded a finished result, made the result depend on the thread count (review finding 2). It is gone at the root (D8).

**D8. A slow format call keeps its result.** The limit was checked after the call returned, so it never stopped a hang; it only turned slowness into missing datasets and `retry`. A call over `SLOW` (5 s) is now logged with the format, the directory and the time, and its result is kept; the log line is not one of the result's warnings, since the time depends on the load (spec `crawl`, "The same data gives the same result or a failure"; spec `recognition`: "Budgets bound every format call" replaced by "A byte budget bounds every format call" and "A slow format call keeps its result"). Stopping a call that hangs needs format calls in worker processes (architecture G), and a timeout there is a failure. @weber, 2026-11-11.
*Alternatives:* CPU time of the thread instead of wall time (still a discarded result, and a hang on NFS never counts); fewer format calls at once (less contention, the same dependence).
- [pyxdg's type cache under threads] → all types are created when the database is loaded, so lookups during the walk only read the cache; the comparison test would show a type object created twice (identity checks in `mime._is_a`).
- [Load on the production storage: 32 requests in flight] → one setting; the staging run measures the round trips under that load.
- [SIGTERM and Ctrl-C during the walk] → the pool is shut down with its queued work cancelled; the crawl records the failed run, as now (`test_trigger.py`). The SIGTERM handler only sets a flag, never raises: a raise from it is dropped where the main thread runs a weakref callback, `__del__` or the garbage collector, or leaves a lock held (review finding 1). The crawl checks the flag at every directory of the walk, at least every second while it extracts (the extraction processes killed) or waits for the store lock (in turns of a 1 s `lock_timeout`), between its phases and before the store commits; each ends as a failed run with status 143.

## Open Questions

- The default of 32 threads: enough for 30 slots; production's slot count is unknown (`BACKLOG.md`).
