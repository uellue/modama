# Review of the change cpu-budget (2026-11-12)

Scope: `proposal.md`, `design.md`, `tasks.md` and `specs/cpu-budget/spec.md` of this change at b9383e4, read by an agent that did not write them. Judged against @weber's statements of 2026-11-12 (quoted in the proposal and in the design's last section, taken as requirements), `design/requirements.md`, `design/requirements-pipeline.md`, the decision log, the specs and the two `AGENTS.md` files; not against the proposal's own reasoning. Every finding was checked against the code, the images or a probe in the VM (throwaway containers with `--network none`; the running `search-stack` project was not touched). Nothing else in the change has been edited. The *Decision* line of each finding is for @weber.

Tally: 14 findings: 1 H, 6 M, 7 L. 11 confirmed. 3 are plausible in whole or in part: 3 (the batch-250 RSS), 4 (the race) and 6.

Severity: **H** the change as planned does not do what @weber decided, or a defect at the stated scale; **M** a defect in a reachable case, or a contradiction between requirement, spec and plan; **L** a gap in a test or the wording, or YAGNI.

Line numbers: `design.md`, `proposal.md`, `spec.md` (short for `specs/cpu-budget/spec.md`) and `tasks.md` in this directory; code paths are from the repository root.

## Findings

### 1 (H) @weber's decisions are only in the design's last section: D6, the spec, the tasks and the proposal still describe the old plan

- **What.** The decision on the DAG limit ("without any settings it should run the full thing, but here (devvms running etc) we restrict it. 16 sounds sensible", `design.md:92`) changes D6, but D6 (`design.md:52`) still says the default of 16 binds ("On the dev server that is 16 × 1"). No task sets the limit: `tasks.md` has no `AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG` at all (grep). The base compose file is not changed to raise it, and staging does not set it to 16. The spec's VM scenario (`spec.md:91-93`) still has "the limit of 16". Its log scenario says "on the dev server without settings" and expects "16 DAG slots" (`spec.md:124-126`), although the 16 will come from a setting there. The proposal promises "no per-machine numbers in env or compose files" (`proposal.md:16`); the decision puts one into `docker-compose.staging.yml`. The perf decision (`design.md:97`) has no task either: task 3.3 still says "if the perf scripts are committed, question in design" (`tasks.md:20`). `prototypes/search-stack/perf/` does not exist on this branch; it is untracked in the main checkout only. Yet tasks 4.2 and 5.1 to 5.4 depend on it, and the proposal's Impact lists `perf/docker-compose.perf.yml` as a file to change (`proposal.md:43`).
- **Where the 16 has to go.** The scheduler enforces the limit and the start script reads it, so both containers need the same value. `x-airflow-common`'s anchors are not visible in `docker-compose.staging.yml` (YAML anchors do not cross files), and today the staging file overrides only the transform worker's `command` (`prototypes/search-stack/docker-compose.staging.yml:48-52`). A line under `airflow-worker-transform` alone makes the script count 16 while the scheduler uses whatever the base file says. One line under `airflow-scheduler` alone does the reverse.
- **Failure scenario.** An implementer follows `tasks.md`. Base compose: Airflow's default of 16 still binds, so a 64-core production machine runs 16 × 4 instead of "the full thing". Staging: nothing changes, and the claim of "no numbers" is false.
- **Verdict.** CONFIRMED (grep of the four files; `git show HEAD --stat`: b9383e4 changed only `design.md`).
- **Fix.** Fold the decisions in with `/opsx:update` before applying. D6: the base file sets the limit in `x-airflow-common`'s environment from one compose variable (for example `AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG: ${INDEXING_SLOTS:-<large>}`), and `staging.env` sets the variable to 16. One value then reaches the scheduler and the worker. A new task for it, with a check that `docker compose config` shows the same value for `airflow-scheduler` and `airflow-worker-transform`. A task to commit `perf/` (with a review, it has not had one). Spec scenarios: the VM with the raised limit, the dev server "with the staging limit of 16". The proposal's sentence on numbers in compose files corrected.

