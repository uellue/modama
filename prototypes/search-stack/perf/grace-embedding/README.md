# Embedding benchmark for grace: CPU against GPU

A folder to copy to grace (NVIDIA GH200) and run there with one command. It measures how fast the
warehouse's embedding runs on the Grace CPU and on the Hopper GPU, each at its own best settings, and writes
one JSON file to send back.

## What it measures, and why

The warehouse turns every record's text (title, subjects, descriptions) into a vector with fastembed, model
`BAAI/bge-small-en-v1.5`, on ONNX Runtime on the CPU. In the modama search stack (patch 0002) it sorts a batch's
texts by length, embeds them in sub-batches of 32 and runs 8 to 16 processes of one thread each. On the VM,
ONNX Runtime is 91 % of the CPU time; a text of 512 tokens costs about 530 ms of CPU, a record of a mixed
batch 87 ms after the sort (change cpu-budget, `python/crawler/openspec/changes/cpu-budget/design.md`); the
rest of a batch is below 1 %. So the question is the device: how many texts per second does grace's GPU do
against its 72 CPU cores? The research note `docs/research/embedding-throughput.md` (section 7) collects what
others did; this package takes the parts that fit a run of a few hours.

**Optimum against optimum.** A CPU is fastest with many processes of one or few threads and small batches; a
GPU needs large batches, and often several processes feeding it at once, to be busy. Run at the same setting,
one of the two would be measured at a bad one, and the comparison would be about the setting. So the script
searches each device's best settings and compares the best CPU case with the best GPU case, for each set of
texts:

- **short**: tens of tokens (title, subjects, a sentence), like most records;
- **mixed**: 12 % at the model's 512 tokens, the rest short, like a batch with EM records among others;
- **long**: all at 512 tokens.

**The model file.** The file fastembed loads (`qdrant/bge-small-en-v1.5-onnx-q`, `model_optimized.onnx`,
66 MB) is already optimised for ONNX Runtime (fused Attention, FastGelu, SkipLayerNormalization) and stores
all 149 weight tensors in float16. On the GPU it computes in float16; on the CPU, ONNX Runtime converts the
weights to float32 on every run. `prepare_model.py` writes two files of our own from it: the same graph in
float32 (133 MB, the weights in a separate file that ONNX Runtime maps into memory, so processes can share the
pages) and an int8 version (information only: it changes every vector).

**The runtimes.** The CPU runs production's versions (fastembed 0.8.0, onnxruntime 1.24.4). The GPU needs
onnxruntime-gpu, which has aarch64 Linux wheels only from 1.29.0 on; the package uses 1.31.1 (CUDA 13). To
separate the device from the version, the best CPU case of each set is run once more with onnxruntime-gpu
1.31.1's CPU provider.

**Correctness.** Every variant's vectors of 512 texts are compared with production's (CPU, float16 file,
sorted, sub-batch 32): the cosine of each pair should be at least 0.9999; the minimum is reported, and the
headline shows it next to each best case. A variant whose vectors do not pass is shown apart, like int8,
and is neither "best" nor in the ratio.

