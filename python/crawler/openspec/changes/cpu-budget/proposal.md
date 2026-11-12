# Proposal

## Why

Where several processes run, each math library sizes its thread pool for the whole machine, on its own. On the dev server (24 cores, 48 logical CPUs) a transform batch process starts about 119 threads (1 + 47 OpenBLAS + 23 ONNX Runtime, pinned to the same 23 cores in every process, + 48 Rayon; a prediction from the code that fits the 95 to 143 observed), and four of them ran at a load of 56 to 106 on 48 CPUs (F16, F17). In the VM, 4 processes × 2 threads embedded 194 texts/s against 118 with the defaults (`docs/research/cpu-oversubscription.md`, commit 1b77989, "For people"). In the crawler, each extraction worker starts CPUs − 1 idle OpenBLAS threads of about 41 MB address space each, which count against its 4 GiB `RLIMIT_AS` (measured 430 MB against 143 MB on 8 CPUs). @weber (2026-11-12): "we will run on big machines where this is super super important to avoid oversubscription. Of course we need to adapt to the local machine always. The dev server is not the same as the production server", and "the whole code should do it right by itself and not rely on the admin for this".

## What Changes

- **The crawler counts the CPUs it may use** (affinity or cpuset, and the cgroup CPU quota, rounded up) instead of the machine's (`os.cpu_count()`), for its worker processes: the walk's matching processes and the extraction processes, still at most 8. `MODAMA_CRAWLER_EXTRACT_WORKERS` stays as the override.
- **The crawler's worker processes start with one thread per math library** (`OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`, `MKL_NUM_THREADS` set to 1 before the process starts), with LiberTEM's `set_num_threads_env` copied under its MIT notice (@weber: "let's just copy the few lines here"; no dependency on LiberTEM).
- **The transform worker of the search stack computes its own budget** before Celery starts: processes P and threads per process T from the physical cores it may use, the memory per batch process and the indexing DAG's active-task limit; it sets the threads of ONNX Runtime (through patch 0002's `EMBEDDING_THREADS`, which also stops ONNX Runtime's pinning), of Rayon and of OpenBLAS. The compose files lose their `--concurrency` for that worker. Overrides for measurements only.
- **Pools are counted by kind** (@weber, 2026-11-12, decision on question 115): I/O-bound pools may count logical CPUs (SMT threads), math pools count physical cores unless a measurement shows otherwise. No per-container CPU split by default; a limit set later for a service is honoured because each process counts what it may use.
- **One log line** at start states the budget and where each number came from.
- Requirement wording for @weber's decisions: `design/requirements.md` R43 and `design/requirements-pipeline.md` 2.4 (below; written into the files by a task once accepted).

Behaviour towards the user (operators): the defaults follow the machine, so no per-machine numbers in env or compose files; staging's `--concurrency 4` goes away. `crawl` and `records` log one more INFO line, for example `CPU budget: 8 worker processes, 1 math thread each; 8 CPUs usable (affinity 8, no quota)`; the transform worker logs `CPU budget: 16 processes × 1 thread; 24 cores usable (48 logical CPUs, no quota); memory for 57, 16 DAG slots`. On a machine with fewer usable CPUs than `os.cpu_count()` (a container with `--cpus` or a cpuset), the crawler starts fewer processes than today. What a harvester or a searcher sees does not change; indexing gets faster (to be measured).

Out of scope (see design, "Not now"): a per-container CPU split in the compose files (@weber: "no split"); the default Airflow worker and the other services' pools (PostgreSQL, OpenSearch); a package of our own for the count (spun out once LiberTEM wants it); patch 0001 (one validator); parent cgroups' quotas; Windows and macOS.

Serves: the new R43 and requirements-pipeline 2.4 (CPU budget); R10 (scale), F16 and F17 (indexing time on staging); R23 (extraction failures from the memory limit, not from the machine's CPU count).

### Proposed requirement wording

`design/requirements-pipeline.md`, 2.4 Operating conditions, a new bullet:

> - **CPU budget** (@weber, 2026-11-12): every service adapts its processes and threads to the machine it runs on and does not oversubscribe it ("we will run on big machines where this is super super important to avoid oversubscription. Of course we need to adapt to the local machine always. The dev server is not the same as the production server."). The code computes the budget itself at start ("the whole code should do it right by itself and not rely on the admin for this. I wouldn't want to maintain this myself as an admin of the service."): in each process tree, processes × threads per process stays within the CPUs that process may use (affinity or cpuset, and the cgroup CPU quota), not the machine's total. Math pools (BLAS, ONNX Runtime, tokenizers) count physical cores; I/O-bound pools may count logical CPUs, since "for I/O bound tasks, hyperthreading works very well" (@weber, 2026-11-12); a measurement may change the count for a math pool. No service relies on a library's default thread count where several of its processes run. No CPU split per container by default ("no split. We may want to reduce the number of available CPUs to specific services since a lot of them are running in parallel"); a limit set for a service later is honoured by the same count. An override exists for measurements; the defaults must be right without it. Each service logs its budget at start. Checked on staging during an indexing run: load average not above the CPUs the containers may use, no batch process with more threads than its budget plus a few. Background: `docs/research/cpu-oversubscription.md`.

`design/requirements.md`, Scale:

> - **R43 (must, @weber 2026-11-12)** The crawl follows the stack's CPU budget (`requirements-pipeline.md`, 2.4): its worker processes count the CPUs the crawler may use on the local machine (affinity or cpuset, and the CPU quota), and the math libraries inside them start one thread each, so that a worker's memory limit (`RLIMIT_AS`) does not depend on the machine's CPU count. The crawler's pools are I/O-bound or pure Python and count logical CPUs. `MODAMA_CRAWLER_EXTRACT_WORKERS` overrides the count for measurements.

## Capabilities

### New Capabilities
- `cpu-budget`: how many processes and threads the crawler's worker pools and the search stack's transform worker start, counted from what the process may use on the machine, and the log line that states it. The transform worker's requirements live here because the stack has no OpenSpec of its own and the requirement's home, `requirements-pipeline.md`, is in this project's `design/`.

### Modified Capabilities
None. The extraction workers' count is in the pending changes `em-formats-and-extraction` and `parallel-walk` only as README text ("by default the number of CPUs up to 8"), not as a requirement; the README is updated by a task.

## Impact

- Crawler: new module `src/modama_crawler/cpus.py` (count, the copied LiberTEM lines with their notice); `extraction.py` (`default_workers`, the pool runs inside the copied context), `walk.py` (the matching pool, the same), `cli.py` (the log line). README configuration, BACKLOG.
- Search stack: new `prototypes/search-stack/transform-worker/budget.py` (count, budget, start of Celery), mounted into `airflow-worker-transform`; patch 0002 applied in the image build (`patches/warehouse/`, following `search-api.Dockerfile`); `docker-compose.yml`, `docker-compose.staging.yml`, `perf/docker-compose.perf.yml`; stack README.
- No new third-party dependency (standard library only; psutil is not used). LiberTEM's code is copied, not depended on.