### 2 (M) "The full thing" is also capped by Airflow's `core.parallelism` (32), which the start script does not read

- **What.** D6 caps P by `max_active_tasks_per_dag` only (`design.md:52`, `spec.md:85`). The scheduler also caps the running task instances of all DAGs at `core.parallelism`, 32 in the image (`airflow config get-value core parallelism` → 32; `default_pool_task_slot_count` 128, `max_active_tasks_per_dag` 16). Once the decision raises the DAG limit (finding 1), parallelism becomes the next cap. Its 32 slots are shared with the default worker's file-metadata batches (concurrency 4) and the harvest.
- **Failure scenario.** On a machine with 64 physical cores and no settings, the script computes P = 64 and T = 1 and logs "64 processes × 1 thread". Celery starts 64 processes, but at most about 28 transform batches ever run. 36 cores stay idle, and the log line states a budget that does not exist. The dev server is not affected (24 cores, staging limited to 16).
- **Verdict.** CONFIRMED for the defaults (read from the image). The 64-core case is an inference from the scheduler's documented caps; it was not run.
- **Fix.** Either raise `AIRFLOW__CORE__PARALLELISM` together with the DAG limit (finding 1's variable), and have the script read both as `slots = min(max_active_tasks_per_dag, parallelism)`, with both in the log line. Or let the decision say which caps "the full thing" means. A spec scenario: 64 cores, parallelism 32.

### 3 (M) The memory term rests on a number from batches of 2,000 and on `MemTotal`; in the VM it would overcommit if it were right, and it is not

- **What.** D7 (`design.md:55`) takes 4.4 GB per batch process and divides `MemTotal` by it. That gives P = 5 in the VM, which @weber accepted ("memory limits it to 5", `design.md:94`).
  - *What the 4.4 GB is.* D7 says it is not known whether F16's 2.3 to 4.4 GB was RSS or address space. It was RSS: the staging probe log (`.claude/field-tests/run-2/indexing-probe.log`, main checkout) records `rss=` per batch process, over 3,984 samples p10 291 MiB, median 2,202 MiB, p90 4,078 MiB, maximum 4,480 MiB, at staging's batch size of 2,000.
  - *The VM's batches are smaller.* It runs `CELERY_BATCH_SIZE` 250 (`prototypes/search-stack/docker-compose.yml:46`). A probe of the embedding part alone (model loaded, 250 or 2,000 texts embedded, the image's transform venv, `threads` 1 or default) peaked at 0.66 to 0.78 GB RSS and 1.35 to 1.9 GB `VmSize`. The real batch also holds the records and the XML, which the probe did not have.
  - *`MemTotal` is not what the batches can use.* The VM has 23 GiB in total, and the running stack already uses 9 GB (`free -g`: 14 GB available; the search API alone 2.6 GiB, OpenSearch 1.2 GiB, `docker stats`).
