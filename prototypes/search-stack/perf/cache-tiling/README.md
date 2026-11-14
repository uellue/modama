# Cache tiling for bge-small-en-v1.5 on CPU: experiments (2026-11-14)

Question (@weber, 2026-11-14): is the embedding model slow on CPU because it does not use the caches, and
would tiling/reordering the work give 5–10×? Measured in the devvm (8 vCPUs of an AMD EPYC 7F72, Zen 2,
AVX2+FMA, no AVX-512/VNNI; per vCPU the VM reports 64 KB L1d, 512 KB L2 and 16 MB L3; which vCPUs share a
physical L3 is not visible), production's ONNX
Runtime 1.24.4, the float32 file (`fp32.py convert` of the pinned `qdrant/bge-small-en-v1.5-onnx-q`).

## For people

- **Roofline: 5–10× is not possible in float32 on this core.** One 512-token text is 26.6 GFLOP, 99.6 % of it
  matrix products. ONNX Runtime already runs one text at 86 GFLOP/s (308 ms), 81 % of its own MatMul rate
  (106 GFLOP/s); the core's float32 peak is about 118 GFLOP/s. Ceiling: 1.23× over one text at a time, about
  1.7× over production's setting, if everything ran at peak.
- **The hunch is right in one place, not where expected.** The weights (133 MB) do not fit any cache, but that
  does not matter: each weight is used 512 times per load (the GEMMs are blocked). What spills is the
  *sub-batch*: 32 texts of 512 tokens make 16,384-row activations (100 MB for the FFN) and a 403 MB score
  buffer per layer. Memory traffic is 770 MB per text at sub-batch 32 against 218 MB at sub-batch 1.
- **Best float32 result: one text per sub-batch** (depth-first over texts). The vectors are bitwise identical.
  At 8 processes: 512-token texts 18.8 → 23.8 texts/s (+26 %), mixed texts 206 → 151 ms CPU per text (+36 %).
  Short texts lose 10 % at sub-batch 1 (30 against 27 ms); a cap of 512 padded tokens per sub-batch keeps
  both (mixed 153–155 ms, short 26–27 ms), also bitwise identical.
- **Plus ONNX Runtime's flash attention** (`MultiHeadAttention` without mask, valid only for unpadded input,
  i.e. sub-batch 1): at 8 processes 24.6–25.6 texts/s on 512-token texts (+31–36 % over production's
  setting) and 55.1 on mixed texts (+44 %); max difference 2.1e-7, min cosine 1.0000000 (not bitwise: other
  kernels).
- **Toy tiling (Rust, same kernels, only the order changed):** attention tiled FlashAttention-style is no
  faster than per-head materialisation at one text (8.1 against 8.3 ms per layer); both take 19 % less time
  than materialising all heads of 8 texts at once (ONNX Runtime's order, 10.2 ms); FFN depth-first over token tiles is
  slower at every tile size (weights re-read per tile), fusing GELU saves 0.5 %.
- **All cores:** 8 single-threaded processes scale 7.4–7.8× and beat one process with 8 threads by 1.6×;
  shared L3 and memory bandwidth are not the limit here (per-process CPU per text +0 to +6 % from 1 to 8).
- **Not equal, for information:** int8 dynamic quantisation is no faster on this CPU (326 ms, AVX2 without
  VNNI) and changes the vectors (min cosine 0.9737). PyTorch is slower than ONNX Runtime (SDPA 422 ms,
  eager 525 ms per text, equal within 3.6e-7); `torch.compile` could not run (no C++ compiler in the VM).
- **For 5–10×** the work itself has to shrink or get cheaper: fewer tokens (attention is quadratic: 128
  tokens cost 65 ms against 308), a smaller model, int8 on hardware with VNNI/AMX, or a GPU. Each changes
  results or hardware.

## Details

Each number below comes with its command (from the repository root, scratch folder
`/var/tmp/embed-research-trials`, `V=/var/tmp/embed-research-trials/venv/bin/python`). Single-thread runs
are pinned with `taskset`, every script sets `OMP/OPENBLAS/MKL_NUM_THREADS=1`; ONNX Runtime runs with
`intra_op_num_threads=1`, sequential. The VM was otherwise idle (no containers). The ORT profiles report the
median of 10 runs, the toys the median of 7; throughput runs are one timed pass after one warm-up pass,
repeated where noted (repeats agreed within 2–4 %). Texts/s is set by the slowest of the 8 workers; other
sessions' short jobs (git) sometimes slowed one worker by 10–25 %, so the CPU per text (median over the
workers) is the steadier number at 8 processes.

