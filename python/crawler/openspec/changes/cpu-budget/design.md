# Design

## Context

See proposal.md, "Why". The facts, measurements and sources are in `docs/research/cpu-oversubscription.md` (commit 1b77989, on branch `worktree-agent-a7ed4152ec18fcbf9`, not yet on `crawler`), cited below as "the note" with its section.

Today:
- **Crawler.** `extraction.default_workers()` is `min(os.cpu_count() or 1, MAX_WORKERS)` with `MAX_WORKERS = 8` (`extraction.py:33,49-50`). `cli._workers()` reads `MODAMA_CRAWLER_EXTRACT_WORKERS` (`cli.py:235-238`) and passes it, or the default, to the walk's matching pool (`cli.py:213`, `520`) and to extraction (`cli.py:223`, `529`). Both pools use the spawn context (`walk.py:131-136`, `extraction.py:224,241-247`); extraction replaces a worker after 100 tasks (`max_tasks_per_child`), and its initializer sets `RLIMIT_AS` to 4 GiB (`extraction.py:38,194-198`). `os.cpu_count()` counts the machine, not the affinity or the quota (the note, section 3).
- **Transform worker.** `airflow-worker-transform` runs `celery worker --queues transform --concurrency 1` (`prototypes/search-stack/docker-compose.yml:422`), staging overrides it with `--concurrency 4` (`docker-compose.staging.yml:52`), `perf/docker-compose.perf.yml` with `${PERF_CONCURRENCY:-1}`. `--concurrency` wins over `AIRFLOW__CELERY__WORKER_CONCURRENCY: "4"` (`docker-compose.yml:39`), whose value is only the option's default (Airflow's celery provider, `cli/definition.py:77-82` in the image; read 2026-11-12). Each batch is a fresh Python of the transform venv (`@task.external_python`, `transform_index.py:68-75`), which inherits the worker's environment: `EMBEDDING_MODEL` is set only there (`docker-compose.yml:431`) and read by `transform_core.py:35`. `transform_core.py` imports fastembed, and with it numpy and ONNX Runtime, at module level (line 10), and creates `TextEmbedding` without `threads` (line 64). The DAG runs one run at a time (`max_active_runs=1`, `transform_index.py:31`) under Airflow's `max_active_tasks_per_dag`, 16 in the image (read 2026-11-12), shared with the file-metadata batches on the default queue (F16). Patch 0002 (`perf/patches/0002-embedding-threads-setting.patch`, untracked in the main checkout) passes `EMBEDDING_THREADS` to fastembed; it is not applied. The airflow image is built from upstream's Dockerfile without patches (`docker-compose.yml:20-27`); the image has no `patch` and no `git` (checked 2026-11-12), as upstream's search API image (`search-api.Dockerfile`).

## Goals / Non-Goals

**Goals:** the defaults right on any machine without numbers per machine; one small module per environment with a tight interface; the budget visible in one log line; overrides for measurement.
**Non-Goals:** a split of the machine between containers (@weber, question 115: "no split"); tuning P × T on the dev server here (that is the measurement task); the default Airflow worker, PostgreSQL and OpenSearch.

## Decisions

**D1. Which pool is which, and what it counts** (@weber, question 115: "for IO bound tasks, hyperthreading works very well in my experience"; math pools on physical cores unless a measurement says otherwise).

| Pool | Kind | Counts | Size |
|---|---|---|---|
| Crawler: the walk's threads (`MODAMA_CRAWLER_WALK_THREADS`, 32) | I/O: wait on NFS (parallel-walk D1) | nothing; outside the CPU budget | unchanged |
| Crawler: matching processes | pure Python, one thread each (pyxdg holds the GIL, parallel-walk D5), fed by the NFS-bound walk | logical CPUs | min(usable, 8) |
| Crawler: extraction processes | I/O: header reads over NFS (`em-formats-and-extraction` D1, D7) | logical CPUs | min(usable, 8), the same setting |
| Crawler: BLAS/OpenMP inside those processes | math, but idle: nothing heavy is computed | – | 1 |
| Transform: batch processes (Celery) | mixed: `jsonschema` validation pure Python (about 60 % before patch 0001, F16), embedding | physical cores | P |
| Transform: ONNX Runtime intra-op | math | physical cores | T, explicit (no pinning) |
| Transform: tokenizers (Rayon) | math-like, runs between the ONNX Runtime calls (the note, section 4, last bullet) | physical cores | T |
| Transform: OpenBLAS (numpy) | math, but only pooling and normalising small vectors (the note, section 5) | – | 1 |