**The CPU's caches and memory.** Every process holds its own copy of the weights; threads of one process
share one. With 72 processes the copies cannot stay in the L3 cache (Grace: one L3 of about 114 MB for all
72 cores, NVIDIA's documentation; the run records `lscpu -C`), with threads they might. Hence, at the same
number of cores: processes against threads against mixes, each also pinned to its own cores; one process
whose threads all call one session (one copy); larger sub-batches for short texts (more rows per pass over
the weights); the float32 file with pre-packing on and off, its memory per process (PSS and USS, from
`/proc/<pid>/smaps_rollup`) at 1, 8 and 72 processes; and, where `perf` may count, instructions per cycle
and last-level cache misses per text. On the GH200 the GPU's memory is a NUMA node of its own; NVIDIA warns
that a CPU program's pages can land there, so CPU workers run with `numactl --membind` to the CPU's node
where numactl is installed (and once without, at the best case).

**What it does not say.** A GPU batch larger than 250 texts needs transform batches larger than today's 250
records; the warehouse's batching is not part of this. Retrieval quality of int8 is not measured, only how
far its vectors move.

## The matrix

**CPU** (`venv-cpu`, onnxruntime 1.24.4), for each set; C is the number of usable cores (72 on grace):

| Step | Cases (quick mode in brackets) |
|---|---|
| A. processes × threads, sub-batch 32, sorted | 1×1, 8×1, 16×1, C×1, C/2×2, C/4×4, C/8×8, 1×C, one process per L3 domain and per NUMA node (1×1, 8×1, C×1, 1×C) |
| B. the same, pinned | every composition of A with C cores and more than one process (only C×1) |
| C. short texts: sub-batch 128 and 512 | at every composition of A and B with C cores (128 at the best) |
| D. sub-batch 16, 64, 128, 256 at the best | skipped where the processes would not fit in memory (none) |
| E. the best in the given order; the best without `--membind` | one case each (the second only where binding applies) |
| F. at the best: float32 file; without pre-packing; bf16 fast math (aarch64 only); int8; one process with C threads calling one session | every set (short only) |
| G. short texts: float32 file, with and without pre-packing, at 1, 8 and C processes | 6 cases (float32 at 1 and C) |

1×1 is the cost of one text on one core. Filling the cores with processes of one thread is what production
does; 8 and 16 processes are the staging settings. Pinned: process k runs on cores k·T to k·T+T−1, in the
order of NUMA node and L3 domain (`os.sched_setaffinity`, nothing to install). bf16 fast math is ONNX
Runtime's `mlas.enable_gemm_fastmath_arm64_bfloat16` (float32 matrix products in bfloat16 on Arm); it changes
the numbers slightly, hence the vector check. Before the cases, the tokenizer alone: texts/s per set with one
thread and with all cores.

**GPU** (`venv-gpu`, onnxruntime-gpu 1.31.1, CUDA provider), for each set:

- Workers × batch size. Workers are processes, each with its own model on the GPU, all feeding the one GPU
  at once (1, 2, 4, 8, 16; quick: 1, 2, 4); each tokenises its texts on the CPU (with C / workers threads)
  while another's batch runs on the GPU. For each number of workers the batch grows by 4 (32, 128, 512, 2048,
  8192, 32768; quick: 32, 256, 2048) until texts/s rises by no more than 3 % or the workers run out of
  their memory (reported as OUT OF MEMORY; the search stops there), then its neighbours (half, double)
  around the best. More workers are tried only while they raise the best by more than 3 %. A batch of more
  than 2^20 (about 1M) tokens at the set's longest text is not tried (the long set stops at 2048 texts of
  512 tokens).
  The workers' ONNX Runtime arenas together get at most half of the GPU's memory (`gpu_mem_limit`, each
  worker its share; `GPU_MEM_FRACTION` changes the half); CUDA's own memory, about 0.5 GB per process, comes
  on top. The GPU is shared: the GPU part does not start, and stops before the next case, when
  `nvidia-smi --query-compute-apps` lists another process (an MPS server aside); `--force` runs it anyway.
- At the best: batches by a token budget instead of a number of texts (4096, 16384, 65536, 262144 tokens,
  counted at each batch's longest text; TEI's default is 16384; quick: 16384); one process with 2 and 4
  threads calling one session (quick: 2); the float32 file at a quarter, the same and four times the batch
  (quick: the same), against the production file's float16; the given order.
- Texts sorted by length in windows of 250, as on the CPU; a batch larger than 250 texts takes consecutive
  sorted windows (padding grows with the batch otherwise). GPU utilisation, memory and power are
  sampled with `nvidia-smi` every 200 ms during each case.
- MPS (NVIDIA's Multi-Process Service, which lets several processes' kernels run at once) is not started by
  the script; the facts record whether it runs. See "With MPS" below.

**Every case**: texts/s, wall and CPU time per text, peak memory per process, PSS and USS per process, model
load and warm-up (not timed), the load average before it. Texts are sorted by length within windows of 250,
production's transform batch, in every case (recorded as `sort_window`): a worker's share is a whole number
of windows, at least one, and each window is sorted on its own, so the rate does not depend on the share
(on the VM, 1×1 mixed, sorting the whole share gave 3.6 texts/s at 64 texts, 6.5 at 250, 9.7 at 1000).
Each case runs at least 20 s (quick: 3 s). Grace's power sensors (Module,
Grace, CPU and SysIO power in hwmon, NVIDIA's Grace performance tuning guide) are sampled too, if the kernel
exposes them and they are readable without root, and give joules per text.

## Setup on grace

