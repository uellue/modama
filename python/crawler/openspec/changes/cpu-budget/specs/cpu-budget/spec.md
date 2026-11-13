# Spec Delta

## Purpose

How many processes and threads the crawler's worker pools, the search stack's transform worker and its search API start: counted at start from what the process may use on the machine it runs on, so that by default processes × threads do not exceed it, with few named overrides, one log line per service that states the budget, and a diagnostic that shows every service's budget and its reasons (R43, requirements-pipeline 2.4: CPU budget, and "The operator stays in control").

## ADDED Requirements

### Requirement: The crawler counts the CPUs it may use
By default the crawl SHALL start as many matching and extraction processes as the logical CPUs the crawler may use, at most 8. The CPUs it may use SHALL be the CPUs of its affinity (a cpuset included), and no more than its CPU quota divided by the period, rounded up. Neither the machine's CPU count nor `PYTHON_CPU_COUNT` SHALL be used.

#### Scenario: The VM
- **WHEN** the crawler runs on a machine with 8 logical CPUs, no cpuset and `cpu.max` `max 100000`
- **THEN** the crawl starts 8 matching and 8 extraction processes

#### Scenario: The dev server
- **WHEN** the crawler runs on a machine with 48 logical CPUs (24 cores, 2 threads each), no cpuset and no CPU quota
- **THEN** the crawl starts 8 processes of each kind

#### Scenario: A container with a CPU quota
- **WHEN** the crawler runs on 8 logical CPUs in a container started with `--cpus 4` (`/proc/self/cgroup` `0::/`, `cpu.max` `400000 100000`)
- **THEN** the crawl starts 4 processes of each kind

#### Scenario: A fractional quota
- **WHEN** the crawler's CPU quota is `250000 100000`
- **THEN** it counts 3 CPUs

#### Scenario: A cpuset
- **WHEN** the crawler runs on 8 logical CPUs with an affinity of CPUs 0 to 3
- **THEN** the crawl starts 4 processes of each kind

#### Scenario: PYTHON_CPU_COUNT is not an override
- **WHEN** `PYTHON_CPU_COUNT` is 3 on 8 logical CPUs without quota
- **THEN** the crawl starts 8 processes of each kind

### Requirement: The CPU quota is read from the own cgroup v2 group
The quota SHALL be the `cpu.max` of the group named by the `0::` line of `/proc/self/cgroup`, under `/sys/fs/cgroup`. `max` or a missing `cpu.max` SHALL mean no quota. Without a `0::` line, or without `/sys/fs/cgroup/cgroup.controllers` (a hybrid host, whose controllers are in cgroup v1), there is no cgroup v2: the quota SHALL NOT be read, and the log line SHALL say so. The crawler, the transform worker and the search API read it alike.

#### Scenario: The host's cgroup
- **WHEN** the crawler runs on the host, its group is `0::/user.slice/user-1000.slice/session-5.scope` with `cpu.max` `max 100000`, and the root group has no `cpu.max`
- **THEN** it counts the CPUs of its affinity, with no quota

#### Scenario: The host's cgroup namespace
- **WHEN** the crawler runs in a container with `--cgroupns host`, its group is `0::/system.slice/docker-abc.scope`, `/sys/fs/cgroup/cpu.max` is missing and `/sys/fs/cgroup/system.slice/docker-abc.scope/cpu.max` is `200000 100000`
- **THEN** it counts 2 CPUs

#### Scenario: No cgroup v2
- **WHEN** `/proc/self/cgroup` has no `0::` line, on 8 logical CPUs
- **THEN** it counts 8 CPUs, and the log line says that the quota was not read (no cgroup v2)

#### Scenario: A hybrid host
- **WHEN** `/proc/self/cgroup` has a `0::` line but `/sys/fs/cgroup/cgroup.controllers` does not exist, on 8 logical CPUs
- **THEN** it counts 8 CPUs, and the log line says that the quota was not read (no cgroup v2)

### Requirement: The number of worker processes can be set
`MODAMA_CRAWLER_EXTRACT_WORKERS` SHALL set the number of matching and extraction processes, in place of the count, also above the CPUs the crawler may use (for measurements).

#### Scenario: Set below the count
- **WHEN** `MODAMA_CRAWLER_EXTRACT_WORKERS` is 2 on a machine with 48 logical CPUs
- **THEN** the crawl starts 2 processes of each kind

#### Scenario: Set above the count
- **WHEN** `MODAMA_CRAWLER_EXTRACT_WORKERS` is 12 on a machine with 8 logical CPUs
- **THEN** the crawl starts 12 processes of each kind

