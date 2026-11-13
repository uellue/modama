# Proposal

## Why

Indexing is the slow stage of the search stack on staging. Run 3's re-index embedded 1,451,848 records in 726 batches: 8 to 9 h at its good rate, up to 27 h at its slow one (`design/field-tests/search-stack-staging-runbook.md`, "Owners' names"). Nearly all of a batch's CPU goes into ONNX Runtime (99.7 % of a transform batch of long texts; change `cpu-budget`, design.md, "Profile of one batch on long texts (249)").

The model file fastembed loads is a graph made for float16 (`onnxruntime.transformers` 1.16.3): fused Attention, FastGelu and SkipLayerNormalization nodes, typed float16. ONNX Runtime's CPU provider has no float16 kernels for these. So on every run it casts the activations between float16 and float32 around them (27 and 25 casts of [8, 512, 384] per run of 8 long texts), and runs the GELU as separate operators. The same graph stored in float32 runs these nodes as fused float32 kernels, without the casts. In the review's measurement on the VM, the kernel time of 8 texts of 512 tokens fell from 4,290 to 3,739 ms (−13 %). The CPU per text fell by 14 % on short, 10 % on mixed and 13 % on long texts (design.md, "Evidence", E4 and E5). The vectors are not identical, but close: minimum cosine 0.99999963, largest component difference 5.35e-4. That is below the index's own scalar quantisation, and the top-10 results agree (E6). @weber (item 283, 2026-11-13): "faster is better, unless there are distinct disadvantages. Indexing time is a huge [issue] upstream and also slowing us down here."

## What Changes

- **A float32 model file in the warehouse's Airflow image**, made at image build from the upstream files of `qdrant/bge-small-en-v1.5-onnx-q`, each pinned by revision and SHA-256 (the graph and the four tokenizer and configuration files). The weights go into a separate file next to the graph, readable by the worker's user. A marker file in the folder names the model it was made from.
- **A check at image build.** It embeds a few dozen fixed short, mixed and long texts with both files in the image's transform venv. It stops the build if any pair's cosine is below 0.99999, and it reports the largest component difference. It also stops the build if fastembed's description of the model no longer names the pinned source.
- **Patch `0004-embedding-model-file.patch`** in `prototypes/search-stack/patches/warehouse/`, beside 0001 to 0003 and with their conventions. `TextEmbedding` gets `specific_model_path` from `EMBEDDING_MODEL_PATH`. If the variable is unset or empty, fastembed loads its own download as before. The patch refuses to start a batch whose folder's marker names another model than `EMBEDDING_MODEL`. The image sets the variable, and the worker's start line names the file.
- **A confirming measurement on staging**, with @weber running the commands in an idle window. The same fixed sample of staging's records is embedded with each file: CPU per record for short, mixed and long texts, memory per batch process at 16 processes, and vector agreement. The `cpu-budget` instruments (`perf/batch-memory.py`, `perf/wrap/`) are used, with small extensions (design D6).

Behaviour towards the user:
- **Searchers.** New and changed records get vectors from the float32 file, within a cosine of 0.99999 of the old file's. In the review's ranking test the difference moved fewer results than the index's own quantisation does (E6). Records indexed before keep their vectors (Q3).
- **Indexing.** It takes about 10 to 14 % less CPU per record on the VM (E5); staging's share is to be confirmed.
- **Operators.**
  - The Airflow image grows by about 133 MB.
  - The transform worker's start log names the file.
  - Setting `EMBEDDING_MODEL_PATH` empty brings back today's file without a rebuild.
  - A build stops, with a message, when an upstream file or fastembed's model description has moved.
- **Unchanged.** The crawler, the harvest and the search API.

Out of scope:
- The search API's query embedding (its own fastembed 0.7.4 and ONNX Runtime 1.23.2; a possible follow-up, Q6).
- Graph optimisation beyond the change of storage type.
- int8, or any change that alters the vectors on purpose.
- The GPU and aarch64 (the grace benchmark, `perf/grace-embedding/`).
- Turning ONNX Runtime's weight pre-packing off (Q4).

Serves:
- requirements-pipeline 2.4 (CPU budget: indexing on the machine at hand);
- the staging findings F16 and F17 (indexing time);
- @weber, item 283.

## Capabilities

### New Capabilities
- `embedding-model`: which model file the warehouse's indexing embeds with, how that file is made and checked at image build, how far its vectors may move from the upstream file's, and how an operator goes back to the upstream file. Like `cpu-budget`, it lives here because the search stack has no OpenSpec of its own.

### Modified Capabilities
None.

## Impact

- `prototypes/search-stack/warehouse-airflow.Dockerfile`:
  - a build stage that fetches the pinned files with `ADD --checksum`, converts and checks;
  - the final image copies the folder with mode 0644 (133 MB of weights plus the graph, tokenizer files and marker), sets `EMBEDDING_MODEL_PATH`, and loads the file once as the image's user (uid 50000) as a test.
- `prototypes/search-stack/patches/warehouse/0004-embedding-model-file.patch` (new).
- `prototypes/search-stack/embedding-model/`: a conversion and check script derived from `perf/grace-embedding/prepare_model.py`'s `to_fp32`, and its test, run in a venv of `perf/grace-embedding/requirements-cpu.in` (design D2).
- `perf/batch-memory.py`, `perf/wrap/embcmp.py`: a hash-ordered fixed sample, `MAX_TOKENS`, PSS and USS, the largest difference (design D6).
- Documentation:
  - `prototypes/search-stack/README.md` ("CPU budget", "Upgrade", "Measurements");
  - the staging runbook (the measurement's commands);
  - `python/crawler/BACKLOG.md`;
  - a decision-log row in `design/architecture.md` once accepted.
- **New build dependency: `onnx` 1.23.2.** It is the current release on PyPI, read on 2026-11-13, with licence `Apache-2.0` (PyPI's `license_expression`), and the same version `perf/grace-embedding/requirements-cpu.in` pins. It is used only in a discarded build stage and in the script's test venv, never in the running image. No new runtime dependency.
