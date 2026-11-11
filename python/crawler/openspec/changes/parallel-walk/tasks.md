# Tasks

## 1. Before

- [x] 1.1 Benchmark the current walk (`records`) on the reference tree with `BENCH_DELAY=10ms`: files/s, NFS operations and bytes per file, CPU, peak memory, `uptime`. Verify: the numbers in `benchmark/README.md`, with the load average. 17.3 files/s (the study's 11 was another run).

## 2. The parallel walk

- [x] 2.1 The walk as asyncio tasks over a thread pool (D1), the result sorted (D2), `threads` as a parameter of `walk()` with default 32. Verify: the whole crawler suite and `modama-formats-em`'s suite pass unchanged, among them the stored-state tests in `test_extraction.py` and `test_walk.py`.
- [x] 2.2 One thread against many: a test that walks every installed collection's fixture trees and a tree with the stored state (a change three levels down) with 1 and 16 threads and compares datasets, warnings, skipped entries, listings and the count of unchanged directories. Verify: the test, spec scenarios "One thread against many on the fixture trees" and "Many threads with the last crawl's state"; the existing `test_collapsed_directory_is_not_entered` with the default threads covers "A collapsed directory with many threads". Checked that it can fail: without sorting the listings, 5 of its 6 cases fail.
- [x] 2.3 Readability from `os.access` per file, in the thread pool (D4; first built from the mode bits, reverted on @weber's decision of 2026-11-11). Verify: `test_unreadable_entries_are_skipped_and_logged`; `test_the_file_system_decides_readability_not_the_mode_bits`; the benchmark again (task 3.1).
- [x] 2.4 `posix_fadvise(POSIX_FADV_RANDOM)` on the sniffing open (D6). Verify: `test_mime.py` still passes; the benchmark's bytes per sniffed file (task 3.1).
- [x] 2.5 Magic matching in worker processes (D5). Verify: a test that a walk with processes gives the same result as one without on the fixture trees.
- [x] 2.6 The setting `MODAMA_CRAWLER_WALK_THREADS` for `crawl` and `records`, and `MODAMA_CRAWLER_EXTRACT_WORKERS` for the matching processes; README and backlog updated. Verify: spec scenarios "A limit on reads in flight" and "Not a number" as tests in `test_cli.py`/`test_walk.py`; `uvx ruff check`, `uvx ruff format --check`.

## 3. After

- [x] 3.1 Benchmark the parallel walk as in 1.1, same tree and delay; then the delay removed (`nfs-up.sh` without `BENCH_DELAY`). Verify: before and after in `benchmark/README.md`; files/s at least 300 (the study's 438 less the crawler's own work per directory), bytes received per sniffed file at most 40 kB, peak memory at most 1.5 times the serial walk's. Met: 546 files/s, 18 kB per file opened, the largest process 219 MB against 210 MB (the cgroup's peak counts page cache: 596 MB against 1,074 MB); `records` output identical.
- [ ] 3.2 Review by an agent that did not write the code, given the code, this change and `design/requirements.md`. Verify: findings verified and listed in this change's `review.md`.
- [ ] 3.3 Staging on the real tree, @weber at the host: the prediction in `proposal.md`. Verify: the findings file, the next run, with S, RTT and k from the run's counters; whether the matching processes limit the walk (CPU of the workers, their memory), since they share `MODAMA_CRAWLER_EXTRACT_WORKERS` with extraction (@weber, 2026-11-11: keep one setting, watch it).
