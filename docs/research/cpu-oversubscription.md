# CPU oversubscription: processes and the thread pools of math libraries

Research note, 2026-11-12, for the search stack's transform worker and the crawler. Written by an agent at @weber's request ("we will run on big machines where this is super super important to avoid oversubscription. Of course we need to adapt to the local machine always."). Not yet reviewed by a person. No code was changed.

## For people

- **What to do:** in every process that does math, set each library's thread count explicitly, so that processes × threads per process ≤ the CPU cores that process may use. Do not rely on library defaults where several processes run.
- **Why:** each library sizes its pool for the whole machine, on its own. A transform batch process starts three pools: OpenBLAS (CPUs − 1 threads as soon as numpy is imported), ONNX Runtime (physical cores − 1 threads, each pinned to its own core, cores 1..n−1, in *every* process) and the `tokenizers` Rayon pool (one thread per CPU). On the 48-CPU dev server that adds up to about 1 + 47 + 23 + 48 = 119 threads per process, which matches the 95 to 143 observed (a prediction from the code, not counted there). ONNX Runtime and OpenBLAS ignore Docker's `--cpus` quota, and ONNX Runtime also ignores a cpuset (measured in the VM).
- **One number:** in the VM, 4 processes × 2 threads embedded 194 texts/s, against 118 with the defaults: 1.6 times faster, at 36.4 instead of 62.6 ms of CPU per text.
- **Warehouse:** apply patch 0002 and set `EMBEDDING_THREADS` = cores ÷ Celery concurrency, `OPENBLAS_NUM_THREADS=1` and `RAYON_NUM_THREADS` = `EMBEDDING_THREADS`. On the dev server, measure 24 × 1 against 12 × 2 (and 24 × 2 for SMT) before choosing.
- **Crawler:** the CPU is not overloaded (extractors read headers, NFS sets the pace), but each extraction worker starts CPUs − 1 idle OpenBLAS threads of about 41 MB address space each, which count against the worker's 4 GiB `RLIMIT_AS` (measured 430 MB against 143 MB per worker on 8 CPUs). Set the BLAS variables to 1 in the workers, and count usable CPUs with `os.process_cpu_count()` instead of `os.cpu_count()`.
- **LiberTEM:** reuse its pattern (one thread per worker, environment variables set before the libraries load). Its CPU count is the physical cores of the whole machine (`psutil.cpu_count(logical=False)`), so it does not adapt to a container or an affinity mask. That part has to be added either way, for example the way `dask.system.cpu_count` does it. The code to copy is about 20 lines under the MIT licence. Lean: copy it now, and spin out a package once LiberTEM wants the improved count too (question below).

---

## Details for agents

Everything below names its source. "Measured" means a command run in the VM on 2026-11-12, given in the appendix. "Quoted" means the text was fetched and checked, not recalled. The VM has 8 vCPUs on an AMD EPYC 7F72 (`lscpu`: 8 sockets × 1 core × 1 thread, so SMT is not visible) and runs the search stack's test deployment.

### 1. LiberTEM's experience (question 1)

Sources: the GitHub API (issues, comments, timelines) and a shallow clone of `LiberTEM/LiberTEM` at commit `d6aa0fa8be9cd069ddbb419aa82dbbf2ac6684a3` (2026-10-22). Line numbers below refer to that commit.

