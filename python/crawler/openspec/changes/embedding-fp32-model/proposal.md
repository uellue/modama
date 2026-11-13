# Proposal

## Why

Indexing is the slow stage of the search stack on staging: run 3's re-index embedded 1,451,848 records in 726 batches, 8 to 9 h at its good rate and up to 27 h at its slow one (`design/field-tests/search-stack-staging-runbook.md`, "Owners' names"), and nearly all of a batch's CPU goes into ONNX Runtime (99.7 % of a transform batch of long texts, change `cpu-budget`, design.md, "Profile of one batch on long texts (249)"). The model file fastembed loads stores its weights in float16, and on the CPU ONNX Runtime converts 53 of them to float32 on every run (same section). The same graph stored once in float32 skips that conversion. A quick run on the VM measured 14 to 18 % less CPU per text on short texts and a minimum cosine of 0.9999997 to production's vectors (design.md here, "Evidence", E4). @weber (item 283, 2026-11-13): "faster is better, unless there are distinct disadvantages. Indexing time is a huge [issue] upstream and also slowing us down here."

## What Changes

- **A float32 model file in the warehouse's Airflow image**, made once at image build from the pinned upstream file (`qdrant/bge-small-en-v1.5-onnx-q`, `model_optimized.onnx`, pinned by revision and checked by SHA-256). The build stops if the downloaded file or fastembed's description of the model no longer matches the pin. The weights go into a separate external-data file, which ONNX Runtime maps into memory, so that the batch processes share its pages.
- **A check at image build** embeds a fixed set of short, mixed and long texts with both files, in the image's own transform venv, and stops the build if the vectors differ by more than the agreed bound (design D4; open question Q2 sets the bound).
- **Patch `0004-embedding-model-file.patch`** in `prototypes/search-stack/patches/warehouse/`, beside 0001 to 0003 and with their conventions: `TextEmbedding` gets `specific_model_path` from `EMBEDDING_MODEL_PATH`; if that is unset or empty, fastembed loads its own download as before. The image sets the variable to the float32 file's folder. The worker's start line names the file it loads.
- **Measurements before acceptance**: on the VM, and then on staging with @weber running the commands, the same batch embedded with each file. CPU seconds per record for short, mixed (staging's own records) and long texts; memory per batch process (peak, PSS, USS) at 8 and 16 processes; vector agreement (bitwise count, maximum absolute difference, cosine). The `cpu-budget` instruments (`perf/batch-memory.py`, `perf/wrap/`) are used for this, with small extensions: a fixed sample of staging's events, PSS and USS, and the largest absolute difference (design D6).

Behaviour towards the user: the vectors stored for new and changed records come from the float32 file. They agree with the float16 file's to within the bound of Q2, and searchers should see the same results. The e2e test and the vector check are what show this. Indexing takes less CPU per record; how much on staging's records is to be measured. Operators get an Airflow image about 133 MB larger, one more line in the transform worker's start log, and one variable (`EMBEDDING_MODEL_PATH`); setting it empty brings back today's file without a rebuild. A build fails, with a message, when the upstream file or fastembed's model description has moved. Nothing changes for the crawler, the harvest or the search API.

Out of scope: the search API's query embedding (its own fastembed 0.7.4 and ONNX Runtime 1.23.2, one query at a time; a possible follow-up, Q6); fusing the GELU or other graph optimisation of our own (research note, ranked change 6; only if the float32 file's profile shows it is still unfused); int8 or any change of the model that changes the vectors on purpose; the GPU and aarch64 (the grace benchmark, `perf/grace-embedding/`); turning ONNX Runtime's weight pre-packing off (Q4).

Serves: requirements-pipeline 2.4 (CPU budget: indexing on the machine at hand) and the staging findings F16 and F17 (indexing time); @weber, item 283.

## Capabilities

### New Capabilities
- `embedding-model`: which model file the warehouse's indexing embeds with, how that file is made and checked at image build, how the vectors it gives must agree with the upstream file's, and how an operator goes back to the upstream file. Like `cpu-budget`, it lives here because the search stack has no OpenSpec of its own.

### Modified Capabilities
None.

## Impact

- `prototypes/search-stack/warehouse-airflow.Dockerfile`: a build stage that downloads, checks, converts and compares the file; the final image copies only the float32 folder (about 133 MB plus the tokenizer files) and sets `EMBEDDING_MODEL_PATH`.
- `prototypes/search-stack/patches/warehouse/0004-embedding-model-file.patch` (new).
- A conversion and check script of the stack (design D2), from `perf/grace-embedding/prepare_model.py`'s `to_fp32`.
- `perf/batch-memory.py`: a fixed sample of staging's events (design D6).
- `prototypes/search-stack/README.md` ("CPU budget", "Upgrade", "Measurements"), the staging runbook (the measurement's commands), `python/crawler/BACKLOG.md`, and a decision-log row in `design/architecture.md` once accepted.
- **New build dependency: `onnx`** (1.23.2, the version `perf/grace-embedding/requirements-cpu.txt` pins, checked on PyPI on 2026-11-13; to be looked up again at implementation). It is used only in a discarded build stage, so it is not in the running image. No new runtime dependency.