Because the crawler's cap of 8 is below both machines' counts, logical against physical matters for it only in a container with fewer than 8 cores; there logical is the decision. For the transform worker the choice is real (24 against 48 on the dev server) and stays open to the measurement (tasks 5.x); until then physical, as ONNX Runtime and oneMKL do by default (the note, section 3).
*Alternative:* logical everywhere, as dask, OpenBLAS and Rayon do: simpler, one count; but no evidence that SMT helps the embedding, and 48 × 1 would double the memory (48 × 4.4 GB = 211 GB of 251).

**D2. The count, modelled on `dask.system.cpu_count`** (dask 2026.8.0, `dask/system.py:17-89`, BSD-3-Clause; read in the crawler's venv): logical CPUs = `os.process_cpu_count()` (affinity and cpuset; also honours `PYTHON_CPU_COUNT`), capped by ⌈quota ÷ period⌉ of the process's own cgroup: v1 `cpu.cfs_quota_us`/`cpu.cfs_period_us`, v2 `cpu.max` of the group named in `/proc/self/cgroup`. Measured in the VM: `--cpus 2.5` gives `cpu.max` `250000 100000`, `/proc/self/cgroup` `0::/`, and `os.process_cpu_count()` 8 (so the quota has to be read). Physical cores (transform only) = the distinct `topology/core_cpus_list` among the CPUs of `os.sched_getaffinity(0)`, then capped by the same ⌈quota⌉; if the topology files are missing, the logical count, said so in the log line. Not psutil (absent in the transform venv, only transitive in the crawler's; the note, section 2) and not a copy of dask's code: about 15 lines of our own in each module, without dask's psutil branch.
*Alternative:* `nproc` in shell: ignores the quota and obeys `OMP_NUM_THREADS` (measured, the note, section 3).

**D3. Crawler: `src/modama_crawler/cpus.py`.** Interface:
- `usable(root: Path = Path("/")) -> Usable`, a frozen dataclass with `affinity: int`, `quota: float | None` and the property `cpus` (min of the two, the quota rounded up). `root` is the seam for tests (a fake `sys/fs/cgroup` and `proc/self/cgroup` under `tmp_path`).
- `set_num_threads_env(n: int = 1)`: LiberTEM's context manager (`src/libertem/common/threading.py:240-284` at `d6aa0fa`), copied without the numba branch (lines 260-262, 268-269; numba is in neither environment, the note, section 2). It sets `MKL_NUM_THREADS`, `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` and restores the old values afterwards. The module's header carries LiberTEM's copyright line ("Copyright (c) 2024 LiberTEM creators") and the MIT permission notice, with the source URL and commit; the crawler is MIT too (`python/crawler/LICENSE`).
- Users: `extraction.default_workers()` becomes `min(cpus.usable().cpus, MAX_WORKERS)`; `extraction._run` runs its pool loop inside `set_num_threads_env(1)`; `walk.walk` creates and uses its matching pool inside it. `cli.py` stays the only reader of the environment and logs the budget (D8).

**D4. Crawler: the variables are set in the parent around the pool's lifetime, not in the worker's initializer.** Spawned workers then have them in their environment from `exec` on, before any import (unpickling the initializer imports `modama_crawler.extraction` and `.formats`), and replacement workers after 100 tasks get them too (LiberTEM's pattern, its docstring: the other methods "only limit the number of threads that are _used_, not the number of threads that are created"). The parent imports no numpy (measured, the note, section 6), so the variables set there do not shrink a pool the parent uses (LiberTEM #1053 was that leak); the context restores them at the end.
*Alternative:* three `os.environ` lines in `_limit_memory`: shorter, but depends on nothing importing numpy before the initializer runs, and @weber chose the copy ("let's just copy the few lines here").

**D5. Transform worker: a start script, not a patch of `transform_core.py`.**
- *(a) Start script* `prototypes/search-stack/transform-worker/budget.py`, mounted read-only into `airflow-worker-transform`; the command becomes `python /opt/modama/budget.py celery worker --queues transform`. The image's entrypoint runs `python` commands directly (`/entrypoint`, `exec_to_bash_or_python_command_if_specified`); the script computes the budget, logs it, sets `EMBEDDING_THREADS=T`, `RAYON_NUM_THREADS=T`, `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`, `MKL_NUM_THREADS` to 1 in its own environment and `exec`s `/entrypoint celery worker … --concurrency P`, so the entrypoint's wait for the broker still runs (it does so only for `celery` and `scheduler` commands). Celery's children and every batch process inherit the variables (evidence: `EMBEDDING_MODEL`, Context). Runs on the image's Python 3.13, where `os.process_cpu_count()` exists, and reads the DAG limit from `airflow.configuration.conf`. Needs patch 0002 for `EMBEDDING_THREADS` (fastembed has no variable of its own, ONNX Runtime none either; the note, section 2).
- *(b) Patch `transform_core.py`* to compute T when `EMBEDDING_THREADS` is unset: it needs P in the environment anyway (the effective `--concurrency` is not visible to the batch), and it is too late for OpenBLAS, which reads its variable when numpy loads, at `transform_core.py:10`. A larger patch to upstream code for each upgrade.
- *Lean: (a).* Patch 0002 stays the only change to upstream code, 4 lines, and is a candidate upstream. *Strongest argument against:* the script replaces a plain compose `command:` with our own program in front of Celery; if it fails, the worker does not start (mitigation: it fails loudly with a message, and the health check shows it).
- Interface: `machine(root: Path = Path("/")) -> Machine` (logical CPUs, cores, quota, memory), `budget(machine, *, slots, per_process, processes=None, threads=None) -> Budget` (P, T, the reasons for the log line), `main(argv)`. Tests with a fake `/sys` and `/proc` under `tmp_path` and a patched `os.sched_getaffinity`; they need no Airflow (`main` imports it, `budget` does not).
- No LiberTEM copy here: the script sets the variables once for the whole process tree and `exec`s, so nothing is to be restored.

**D6. Transform worker: P is capped by the DAG's limit of active tasks.** With `max_active_runs=1`, at most 16 tasks of the indexing DAG run or wait at once, transform and file-metadata batches together (F16: "16/16 running and queued tasks" 468 times). A P above it only adds idle processes, and T = cores ÷ P would be too small. So P = min(cores, ⌊memory ÷ per process⌋, slots), read from Airflow's configuration, which also covers `AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG` when one is set later. On the dev server that is 16 × 1 on 24 cores, leaving 8 for PostgreSQL and OpenSearch, which run at the same time.
*Alternatives:* raise the DAG limit to a large constant so that only cores and memory govern (24 × 1 on the dev server); or let T absorb the rest (24 ÷ 16 → 1 now; a rule like 12 × 2 would use all 24). Both are for the measurement to settle; question below.

**D7. Memory as the second limit.** Memory = the container's cgroup memory limit (v2 `memory.max`, v1 `memory.limit_in_bytes`) if set, else `MemTotal`. Per batch process 4.4 GB, the upper end of F16's 2.3 to 4.4 GB (staging, batches of 2,000; whether that was RSS or address space is not stated there). In the VM (`MemTotal` 24,615,748 kB, read 2026-11-12) that gives 5, so the VM's default becomes 5 × 1, where the base compose file runs 1 today. The constant is provisional until measured at the test deployment's batch size of 250 (task 5.3).

**D8. Overrides and the log line.** Crawler: `MODAMA_CRAWLER_EXTRACT_WORKERS` as today; the BLAS threads have no override (nothing to measure there). Transform: `TRANSFORM_PROCESSES` and `EMBEDDING_THREADS` (patch 0002's name); `perf/docker-compose.perf.yml` sets `TRANSFORM_PROCESSES` from `PERF_CONCURRENCY` instead of the command. The log lines are in the spec; the crawler's goes to stderr at INFO, the transform worker's to the container log before Celery's banner.

**D9. Patch 0002 in the image.** As `search-api.Dockerfile`: a `warehouse-airflow.Dockerfile` that copies `/opt/airflow/project/src` from the built airflow image into a busybox stage, applies `patches/warehouse/*.patch` (a patch that does not apply fails the build) and copies the result back. Since the base is itself built by compose, it is referenced through `additional_contexts` with `service:` (Docker Compose 2.26.1 in the VM; to be confirmed that it builds in order) or the airflow image is built by our Dockerfile from the submodule's context; decided in task 3.1 by what builds.

## Verification in the VM, and what only the dev server can settle

- Crawler: unit tests (fake cgroup, patched `os.process_cpu_count`), a test extractor that reports its threads, the crawler's suite, then a crawl in the stack with `--cpus 4` on the crawler service (log line says 4).
- Transform worker: unit tests of `budget()` with the spec's numbers; the stack up, its log line; `perf/batch-probe.py` on a batch process (thread count, `Cpus_allowed_list`); `perf/embed-bench.py 1:8 2:4 4:2 5:1 8:1` and `perf/indexing-bench.sh 16000 250` with the budget against `TRANSFORM_PROCESSES=1` (today's base) and `4` with `EMBEDDING_THREADS=2` (the note's best); load average ≤ 8.
- Only the dev server: SMT (`embed-bench.py` 24:1, 12:2, 8:3, 24:2, 48:1 while staging is idle), the thread composition at 48 CPUs (the note's 119 prediction), contention with PostgreSQL and OpenSearch at staging volume, and the 16 against 24 processes question. @weber runs it (task 5.4); its outcome may change D1's count for the transform worker or the DAG limit, not the interfaces.

## Risks / Trade-offs

- [Two copies of the quota reading (crawler, transform worker) drift apart] → both small and tested with the same fake files; a package once LiberTEM wants it (Not now).
- [A quota on a parent cgroup is not seen (as dask)] → only the own group's quota is read; whether production sets quotas on a slice is a question below.
- [The VM's test deployment runs 5 batch processes instead of 1, and the e2e test's other services get less CPU] → the e2e test's timings are checked in task 4.2; `TRANSFORM_PROCESSES=1` in the override file if needed.
- [4.4 GB per process is a guess for batch 250] → task 5.3 measures it; the constant is one number in the script.
- [The start script is between Docker and Celery] → it only computes and `exec`s; a failure is a clear message and a container that does not become healthy.
- [Crawler and transform worker overlap on the dev server (a crawl and a 19-hour indexing run, F16) and each counts all CPUs] → accepted with "no split"; the crawler's 8 processes are mostly waiting on NFS.

## Migration Plan

Rebuild the stack's images, `./downtest.sh && ./uptest.sh`; staging picks it up at its next `./upstaging.sh`. Rollback: the compose files' old `--concurrency`, the crawler's previous image. No data is touched.

## Not now

- A CPU split per container in the compose files (@weber: "no split"), and a reserve for PostgreSQL and OpenSearch beyond D6.
- The default Airflow worker (`AIRFLOW__CELERY__WORKER_CONCURRENCY: "4"`), its file-metadata batches, and the other services' pools.
- A package for the count (the note, section 7, option b), for example in the LiberTEM organization, once LiberTEM wants the container-aware count too.
- Quotas on parent cgroups; Windows and macOS.
- Memory per batch process from `CELERY_BATCH_SIZE` instead of a constant.
- Patch 0001 (one validator), which changes the best P against T (the note, section 5).
- Turning ONNX Runtime's spinning off (not reachable through fastembed 0.8.0).

## Decisions by @weber, 2026-11-12

- **The DAG's limit (D6):** "without any settings it should run the full thing, but here (devvms running etc) we restrict it. 16 sounds sensible." So with no setting the cores and memory govern: the base compose file must not let Airflow's default of 16 active tasks per DAG bind (D6 changes: raise or derive it there), and the dev server restricts it to 16 in its own deployment file (`docker-compose.staging.yml`, `AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG: "16"`), which the start script reads as today.
- **Physical cores for the math pools (D1): agreed.** "In my experience it worked well to have physical cores for math, and background work done by hyperthreading in parallel."
- **The VM: 5 × 1 is fine** (8 cores, memory limits it to 5).
- **Production limits:** "I don't think we have any limits beyond what we do with docker at this time." A backlog item: whether and how to manage CPU limits in production (slices, per-container quotas).
- **Override names:** explained to @weber (they bypass the computed budget for measurements; no clash found with existing variables); pending his answer, the names stay.
- **`perf/`: commit it** with this change, in `prototypes/search-stack/perf/` (search-stack benchmarks, next to the compose files they use).