**What went wrong.**
- [#546](https://github.com/LiberTEM/LiberTEM/issues/546) (2020): the thread count had to be set "to one for numerics libraries by setting appropriate environment variables before loading these libraries". That is fragile when LiberTEM is embedded ("may have to happen very, very early in the start-up process"), and it takes threads away from the main process too. sk1p collected the controls (OpenBLAS `openblas_set_num_threads`, MKL, pyFFTW, numba) and found threadpoolctl as a partial answer.
- [#602](https://github.com/LiberTEM/LiberTEM/issues/602) (2020): with a stand-alone Dask cluster, analyses were 4× (mask) to 50× (disk) slower than with a local cluster. The cause, per uellue on 2020-03-17: "The regression was caused by not setting the thread count for the stand-alone workers correctly."
- [PR #685](https://github.com/LiberTEM/LiberTEM/pull/685) calls the environment variables "an error source with severe performance penalties from over-subscription on machines with many cores". On the test notebook, uellue wrote: "It will tank by a factor of about 100 when running with 18x36 multithreading."
- [#1117](https://github.com/LiberTEM/LiberTEM/issues/1117) (2021): `threadpoolctl.threadpool_limits(n)` spent 98.7 % of its time discovering the loaded libraries (about 3.7 ms per call). Fixed by caching a `ThreadpoolController` ([PR #1118](https://github.com/LiberTEM/LiberTEM/pull/1118)).
- [#1053](https://github.com/LiberTEM/LiberTEM/issues/1053) / [PR #1100](https://github.com/LiberTEM/LiberTEM/pull/1100) (2021): environment variables set for the workers leaked into the main process (numba fixed to 1 thread). Fixed by unsetting them properly afterwards.

**What LiberTEM does now.**
- **CPU count:** `libertem.utils.devices.detect()` returns `cpus = range(psutil.cpu_count(logical=False))`, and falls back to 2 when that count is `None` ([`src/libertem/utils/devices.py:47-49`](https://github.com/LiberTEM/LiberTEM/blob/d6aa0fa8be9cd069ddbb419aa82dbbf2ac6684a3/src/libertem/utils/devices.py#L47-L49); docstring: "Only physical CPU cores are counted, i.e. no hyperthreading."). The same call appears in `executor/inline.py:82`, `web/state.py:494` and several datasets. The module imports `numba.cuda` at the top (line 8) and tries `cupy`.
- **Workers:** one process per physical core, one thread each. The Dask spec defaults to `nthreads = 1` ([`executor/dask.py:160-161`](https://github.com/LiberTEM/LiberTEM/blob/d6aa0fa8be9cd069ddbb419aa82dbbf2ac6684a3/src/libertem/executor/dask.py#L160-L161)), and every task runs in `Environment(threads_per_worker=1, ...)` (`dask.py:251`, `pipelined.py:618-620`).
- **Two mechanisms, both used:**
  - *Before the libraries load:* `set_num_threads_env(n=1)` sets `MKL_NUM_THREADS`, `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` and, if numba is not initialized yet, `NUMBA_NUM_THREADS`. Afterwards it restores the old values ([`common/threading.py:240-284`](https://github.com/LiberTEM/LiberTEM/blob/d6aa0fa8be9cd069ddbb419aa82dbbf2ac6684a3/src/libertem/common/threading.py#L240-L284)). It is used around starting the Dask cluster (`dask.py:879`), the worker CLI (`executor/cli.py:41`) and the web server (`web/cli.py:95`). The docstring holds the lesson: "This is needed if you want to limit the number of threads that are created at startup of those libraries, because the other methods usually only limit the number of threads that are _used_, not the number of threads that are created."
  - *At run time, per task:* `set_num_threads(n)` is a re-entrant context manager over pyFFTW, torch, numba and a cached `threadpoolctl.ThreadpoolController` ([`common/threading.py:160-237`](https://github.com/LiberTEM/LiberTEM/blob/d6aa0fa8be9cd069ddbb419aa82dbbf2ac6684a3/src/libertem/common/threading.py#L160-L237)), entered from `Environment.enter()` ([`common/executor.py:127`](https://github.com/LiberTEM/LiberTEM/blob/d6aa0fa8be9cd069ddbb419aa82dbbf2ac6684a3/src/libertem/common/executor.py#L127)). It imports `scipy` and `numpy` first (line 211) so that their BLAS is found.
- **Pinning:** the `PipelinedExecutor` pins worker *i* to CPU id *i* by default (`pin_workers: bool = True`, `pipelined.py:830`; `os.sched_setaffinity(0, [spec["device_id"]])`, `pipelined.py:548-549`), with ids from `range(cores)` (`pipelined.py:742-743`).

**What this means for us.**
- The thread-limiting pattern carries over directly: one thread per worker, set by environment variables before the libraries load. Our workers are fresh processes (Celery runs each batch in a new Python, the crawler uses `spawn`), so the run-time `threadpoolctl` part is not needed.
- The CPU count does not carry over as it is. psutil's documentation says of `cpu_count`: "Note that this may differ from the number of CPUs the current process can actually use (e.g. due to CPU affinity, cgroups, or Windows processor groups)" ([psutil `docs/api.rst`](https://github.com/giampaolo/psutil/blob/940b61bd081bce935f806db65b8f671a0fdf6d49/docs/api.rst), `cpu_count`). In a container limited to 8 CPUs on the dev server, LiberTEM would start 24 workers.
- LiberTEM's pinning has the same pitfall we saw with ONNX Runtime: two LiberTEM processes on one machine both pin to CPUs 0..n−1. In a cpuset that does not contain CPU *i*, `sched_setaffinity` fails with `EINVAL` (compare ONNX Runtime's errors below). These are inferences from the code and were not tried.

### 2. The thread pools in our processes (question 2)

**Versions** (read from the images and venvs on 2026-11-12):

| Environment | Python | Libraries |
|---|---|---|
| transform venv (`/opt/airflow/transform-venv` in `search-stack-airflow:3.3.2`) | 3.13.15 | fastembed 0.8.0, onnxruntime 1.24.4, tokenizers 0.22.2, numpy 2.4.4 with scipy-openblas 0.3.31 (pthreads, `NO_AFFINITY`, `MAX_THREADS=64`), jsonschema 4.26.0; **absent:** scipy, numba, torch, threadpoolctl, psutil; no OpenMP or MKL library in site-packages |
| crawler `~/.venv` | 3.14.10 | numpy 2.5.4 with scipy-openblas 0.3.34 (pthreads, `NO_AFFINITY`, `MAX_THREADS=64`), rosettasciio 0.15.0, dask 2026.8.0, zarr 3.4.2, numcodecs 0.17.1; psutil present (transitively, not declared); **absent:** scipy, numba, torch, threadpoolctl |

**Measured** in a throwaway container of the transform worker's image (`--network none`, the model cache volume read-only; probe in the appendix). The table counts threads after each step, with each thread's `Cpus_allowed_list`, on 8 vCPUs:

| Step | Defaults (fastembed `threads=None`) | `threads=2` |
|---|---|---|
| start | 1 | 1 |
| `import numpy` | 8 (OpenBLAS: 7 more) | 8 |
| model loaded | 15: 7 more, pinned one each to CPUs 1..7 | 9: 1 more, not pinned |
| after `embed` of 600 texts | 23: 8 more (Rayon) | 17 |

Environment variables, with `threads=2`, after `embed`:
- `OPENBLAS_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false`: 2 threads.
- `OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=2`: 4 threads.
- `OMP_NUM_THREADS=1` alone: 10 threads, so this pthreads OpenBLAS also obeys `OMP_NUM_THREADS`.

What controls each pool, and whether it adapts:

| Pool | Default size | Control | Affinity / cpuset | Docker `--cpus` (cgroup `cpu.max`) |
|---|---|---|---|---|
| **ONNX Runtime** intra-op | physical cores of the machine (cpuinfo), including the calling thread; pinned per core | `SessionOptions.intra_op_num_threads`, via fastembed `threads`; no environment variable | **ignored**: with `--cpuset-cpus 0-3` it still made 7 threads, failed to pin 4 of them ("pthread_setaffinity_np failed ... error code: 22 ... Specify the number of threads explicitly so the affinity is not set."), and pinned 3 to CPUs 1..3 | **ignored**: with `--cpus 2`, 7 threads pinned to 1..7 |
| ONNX Runtime inter-op | only in parallel execution mode | `inter_op_num_threads` (fastembed sets it to `threads` too; no pool in sequential mode, measured) | – | – |
| **tokenizers** (Rayon) | logical CPUs | `RAYON_NUM_THREADS`; `TOKENIZERS_PARALLELISM=false` turns it off | honoured (4 threads with cpuset 0-3) | honoured (2 threads with `--cpus 2`) |
| **OpenBLAS** (numpy) | CPUs in the affinity mask (capped by `MAX_THREADS=64`), started at `import numpy` | `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` (measured), `OPENBLAS_DEFAULT_NUM_THREADS`; at run time `threadpoolctl` (not installed) | honoured (3 extra threads with cpuset 0-3) | **ignored** (7 extra threads with `--cpus 2`) |
| fastembed `parallel` | `None`: no extra processes. `0`: `os.cpu_count()` processes. Each process uses `threads=1` | `embed(..., parallel=)`; the warehouse calls `embed(texts)`, so `None` | `os.cpu_count()` ignores affinity | ignored |
| numba, MKL, OpenMP | not present in either environment | – | – | – |

Sources for the table:
- ONNX Runtime's [threading documentation](https://onnxruntime.ai/docs/performance/tune-performance/threading.html) (quoted): "INTRA Threads Total = Number of physical CPU Cores. Leaving at default also enables some affinitization". It goes on: "each session will start with the main thread on the 1st core (not affinitized). Then extra threads per additional physical core are created, and affinitized to that core (1 or 2 logical processors)". And: "if customer explicitly set the number of threads like showcased above, there will be no affinity set to any of the created thread". It also advises: "It is normally best to not set thread affinity and let the OS handle thread assignment".
- ONNX Runtime's source at v1.24.4: [`core/util/thread_utils.cc:92-121`](https://github.com/microsoft/onnxruntime/blob/v1.24.4/onnxruntime/core/util/thread_utils.cc#L92-L121) (default size and affinities) and [`core/platform/posix/env.cc:262-301`](https://github.com/microsoft/onnxruntime/blob/v1.24.4/onnxruntime/core/platform/posix/env.cc#L262-L301). There `cpuinfo_get_cores_count()` is the core count of the machine; the fallback is `hardware_concurrency() / 2`, "guessing the number of phys cores based on a popular HT case".
- fastembed 0.8.0: `common/onnx_model.py:103-108` (`threads` sets both intra and inter), `text/onnx_text_model.py:128-137` (`parallel`), `text/onnx_embedding.py:351` (workers use `threads=1`). fastembed exposes only `enable_cpu_mem_arena` as an extra session option (`onnx_model.py:139-156`), so **ONNX Runtime's spinning cannot be switched off through fastembed**.
- tokenizers v0.22.2: [`tokenizers/src/utils/parallelism.rs`](https://github.com/huggingface/tokenizers/blob/v0.22.2/tokenizers/src/utils/parallelism.rs) (`TOKENIZERS_PARALLELISM`). Rayon's [`ThreadPoolBuilder::num_threads`](https://docs.rs/rayon/latest/rayon/struct.ThreadPoolBuilder.html) (1.12.0, quoted): the count "is based on the `RAYON_NUM_THREADS` environment variable (if set) or the number of logical CPUs (otherwise)". `RAYON_RS_NUM_CPUS` is its deprecated predecessor.
- OpenBLAS [runtime variables](https://openmathlib.org/OpenBLAS/docs/runtime_variables/): `OPENBLAS_NUM_THREADS` "for non-OpenMP builds", `OMP_NUM_THREADS` "for OpenMP builds", `OPENBLAS_DEFAULT_NUM_THREADS` "irrespective if OpenBLAS was built for OpenMP or pthreads". The page states no precedence. That `OMP_NUM_THREADS` also limits this pthreads build was measured, not documented.
- threadpoolctl (README at `13b1a12`, 2026-11-05): it limits "BLAS and OpenMP" through their runtime APIs. It "will not act on libraries loaded after the instantiation of the `ThreadpoolController`". With OpenBLAS on pthreads the limit "affects the whole process", and calls from threads other than the controlling one "will be silently ignored". It does not cover ONNX Runtime or Rayon (neither is in its list). It limits the threads used, not the threads created (LiberTEM's docstring above).
- **Spinning:** ONNX Runtime's intra-op threads spin by default (`session.intra_op.allow_spinning`, "Default: 1 (Enabled)", "Provides faster inference but consumes more CPU cycles"). For comparison, GCC's libgomp lowers its spin count when "there are more OpenMP threads than available CPUs" ([GOMP_SPINCOUNT](https://gcc.gnu.org/onlinedocs/libgomp/GOMP_005fSPINCOUNT.html)). That protection sees only its own process, and none of our libraries uses libgomp. The 62.6 against 36.4 ms of CPU per text (section "For people") is the combined cost of spinning, pinning and contention. The VM bench did not separate them; see the measurement plan.

**The dev server's 95 to 143 threads per process.** The rule above predicts 1 (main) + 47 (OpenBLAS, 48 CPUs) + 23 (ONNX Runtime, 24 physical cores) + 48 (Rayon) = 119, plus Python's and Celery's own threads. That fits, but nobody counted the threads by pool on the dev server. With 4 processes, all four pin their 23 ONNX threads to the same 23 cores.

### 3. How a process finds the CPUs it may use (question 3)

| Way | What it counts | Affinity | cgroup quota | Source |
|---|---|---|---|---|
| `os.cpu_count()` | "the number of logical CPUs in the **system**" | no | no | [Python 3.14 `os.rst`](https://github.com/python/cpython/blob/3.14/Doc/library/os.rst), lines 5773 ff. |
| `os.process_cpu_count()` (3.13+) | "logical CPUs usable by the calling thread of the **current process** ... It can be less than `cpu_count` depending on the CPU affinity" | yes | **no** (measured: 8 with `--cpus 2`) | same, lines 5797 ff. |
| `os.sched_getaffinity(0)` | "the set of CPUs the calling thread of the current process is restricted to" | yes | no | same, line 5727 |
| `PYTHON_CPU_COUNT` / `-X cpu_count` | overrides both functions above | – | – | same |
| `nproc` (coreutils 9.7) | affinity; **also lowered by `OMP_NUM_THREADS`** (measured: `OMP_NUM_THREADS=1 nproc` prints 1) | yes | no (measured: 8 with `--cpus 2`) | measured |
| `psutil.cpu_count(logical=False)` | physical cores of the machine | no | no | psutil docs, quoted above |
| `dask.system.cpu_count()` | min(process CPUs, psutil affinity, ⌈quota/period⌉ of cgroup v1 or the process's own v2 `cpu.max`) | yes | yes | `dask/system.py:17-89` in dask 2026.8.0 (BSD-3-Clause) |
| Rust `std::thread::available_parallelism` (Rayon's default) | affinity and cgroup quota; "may overcount ... when ... cgroup fs can't be queried" | yes | yes | [Rust std docs](https://doc.rust-lang.org/std/thread/fn.available_parallelism.html); measured via Rayon |

The kernel side:
- cgroup v2 `cpu.max` is "$MAX $PERIOD", meaning "the group may consume up to $MAX in each $PERIOD duration"; the default is "max 100000" ([cgroup-v2](https://docs.kernel.org/admin-guide/cgroup-v2.html), "cpu.max"). Docker's `--cpus 2` wrote `200000 100000` (measured).
- `cpuset.cpus.effective` "lists the active CPUs available to tasks in this cgroup" (same document).
- Physical cores come from `/sys/devices/system/cpu/cpuX/topology/core_cpus_list`, the "human-readable list of CPUs within the same core" (deprecated name `thread_siblings_list`) ([sysfs ABI](https://github.com/torvalds/linux/blob/master/Documentation/ABI/stable/sysfs-devices-system-cpu)). It is readable inside containers (measured).
- Docker: `--cpus` "Specify how much of the available CPU resources a container can use"; `--cpuset-cpus` "Limit the specific CPUs or cores a container can use" ([resource constraints](https://docs.docker.com/engine/containers/resource_constraints/)).

**Proposed count, as outcomes rather than code:**
- usable logical CPUs = min(`os.process_cpu_count()`, ⌈`cpu.max` quota / period⌉);
- usable cores = the number of distinct `core_cpus_list` sets among the CPUs in the affinity mask, capped by the quota;
- an explicit setting always wins.

The pieces are known. `dask.system.cpu_count` is the precedent for affinity plus quota, and LiberTEM and ONNX Runtime are the precedents for counting cores. Parent cgroups are not covered: dask reads only the process's own v2 `cpu.max`, so a quota on a parent slice goes unseen. Whether that matters depends on how production runs the containers.

**Physical cores or SMT threads for math.** The libraries' own defaults count physical cores:
- ONNX Runtime (quoted above);
- oneMKL: "By default, Intel® oneAPI Math Kernel Library (oneMKL) uses the number ofOpenMP threads equal to the number of physical cores on the system" ([oneMKL Linux developer guide 2025-2](https://www.intel.com/content/www/us/en/docs/onemkl/developer-guide-linux/2025-2/improving-performance-with-threading.html), typo as in the source);
- LiberTEM (`devices.py`).

OpenBLAS and Rayon count logical CPUs. **I found no primary source with numbers on the SMT gain for our kind of work** (small-model ONNX inference plus pure-Python validation). It has to be measured on the dev server, because the VM has no SMT.

### 4. Rules of thumb, with sources (question 4)

- **Processes × threads ≤ CPUs.** joblib (`doc/user_guide/parallel.rst` at `1e49a29`): "It is generally better to avoid using significantly more processes or threads than the number of CPUs on a machine." Its loky workers get thread variables set to "`cpu_count() // n_jobs` so that the total number of threads used by all the workers does not exceed the number of CPUs of the host". BLAS pools in each worker otherwise cause "a massive over-subscription of resources that can slow down the computation compared to a sequential one". LiberTEM's numbers: 4× to 50× (#602), about 100× at "18x36" (#685).
- **Set the count before the library creates its pool.** For OpenBLAS that is at `import numpy`; for ONNX Runtime at session creation; for Rayon at the first parallel call. Run-time limits only reduce the threads used (LiberTEM's docstring; threadpoolctl's README).
- **Spinning pools punish oversubscription.** ONNX Runtime spins by default, and libgomp backs off only within one process (section 2).
- **Do not pin when several processes share the machine.** ONNX Runtime pins only with its default thread count. Every process then pins thread *k* to core *k*, so with P processes P threads share each core while the OS cannot move them (measured: CPUs 1..7 in each process). Setting the count explicitly turns pinning off (ONNX Runtime documentation, measured). LiberTEM's `PipelinedExecutor` pins the same way across instances (section 1).
- **Pools inside one process take turns** when its stages run one after the other: tokenization (Rayon), then inference (ONNX Runtime), then numpy post-processing, all in the calling thread's sequence (fastembed's `onnx_embed`). Each pool may then have T threads without adding up within a process. Their idle and spinning threads still count. This is an inference from the code path, not measured.

### 5. Recommendations for the warehouse's transform worker

**Settings, for P = Celery concurrency of queue `transform` and T = threads per batch process:**

- `EMBEDDING_THREADS=T` through patch `perf/patches/0002-embedding-threads-setting.patch`. Always set it explicitly: that alone turns off ONNX Runtime's pinning. T = max(1, C ÷ P), where C is the cores the transform worker may use.
- `OPENBLAS_NUM_THREADS=1`. numpy's BLAS does no heavy work in the transform (pooling and normalizing small vectors), so this drops 47 idle threads per process on the dev server. Set it in the worker container's environment, which the batch processes inherit; the variable must be in place before `import numpy`.
- `RAYON_NUM_THREADS=T`, or `TOKENIZERS_PARALLELISM=false` if measurement shows no gain from parallel tokenization.
- P × T ≤ C. Before patch 0001, about 60 % of a batch is single-threaded `jsonschema.validate` (F16). There, more processes with fewer threads use the CPUs better (P ≈ C, T = 1). After 0001, embedding dominates, and the VM's 8 × 1 (206 texts/s) against 4 × 2 (194) suggests the split matters little once P × T = C.
- Upper bounds on P besides CPUs:
  - memory: 2.3 to 4.4 GB per batch process (F16);
  - the indexing DAG's 16 active tasks, shared with the file-metadata batches (F16);
  - the database and OpenSearch, which run on the same machine and need CPU too.
- **The dev server** (24 cores, 48 logical CPUs, 251 GB): candidates are 24 × 1, 12 × 2 and 8 × 3, plus 24 × 2 or 48 × 1 to test SMT, within the 16-slot limit (so 12 × 2 or 16 × 1 unless the DAG limit is raised). Which one is a measurement (below), not a recommendation from here.
- **Production:** the same formula with its own C. It needs no numbers of its own once C is counted at start; until then, the operator sets the values per machine.

**How to set them.** One variable for the concurrency instead of two today: `AIRFLOW__CELERY__WORKER_CONCURRENCY: "4"` in `docker-compose.yml:38` and `--concurrency` in the transform worker's command (`docker-compose.yml:408`, `docker-compose.staging.yml:52`). Which one wins was not checked. The thread variables go next to it in the worker's environment. The upstream DAG's docstring says the worker runs "one task at a time" (`transform_index.py:9`), while staging runs 4; worth aligning when patching. To adapt automatically, either:
- (i) the patched `transform_core.py` computes T = usable cores ÷ concurrency when `EMBEDDING_THREADS` is unset. It needs the concurrency in its environment and the count from section 3, so it must run on Python 3.13. Or:
- (ii) a launcher in the worker container computes P and T before Celery starts. In shell, `nproc` is not enough: it ignores the quota and obeys `OMP_NUM_THREADS`.

**How to check each one in the VM:**

| Claim | Measurement | Expected |
|---|---|---|
| Pinning, not only thread count, hurts | `perf/embed-bench.py 4:0 4:7 4:2 8:1` (4:7 = default count, unpinned) | 4:7 between 4:0 (118 texts/s) and 4:2 (194) |
| Idle OpenBLAS and Rayon threads cost little | the same specs with `docker compose exec -e OPENBLAS_NUM_THREADS=1 -e RAYON_NUM_THREADS=2 ...` | within noise of the runs without |
| P × T = C is the best total | `embed-bench.py 1:8 2:4 4:2 8:1 8:2 16:1` | 8:2 and 16:1 no faster than 8:1, more CPU per text |
| The patch works in the real pipeline | apply 0002; `perf/indexing-bench.sh 16000 2000 4` with `EMBEDDING_THREADS=2` and the two variables, against the same run without; `batch-probe.py` thread counts | records/s up; threads per batch process ≈ 1 + (T − 1) + T + a few; no pinned threads; load average ≤ 8 |
| Validator plus threads | the same with 0001 applied, P × T = 8: 8 × 1 against 4 × 2 | 8 × 1 ahead before 0001, the two close after |

**What the VM cannot show:**
- SMT: no sibling threads are visible, so physical against logical cannot be decided there.
- The ONNX Runtime core count of 24 against 48 logical CPUs.
- The thread composition at 48 CPUs (the 119 prediction).
- Memory bandwidth and cache effects with 24 or more busy cores on the EPYC.
- Contention with the database and OpenSearch at staging volume.

Those need `embed-bench.py` in the dev server's transform worker while staging is idle (24:1, 12:2, 8:3, 6:4, 4:6, 24:2, 48:1), and one counted thread listing of a batch process (`batch-probe.py`).

### 6. Recommendations for the crawler

- **Extraction pool** (`extraction.py`, `MODAMA_CRAWLER_EXTRACT_WORKERS`, default `min(os.cpu_count(), 8)`):
  - It is not at risk of CPU oversubscription. Extractors read headers (D7), and the cap of 8 is there because "NFS latency, not the CPU, sets the pace" (D1).
  - It is at risk from the thread pools' **address space**. Each worker that imports numpy (RosettaSciIO's DM reader does, inside `extract()`) starts CPUs − 1 OpenBLAS threads. Measured on 8 CPUs, after importing numpy and the DM reader: 8 threads and a VmSize of 430 MB, against 1 thread and 143 MB with `OPENBLAS_NUM_THREADS=1`; that is about 41 MB per thread. VmSize is what `RLIMIT_AS` (`MEMORY = 4 << 30`) limits; the code comment at `extraction.py:34-37` already notes "more with more CPUs (thread buffers)".
  - On 48 CPUs that would be about 143 MB + 47 × 41 MB ≈ 2 GB of the 4 GiB per worker, and about 2.7 GB at OpenBLAS's cap of 64. These are extrapolations, not measured.
  - Recommendation: set `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` to 1 in each worker before the first extractor runs. The pool's initializer (`_limit_memory`) is early enough today: numpy is not imported by `modama_crawler.cli`, `mime`, `mimedb` or the format collections' entry points (measured: `'numpy' in sys.modules` stays `False`). Setting them in the parent's environment around the pool, as LiberTEM does, also covers replacement workers (`max_tasks_per_child`).
  - Count CPUs with the affinity at least (`os.process_cpu_count()`, Python ≥ 3.13 is given), better also with the quota (section 3). In the VM with cpuset 0-3, `os.cpu_count()` said 8 and `os.process_cpu_count()` said 4.
- **Walk, magic matching** (`walk.py`, the same worker count): pyxdg's matching is pure Python (`mime.py:136-141`, "holds the GIL for about 4 ms per file"), and those processes do not import numpy (measured). They have no math-library pools and are CPU-bound single threads, so the count should not exceed the usable CPUs. The default goes wrong only where the crawler runs in a container with fewer CPUs than `os.cpu_count()` reports; the fix is the same count. The walk's 32 I/O threads wait on NFS and are not part of the CPU budget.
- **The crawl and the indexing share the machine** on the dev server (the search stack runs both), and they can overlap: an indexing run took about 19 hours (F16, extrapolated). The machine-wide rule (section 8) therefore needs either a CPU budget per container (`cpus`/`cpuset` in compose, which each process then counts) or numbers the operator divides by hand.

### 7. Reusing LiberTEM's code: copy or package (@weber, 2026-11-12: "I'd just copy the relevant parts, or we spin it out as a utility package in the LiberTEM organization, like we did with sparseconverter.")

**Which parts, at `d6aa0fa`, and what they need:**

| Part | Lines | Own dependencies | Take it? |
|---|---|---|---|
| `set_num_threads_env` (`src/libertem/common/threading.py:240-284`) | 45 with docstring; about 20 without the numba branch (260-262, 268-269) | `os`, `contextlib`; numba only in the dropped branch | **yes**: the pattern we need |
| `set_num_threads` and `ThreadpoolWrapper` (`threading.py:160-237`) plus the pyFFTW, torch and numba helpers (40-157) | about 200 | threadpoolctl (in neither environment, so a new dependency), scipy (`import scipy` at 211; in neither environment), numba, torch, pyFFTW | no: our workers are fresh processes, so environment variables suffice |
| `detect()` (`src/libertem/utils/devices.py:31-60`) | 1 relevant line (`psutil.cpu_count(logical=False)`) | psutil, `numba.cuda` at import, cupy | no: replace with the affinity- and quota-aware count of section 3 (new code, about 30 lines; dask's `cpu_count`, BSD-3-Clause, as the model) |

**Licence.** LiberTEM is MIT since its relicensing ([#1649](https://github.com/LiberTEM/LiberTEM/issues/1649), consent of all creators by 2024-10-23); `LICENSE` reads "Copyright (c) 2024 LiberTEM creators", and `pyproject.toml` has `license = "MIT"`. MIT requires: "The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software." The crawler is MIT too (`python/crawler/LICENSE`). A copy carries the notice in the file's header, or in a file next to it like `python/modama-formats-em/COPYING.rosettasciio` (the repo's precedent for third-party licence text). The warehouse is upstream code (EOSC Data Commons); its licence was not checked here.

**(a) Copy into our repository.**
- Where: the crawler (a small module next to `extraction.py`, used by `extraction.default_workers()` and the pool's initializer). The transform worker is a separate environment, upstream code patched by us, on Python 3.13; there the copy would be a second one inside patch 0002, or no code at all if the operator sets the variables (section 5, (ii)).
- For: no new dependency, no release step, about 50 lines in total, changes stay reversible.
- Against: up to two copies that drift apart (crawler, warehouse patch); tested on Linux only; LiberTEM keeps its machine-wide count.

**(b) A small package in the LiberTEM organization**, following `LiberTEM/sparseconverter` (checked at `a3695f8`, 2026-09-29):
- setuptools `pyproject.toml` with `license = "MIT"`, `license-files`, the version from `__version__`;
- a GitHub Actions workflow testing Python 3.10 to 3.14 on Ubuntu, Windows and macOS with codecov;
- a release job that builds and publishes to PyPI on a tag (`pypa/gh-action-pypi-publish`, token secret); LiberTEM depends on it as `sparseconverter>=0.4.0`.
- For: one tested home for the subtle part (cgroup v1/v2, quotas on parent cgroups, SMT topology, Windows processor groups); LiberTEM could replace its `psutil.cpu_count(logical=False)` with it and gain container awareness; pure Python, no dependencies.
- Against: a new dependency in both of our environments; a release before first use; another repository to maintain; cross-platform scope we do not need (Linux only); upstream EOSC may not accept a dependency on a LiberTEM-organization package in the warehouse.

**Lean: (a) now, (b) once a second user (LiberTEM) wants the count.** Copy the 20 lines of the environment-variable pattern into the crawler; write the count there with tests on the VM's cpuset and quota cases; configure the warehouse with environment variables plus patch 0002, without copying code into upstream. **Strongest argument against:** the count is the part that is easy to get subtly wrong, and LiberTEM has the same gap. Writing it in our repository first means a second implementation later, or LiberTEM depending on our code, while a package from the start would be one tested place and fix LiberTEM too.

### 8. Where the requirement goes (proposed wording; the files are not edited)

The rule concerns the whole stack, so its home is the search stack's `python/crawler/design/requirements-pipeline.md`, section 2.4 "Operating conditions". The crawler's own requirement refers to it (one home per fact).

`requirements-pipeline.md`, 2.4, a new bullet:

> - **CPU budget** (@weber, 2026-11-12): every service adapts its processes and threads to the machine it runs on (the dev server is not the production server) and does not oversubscribe it. In each container, processes × threads per process stays within the CPU cores that container may use: its affinity, cpuset and CPU quota, counted at start, not the machine's total. An explicit setting overrides the count. No service relies on a library's default thread count where several of its processes run at once. Checked on staging during an indexing run: load average not above the CPUs the containers may use, and no batch process with more threads than its setting plus a few. Background: `docs/research/cpu-oversubscription.md`.

`design/requirements.md`, Scale, the next free number (R41 at the time of writing):

> - **R41 (must, @weber 2026-11-12)** The crawl follows the stack's CPU budget (`requirements-pipeline.md`, 2.4): its worker processes count the CPUs they may use on the local machine (affinity, cpuset, quota), and the math libraries inside them start no thread pools beyond what the crawl gives them (BLAS: one thread per extraction worker), so that a worker's memory limit does not depend on the machine's CPU count.

### 9. Not verified

- The dev server's thread composition per batch process (the 119 prediction); ONNX Runtime's core count there (24 expected from cpuinfo) and how it pins with SMT siblings; whether the staging containers have CPU limits.
- The SMT gain for this work; no primary source with numbers was found.
- OpenBLAS's address space per thread at 48 or 64 threads (extrapolated from 8 CPUs, where OpenBLAS caps its threads at the CPUs it sees even with `OPENBLAS_NUM_THREADS=48`).
- Which of `AIRFLOW__CELERY__WORKER_CONCURRENCY` and `--concurrency` wins for the transform worker.
- The cost of ONNX Runtime's spinning on its own (not separable through fastembed 0.8.0, which does not expose the option).
- The warehouse's licence (for a copy inside the patch).
- No benchmarks were run for this note: another agent was using the VM's test stack, and the 8-CPU benches would have disturbed it. Only short probes (one process, 600 texts) ran, in throwaway containers.

### Appendix: probes (2026-11-12, VM)

Thread pools in a transform process (`pools.py`, run in throwaway containers of the worker's image):

```python
import collections, os, sys


def snapshot(step):
    by = collections.Counter()
    for tid in os.listdir("/proc/self/task"):
        name = open(f"/proc/self/task/{tid}/comm").read().strip()
        aff = next(
            l.split(":", 1)[1].strip()
            for l in open(f"/proc/self/task/{tid}/status")
            if l.startswith("Cpus_allowed_list")
        )
        by[(name, aff)] += 1
    print(
        f"{step}: {sum(by.values())} threads",
        {f"{n}@{a}": c for (n, a), c in sorted(by.items())},
    )


threads = int(sys.argv[1]) if len(sys.argv) > 1 else 0
snapshot("start")
import numpy

snapshot("numpy")
from fastembed import TextEmbedding

snapshot("fastembed imported")
m = TextEmbedding(
    model_name=os.environ["EMBEDDING_MODEL"],
    cache_dir=os.environ["FASTEMBED_CACHE_DIR"],
    threads=threads or None,
    local_files_only=True,
)
snapshot("model loaded")
list(m.embed([f"text number {i} about a beam and a sample" for i in range(600)]))
snapshot("after embed of 600 texts")
print(
    "os.cpu_count",
    os.cpu_count(),
    "process_cpu_count",
    os.process_cpu_count(),
    "affinity",
    len(os.sched_getaffinity(0)),
)
```

```sh
docker run --rm --network none \
  -v search-stack_fastembed-airflow:/opt/airflow/cache/fastembed:ro -v "$PWD":/probe:ro \
  -e EMBEDDING_MODEL=BAAI/bge-small-en-v1.5 -e FASTEMBED_CACHE_DIR=/opt/airflow/cache/fastembed -e HF_HUB_OFFLINE=1 \
  [-e OPENBLAS_NUM_THREADS=1 -e RAYON_NUM_THREADS=2 | --cpuset-cpus 0-3 | --cpus 2] \
  --entrypoint /opt/airflow/transform-venv/bin/python search-stack-airflow:3.3.2 -I /probe/pools.py [THREADS]
```

Address space of an extraction worker (crawler `~/.venv`): import `numpy` and `rsciio.digitalmicrograph`, then read `Threads` and `VmSize` from `/proc/self/status`, with `OPENBLAS_NUM_THREADS` set to 1, 8, 24, 48 and unset. Results: 1 thread / 143,248 kB, and 8 threads / about 429,870 kB for every other value.