- **Failure scenario.** If 4.4 GB were right, the VM would run 5 × 4.4 = 22 GB of batches next to 9 GB of services on 23 GiB without swap, and the kernel's OOM killer would end batches. Since it is not right for batch 250, P = 5 instead of 8 follows from a number measured for another batch size. On the dev server (251 GB) the term never binds. As planned, the term limits only where its constant does not apply.
- **Verdict.** CONFIRMED (RSS from the probe log; the VM's memory). The probe was not a whole batch, so the batch-250 RSS is PLAUSIBLE, not measured.
- **Fix.** Run task 5.3 (RSS at 250 and 2,000) before task 3.2 fixes the constant, and decide with the numbers. Either the per-process figure follows `CELERY_BATCH_SIZE`, which the worker already has in its environment (the design lists this under Not now, `design.md:86`; it is the case that exists today, with two deployments at two batch sizes), or the memory term goes until a machine hits it. Whichever stays, state in the log line and README that memory is `MemTotal`, which other services share. Ask @weber again about the VM's 5 × 1 once the number is known.

### 4 (M) The crawler changes `os.environ` inside `walk()` and `extraction._run()`, while the crawl's heartbeat thread opens its database connection

- **What.** D3 places `set_num_threads_env(1)` in `walk.walk` and `extraction._run` (`design.md:40`), and says that "`cli.py` stays the only reader of the environment". The copied context manager reads `os.environ` itself and writes it (LiberTEM `threading.py:270-284`). That contradicts D3's own sentence and the code map (`python/crawler/AGENTS.md`: `cli.py`, "the only place that reads the environment"). It also writes the environment while other threads run: `cmd_crawl` starts `_Heartbeat` (`src/modama_crawler/cli.py:282-283`), whose `run()` first calls `psycopg.connect` (`cli.py:131`). Right after that the walk starts. libpq reads its `PG*` defaults with `getenv` during the connect, and glibc's `setenv` may reallocate the environment array underneath a concurrent `getenv`. The restore at the end runs while the heartbeat is still alive (it is stopped after the extraction, `cli.py:299/321`).
- **Failure scenario.** Rare. On some crawl, the heartbeat's connect runs at the moment the walk sets the three variables. The heartbeat then reads a freed environment array and crashes, or connects with a wrong default.
- **Verdict.** The contradiction with D3 and the code map: CONFIRMED (code). The race: PLAUSIBLE (from the code and glibc's documented thread-safety of `setenv`; not reproduced).
- **Fix.** Enter the context once in `cli.py`, in `cmd_crawl` and `cmd_records`, before the heartbeat starts and around the walk and the extraction together. It is the same copied code with one `with`, the library functions stay free of environment access, and the restore happens when only the main thread is left. Add a test that a replacement worker (monkeypatch `TASKS_PER_WORKER` to 1, two datasets) also reports 1 thread. Replacement workers are D4's main argument for the parent's environment (`design.md:42`), and no scenario covers them.

### 5 (M) The search API runs 6 processes with ONNX Runtime's defaults, pinned to the same cores, against the proposed requirement 2.4

- **What.** The proposed 2.4 says "every service" and "No service relies on a library's default thread count where several of its processes run" (`proposal.md:26`). The search API (`search-stack-search-api:0.10.2-patched`) runs `uvicorn ... --workers $WORKERS` with `WORKERS=6`, and each worker loads fastembed 0.7.4 with onnxruntime 1.23.2 and numpy. Measured in the running VM stack (read only, `/proc/<pid>/task/*/status`): each worker has 25 threads, 7 of them pinned one each to CPUs 1 to 7, the same in all six. It is the pattern this change removes from the transform worker. The change's Not now names only "the other services' pools (PostgreSQL, OpenSearch)" (`proposal.md:18`, `design.md:83`) and does not mention the search API. The `transform` FastAPI service is one process (6 threads) and is fine.
- **Failure scenario.** 2.4 is written as accepted, and the stack violates it from the first day. If a CPU limit is later set for the search API (@weber: "We may want to reduce the number of available CPUs to specific services"), ONNX Runtime ignores the quota and fails to pin in a cpuset (the note, section 2). That contradicts "a limit set for a service later is honoured by the same count".
- **Verdict.** CONFIRMED (measured).
- **Fix.** Name the search API in Not now with a backlog item: a patch like 0002 for its `TextEmbedding`, and `WORKERS` from the count. `patches/search-api/` already exists. Or narrow 2.4's wording to what this change covers. Ask @weber which.

### 6 (M) "Load average not above the CPUs" cannot be the acceptance check on staging

- **What.** The proposed 2.4 checks the budget by "load average not above the CPUs the containers may use" (`proposal.md:26`), and the VM verification by "load average ≤ 8" (`design.md:64`, `tasks.md:31`). `/proc/loadavg`, which `perf/indexing-bench.sh:68,81` reads, is machine-wide. Linux counts tasks in uninterruptible sleep in it, and NFS waits are such sleeps. So the crawler's 32 walk threads and 8 processes raise it without using CPU. On the dev server the devvms add their load (@weber: "here (devvms running etc)"). The accepted overlap of a crawl and an indexing run (`design.md:74`) makes it worse.
- **Failure scenario.** An indexing run on staging with a correct budget, during a crawl or a busy devvm, shows a load of 60 on 48 CPUs, and the check fails. Or the check passes because the load is right, while one container is oversubscribed.
- **Verdict.** PLAUSIBLE (Linux load-average semantics and @weber's statement; not measured on staging).
- **Fix.** Check per container: CPU time from the container's cgroup `cpu.stat` `usage_usec` over the run (or `docker stats`) against the CPUs it may use, `cpu.pressure` for waiting, and the thread count per batch process (`batch-probe.py`). Keep the load average as context, not as the criterion.

### 7 (M) The VM's comparisons do not measure what they say, and task 5.3 needs a probe that does not exist

- **What.**
  - *The baseline.* "`TRANSFORM_PROCESSES=1` (today's base)" (`design.md:64`, `tasks.md:31`) is not today's base. Under the budget, P = 1 gives T = 8 explicit threads with BLAS at 1 (`spec.md:111`, "with only one set, the other SHALL be computed"). Today's base is one process with the libraries' defaults: 7 pinned ONNX threads, 7 OpenBLAS, 8 Rayon.
  - *The memory probe.* Task 5.3 takes RSS and `VmSize` "by `batch-probe.py`" (`tasks.md:32`), but that script records CPU time, thread names and `Cpus_allowed_list` only (grep of `/workspaces/data-management-system/prototypes/search-stack/perf/batch-probe.py`: no `Vm` or `rss`).
  - *Probes in the worker don't see the budget.* `docker compose exec` (how `embed-bench.py` and `batch-probe.py` run) starts processes with the container's configured environment, not with the variables the start script set before its `exec`. The budget is visible only in the log line and in `/proc/<pid>/environ` of the worker's processes. The tasks do not say so. Without it, "with and without `OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=T`" in task 5.1 can be misread.
- **Failure scenario.** Task 5.2 reports "the budget is X % faster than today" against a 1 × 8 run, which nobody ever ran in production. Task 5.3 cannot be done as written.
- **Verdict.** CONFIRMED (spec text, the probe's source, how `docker exec` works).
- **Fix.** Measure the baseline with today's command (a compose override with `celery worker --queues transform --concurrency 1`, bypassing the script), and name it so. Extend `batch-probe.py` with `VmRSS`, `VmHWM` and `VmSize` (or reuse the staging indexing probe that already records `rss=`). Say in the tasks that `exec` probes need the variables passed with `-e`.

### 8 (L) Counting: cases the spec leaves out, and cgroup v1 nobody has shown to be needed

- **What.** Checked in the VM:
  - *No quota.* In a container, `cpu.max` reads `max 100000` without `--cpus`.
  - *On the host.* The root cgroup has no `cpu.max` at all, and the own group is `0::/user.slice/user-20335.slice/session-5.scope` (`max 100000`).
  - *`--cgroupns host`.* `/proc/self/cgroup` names `/system.slice/docker-<id>.scope`, the root file is missing, and the quota (`250000 100000`) is only under the joined path.
  - *The topology.* `topology/core_cpus_list` is readable in a container.

  The spec has no scenario for `max`, for a missing file, for the joined path, for v1's `-1` (no quota), or for the hybrid layout, where `/proc/self/cgroup` has several lines and the v2 one is `0::`. Note that dask's own code takes the last line's path (`split(":")[-1]` of the whole file) and reads v1 at the hierarchy root, not the own group (`dask/system.py`). It is a model, not something to copy. Task 2.1 fakes a v1 file (`tasks.md:11`), but nothing shows that v1 runs anywhere. The VM is v2 (Docker 26.1.5, systemd driver), and the dev server and production are unknown (`design.md:95`: "no limits beyond what we do with docker").
- **Failure scenario.** An implementation parses `max` as a number and fails at start, which stops the worker (finding 10), or treats a missing file as an error on the host.
- **Verdict.** CONFIRMED (probes).
- **Fix.** Add the `max`, missing-file and joined-path scenarios with their tests. Ask for `docker info --format '{{.CgroupVersion}}'` on the dev server and production, and drop the v1 branch and its test if both say 2 (AGENTS.md: no cases nobody has hit). If the topology is read, fall back to `thread_siblings_list` (the same content under the deprecated name) before falling back to logical CPUs. Without that fallback, an SMT machine with only the old name counts twice its cores.

### 9 (L) `PYTHON_CPU_COUNT` acts on the crawler's count but not on the transform worker's cores

- **What.** D2 uses `os.process_cpu_count()` for logical CPUs, "also honours `PYTHON_CPU_COUNT`", and `os.sched_getaffinity(0)` for cores (`design.md:34`). Measured: `PYTHON_CPU_COUNT=3` gives `process_cpu_count()` 3, `cpu_count()` 3, `len(sched_getaffinity(0))` 8.
- **Failure scenario.** Someone sets the variable. The crawler obeys it as an undocumented second override. The transform worker logs "8 cores usable (3 logical CPUs)".
- **Verdict.** CONFIRMED.
- **Fix.** Count from `os.sched_getaffinity(0)` in both modules (the overrides are `MODAMA_CRAWLER_EXTRACT_WORKERS`, `TRANSFORM_PROCESSES` and `EMBEDDING_THREADS`), or document it as an override in both. One sentence in D2 either way.

### 10 (L) What happens when the start script fails is not what the design says

- **What.** The design says a failure gives "a container that does not become healthy" (`design.md:73`). The service has `restart: unless-stopped` (`prototypes/search-stack/docker-compose.yml:423`), so a script that exits makes a restart loop, and the health check never runs. Meanwhile the crawler's harvest and the scheduler go on, and the transform batches wait in the `transform` queue with no consumer, as the default queue did in F17. The rest checked out:
  - `/entrypoint` runs `python …` directly (`exec_to_bash_or_python_command_if_specified`), and waits for the broker only for `celery` and `scheduler`.
  - `--concurrency` overrides `AIRFLOW__CELERY__WORKER_CONCURRENCY`, which is only the option's default (`airflow/providers/celery/cli/definition.py:77-82` in the image).
  - The batch subprocess copies `os.environ` (`inherit_env=True`, `airflow/providers/standard/operators/python.py:501,666`).
  - Importing `airflow.configuration` takes 2.9 s and loads no numpy.
- **Failure scenario.** A `cpu.max` that cannot be parsed on some host, and indexing silently stops.
- **Verdict.** CONFIRMED (compose file, entrypoint).
- **Fix.** Say which inputs fail the start (malformed files) and which fall back with a note in the log line (missing files). State the restart loop in Risks, and add one test that a malformed `cpu.max` exits with a message that names the file.

### 11 (L) `records --verbose` suppresses the budget line the spec requires

- **What.** "`crawl` and `records` SHALL log one line at INFO level" (`spec.md:51`). `cmd_records` sets the package logger to ERROR under `--verbose` (`src/modama_crawler/cli.py:509-510`).
- **Verdict.** CONFIRMED.
- **Fix.** "…except `records --verbose`, which logs errors only", in the requirement and task 2.3.

### 12 (L) Spec scenarios and tasks that do not yet pin anything down

- **What.**
  - *The thread bound.* "A batch in the test deployment" allows "4 for the database and HTTP clients; the 4 to be confirmed by the first probe" (`spec.md:108`). psycopg and opensearch-py start no threads. With T = 1 the note's own data predicts main + 1 Rayon thread, 2 in all (its `RAYON_NUM_THREADS=2`, `threads=2` case gave 4). A bound that is fixed after the probe is not a contract.
  - *Uncited scenarios.* The transform worker's log scenario (`spec.md:124`) and the "Batch processes" requirement have no unit test in task 3.2, which cites only counting, sizing and overrides. "Set below the count" (`spec.md:35`) is cited by no task.
  - *The extractor test.* "An extractor that loads numpy … succeeds within the default memory limit" (`spec.md:42-44`) passes without the change on 8 CPUs (430 MB is far below 4 GiB); only the thread count tests the change.
- **Verdict.** CONFIRMED (spec and tasks text; the thread counts from the note's table).
- **Fix.** Run the probe before the spec is final and write the number. Cite every scenario in a task. For the memory part, either a test with `MODAMA_CRAWLER_EXTRACT_MEMORY` set just above the 143 MB of one thread, or drop that clause.

### 13 (L) Stale references to the research note and the branch

- **What.** The design cites the note as "commit 1b77989, on branch `worktree-agent-a7ed4152ec18fcbf9`, not yet on `crawler`" (`design.md:5`), and task 1.1 merges it (`tasks.md:7`). It is on `crawler` now (d0dca90, then 602ce5d "shorten the part for people"). This branch is 4 commits behind `crawler` (`git log HEAD..crawler`). The proposal's citation of "For people" (`proposal.md:5`) points at a section that 602ce5d rewrote.
- **Verdict.** CONFIRMED.
- **Fix.** Rebase onto `crawler`, cite the note by path, and drop the merge from task 1.1.

### 14 (L) Smaller points of scope and wording

- **What.**
  - *"Never".* The spec's Purpose promises that "processes × threads never exceed" what a process may use (`spec.md:5`). The overrides may exceed it by design (`spec.md:111`), and the accepted overlap of crawl and indexing does too (`design.md:74`). "By default" would be accurate.
  - *Matching is not I/O.* R43 calls the crawler's pools "I/O-bound or pure Python" (`proposal.md:30`). The matching processes are CPU-bound pure Python (the note, section 6). The outcome is the same under the cap of 8; only the reason is wrong.
  - *The mount.* D5 mounts `budget.py` from the repository (`design.md:46`), while D9 builds an image of our own anyway. A `COPY` there would keep the script with the patch it depends on, in one artifact, without a bind mount of the source tree.
- **Verdict.** CONFIRMED (text).
- **Fix.** Reword the first two. The third is optional: decide it in task 3.1.

## What is right and should stay

- **Variables in the parent's environment before `exec`, not in an initializer and not at run time.** It is the only way that covers spawned workers, replacement workers and the transform worker's whole process tree, and it is LiberTEM's lesson ("limit the number of threads that are created"). Verified: the extraction workers drop from 8 threads and 430 MB `VmSize` to 1 thread and 143 MB after `import rsciio.digitalmicrograph` with the three variables set. Airflow's external-Python batch copies `os.environ`. The crawler's parent imports no numpy.
- **An explicit ONNX Runtime thread count through patch 0002.** It is the only switch that also stops the pinning (the note's measurements, and the search API's measured pinning in finding 5). It is 4 lines of upstream code and a candidate upstream.
- **No OpenMP or MKL pools to chase.** No `libgomp`, `libiomp` or MKL in the transform venv (`find` in the image), and only scipy-openblas in numpy. numba is absent from both environments, and the file-metadata batches load no numpy (probed). The three variables plus `RAYON_NUM_THREADS` cover what is loaded.
- **The quota from the process's own cgroup, the affinity from the kernel.** Verified: `--cpus 2.5` gives `250000 100000` with `os.process_cpu_count()` 8. `--cpuset-cpus 0-3` gives 4. The topology is readable in a container. No psutil, no new dependency, and the transform worker's Python 3.13.15 has `os.process_cpu_count()`.
- **A start script that `exec`s `/entrypoint celery worker … --concurrency P`.** It keeps the broker wait and dumb-init's direct child, and `--concurrency` overrides the shared `WORKER_CONCURRENCY`. Removing the two numbers per deployment (`--concurrency 1`, staging's `4`) is the point of @weber's "not rely on the admin".
- **Pools counted by kind**, with the transform worker on physical cores and the crawler capped at 8, as @weber agreed. The SMT question is left to the dev server's measurement (task 5.4) instead of being guessed. The interfaces stay put when the count changes.
- **"No split"** is respected: no per-container CPU numbers, and a later limit is honoured because each process counts what it may use.
- **The copy of LiberTEM's lines without the numba branch**, under its MIT notice, as @weber asked.
- **The Not now list** (a package, parent-cgroup quotas, spinning, patch 0001) is the right size, apart from the search API (finding 5).