You need: Python 3.12 (the lock files `requirements-*.txt` are compiled for it, grace's miniforge Python
3.12.12; for another version, compile them again from `requirements-*.in` with the command in their first
lines), glibc 2.34 or newer (onnxruntime-gpu's wheels),
an NVIDIA driver 580 or newer (CUDA 13), and access to pypi.org and huggingface.co (the model, 65 MB, at the
pinned revision `aa8f8b060edb00e03bfdd08813a2949946c8ba55` of `qdrant/bge-small-en-v1.5-onnx-q`, is downloaded
on the first run into `cache/`; the variants, 170 MB, are written next to it). Everything stays in the folder:
pip runs without its cache, and `HF_HOME` (with Hugging Face's xet cache) is `cache/hf`.

```bash
# from a checkout of the repository
rsync -a prototypes/search-stack/perf/grace-embedding/ grace:grace-embedding/
ssh grace
cd ~/grace-embedding

uname -m                  # aarch64
python3 --version         # 3.12
ldd --version | head -1   # 2.34 or newer
nvidia-smi                # "Driver Version: 580..." or newer, "CUDA Version: 13.x"; no other processes
                          # (grace, 2026-11-13: driver 620.70.06, CUDA 13.5, GH200 with 146831 MiB)
free -g                   # confirm the RAM (grace, 2026-11-13: 478 GiB total, about 412 GiB available);
                          # memory is checked before step D only (not yet before every case)

python3 -m venv venv-cpu
venv-cpu/bin/pip install --no-cache-dir --require-hashes -r requirements-cpu.txt
python3 -m venv venv-gpu
venv-gpu/bin/pip install --no-cache-dir --require-hashes -r requirements-gpu.txt  # about 2 GB of CUDA libraries

venv-gpu/bin/python bench.py gpu-check
# GPU check passed: onnxruntime-gpu 1.31.1, session providers ['CUDAExecutionProvider', ...]
```

If `python3` is older than 3.11 or has no `venv` module: `uv venv --seed --python 3.13 venv-cpu` (and the same
for `venv-gpu`), then the `pip install` lines as above. uv downloads a Python of its own into
`~/.local/share/uv/python` (outside the folder; `uv python uninstall 3.13` removes it afterwards) and keeps a
cache in `~/.cache/uv` (`uv cache clean`).

The quick provider check, without loading the model:
`venv-gpu/bin/python -c "import onnxruntime as o; o.preload_dlls(); print(o.__version__, o.get_available_providers())"`
must list `CUDAExecutionProvider`. Only `gpu-check` shows that a session really starts on the GPU: when the
CUDA libraries do not load, ONNX Runtime prints "Failed to load ..." and falls back to the CPU.

**Optional, if you may and want them:**
- Cache counters: `perf stat` is used if installed and allowed for your processes
  (`cat /proc/sys/kernel/perf_event_paranoid`: 2 or lower). Without, the IPC and LLC columns stay empty.
  `sudo sysctl kernel.perf_event_paranoid=2` would allow it, but it changes the whole host, for every user,
  until set back: a decision for grace's admins, not for this run.
- `numactl` (package `numactl`): binds the CPU workers' memory to the CPU's node. Without, the run says so.

## Run

```bash
./run.sh quick   # a small grid: checks the setup end to end
./run.sh full    # the numbers to keep
```

Run `full` in `tmux` or `screen`, on an otherwise idle machine (the output records the load average before
each case; the GPU part stops when another process uses the GPU, see "What can go wrong"). It prints each case as it goes, then the table: first, for
each set, the best CPU and the best GPU with their settings, texts/s, joules per text where readable, the
vectors' agreement and the ratio; then every case.

`./run.sh quick|full cpu` or `... gpu` runs only one part (the report covers what ran); a last argument
`--force` runs the GPU part even while other processes use the GPU.

**With MPS** (optional, a second GPU run; only if nobody else uses the GPU and MPS may be started without
root, which this package could not check):

```bash
export CUDA_MPS_PIPE_DIRECTORY=$HOME/mps/pipe CUDA_MPS_LOG_DIRECTORY=$HOME/mps/log
mkdir -p $CUDA_MPS_PIPE_DIRECTORY $CUDA_MPS_LOG_DIRECTORY
nvidia-cuda-mps-control -d          # start
./run.sh full gpu
echo quit | nvidia-cuda-mps-control # stop
```

**How long.** On the VM (8 cores, no GPU) the quick CPU part took 12 minutes (22 cases), when a quick case's
worker embedded 64 texts; now it embeds at least one window of 250, so quick takes longer. On grace, not
measured; estimated from the VM's cost per text: quick more than the 15 to 30 minutes estimated with 64, full 2.5 to 3.5 hours (about 100 CPU cases,
the long texts' at about 2 minutes each, since every worker embeds at least 250 texts; the GPU search depends
on where it stops). Each case prints when done.

## What to send back

`results/<host>-<date>-<mode>-all/summary.json`: everything in one file (the machine's facts with `lscpu`,
caches, NUMA, MPS and GPU, the token lengths of the sets, the tokenizer alone, every case, the vector checks
and the headline). The same table as printed is in `table.txt` next to it. If something failed, also
`run.log` and the `logs/` folder.

## What can go wrong, and how to check

| Symptom | Check | Cause, remedy |
|---|---|---|
| "no NVIDIA GPU visible" | `nvidia-smi` | No driver, or the GPU not passed into a container or batch job. |
| "this venv's ONNX Runtime has no CUDA provider" or "both onnxruntime and onnxruntime-gpu are installed" | `venv-gpu/bin/pip list \| grep -i onnx` | The CPU build in `venv-gpu`. Remove `venv-gpu`, make it again with `requirements-gpu.txt` only. |
| "the model did not start on the GPU", after "Failed to load libcublas.so.13 ..." | `nvidia-smi` (driver, CUDA version at the top); `venv-gpu/bin/pip list \| grep nvidia`; the log named in the message | Driver older than 580 (CUDA 12): ask for a newer one. CUDA or cuDNN libraries missing or of another major version: make `venv-gpu` again. |
| pip: "No matching distribution found for onnxruntime-gpu" | `ldd --version`, `python3 --version` | glibc older than 2.34, or Python outside 3.11 to 3.14. |
| A case "OUT OF MEMORY" | | Expected at the largest GPU batches (the workers' share of the GPU's memory): the search stops there. |
| "other processes use the GPU" | `nvidia-smi` | Someone else uses the GPU: wait, or ask them; `--force` runs anyway (the numbers then depend on them). |
| A variant FAILED (for example bf16) | its log in `logs/` | Reported in the table; the other cases go on. |
| "No cache counters: ..." | `cat /proc/sys/kernel/perf_event_paranoid` | perf may not count; see Optional above. Not an error. |
| The model download fails | `curl -I https://huggingface.co` | No internet on grace: copy `cache/` from a machine that ran it (`FASTEMBED_CACHE_DIR` points elsewhere if needed). |

If the driver cannot be 580 or newer: onnxruntime-gpu has no aarch64 wheels for CUDA 12 on PyPI (none at all
before 1.29.0). The route then is another runtime, PyTorch's aarch64 CUDA 12.6 wheels (download.pytorch.org,
`torch 2.14.1+cu126`) with the same model; not in this package.

