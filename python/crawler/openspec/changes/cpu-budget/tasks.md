# Tasks

Written with the leans of design.md as assumptions (D1 physical cores for the transform worker, D5 a start script, D6 P capped by the DAG limit); an answer of @weber to a question there changes the task named with it.

## 1. Requirements

- [ ] 1.1 Merge the research note (`docs/research/cpu-oversubscription.md`, commit 1b77989) into `crawler`, then write R43 into `design/requirements.md` (Scale) and the CPU-budget bullet into `design/requirements-pipeline.md` 2.4, with the wording of proposal.md, and a decision-log row in `design/architecture.md` (copy of LiberTEM's lines, the start script, pools by kind). Verify: `git diff` shows the three additions and the note's path resolves from both files.

## 2. Crawler

- [ ] 2.1 `src/modama_crawler/cpus.py`: `usable(root)` (D2, D3) and `set_num_threads_env` copied from LiberTEM `d6aa0fa` `src/libertem/common/threading.py:240-284` without the numba branch, the MIT notice and "Copyright (c) 2024 LiberTEM creators" in the header. Verify: `tests/test_cpus.py`, one test per spec scenario of "The crawler counts the CPUs it may use" with a patched `os.process_cpu_count` and fake `sys/fs/cgroup/cpu.max` (v2) and `cpu,cpuacct/cpu.cfs_quota_us` (v1) under `tmp_path`, plus a test that the environment is restored ("The crawler's environment is restored").
- [ ] 2.2 `extraction.default_workers()` from `cpus.usable()`; `extraction._run` and the walk's matching pool inside `set_num_threads_env(1)` (D4). Verify: a test extractor that imports numpy and returns its `Threads` from `/proc/self/status` gets 1 on the VM's 8 CPUs ("An extractor that loads numpy"); the crawler's suite and `modama-formats-em`'s suite pass.
- [ ] 2.3 The log line in `cmd_crawl` and `cmd_records` (D8). Verify: `test_cli.py` checks the two spec scenarios of "The crawl logs its CPU budget"; the line read by eye in a terminal run of `modama-crawler records` on a test tree.
- [ ] 2.4 README (configuration: the count instead of "the number of CPUs up to 8", the log line, the BLAS threads and why), `BACKLOG.md`. Verify: the README's sentences match the spec; `uvx ruff check` and `uvx ruff format --check --diff` from the repo root, `pre-commit run --all-files`.

## 3. Transform worker

- [ ] 3.1 Patch 0002 into the image (D9): `prototypes/search-stack/patches/warehouse/0002-embedding-threads-setting.patch`, a Dockerfile in the pattern of `search-api.Dockerfile`, the compose build entry. Verify: `docker compose build` applies the patch (its log line `applying …`), and `grep -n EMBEDDING_THREADS` in the built image's `transform_core.py` finds it.
- [ ] 3.2 `prototypes/search-stack/transform-worker/budget.py`: `machine(root)`, `budget(...)`, `main(argv)` (D2, D5 to D8); per-process memory 4.4 GB. Verify: `test_budget.py` next to it, run with the crawler's `~/.venv/bin/pytest`, one test per spec scenario of the three transform-worker requirements on counting, sizing and overrides, with fake `sys/devices/system/cpu/cpu*/topology/core_cpus_list`, `cpu.max`, `memory.max`, `proc/meminfo` and a patched `os.sched_getaffinity`; a syntax check with the image's Python 3.13 (`docker run … python -m py_compile`).
- [ ] 3.3 Compose: mount the script, the command `python /opt/modama/budget.py celery worker --queues transform` in `docker-compose.yml`; staging's `--concurrency 4` removed; `perf/docker-compose.perf.yml` sets `TRANSFORM_PROCESSES` from `PERF_CONCURRENCY` (if the perf scripts are committed, question in design). Verify: `docker compose config` shows no `--concurrency` for `airflow-worker-transform`; after `./uptest.sh` its log has the `CPU budget:` line with 5 × 1 in the VM, and `celery inspect stats` reports a pool of 5 processes.
- [ ] 3.4 The stack's README: the budget, the log line, the overrides, the dependence on patch 0002. Verify: the commands in it run as written.

## 4. Integration in the VM

- [ ] 4.1 A crawl in the test deployment with `cpus: 4` added to the crawler service for the run only. Verify: its log line says 4 worker processes, `affinity 8, quota 4`.
- [ ] 4.2 `./runtest.sh e2e` with the budget. Verify: PASS, the number of skipped tests given, its time against the last run's; `perf/batch-probe.py` on one batch process: threads within the scenario "A batch in the test deployment", no pinned thread.

## 5. Measurements

- [ ] 5.1 `perf/embed-bench.py 1:8 2:4 4:2 5:1 8:1` in the VM's transform worker, with and without `OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=T`. Verify: texts/s and CPU ms per text in a table in the stack's README or the field-test findings; the budget's P × T within 10 % of the best.
- [ ] 5.2 `perf/indexing-bench.sh 16000 250` with the budget (5 × 1) against `TRANSFORM_PROCESSES=1` and against 4 × 2. Verify: records/s, load average ≤ 8, recorded as above.
- [ ] 5.3 Memory per batch process at batch sizes 250 and 2,000 (RSS and `VmSize` from `/proc/<pid>/status` by `batch-probe.py`). Verify: the numbers recorded; the 4.4 GB constant in `budget.py` kept or changed with them, and the VM's scenario in the spec updated if P changes.
- [ ] 5.4 On staging (@weber, while it is idle): `embed-bench.py` 24:1, 12:2, 8:3, 24:2, 48:1 in the transform worker; one thread listing of a batch process by pool; the `CPU budget:` line after `./upstaging.sh`; core siblings from `/sys/devices/system/cpu/cpu0/topology/core_cpus_list`. Verify: the numbers in `design/field-tests/search-stack-staging-findings.md`; then D1's count for the transform worker (physical or logical) and the DAG limit (D6) confirmed or changed in design.md and the spec.

## Workflow follow-up

- Review by an agent that did not write the code (the start script decides how a service starts), given the code and the spec.
- Archive after @weber's review and the measurement of 5.4.