### 1. Roofline

FLOPs per pass, batch 1, all 12 layers (`taskset -c 2 $V roofline.py flops`); the formula and
`torch.utils.flop_counter` on the Hugging Face model agree to the digit (26.575 GFLOP at 512, 5.738 at 128):

| Part | 512 tokens | share | 128 tokens |
|---|---|---|---|
| QKV projection 2·T·384·1152 | 5.436 GFLOP | 20.2 % | 1.359 |
| scores Q·Kᵀ 2·T²·384 | 2.416 | 9.0 % | 0.151 |
| A·V 2·T²·384 | 2.416 | 9.0 % | 0.151 |
| output projection 2·T·384² | 1.812 | 6.7 % | 0.453 |
| FFN up / down 2·T·384·1536 each | 7.248 + 7.248 | 54 % | 1.812 + 1.812 |
| softmax, GELU, LayerNorm (element-wise, rough) | 0.31 | 1.2 % | 0.04 |

sgemm rate on one core (`taskset -c 2 $V roofline.py gemm`, numpy 2.5.4 with OpenBLAS 0.3.34): 98–100 GFLOP/s
at 2048³ and 4096³ and at the model's shapes (512×384×1152: 99, 512×1536×384: 97); 78–81 for one head's
512×32×512 and 512×512×32; 80 for a 32-token tile. Zen 2 peak: 2 FMA pipes × 8 floats × 2 = 32 FLOP/cycle,
at 3.2–3.7 GHz 102–118 GFLOP/s. (The VM's cycle counter reads 2.4 GHz during sgemm, which would mean
42 FLOP/cycle: it is not trustworthy here; instructions are.)

ONNX Runtime per operator (`taskset -c 2 $V roofline.py ort T B [MODEL]`), float32 file:

| T × B | ms per run | per text | MatMul | Attention (QKV+scores+AV+softmax) | FastGelu | SkipLayerNorm | overall |
|---|---|---|---|---|---|---|---|
| 512 × 1 | 308 | 308 | 154 ms, 106 GFLOP/s | 138 ms, 74 GFLOP/s | 8.6 | 5.6 | 86 GFLOP/s |
| 512 × 4 | 1319 | 330 | 106 GFLOP/s | 64 GFLOP/s | | | |
| 512 × 32 | 11913 | 372 | 6242 ms, 84 GFLOP/s | 5164 ms, 64 GFLOP/s | 295 | 184 | 71 GFLOP/s |
| 128 × 1 | 65 | 65 | 98 GFLOP/s | 87 GFLOP/s | | | 88 GFLOP/s |
| 128 × 4 | 243 | 61 | 107 GFLOP/s | 88 GFLOP/s | | | 94 GFLOP/s |

`mha-nomask.onnx` (section 4) at 512 × 1: 294.5 ms; MultiHeadAttention 72.8 ms for scores, softmax and A·V
(66 GFLOP/s) where the Attention operator spends about 87 ms on them (138 ms less 51 ms for its QKV
projection at MatMul speed); MatMul (now with Q, K, V) 206 ms at 105.6 GFLOP/s.

