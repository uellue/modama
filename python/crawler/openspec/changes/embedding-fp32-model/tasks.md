# Tasks

The tasks assume the leans of design.md's Q1 to Q8; an answer from @weber changes the tasks named with it. Image builds and stack runs on the VM wait for the main session's OK (AGENTS.md, "Parallel coding agents"). On staging @weber runs every command, and only while `dc exec crawler modama-chain status` shows no harvest and no indexing running (design D6). Every spec scenario is cited by the task that tests it.

## 1. The file and its vectors, before any image change

- [ ] 1.1 The pin (D1): the SHA-256 of `model_optimized.onnx` and the tokenizer files in the VM's volume `search-stack_fastembed-airflow`, and the Hub revision (the snapshot folder's name). @weber reads the same on staging (`dc run --rm --no-deps --entrypoint sha256sum airflow-worker-transform …`). Verify: both hosts give the same hashes, recorded in design.md, "Evidence".
- [ ] 1.2 The script of D2 (`convert`, `check`), from `perf/grace-embedding/prepare_model.py`'s `to_fp32`, in a venv under `/var/tmp/fp32-model/` with `onnx` (Q2's version looked up on PyPI first, flagged in the hand-over). Verify: the converted file's SHA-256 equals `prepare_model.py`'s output for the same input; `check` exits non-zero with the set and the largest difference on `prepare_model.py`'s int8 file (scenario "A file that changes the vectors"), in a test next to the script run with the crawler's pytest.
- [ ] 1.3 Vector agreement (D4): the three sets of 512 texts (`gen_texts.py`, fixed seed), in throwaway containers of the existing images, no build. (i) the float32 file against the production file in `search-stack-airflow:3.3.2`'s transform venv (onnxruntime 1.24.4); (ii) the production file there against the same file in the search API's image (onnxruntime 1.23.2, fastembed 0.7.4). Verify: a table in design.md with, per set and pair, the bitwise-identical count, the largest absolute difference and the minimum cosine (float64); the bound proposed to @weber (Q2) before 2.1.
- [ ] 1.4 Where the float32 file spends its time at 512 tokens (D5, the GELU question of E3): `perf/wrap/run.sh plain 250 500 1 0` with `ORT_PROFILE=1` and the float32 folder mounted, `perf/wrap/ortsum.py`. Verify: the operator table in design.md next to E1's; it says whether Mul, Add and Tanh are still there.

## 2. The image and patch 0004

- [ ] 2.1 `warehouse-airflow.Dockerfile`: the stage of D1 (download at the pinned revision, SHA-256 check, `convert`, `check` with the transform venv, fastembed's description of `EMBEDDING_MODEL` compared with the pin), the final stage copying the folder from the check's output, `ENV EMBEDDING_MODEL_PATH`. Verify: `docker compose build airflow-worker-transform` shows the hash check, the conversion and the check's report per set; with a wrong SHA-256 passed as a build argument the build stops with both hashes (scenario "A changed upstream file"); the description comparison has a test with a fake description (scenario "fastembed names another file").
- [ ] 2.2 Patch `patches/warehouse/0004-embedding-model-file.patch` (D3), header as 0001 to 0003. Verify: the build prints `applying /patches/0004-embedding-model-file.patch`; `perf/batch-memory.py` in the built image logs the image's folder (scenario "A batch in the built image") and, with `-e EMBEDDING_MODEL_PATH=`, fastembed's download (scenario "Going back").
- [ ] 2.3 Build time and size (D5): the stage's time from the build log on a clean cache and the folder's size (`du -sh` in the image). Verify: both numbers in design.md, D5; if the check takes more than a minute or two, the long set's size per Q2.
- [ ] 2.4 Documentation: `prototypes/search-stack/README.md` ("CPU budget": the model file and `EMBEDDING_MODEL_PATH`; "Upgrade": a stopped build means re-pinning, task 1.3 again and the re-index decision; "Measurements": the extended instruments), `python/crawler/BACKLOG.md`. Verify: the README's sentences match the spec; `uvx pre-commit run --all-files` from the repo root after `git add`.
- [ ] 2.5 Review by an agent that did not write the stage, the script and the patch (the build writes a model file on its own; AGENTS.md), given the code and the spec, not these conclusions. Verify: its findings verified and addressed, or listed in design.md.

## 3. Measurement on the VM

- [ ] 3.1 The instruments (D6, Q7): in `perf/batch-memory.py` an opt-in fixed sample (the first N non-deleted events of the newest closed harvest run) and `MAX_TOKENS`, PSS and USS from `/proc/self/smaps_rollup` in its memory line; in `perf/wrap/embcmp.py` the largest absolute difference. Verify: unset, `batch-memory.py 250 0 1` on the VM prints the same lines as before plus PSS and USS; `embcmp.py` on two bodies of the same image reports 250 identical and a difference of 0.
- [ ] 3.2 CPU per record (D6): short (`MAX_TOKENS=64`), mixed (FILL 0), long (FILL 500); N 250, T 1, the image's sub-batch; before (`-e EMBEDDING_MODEL_PATH=`) and after, interleaved, twice each; `BULK_OUT` for both. Verify: a table in design.md with CPU seconds per record and `transform_batch_impl`'s time per case and run; `embcmp.py` per set within the bound of Q2.
- [ ] 3.3 Memory at 8 processes (D5, Q8): `perf/wrap/par.sh 8 1 0` and `… 8 1 500`, each file. Verify: peak, PSS and USS per process in design.md; Q8's lean holds or is put to @weber.
- [ ] 3.4 The stack: `./downtest.sh --reset && ./uptest.sh && ./runtest.sh e2e`. Verify: passed, with the number skipped; the transform worker's log names the float32 folder.

## 4. Measurement on staging, and the decision

- [ ] 4.1 The commands for @weber in `design/field-tests/search-stack-staging-runbook.md`: the idle check, the build, the measurement containers with staging's network and volume names, the sample variable, `perf/wrap/lengths.py` on the sample. Verify: @weber's run of the first command (the idle check) reads as the runbook says.
- [ ] 4.2 @weber runs 3.2's cases and 3.3's memory at 16 processes on staging's own records, in an idle window; the agent reads the recording. Verify: the tables in design.md with staging's numbers and the sample's token lengths; the vector counts within the bound.
- [ ] 4.3 The decision (D6, Risks): the numbers to @weber with a verdict and the strongest argument against; on a yes, the decision-log row in `design/architecture.md` and `./upstaging.sh --build` in an idle window; on a no, the branch stays unmerged and BACKLOG says why. Verify: the row or the BACKLOG entry; after the deploy, the first indexing batch's log names the float32 folder.

## Workflow follow-up

- The grace benchmark's float32 results (D7), when they come, go into design.md as information; they do not block this change.
- Archive after 4.3, with the spec `embedding-model` synced.
