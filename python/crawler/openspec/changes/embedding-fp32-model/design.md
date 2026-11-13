# Design

## Context

See proposal.md, "Why". Current state:

- **The warehouse's Airflow image** is upstream's, built unchanged as `search-stack-airflow-upstream:3.3.2`. Our patches `patches/warehouse/0001` to `0003` are applied in a busybox stage and copied over it (`prototypes/search-stack/warehouse-airflow.Dockerfile`). Patch 0002 passes `threads` to `TextEmbedding` and embeds the texts in order of length, in sub-batches of 32.
  - Each patch starts with a header: what it does and why, with the numbers measured.
  - Then `Against metadata-warehouse v1.10.0 with … applied; applied with patch -p1 in the image build (modama search stack, warehouse-airflow.Dockerfile; change …, decision …)`.
  - Where a variable switches the patch, the header says "Unset, nothing changes".
  - The image's user is `airflow`, uid 50000, gid 0.
- **The model file** is not in the image. On first use, fastembed 0.8.0 downloads `qdrant/bge-small-en-v1.5-onnx-q` into the volume `fastembed-airflow`. On the VM that is revision `aa8f8b060edb00e03bfdd08813a2949946c8ba55`, with these SHA-256 values (read from the volume on 2026-11-13):

  | File | SHA-256 |
  |---|---|
  | `model_optimized.onnx` (66,465,124 bytes) | `51f1bd0addd6e859e42c2c8021a5e5461385bb676a649f4b269aa445449f2431` |
  | `tokenizer.json` | `d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66` |
  | `tokenizer_config.json` | `0b29c7bfc889e53b36d9dd3e686dd4300f6525110eaa98c76a5dafceb2029f53` |
  | `special_tokens_map.json` | `5d5b662e421ea9fac075174bb0688ee0d9431699900b90662acd44b2a350503a` |
  | `config.json` | `13582bcf2effc85b7bf3d3f5532e686bc1c9ce86bb009d10f0ec33cbe92299dd` |

  Staging's volume is read in task 1.1. The transform venv (Python 3.13) has fastembed 0.8.0, onnxruntime 1.24.4, tokenizers 0.22.2 and numpy 2.4.4, and no `onnx`.
- **The graph.** Read with onnx 1.23.2 (`/var/tmp/fp32-model/graph_facts.py`, 2026-11-13):
  - IR 6, opsets `''` 11 and `com.microsoft` 1, producer `onnxruntime.transformers` 1.16.3;
  - 12 Attention, 12 FastGelu, 24 SkipLayerNormalization and 36 MatMul nodes, all with float16 inputs, and 149 float16 initializers;
  - the output `last_hidden_state` is float.

  It is a graph optimised for float16. ONNX Runtime's CPU provider has no float16 kernels for these operators, so it casts the activations around them on every run (E1).
