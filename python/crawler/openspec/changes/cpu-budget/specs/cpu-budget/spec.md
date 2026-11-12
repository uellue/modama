# Spec Delta

## Purpose

How many processes and threads the crawler's worker pools and the search stack's transform worker start: counted at start from what the process may use on the machine it runs on, so that processes × threads never exceed it, with an override for measurements and one log line that states the budget (R43, requirements-pipeline 2.4).

## ADDED Requirements

### Requirement: The crawler counts the CPUs it may use
By default the crawl SHALL start as many matching and extraction processes as the logical CPUs the crawler may use, at most 8. The CPUs it may use SHALL be the CPUs of its affinity (a cpuset included), and no more than its cgroup CPU quota divided by the period, rounded up. The machine's CPU count SHALL NOT be used.

#### Scenario: The VM
- **WHEN** the crawler runs on a machine with 8 logical CPUs, no cpuset and no CPU quota
- **THEN** the crawl starts 8 matching and 8 extraction processes

#### Scenario: The dev server
- **WHEN** the crawler runs on a machine with 48 logical CPUs (24 cores, 2 threads each), no cpuset and no CPU quota
- **THEN** the crawl starts 8 processes of each kind

#### Scenario: A container with a CPU quota
- **WHEN** the crawler runs on 8 logical CPUs in a container started with `--cpus 4` (`cpu.max` is `400000 100000`)
- **THEN** the crawl starts 4 processes of each kind

#### Scenario: A fractional quota
- **WHEN** the crawler's CPU quota is `250000 100000`
- **THEN** it counts 3 CPUs

#### Scenario: A cpuset
- **WHEN** the crawler runs on 8 logical CPUs with an affinity of CPUs 0 to 3
- **THEN** the crawl starts 4 processes of each kind

### Requirement: The number of worker processes can be set
`MODAMA_CRAWLER_EXTRACT_WORKERS` SHALL set the number of matching and extraction processes, in place of the count, also above the CPUs the crawler may use (for measurements).

#### Scenario: Set below the count
- **WHEN** `MODAMA_CRAWLER_EXTRACT_WORKERS` is 2 on a machine with 48 logical CPUs
- **THEN** the crawl starts 2 processes of each kind

### Requirement: Math libraries in the crawler's worker processes start one thread
Every matching and extraction process SHALL start with `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` set to 1 in its environment, whatever the crawler's own environment holds, so that a library loaded by an extractor starts no thread pool of its own. After the crawl's pools have ended, the crawler's own environment SHALL be as before.

#### Scenario: An extractor that loads numpy
- **WHEN** a test extractor imports numpy and reports the threads of its process, on a machine with 8 logical CPUs
- **THEN** its process has 1 thread after the import, and the dataset's extraction succeeds within the default memory limit

#### Scenario: The crawler's environment is restored
- **WHEN** the crawler's environment holds `OMP_NUM_THREADS=4` and no `OPENBLAS_NUM_THREADS`, and a crawl with extraction ends
- **THEN** the crawler's environment again holds `OMP_NUM_THREADS=4` and no `OPENBLAS_NUM_THREADS`

### Requirement: The crawl logs its CPU budget
`crawl` and `records` SHALL log one line at INFO level before the walk that states the number of worker processes, the threads each math library gets, and where the number of processes came from: the CPUs counted by affinity and by quota, or the setting.

#### Scenario: Counted
- **WHEN** a crawl starts on 8 logical CPUs without a quota or a setting
- **THEN** the log has the line `CPU budget: 8 worker processes, 1 math thread each; 8 CPUs usable (affinity 8, no quota)`

#### Scenario: Set
- **WHEN** a crawl starts with `MODAMA_CRAWLER_EXTRACT_WORKERS` set to 2
- **THEN** the log line says 2 worker processes, set by `MODAMA_CRAWLER_EXTRACT_WORKERS`

### Requirement: The transform worker counts the physical cores it may use
The search stack's transform worker SHALL count, at start, the physical cores among the CPUs of its affinity (logical CPUs that share a core count once), and no more than its cgroup CPU quota divided by the period, rounded up.

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

### Requirement: The transform worker sizes its processes and threads
The transform worker SHALL run P batch processes at once, P being the smallest of: the cores it counts, its memory divided by the memory of one batch process (rounded down, at least 1), and the indexing DAG's limit of active tasks. Each batch process SHALL get T = the cores divided by P, rounded down, at least 1, threads for its math libraries.

#### Scenario: The dev server
- **WHEN** the transform worker counts 24 cores, has 251 GB of memory, a batch process needs 4.4 GB and the DAG's limit is 16 active tasks
- **THEN** it runs 16 batch processes with 1 thread each

#### Scenario: The VM
- **WHEN** it counts 8 cores and has 25.2 GB of memory, with 4.4 GB per batch process and the limit of 16
- **THEN** it runs 5 batch processes with 1 thread each

#### Scenario: Memory is the limit
- **WHEN** it counts 24 cores in a container with a memory limit of 16 GB, with 4.4 GB per batch process and the limit of 16
- **THEN** it runs 3 batch processes with 8 threads each

#### Scenario: A higher DAG limit
- **WHEN** it counts 24 cores, has 251 GB of memory and the DAG's limit is 32 active tasks
- **THEN** it runs 24 batch processes with 1 thread each

### Requirement: Batch processes start the threads of their budget
Each batch process SHALL run ONNX Runtime with T intra-op threads set explicitly (so that it pins none), the tokenizer with T threads, and BLAS with 1 thread, all set before the libraries load. No thread of a batch process SHALL be pinned to fewer CPUs than the process may use.

#### Scenario: A batch in the test deployment
- **WHEN** the end-to-end test indexes its records in the VM with a budget of T = 1 and a probe lists a batch process's threads after its embedding
- **THEN** the process has at most 1 + (T − 1) + T + 4 = 6 threads (main, ONNX Runtime, tokenizer, and 4 for the database and HTTP clients; the 4 to be confirmed by the first probe), against 23 with the libraries' defaults on 8 CPUs, and every thread's `Cpus_allowed_list` is the process's

### Requirement: The transform worker's budget can be set
`TRANSFORM_PROCESSES` SHALL set P and `EMBEDDING_THREADS` SHALL set T, for measurements; with only one set, the other SHALL be computed from it as above (T = cores ÷ P, or P = cores ÷ T within the memory and DAG limits). A budget above the cores SHALL be obeyed and logged as such.

#### Scenario: Processes set
- **WHEN** `TRANSFORM_PROCESSES` is 4 and the worker counts 24 cores
- **THEN** it runs 4 batch processes with 6 threads each

#### Scenario: Both set beyond the cores
- **WHEN** `TRANSFORM_PROCESSES` is 24 and `EMBEDDING_THREADS` is 2 and the worker counts 24 cores
- **THEN** it runs 24 batch processes with 2 threads each, and its log line says that 48 threads exceed the 24 cores

### Requirement: The transform worker logs its CPU budget
At start, the transform worker SHALL log one line that states P, T, the cores counted and from what (logical CPUs of the affinity, quota), the number of processes the memory allows, and the DAG's limit, or which numbers were set.

#### Scenario: The dev server
- **WHEN** the transform worker starts on the dev server without settings
- **THEN** its log has the line `CPU budget: 16 processes × 1 thread; 24 cores usable (48 logical CPUs, no quota); memory for 57, 16 DAG slots`