### Requirement: Math libraries in the crawler's worker processes start one thread
Every matching and extraction process, replacement workers included, SHALL start with `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` set to 1 in its environment, whatever the crawler's own environment holds, so that a library loaded by an extractor starts no thread pool of its own. The crawler SHALL change its environment only while no other thread of it runs, and after the crawl's pools have ended its environment SHALL be as before.

#### Scenario: An extractor that loads numpy
- **WHEN** a test extractor imports numpy and reports the threads of its process, on a machine with 8 logical CPUs, with `MODAMA_CRAWLER_EXTRACT_MEMORY` at 256 MiB
- **THEN** its process has 1 thread after the import, and the dataset's extraction succeeds (without the variables the process maps about 430 MB and fails)

#### Scenario: A replacement worker
- **WHEN** a worker is replaced after its tasks (`TASKS_PER_WORKER` 1, two datasets) and the test extractor runs in the new one
- **THEN** the new worker's process also has 1 thread after the import

#### Scenario: The crawler's environment is restored
- **WHEN** the crawler's environment holds `OMP_NUM_THREADS=4` and no `OPENBLAS_NUM_THREADS`, and a crawl with extraction ends
- **THEN** the crawler's environment again holds `OMP_NUM_THREADS=4` and no `OPENBLAS_NUM_THREADS`

### Requirement: The crawl logs its CPU budget
`crawl` and `records` SHALL log one line at INFO level before the walk that states the number of worker processes, the threads each math library gets, and where the number of processes came from: the CPUs counted by affinity and by quota, or the setting. `records --verbose`, which logs errors only, SHALL NOT log it.

#### Scenario: Counted
- **WHEN** a crawl starts on 8 logical CPUs without a quota or a setting
- **THEN** the log has the line `CPU budget: 8 worker processes, 1 math thread each; 8 CPUs usable (affinity 8, no quota)`

#### Scenario: Set
- **WHEN** a crawl starts with `MODAMA_CRAWLER_EXTRACT_WORKERS` set to 2
- **THEN** the log line says 2 worker processes, set by `MODAMA_CRAWLER_EXTRACT_WORKERS`

#### Scenario: records --verbose
- **WHEN** `modama-crawler records --verbose` runs on a test tree
- **THEN** standard error has no `CPU budget:` line

### Requirement: The crawler explains its CPU budget
`modama-crawler cpu-budget` SHALL print, without crawling, the budget line of the crawl, the inputs it came from (logical CPUs of the affinity, cgroup v2 or not, the quota), whether `MODAMA_CRAWLER_EXTRACT_WORKERS` is set, and how to set it.

#### Scenario: In a container with a quota
- **WHEN** `modama-crawler cpu-budget` runs on 8 logical CPUs with `cpu.max` `400000 100000`
- **THEN** it prints `CPU budget: 4 worker processes, 1 math thread each; 4 CPUs usable (affinity 8, quota 4)`, that no override is set, and the line on `MODAMA_CRAWLER_EXTRACT_WORKERS`, and exits with status 0

### Requirement: The transform worker counts the physical cores it may use
The search stack's transform worker SHALL count, at start, the physical cores among the CPUs of its affinity (logical CPUs that share a core count once, by `topology/core_cpus_list`, else `topology/thread_siblings_list`), and no more than its CPU quota divided by the period, rounded down, at least 1 (a math pool: processes × threads stay within the quota). Without either topology file it SHALL count the logical CPUs and say so in its log line.

#### Scenario: A fractional quota
- **WHEN** the transform worker runs on 8 cores with `cpu.max` `250000 100000`, `150000 100000` or `50000 100000`
- **THEN** it counts 2, 1 or 1 cores, and its explanation says, for the first, `2.5 CPUs: 2 for math (rounded down), 3 for I/O (rounded up)`

#### Scenario: The VM
- **WHEN** the transform worker runs on 8 logical CPUs, each its own core, without quota
- **THEN** it counts 8 cores

#### Scenario: The dev server
- **WHEN** the transform worker runs on 48 logical CPUs that are 24 cores with 2 threads each, without quota
- **THEN** it counts 24 cores

#### Scenario: A container with a CPU quota
- **WHEN** the transform worker runs on the dev server in a container started with `--cpus 4`
- **THEN** it counts 4 cores

#### Scenario: A cpuset of 8 CPUs on 8 cores
- **WHEN** its affinity is 8 logical CPUs of 8 different cores
- **THEN** it counts 8 cores