- **fastembed can load a local folder.** `TextEmbedding(..., specific_model_path=<dir>)` keeps the registered description of `BAAI/bge-small-en-v1.5` (its model file name, pooling and normalisation) and loads from the folder, tokenizer files included, without downloading (`fastembed/common/model_management.py:400-404`, `fastembed/text/onnx_embedding.py:209,251`, in the image).
- **The query side.** The search API embeds each query with its own fastembed 0.7.4 and onnxruntime 1.23.2, from its own download of the same model (change `cpu-budget`, design.md, "Search API"). With the production file, its vectors and the warehouse's are bitwise identical (E6).
- **The index** stores the vectors in OpenSearch's HNSW (lucene) with `encoder: sq`, scalar quantisation (`metadata-warehouse/config/opensearch_mapping.json`).
- **The service `transform`** (the warehouse's API) also sets `EMBEDDING_MODEL`. Whether it embeds anything on the indexing path was not checked. This change touches only the Airflow image's transform batches.

## Evidence

- **E1. Where the time goes** (change `cpu-budget`, design.md, "Profile of one batch on long texts (249)", corrected by the review of a8dc31d9). Each run of the production file has 53 Casts. Per the review's ONNX Runtime profile of 8 texts × 512 tokens, they act on activations, not weights: 27 float16 → float and 25 float → float16 casts of [8, 512, 384] per run. Where the graph has FastGelu, the production file's profile shows Mul, Add, Tanh and FusedMatMul (11 % with the Mul/Add/Tanh). With the float32 file, FastGelu runs as one kernel and those operators are gone. The kernel time of the 8 texts fell from 4,290 to 3,739 ms (−13 %). This supersedes earlier readings:
  - `cpu-budget`'s ("casts 53 float16 tensors", "the GELU is not fused");
  - the research note's ("conversion of 53 fp16 weight tensors", "1 % Cast");
  - this change's first draft ("about 1 % on long texts").

  Task 1.4 repeated it with the built image: `perf/wrap/run.sh plain 32 500 1 0` with `ORT_PROFILE=1` and `perf/wrap/ortsum.py`, one run of 32 texts × 512 tokens each, 2026-11-13, with the VM loaded by another agent's stack (load average 15 to 30).

  | | production file (`BEFORE=1`) | float32 file |
  |---|---|---|
  | kernel time | 14.7 s | 13.3 s (−10 %) |
  | operators | Attention 39.1 %, MatMul 28.3 % (24), FusedMatMul 19.1 % (12), Mul 5.2 % (48), Add 3.2 % (38), SkipLayerNormalization 2.7 %, Tanh 1.1 % (12), Cast 0.9 % (53) | MatMul 53.0 % (36), Attention 42.4 % (12), FastGelu 2.7 % (12), SkipLayerNormalization 1.5 %, Cast 0.0 % (2) |

  The GELU runs fused as FastGelu, and the 53 Casts are down to the graph's own 2.
- **E2. Size** (`docs/research/embedding-throughput.md`, section 1): 33.4 M parameters, 133 MB in float32. Measured: the converted weight file is 132,848,640 bytes and the graph 45,749 bytes. The note's expectation of "identical numbers if only the storage changes" does not hold (E6).
- **E3. The conversion** (`perf/grace-embedding/prepare_model.py`, `to_fp32`). Every float16 initializer and Constant becomes float32, Casts to float16 now cast to float, float16 inputs and outputs become float, and `value_info` is dropped. There is no `onnx.checker` run, because LayerNormalization at opset 11 is accepted by ONNX Runtime but not by the checker. The weights go to one external file (`size_threshold=1024`). **onnx 1.23.2 writes that file with mode 0600** even under umask 0002 (reproduced on 2026-11-13: `model_optimized.onnx` 0664, `model_optimized.onnx.data` 0600). Copied as it is, the worker's user could not read it if another user owns it.
- **E4. VM quick run of the grace benchmark** (2026-11-13 06:51 UTC). It was not in the repository; its files were copied to `/var/tmp/fp32-model/vm-quick-run/` (temporary). It used 4 cores, the load was 3.5 at the start, and each case is one sample of 2 to 4 s. On synthetic short texts, at 4 × 1, CPU per text was 37.3 ms with the production file against 32.1 and 30.5 ms with the float32 file.
  - Per process at 4 × 1, short texts (peak RSS, PSS, USS): production file 351, 304 and 297 MB; float32 file 261, 217 and 205 MB; float32 file without pre-packing 259, 159 and 123 MB.
  - With pre-packing on, the mapped weights are barely shared (PSS − USS 12 MB).
- **E5. CPU per text** (review of a8dc31d9, VM, one process, T = 1, sub-batch 32, sorted, interleaved A B B A; raw files not in the repository):

  | Set | production file (ms per text) | float32 file (ms per text) | change |
  |---|---|---|---|
  | short | 33.2, 33.4 | 28.7, 28.6 | −14 % |
  | mixed | 155.2, 157.1 | 141.3, 137.9 | −10 % |
  | long (512 tokens) | 541.5, 539.1 | 475.5, 461.7 | −13 % |

  Repeats were within 3 %. Peak VmHWM at 512 tokens was 1,322 MB with the production file and 1,245 MB with the float32 file.
- **E6. Vectors and ranking** (review of a8dc31d9; raw files not in the repository).
  - **Today's spread is zero.** The production file in the search API's runtime (onnxruntime 1.23.2) against the warehouse's (1.24.4), and one text embedded alone against the same text in a sorted batch of 32: 832 of 832 vectors bitwise identical.
  - **Float32 file against production file:**
    - short: 0 of 512 identical, largest component difference 5.35e-4, minimum cosine 0.99999963;
    - long: 0 of 64 identical, 4.71e-4, 0.99999974.
    - The index's `sq` encoder moves a component by up to about 3e-3, by a rough 7-bit stand-in.
  - **Ranking.** 192 synthetic near-tie queries, each embedded alone, against 832 records:
    - float vectors, float32 file against production file: the same top-10 sets for every query, and the same order in 97 %;
    - the 7-bit stand-in alone (production against itself, quantised against not): overlap 0.970, same order 26 %;
    - both quantised, float32 file against production file: overlap 0.997.

  Task 1.3 repeated this with `embedding-model/agreement.py`, 2026-11-13, in `/var/tmp/fp32-model/venv` (fastembed 0.8.0, onnxruntime 1.24.4, as production):

  ```bash
  FASTEMBED_CACHE_DIR=/var/tmp/fp32-model/fe /var/tmp/fp32-model/venv/bin/python -B \
    prototypes/search-stack/embedding-model/agreement.py UPSTREAM FP32 /var/tmp/fp32-model/agreement
  ```

  The two folders are the test's (`/var/tmp/fp32-model/files/`, temporary); the output is in `/var/tmp/fp32-model/agreement.log`.

  | | bitwise identical | largest difference | minimum cosine |
  |---|---|---|---|
  | short, 512 texts | 0 | 5.04e-4 | 0.99999964 |
  | mixed, 512 texts | 0 | 5.75e-4 | 0.99999964 |
  | long, 64 texts | 0 | 4.76e-4 | 0.99999974 |

  Ranking: 192 short queries (`gen_texts.py`, seed 5), each embedded alone, against 832 mixed records (seed 4), top 10 by cosine. The 7-bit stand-in quantises with one step for all components, (max − min) / 127 over the corpus: 6.6e-3, rougher than the review's.
  - (a) float32 file against production file, float vectors: overlap 0.998, same order 93 %;
  - (b) production file, quantised against not: overlap 0.968, same order 28 %;
  - (c) both quantised, float32 file against production file: overlap 0.993, same order 75 %.

  So the change of file moves results less than the index's own quantisation does.

## Goals / Non-Goals

**Goals:**
- less CPU per indexed record on the x86 staging and production host;
- vectors within a stated cosine of the upstream file's;
- a guard against drift and against the wrong folder;
- a way back without a rebuild.

**Non-Goals:**
- changing the vectors on purpose (int8, another model);
- graph optimisation beyond the change of storage type;
- the search API;
- the GPU and aarch64.

## Decisions

**D1. The conversion happens at image build, from pinned upstream files.** A build stage `FROM search-stack-airflow-upstream:3.3.2 AS model` does the following:
- It fetches the five files of the table above with `ADD --checksum=sha256:<pin> https://huggingface.co/qdrant/bge-small-en-v1.5-onnx-q/resolve/aa8f8b060edb00e03bfdd08813a2949946c8ba55/<file>`. BuildKit checks each hash, and no download code of our own is needed. Docker on the VM is 26.1.5; task 2.1 confirms its Dockerfile frontend accepts `--checksum` for HTTP sources.
- A throwaway venv in the stage gets `onnx==1.23.2` and converts the graph (D2). The script writes the marker (D3) and sets every file to mode 0644 (E3).
- The transform venv runs the check (D4).

The final stage copies the folder from the check's output to `/opt/modama/models/bge-small-en-v1.5-fp32/`, so BuildKit cannot skip the check, which it would for a stage nobody depends on. It sets `ENV EMBEDDING_MODEL_PATH` to the folder. Then a `RUN`, as the image's user (uid 50000), opens the graph in an ONNX Runtime session: this is the scenario "The worker's user reads the files". The check runs whenever the stage's cache is invalidated: on a change of a pin, the script, the upstream image or the stage.

Alternatives:
- Convert at the worker's start: needs `onnx` in the running image, and the batch processes would race for the file.
- Commit the converted file: 133 MB in git.
- A model image or volume of its own: one more artifact to version, for one consumer.
- One file without external data (it fits under protobuf's 2 GB): avoids the separate file's mode, but ONNX Runtime then reads the weights rather than mapping them, and E4's memory numbers are for external data. Not taken unless task 3.3 shows that the mapping gains nothing.
- Making the CPU provider run the float16 graph without the casts: it has no float16 kernels for these operators, and no session option changes that. The float32 file is the route.

**D2. The conversion is `prepare_model.py`'s `to_fp32`, as a script of the stack.** It goes in `prototypes/search-stack/embedding-model/fp32.py`, with the commands `convert` (E3, the marker, the modes) and `check` (D4). Its test is `test_fp32.py` next to it, run with pytest in `/var/tmp/fp32-model/venv`. That venv is made from `perf/grace-embedding/requirements-cpu.in` (production's fastembed 0.8.0, onnxruntime 1.24.4, tokenizers and numpy, plus onnx 1.23.2) and pytest. Not from the `.txt` lock next to it, which is compiled for aarch64. The crawler's pytest has neither onnx nor ONNX Runtime. The test fetches the pinned graph from the Hub. Without the network it fails and says so (AGENTS.md, "Fail, don't skip"). `prepare_model.py` stays as it is, so that the grace folder remains a self-contained copy; `test_fp32.py` compares both outputs for the same input by SHA-256 (task 1.2).

As built:
- The build stage installs onnx from a hash lock of its own, `embedding-model/requirements-onnx.txt` (onnx 1.23.2, numpy 2.4.4, protobuf, ml-dtypes, typing-extensions; compiled for x86_64 and Python 3.13, the image's). It makes the check's texts with `gen_texts.py` from the named build context `texts` (`perf/grace-embedding/`).
- `check` takes the sets as `NAME=FILE` arguments.
- `embedding-model/agreement.py` runs the full sets and the ranking test of E6 by hand (task 1.3).

**D3. The warehouse loads the file through fastembed (patch 0004).** `0004-embedding-model-file.patch` does three things:
- It adds `specific_model_path=os.environ.get('EMBEDDING_MODEL_PATH') or None` to the `TextEmbedding` call that 0002 shaped.
- When the path is set, it first reads the folder's marker, `modama-model.json`. The marker names the model, the source repository, the revision, each upstream file's SHA-256 and the onnx version. The patch raises an error naming both models if the marker's model is not `EMBEDDING_MODEL` (review S3; scenario "Another model configured").
- It names the folder, or "fastembed's download", in the existing log line `Setting up embedding transformer with model …` (requirements-pipeline 2.4, "The operator stays in control").

The header follows 0002's form, with E5's numbers, "Unset or empty, nothing changes", and "Against metadata-warehouse v1.10.0 with 0001 to 0003 applied; … change embedding-fp32-model, decision 283".

**Order with `embedding-service-grace`'s 0005.** That patch reached `crawler` first (f61a3ec4). It was written against 0001 to 0003 and adds `lazy_load=True` to the same `TextEmbedding` call. Its header expected 0004 to come before it, and the service's README, `server.py` and that change's proposal all name this patch 0004.

So the smallest change keeps both numbers. 0004 stays as it is, and only 0005's first hunk is regenerated against 0001 to 0004: `lazy_load=True,` becomes a line after `specific_model_path=model_path,`. Its header now says "with 0001 to 0004 applied"; its `embedding_utils.py` hunks are unchanged.

Renumbering this patch to 0006 would have left those references wrong. With lazy loading, the marker check stays eager, at the start of the batch, and fastembed keeps `specific_model_path` for the deferred load.

Alternatives:
- `TextEmbedding.add_custom_model`: it needs a new model name and a download source, and a local file still needs `specific_model_path`.
- ONNX Runtime directly: our own tokenisation, pooling and normalisation in place of fastembed's. That is code of our own where the library already does it, and the review's cosine of 0.9999996 shows that fastembed's pre- and post-processing are the same either way.

**D4. "Agree", made precise.** The vectors cannot be bitwise identical: the float32 file runs other kernels (E1), and 0 of 576 vectors were identical (E6). Today's spread between runtimes and batch compositions is zero, so it cannot serve as the bound. The bound is set against what matters downstream.
- **The build's criterion:** every pair's cosine at least 0.99999, computed in float64. The measured minimum is 0.99999963, so the bound leaves a margin of about 27 times in 1 − cosine. That margin covers a build host whose instruction set differs from staging's: ONNX Runtime picks its kernels by CPU, for example AVX-512 against staging's AVX2. The int8 file (0.9647) fails it. The grace benchmark's 0.9999 is looser.
- **Reported, not gated:** the bitwise-identical count, and the largest component difference against the index's `sq` step of about 3e-3 (E6).
- **The build's texts:** 32 to 64 per set (short, mixed, long; `gen_texts.py` with a fixed seed), so that the check costs tens of seconds. The full sets (512 short, 512 mixed, 64 long) and the ranking test of E6 run once, in task 1.3.
- **Re-index (Q3, decided: none):** @weber, 343, 2026-11-13: "Doesn't matter I think, just shifts search results around a bit. Not an exact science anyways". E6's ranking result supports this: the change moves results less than `sq` does. Records indexed before keep the production file's vectors, and the next full re-index, done for whatever reason, brings every record onto the float32 file.

**D5. The disadvantages, weighed.**

| What | Known | Still to measure |
|---|---|---|
| Disk | The folder is 128 MB (`du -sh`; the weight file 132,848,640 bytes). The image grew from 2.82 to 2.96 GB (`docker images`, task 2.3). The float16 file stays in the volume, unused by the batches. Staging's disk is watched (`monitor.sh`). | — |
| RAM per batch process | Lower: USS 205 against 297 MB at 4 × 1 on short texts (E4); peak at 512 tokens 1,245 against 1,322 MB (E5). The CPU budget's 1.6 GiB stays (Q8). | 8 processes on the VM (task 3.3), 16 on staging (task 4.2) |
| Build time | One more stage, measured on the VM on 2026-11-13 under load from another agent's stack (load average about 11). On a clean cache: fetching the five files 1.6 s, then onnx venv, conversion and check 83.8 s (the conversion is done after about 3 s), and opening the file as uid 50000 0.9 s. The whole image took 1 min 28 s. With the stage cached, the build takes 2 s. | — |
| A new build dependency, **`onnx` 1.23.2** | The current PyPI release, licence Apache-2.0 (PyPI's `license_expression`, read on 2026-11-13). Only in the discarded stage and in the script's test venv. | — |
| Drift from upstream | Pins on all five files: a changed tokenizer changes vectors too. A changed fastembed description stops the build (spec). The marker stops a batch under another `EMBEDDING_MODEL`. The search API still downloads unpinned at its first start, as today. | The README's "Upgrade" gets the steps for a stopped build: re-pin, task 1.3 again, decide on a re-index |
| File modes | onnx writes the weight file 0600 (E3). The script sets 0644, and the build opens the file as uid 50000. | — |
| Long and mixed texts | −13 % and −10 % CPU per text (E5). | Staging's own mix, task 4.2 |

None of these is a distinct disadvantage in @weber's sense (item 283). Memory and CPU go down, and the disk and the dependency are small and confined to the build.

**D6. Measurement.** The VM numbers exist (E5). The order is decided by the main session, in line with @weber's "faster is better" (283) and no re-index (343): **merge first, then measure on staging.** Staging confirms the gain rather than gating the change; on staging's own records the mix differs, and the host's CPU is not the VM's.

On a "no", the way back is `EMBEDDING_MODEL_PATH=` (empty) for `airflow-worker-transform`, with no rebuild and no revert. The measurement runs on the deployed image, which then holds both files.
- **Before and after:** the same image and the same sample. Only `EMBEDDING_MODEL_PATH` is switched: empty for before, the image's value for after.
- **Order and repeats:** cases run in the order A B B A B A, so three repeats each; the median is reported, with the spread.
- **Keep rule:** keep the float32 file if the mixed set's gain is at least 5 % and more than twice the spread.
  - The gain is the median CPU per record of A minus that of B, as a share of A's.
  - The spread is max − min of the three repeats, taken per file; the larger of the two counts.
- **Instruments:** `cpu-budget`'s `perf/batch-memory.py`, `perf/wrap/run.sh`, `cpu.py`, `embcmp.py` and `lengths.py`. Gaps found while planning (AGENTS.md, "Own instruments first"):
  - `batch-memory.py` loads every closed harvest run's events before it picks N; on staging that is 1.45 M records. It gets an opt-in fixed sample, `SAMPLE=1`: N non-deleted events ordered by `md5` of their event id (representative and repeatable, review S7), each loaded as the DAG loads a batch. It also gets `CUT=<chars>`, which cuts each record's own text for the short set. That is simpler than a token filter, which would have to compute the texts before the transform does.
  - Its memory line gets PSS and USS from `/proc/self/smaps_rollup`.
  - `embcmp.py` gets the largest absolute difference.
  - `wrap/run.sh` gets `PROJECT` (staging's network and cache: `search-staging`), `IMAGE`, and `BEFORE=1` (`-e EMBEDDING_MODEL_PATH=`).
- **Sets:** short (`CUT=200`), mixed (the sample as it is), long (FILL 500). N = 250, T = 1, the image's sub-batch of 32.
- **On staging, @weber runs the commands**, and only while `dc exec crawler modama-chain status` shows no harvest and no indexing running. No `up`, image start or measurement container runs during either. The build waits for the same window.

**D7. The grace benchmark.** `perf/grace-embedding/` measures the float32 file on aarch64 (CPU steps F and G) and on the GPU. The CPU kernels there are different, so its numbers neither confirm nor rule out x86's. This change does not wait for it. When grace's results come, they add the same conversion's vector agreement on a second architecture. On the GPU the float16 file computes in float16; that is grace's question.

## Risks / Trade-offs

- [Staging's mix gains less than the VM's] → D6's keep rule. If it fails, `EMBEDDING_MODEL_PATH=` (empty) for `airflow-worker-transform`, without a rebuild, and BACKLOG says why. The patch and the folder stay in the image, unused, until a decision to remove them.
- [A mixed index, with old vectors from the production file and new ones from the float32 file] → E6: the change moves results less than `sq` does. No re-index (Q3, @weber, 343).
- [The query side stays on the production file] → That is the agreement D4 bounds and E6 measured (queries embedded alone, with the production file's runtime behaviour).
- [A build host with another instruction set fails the check] → The margin of D4. A failure names the set and the cosine.
- [The weight file is unreadable at run time] → The modes are set in the script, and the build opens the file as uid 50000.
- [A BuildKit cache hides a moved upstream file] → `ADD --checksum` checks at every fetch, and a changed pin invalidates the stage.

## Migration Plan

1. VM, with the main session's OK (the image tags are shared): build, tasks 3.x, then `./downtest.sh --reset && ./uptest.sh && ./runtest.sh e2e`.
2. Merge, then staging: `./upstaging.sh --build` in an idle window (D6). The next indexing's batches use the float32 file, and indexed records keep their vectors (Q3).
3. The before/after on staging's sample with the deployed image (tasks 4.2, 4.3), A with `BEFORE=1`.
4. The way back on a "no", without a rebuild: `EMBEDDING_MODEL_PATH=` (empty) for `airflow-worker-transform` in a compose file of the deployment, then `dc up -d airflow-worker-transform` in an idle window.

## Open Questions

The reviewer's answers are recorded as leans, and the tasks assume them. @weber decided Q3.

- **Q1. Load the file through fastembed or ONNX Runtime directly?** Lean, and the reviewer's answer: fastembed's `specific_model_path` (D3).
- **Q2. The bound.** Lean, and the reviewer's answer: a minimum cosine of 0.99999 (float64) gates the build, and the largest difference against `sq`'s step is reported (D4).
- **Q3. Re-index after the switch? Decided: no** (@weber, 343, 2026-11-13: "Doesn't matter I think, just shifts search results around a bit. Not an exact science anyways"). This was the main session's and the reviewer's lean too, on the basis of E6's ranking result.
- **Q4. Pre-packing off?** Lean, and the reviewer's answer: leave it on. fastembed exposes no option for it, and the saving is about 80 MB of USS per process (E4).
- **Q5. Where `EMBEDDING_MODEL_PATH` is set.** Lean, and the reviewer's answer: `ENV` in the Dockerfile, with the marker guard of D3. Compose sets it only empty, for the way back and the before-measurement.
- **Q6. The search API's query embedding too?** Lean, and the reviewer's answer: not in this change; a follow-up with its own latency measurement.
- **Q7. The fixed sample in `batch-memory.py`.** Lean, and the reviewer's answer: opt-in, ordered by a hash of the event id. As built: `SAMPLE=1`, and `CUT` in place of `MAX_TOKENS` (D6).
- **Q8. The CPU budget's 1.6 GiB per batch process.** Lean, and the reviewer's answer: keep it (peak 1,322 MB with the production file, 1,245 MB with the float32 file).