## Files

- `run.sh`: the one command; creates the texts and the model variants, runs the CPU part in `venv-cpu`, the
  GPU part in `venv-gpu`, then the report. Exit status 0, or 3 and 4 when the GPU part could not run, 5 when
  it stopped because another process used the GPU (the CPU results are still reported).
- `gen_texts.py`: the synthetic record texts (standard library only; deterministic by seed; `--help`).
- `prepare_model.py`: the float32 and int8 model files (needs `onnx`).
- `bench.py`: the measurement (`cpu`, `gpu`, `gpu-check`, `report`; see its docstring).
- `requirements-cpu.txt`, `requirements-gpu.txt`: the pinned packages, for grace only (not the repository's
  dependencies): fastembed 0.8.0 / fastembed-gpu 0.8.0, onnxruntime 1.24.4 / onnxruntime-gpu 1.31.1 with
  NVIDIA's CUDA 13 and cuDNN 9 wheels, tokenizers 0.22.2, numpy 2.4.4, huggingface-hub 1.8.0, onnx 1.23.2
  (CPU venv only, for `prepare_model.py`; not used in production), and what these pull in. Checked on PyPI
  on 2026-11-13: every package has a wheel for Linux aarch64 and CPython 3.13.

Environment variables of `run.sh`: `VENV_CPU`, `VENV_GPU` (default `./venv-cpu`, `./venv-gpu`), `RESULTS`
(default `./results`), `FASTEMBED_CACHE_DIR` (default `./cache`), `GPU_MEM_FRACTION` (default 0.5).