The upstream float16-stored file: 322 ms at 512 × 1, 403 ms per text at 512 × 32 (its profile has the
unfused GELU and FusedMatMul of cpu-budget's profile). If every operator ran at MLAS's MatMul rate,
26.575 GFLOP / 106 GFLOP/s = 251 ms: **1.23× over 512 × 1, 1.48× over 512 × 32**; at the theoretical peak
(225 ms) 1.37× and 1.65×. The non-GEMM operators are 4.6 % of the time; the rest of the gap is Attention's
lower rate (head dim 32 gives small GEMMs, plus softmax).

Note: cpu-budget and embedding-fp32-model measured 0.54 s and 0.47 s per 512-token text in the VM; those
runs had the test deployment up (embedding-fp32-model notes load 15–30). Here, idle: 0.39 s (sub-batch 32,
`throughput.py`), 0.37 s in ONNX Runtime's own profile.

### 2. Where the cache matters, measured

Working sets at 512 tokens, float32: weights 7.1 MB per layer (133 MB in all); activations per text and
layer: hidden 0.75 MB, QKV 2.25 MB, FFN intermediate 3 MB, scores 1 MB per head (12 MB for 12 heads).
At sub-batch 32 all of these ×32: FFN intermediate 100 MB, scores 403 MB.

Counters (`sudo perf stat`; `perf_event_paranoid` stays 3, perf runs as root; `kptr_restrict` 0, unchanged).
The VM exposes the core PMU only: no L3 (`amd_l3`) or memory-controller PMU, so memory traffic is the lines
the L1 and L2 prefetchers and demand misses fill from memory, × 64 B (`scale.sh`). Per text, 512-token texts:

| | sub-batch 32 | sub-batch 1 |
|---|---|---|
| instructions | 1.7 G | 1.8 G |
| L2 demand misses (data) | 8.0 M | 7.6 M |
| L2 prefetches served by L3 / by memory | 3.8 M / 7.0 M | 10.4 M / 1.9 M |
| L1 fills from memory (demand + prefetch) | 1.3 M + 3.7 M | 0.3 M + 1.1 M |
| memory traffic | 768 MB | 218 MB |

The same at 1, 2, 4 and 8 processes within 1 %: no extra L3 or memory pressure from sharing. Aggregate at
8 processes: 770 MB × 18.8/s = 14.5 GB/s at sub-batch 32, 5.2 GB/s at sub-batch 1.

What spills at sub-batch 32: the GEMMs' M dimension is 16,384 rows, and MLAS blocks K and N but walks all
rows for each block, so A (up to 100 MB) and the accumulating C go to memory (MatMul drops from 106 to
84 GFLOP/s); and Attention writes the 403 MB score buffer (74 → 64 GFLOP/s). The flash variant at
sub-batch 32 (no score buffer) still moves 755 MB per text, so most of the traffic is the activations.

`cachegrind` was not run: valgrind is not installed and installing system packages was refused by the
session's permission check.

### 3. Toys (Rust, `toy/`)

`RUSTFLAGS="-C target-cpu=native" cargo run --release --manifest-path prototypes/search-stack/perf/cache-tiling/toy/Cargo.toml --target-dir /var/tmp/embed-research-trials/toy-target -- attn|ffn B`, pinned
with `taskset -c 2`. All variants use the same sgemm (`matrixmultiply` 0.3.11, AVX2/FMA kernel) and the same
AVX2 exp, so only the order of the work differs. Check: max abs difference against a float64 reference
(first text) and against the first variant (all texts).

Attention, 12 heads × 32, 512 tokens, per text and layer (QKV projection not included):

| | B = 1 | B = 8 | B = 8, 8 copies at once |
|---|---|---|---|
| materialised, all heads of all texts (ONNX Runtime's order) | 8.89 ms | 10.24 ms | 10.6–11.0 ms |
| materialised, 12 heads of one text at a time (12 MB) | = above | 8.54 | 8.5–9.0 |
| materialised, one head at a time (1 MB) | 8.29 | 8.35 | 8.3–8.5 |
| tiled, online softmax, best (BQ 256, BK 512) | 8.12 | 8.27 | 8.2 |
| tiled, BQ 64, BK 128 | 9.10 | | |

Differences against float64 6e-8 to 1.2e-7, between variants ≤ 1.3e-7. Parts at B = 1: Q·Kᵀ 2.82 ms,
softmax 1.99 ms, P·V 3.44 ms. Small tiles lose (more, smaller GEMM calls); the order of the materialised
version matters (−18 % per text going from all heads of 8 texts to one head), the tiling within a head
does not (a head's 1 MB of scores already lives in L2/L3).

FFN 384 → 1536 → 384 with bias and tanh-GELU, per text of 512 tokens:

| | B = 1 | B = 8 |
|---|---|---|
| unfused (sgemm, bias pass, GELU pass, sgemm) | 15.98 ms | 16.71 ms |
| bias+GELU fused into one pass | 15.91 | 16.62 |
| depth-first, token tiles 32 / 64 / 128 / 256 | 20.38 / 18.10 / 16.95 / 16.22 | 20.52 / 18.18 / 16.97 / 16.42 |
| depth-first, tiles of one text (512) | | 16.12 |

Differences against float64 1.8e-6, between variants 0. Parts at B = 1: up 7.61 ms, bias+GELU 0.67 ms,
down 7.55 ms. A whole encoder layer depth-first over token tiles was not tried: neither part gained from
token tiles, only from not batching texts.

### 4. The real model: options, all compared with the float32 file at sub-batch 32 or 1

`$V throughput.py METHOD N TEXTS ...` and `scale.sh` (adds the counters); TEXTS made with
`gen_texts.py`: `long64` (64 texts, all 512 tokens: `--n 64 --long-share 1.0 --seed 2`), `mixed300` (300,
122 long: `--n 300 --long-share 0.4`), `short1000` (1000 short: `--n 1000 --long-share 0 --seed 3`).
References: the float32 file, one process, sub-batch 32 (`--save ref/…npy`).

| Method, long64 | 1 process: texts/s, CPU per text | 8 processes: texts/s, CPU per text | vs reference |
|---|---|---|---|
| float32 file, sub-batch 32 (production) | 2.56, 391 ms | 18.83, 413 ms (repeat: 18.53, 422) | bitwise |
| float32 file, sub-batch 1 | 3.06, 327 ms | 23.79, 327 ms (repeat: 24.09, 325) | bitwise |
| optimizer `attn.onnx` (same operators, from BAAI's ONNX), sub-batch 1 | 3.08, 325 ms | 21.70, 333 ms (one slow worker) | bitwise |
| optimizer `mha.onnx` (MultiHeadAttention, mask), sub-batch 1 | 3.03, 330 ms | 23.68, 333 ms | 1.5e-7, cos 1.0000000 |
| optimizer `mha-nomask.onnx` (flash attention), sub-batch 1 | 3.27, 305 ms | 25.62, 306 ms (repeat: 24.60, 308) | 1.5e-7, cos 1.0000000 |
| `mha-nomask.onnx`, sub-batch 32 (all texts 512 tokens, so unpadded) | 2.70, 370 ms | 20.04, 388 ms | 1.5e-7 |
| one process, 8 threads, float32 file, sub-batch 1 / 32 | | 14.79 / 17.72 | bitwise |
| one process, 8 threads, `mha-nomask`, sub-batch 1 | | 15.06 | 1.5e-7 |
| PyTorch 2.15 SDPA, tanh GELU, sub-batch 1 | 2.36, 422 ms | | 2.7e-7, cos 1.0000000 |
| PyTorch eager attention | 1.90, 525 ms | | 3.6e-7 |
| int8 dynamic (QInt8 weights): **changes results** | 3.07, 326 ms | 23.92, 328 ms | 4.1e-2, **min cos 0.9737** |

Mixed and short texts, 8 processes: CPU per text (median over workers) and texts/s, first run / repeat
45 minutes later (the machine busier); float32 file unless named; all bitwise equal to the reference
except `mha-nomask` (2.1e-7 and 2.4e-7, min cosine 1.0000000):

| Sub-batch rule | mixed300 | short1000 |
|---|---|---|
| 32 texts (production) | 206 / 209 ms; 38.1 / 32.6 per s (1 process: 197 ms, 5.08/s) | 27 / 27 ms; 292 / 291 per s (1 process: 37.7/s) |
| 1 text | 151 / 154 ms; 52.3 / 42.9 (1 process: 148 ms, 6.76/s) | 30 / 30 ms; 258 / 243 (1 process: 37.0/s) |
| 32 texts and ≤ 512 padded tokens | 155 / 153 ms; 38.0 / 47.5 | 26 / 27 ms; 267 / 277 |
| … ≤ 1024 / 2048 / 4096 / 8192 | 162 / 162 / 167 / 182 ms; 45.8 / 48.4 / 47.2 / 42.9 | 26 / 27 / – / – ms; 263 / 292 |
| `mha-nomask.onnx`, 1 text | 142 ms; 55.1 | 30 ms; 252 |

A cap of padded tokens per sub-batch (`common.sub_batches`) is the general form of "one long text at a time":
at 512 it puts each long text alone and batches short ones; at 1 process on mixed300 the caps 2048 / 4096 / 8192 gave 160 / 164 / 176 ms against 197 at sub-batch 32.

Commands: `REF=… [TOKENS=…] scale.sh ort:…/model_optimized.onnx mixed300.jsonl 32|1 1 8` (and `short1000`,
`long64`; `ort:…/variants/NAME.onnx` for the variants); threads: `$V throughput.py ort:… 1 long64.jsonl
--threads 8 --sub-batch 1|32 --ref …`; PyTorch: `$V throughput.py torch-sdpa|torch-eager 1 long64.jsonl
--sub-batch 1 --cpus 2 --ref …`. Raw outputs: `/var/tmp/embed-research-trials/results-*.txt` (not committed).

The optimizer reproduces the production graph from BAAI's own `onnx/model.onnx`, whose weights are bitwise
the pinned file's (`ort_variants.py` checks it); `--use_multi_head_attention` splits QKV into three MatMuls
and `disable_attention_mask` drops the mask input (the model then attends to padding: valid only for
unpadded sub-batches).

## What would be needed for 5–10×

In float32 on this core the ceiling is about 1.7× over production's setting; the measured best at all cores is
1.31–1.36× on 512-token texts and 1.44× on mixed texts (`mha-nomask`, sub-batch 1). Beyond that the FLOPs must shrink or get cheaper, and each option
changes results or hardware: shorter inputs (256 tokens ≈ 2.2× less work, 128 ≈ 4.6×), a smaller or
distilled model (6 layers ≈ 2×), int8 with VNNI (Zen 4, Ice Lake and later) or AMX, a GPU, or bfloat16 on
CPUs that have it. Each needs a retrieval-quality check, not only a cosine.

## Open

- In production the sub-batch rule is patch 0002's (fastembed, 32 texts). A cap of padded tokens there, and
  `mha-nomask` for single long texts, would need the transform worker's own measurement (`perf/batch-memory.py`).
- `torch.compile` (needs `g++` in the VM), cachegrind (valgrind), likwid: not installed, see below.
- int8 on this CPU gave no speed; whether int8 with VNNI or a shorter context keeps retrieval quality is a
  separate question (it changes results).
- A hand-written fused encoder layer (Rust) was not pursued: the roofline leaves at most 1.23× over one
  text at a time, and ONNX Runtime's flash path already takes 4 % of it.

## Packages and environment

Scratch venv (`uv venv --python 3.13`): numpy 2.5.4 (scipy-openblas 0.3.34), onnx 1.23.2, onnxruntime 1.24.4
(production's), torch 2.15.0+cpu (MKL, oneDNN 3.13.3), transformers 5.23.0, tokenizers 0.23.3,
huggingface-hub 2.4.0; numba 0.68.1 and sympy 1.14.0 installed, not used. Rust 1.99.1, crate
`matrixmultiply` 0.3.11 (the toy's only dependency, new to the repository, prototype only). Models from
Hugging Face into the scratch folder: `qdrant/bge-small-en-v1.5-onnx-q` at fp32.py's revision (hash
checked), `BAAI/bge-small-en-v1.5` (`model.safetensors`, `onnx/model.onnx`).

Not done: `torch.compile` (Inductor needs `g++`, absent; installing it was refused by the permission check),
cachegrind and likwid (same), L3 and memory-controller counters (not exposed in the VM).