#### Scenario: A cpuset of 8 CPUs on 4 cores
- **WHEN** its affinity is 8 logical CPUs that are both threads of 4 cores
- **THEN** it counts 4 cores

#### Scenario: Only the old topology name
- **WHEN** its affinity is 8 logical CPUs, both threads of 4 cores, and only `thread_siblings_list` exists
- **THEN** it counts 4 cores

#### Scenario: No topology
- **WHEN** neither topology file exists, on 8 logical CPUs
- **THEN** it counts 8 cores, and its log line says that the cores are logical CPUs

### Requirement: Malformed input stops the start of a search-stack service
A `cpu.max`, topology list or `memory.max` that exists and cannot be parsed, or an override that is not a positive integer, SHALL stop the start of the transform worker or the search API with a message that names the file or the variable, before Celery or uvicorn starts.

#### Scenario: A malformed quota
- **WHEN** `cpu.max` holds `unlimited`
- **THEN** the start stops with a message that names `cpu.max` and its content, and Celery is not started

#### Scenario: Not a number
- **WHEN** `TRANSFORM_PROCESSES` is `four`
- **THEN** the start stops with a message that names `TRANSFORM_PROCESSES`, and Celery is not started

### Requirement: The transform worker sizes its processes and threads
The transform worker SHALL run P batch processes at once, P being the smallest of: the cores it counts, its task slots (the smaller of Airflow's `core.max_active_tasks_per_dag` and `core.parallelism`), and, only where its cgroup's `memory.max` is a number, that memory divided by the memory of one batch process (rounded down, at least 1). Without a memory limit, memory SHALL NOT reduce P. Each batch process SHALL get T = the cores divided by P, rounded down, at least 1, threads for its math libraries.

#### Scenario: The dev server
- **WHEN** the transform worker counts 24 cores, has no memory limit and `staging.env` sets `AIRFLOW_TASK_LIMIT` to 16
- **THEN** it runs 16 batch processes with 1 thread each

#### Scenario: The dev server without the limit
- **WHEN** it counts 24 cores, has no memory limit, and no `AIRFLOW_TASK_LIMIT` is set
- **THEN** it runs 24 batch processes with 1 thread each

#### Scenario: The VM
- **WHEN** it counts 8 cores, has no memory limit (9.1 GB available), and no `AIRFLOW_TASK_LIMIT`
- **THEN** it runs 8 batch processes with 1 thread each

#### Scenario: Memory is the limit
- **WHEN** it counts 24 cores in a container with a memory limit (`memory.max`) of 16 GiB, with 1.6 GiB per batch process
- **THEN** it runs 10 batch processes with 2 threads each

#### Scenario: Parallelism is the limit
- **WHEN** it counts 64 cores, has no memory limit, `core.max_active_tasks_per_dag` is 1024 and `core.parallelism` is 32
- **THEN** it runs 32 batch processes with 2 threads each

### Requirement: Airflow's task limits are one setting
Without settings the base compose file SHALL set `core.max_active_tasks_per_dag` and `core.parallelism` to 1024, so that they do not bind; `AIRFLOW_TASK_LIMIT` SHALL set both, in the scheduler and in the workers alike.

#### Scenario: One value for scheduler and worker
- **WHEN** `docker compose config` renders the staging deployment with `AIRFLOW_TASK_LIMIT=16`
- **THEN** `airflow-scheduler` and `airflow-worker-transform` both have `AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG` and `AIRFLOW__CORE__PARALLELISM` 16

### Requirement: Batches beyond the budget wait without timing out
An indexing run with more transform batches than P SHALL run them all, P at a time; a batch that waits for a free batch process SHALL NOT be failed or retried by Airflow's `task_queued_timeout`.

#### Scenario: More batches than processes
- **WHEN** the test deployment indexes 16,000 records in batches of 250 (64 batches) with P = 8 and `AIRFLOW__SCHEDULER__TASK_QUEUED_TIMEOUT` set to 60 s
- **THEN** all 64 transform batches succeed at their first try

### Requirement: Batch processes start the threads of their budget
Each batch process SHALL run ONNX Runtime with T intra-op threads set explicitly (so that it pins none), the tokenizer with T threads, and BLAS with 1 thread, all set before the libraries load, and SHALL embed in sub-batches of 32 texts, the texts in order of their length and the vectors returned in the given order (decision 250). No thread of a batch process SHALL be pinned to fewer CPUs than the process may use.

#### Scenario: A batch in the test deployment
- **WHEN** the end-to-end test indexes its records in the VM with a budget of T = 1 and a probe lists a batch process's threads after its embedding
- **THEN** the process has 2 threads (main and one tokenizer thread; measured 2026-11-12), against 23 with the libraries' defaults on 8 CPUs, and every thread's `Cpus_allowed_list` is the process's

#### Scenario: A batch of long texts
- **WHEN** a batch process embeds 250 or 2,000 texts of 512 tokens each
- **THEN** its peak RSS (`VmHWM`) stays below 1.45 GB (measured 2026-11-12: 1.40 and 1.42 GB with sub-batches of 32; 5.30 and 9.05 GB with fastembed's 256)

#### Scenario: A batch of short and long texts
- **WHEN** a batch process embeds 250 texts of mixed length, short ones (19 to 43 tokens) in the same sub-batches as long ones (321 and 512 tokens)
- **THEN** each document gets the embedding it gets when the texts are embedded in the given order, byte for byte and in the same position of the bulk body, and the batch takes less time (measured 2026-11-13: 18.8 against 131.7 s)

### Requirement: The transform worker's budget can be set
`TRANSFORM_PROCESSES` SHALL set P and `EMBEDDING_THREADS` SHALL set T, for measurements and for the operator; with only one set, the other SHALL be computed from it as above (T = cores ÷ P, or P = cores ÷ T within the memory and slot limits). A budget above the cores SHALL be obeyed and logged as such. 

#### Scenario: Processes set
- **WHEN** `TRANSFORM_PROCESSES` is 4 and the worker counts 24 cores
- **THEN** it runs 4 batch processes with 6 threads each

#### Scenario: Both set beyond the cores
- **WHEN** `TRANSFORM_PROCESSES` is 24 and `EMBEDDING_THREADS` is 2 and the worker counts 24 cores
- **THEN** it runs 24 batch processes with 2 threads each, and its log line says that 48 threads exceed the 24 cores

### Requirement: The transform worker logs its CPU budget
At start, before Celery's banner, the transform worker SHALL log one line that states P, T, the cores counted and from what (logical CPUs of the affinity, quota, cgroup v2 or not), the memory limit and the number of processes it allows, or that there is none, the task slots, and which overrides are set.

#### Scenario: The dev server
- **WHEN** the transform worker starts on the dev server without a memory limit and with `AIRFLOW_TASK_LIMIT` 16
- **THEN** its log has the line `CPU budget: 16 processes × 1 thread; 24 cores usable (48 logical CPUs, no quota); no memory limit; 16 task slots (max_active_tasks_per_dag 16, parallelism 16); no override`

#### Scenario: A memory limit
- **WHEN** it starts on 24 cores with `memory.max` 16 GiB and no other limit
- **THEN** its log line has `memory for 10 (memory.max 16.0 GiB, 1.6 GiB each)`

### Requirement: More memory expected than available is a warning
Without a memory limit, when the expected memory (the transform worker's processes × 1.6 GiB, the search API's workers × 0.45 GiB) is more than `MemAvailable` at start, the service SHALL log a second line that names both amounts and the override that lowers the count (`TRANSFORM_PROCESSES`, `WORKERS`), and SHALL NOT change the count (@weber, 159). Memory SHALL be shown in GiB.

#### Scenario: The VM with 9 GiB available
- **WHEN** the transform worker starts on 8 cores without a memory limit and `MemAvailable` is 9 GiB
- **THEN** it runs 8 batch processes, and its log has `CPU budget warning: 8 batch processes × 1.6 GiB = 12.8 GiB expected at most, more than the 9.0 GiB available now (MemAvailable), and no memory limit; the count stays; TRANSFORM_PROCESSES=N lowers it`

#### Scenario: The search API on the dev server
- **WHEN** the search API starts on 48 logical CPUs without a memory limit and 16 GiB available
- **THEN** it runs 48 workers and warns of `48 workers × 0.45 GiB = 21.6 GiB`, naming `WORKERS`

#### Scenario: A memory limit, or enough memory
- **WHEN** the container has a `memory.max`, or the expected memory fits into `MemAvailable`, or `/proc/meminfo` has no `MemAvailable`
- **THEN** there is no warning

#### Scenario: An override
- **WHEN** it starts with `TRANSFORM_PROCESSES` 4 on 24 cores
- **THEN** its log line says 4 processes × 6 threads and names `TRANSFORM_PROCESSES` as set

### Requirement: The search API sizes its workers and their threads
The search API SHALL start as many uvicorn workers as the logical CPUs it may use, counted as the crawler counts them (@weber, 158: "Let's run on all usable CPUs"), and each worker SHALL run ONNX Runtime with 1 intra-op thread set explicitly, the tokenizer with 1 thread and BLAS with 1 thread, all set before the libraries load. Upstream's `WORKERS=6` in its image SHALL NOT count as a setting. No thread of a worker SHALL be pinned to fewer CPUs than the process may use.

#### Scenario: The VM
- **WHEN** the search API starts on 8 logical CPUs without quota
- **THEN** it runs 8 workers with 1 thread each

#### Scenario: A container with a CPU quota
- **WHEN** it starts in a container with `cpu.max` `200000 100000`
- **THEN** it runs 2 workers with 1 thread each

#### Scenario: A fractional quota
- **WHEN** it starts in a container with `cpu.max` `250000 100000` (its workers are I/O-bound: rounded up)
- **THEN** it runs 3 workers with 1 thread each

#### Scenario: The dev server
- **WHEN** it starts on 48 logical CPUs without quota
- **THEN** it runs 48 workers with 1 thread each

#### Scenario: No pinned threads
- **WHEN** the search API runs in the VM's test deployment and a probe lists each worker's threads after a search
- **THEN** every thread's `Cpus_allowed_list` is the process's (today 7 per worker are pinned, one each to CPUs 1 to 7)

### Requirement: The search API's budget can be set
`WORKERS` SHALL set the number of workers and `EMBEDDING_THREADS` the threads per worker, in place of the count, also above the CPUs (for measurements and for the operator).

#### Scenario: Workers set
- **WHEN** `WORKERS` is 2 in the search API's environment on 8 logical CPUs
- **THEN** it runs 2 workers with 1 thread each, and its log line names `WORKERS` as set

### Requirement: The search API logs its CPU budget
At start, before uvicorn's first line, the search API SHALL log one line that states its workers, the threads each, the CPUs counted and from what, and which overrides are set.

#### Scenario: The VM
- **WHEN** the search API starts in the VM's test deployment without settings
- **THEN** its log has the line `CPU budget: 8 workers × 1 thread; 8 CPUs usable (affinity 8, no quota); no override`

### Requirement: Background services run at a lower CPU weight
The services that do background work, `crawler`, `crawl-timer`, `airflow-worker`, `airflow-worker-transform` and `transform`, SHALL run with a CPU weight below Docker's default (`cpu_shares` 512), and the services that answer users, `search-api` and `matchmaker`, with the default, so that live requests go first when the CPUs are contended (@weber, 163). No service SHALL get a CPU limit or reservation from this.

#### Scenario: The compose files
- **WHEN** `docker compose config` renders the test deployment or staging
- **THEN** the five background services have `cpu_shares: 512`, and `search-api` and `matchmaker` have none

#### Scenario: In the VM
- **WHEN** the test deployment runs in the VM (cgroup v2, runc 1.1.15)
- **THEN** `/sys/fs/cgroup/cpu.weight` is 20 in the background services' containers and 100 in `search-api`'s

### Requirement: The diagnostic shows every service's budget
`prototypes/search-stack/cpu-budget.sh` SHALL print, for a deployment (the test deployment by default, `staging`), the cgroup version and driver Docker reports, and for the crawler, the transform worker and the search API, each in a container with the service's limits: the budget line of its next start, its inputs (a fractional quota with what each kind of pool counts of it), its CPU weight, a memory warning, the active overrides, and how to set each. A service whose budget cannot be computed SHALL be reported with its start's message, and the script SHALL exit non-zero. When the service's running container has other cgroup limits (`cpu.max`, `cpuset.cpus.effective`, `memory.max`) than its next start would get, the script SHALL say so in one line for that service, with both.

#### Scenario: The test deployment in the VM
- **WHEN** `./cpu-budget.sh` runs in the VM with the images built
- **THEN** it prints `cgroup v2 (systemd)`, and for each of the three services the same budget line its log has after the next `./uptest.sh`

#### Scenario: A limit on a service
- **WHEN** a compose override sets `cpus: 4` on the crawler service and `./cpu-budget.sh` runs
- **THEN** the crawler's part says 4 worker processes, `affinity 8, quota 4`

#### Scenario: An override
- **WHEN** `TRANSFORM_PROCESSES=2` is set for `airflow-worker-transform` and `./cpu-budget.sh` runs
- **THEN** the transform worker's part names `TRANSFORM_PROCESSES` as set and shows 2 processes

#### Scenario: A running container with other limits
- **WHEN** the crawler runs with `cpus: 4` from an earlier start and the compose files no longer set it
- **THEN** the crawler's part has the line `the running container has other limits than its next start: running cpu.max 400000 100000, …; next start cpu.max max 100000, …`
