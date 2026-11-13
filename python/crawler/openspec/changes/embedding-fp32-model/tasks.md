# Tasks

The tasks assume the leans of design.md, Q1 to Q8 (the reviewer's answers); an answer from @weber changes the tasks named with it. Q3 is decided: no re-index (@weber, 343, 2026-11-13). Image builds and stack runs on the VM wait for the main session's OK (AGENTS.md, "Parallel coding agents"). Scratch files and venvs go under `/var/tmp/fp32-model/`. On staging, @weber runs every command, and only while `dc exec crawler modama-chain status` shows no harvest and no indexing running (design D6). Every spec scenario is cited by the task that tests it.

## 1. The file and its vectors, before any image change

- [ ] 1.1 The pins (D1). The VM's are in design.md, "Context". @weber reads staging's from its volume `fastembed-airflow` (the snapshot folder and `sha256sum` of the five files, with a `dc run --rm --no-deps --entrypoint sh airflow-worker-transform -c …` command written into the runbook). Verify: staging's revision and five hashes equal the VM's, noted in design.md; if they differ, the pin is staging's and task 1.3 uses staging's files.
- [ ] 1.2 The script of D2 (`convert` with the marker and mode 0644, `check`) and `test_fp32.py`, in `/var/tmp/fp32-model/venv`, made from `perf/grace-embedding/requirements-cpu.in` (not the aarch64 lock `.txt`) plus pytest. Verify: the converted graph and weight file have the same SHA-256 as `prepare_model.py`'s output for the same input; the test checks that every file is mode 0644, that the marker names `BAAI/bge-small-en-v1.5` and the pins, and that `check` exits non-zero on `prepare_model.py`'s int8 file, naming the set and the lowest cosine (scenario "A file that changes the vectors"); `pytest prototypes/search-stack/embedding-model/` in that venv passes, and without the network it fails, saying so.
- [ ] 1.3 The full sets once (D4): 512 short, 512 mixed and 64 long texts (`gen_texts.py`, fixed seed), in throwaway containers of the existing images, with no build. Compare the float32 file against the production file in `search-stack-airflow:3.3.2`'s transform venv, and repeat E6's ranking test. Verify: design.md's E6 is replaced by these runs' numbers, with the commands and the raw files' location; every cosine is at least 0.99999. If not, stop and report.

## 2. The image and patch 0004

- [ ] 2.1 `warehouse-airflow.Dockerfile` (D1):
  - the stage with `ADD --checksum` for the five pinned files, the throwaway onnx venv, `convert` and `check` (32 to 64 texts per set);
  - the fastembed description compared with the pin;
  - the final stage copying the folder from the check's output, `ENV EMBEDDING_MODEL_PATH`, and a `RUN` as uid 50000 that opens the graph in an ONNX Runtime session.

  Verify:
  - `docker compose build airflow-worker-transform` shows the check's report per set and the session load;
  - with one pin changed (for example `tokenizer.json`'s) the build stops at fetching that file (scenario "A changed upstream file");
  - a test of the description comparison with a fake description (scenario "fastembed names another file");
  - with the script's chmod removed, the build fails at the uid 50000 load (scenario "The worker's user reads the files"), and passes again with it;
  - the Docker frontend's support for `ADD --checksum` over HTTP is noted.
- [ ] 2.2 Patch `patches/warehouse/0004-embedding-model-file.patch` (D3): `specific_model_path`, the marker check, the log line; header as 0001 to 0003. Verify:
  - the build prints `applying /patches/0004-embedding-model-file.patch`;
  - `perf/batch-memory.py` in the built image logs the image's folder (scenario "A batch in the built image");
  - with `-e EMBEDDING_MODEL_PATH=` it logs fastembed's download (scenario "Going back");
  - with `-e EMBEDDING_MODEL=BAAI/bge-base-en-v1.5` it fails before embedding, naming both models (scenario "Another model configured").
- [ ] 2.3 Build time and size (D5): the stage's time from the build log on a clean cache, and the folder's size (`du -sh` in the image). Verify: both numbers in design.md, D5.
- [ ] 2.4 Documentation. In `prototypes/search-stack/README.md`:
  - "CPU budget": the model file, `EMBEDDING_MODEL_PATH`, the marker;
  - "Upgrade": a stopped build means re-pinning, task 1.3 again, and the re-index decision;
  - "Measurements": the extended instruments and `embedding-model/`.

  Also `python/crawler/BACKLOG.md`. Verify: the README's sentences match the spec; `uvx pre-commit run --all-files` from the repo root, after `git add`.
- [ ] 2.5 Review by an agent that did not write the stage, the script and the patch (the build writes a model file on its own; AGENTS.md). Give it the code and the spec, not these conclusions. Verify: its findings verified and addressed, or listed in design.md.

## 3. Measurement on the VM

- [ ] 3.1 The instruments (D6, Q7):
  - in `perf/batch-memory.py`, an opt-in fixed sample of N non-deleted events ordered by a hash of the event id, `MAX_TOKENS`, and PSS and USS from `/proc/self/smaps_rollup` in its memory line;
  - in `perf/wrap/embcmp.py`, the largest absolute difference.

  Verify:
  - unset, `batch-memory.py 250 0 1` prints the same lines as before, plus PSS and USS;
  - the sample is the same in two runs;
  - `embcmp.py` on two bodies of the same image reports 250 identical and a difference of 0.
- [ ] 3.2 CPU per record with the built image (D6): short, mixed and long; A B B A B A; `BULK_OUT` for both files. Verify: the medians and spreads in design.md next to E5; `embcmp.py` per set, every cosine at least 0.99999.
- [ ] 3.3 Memory at 8 processes (D5, Q8): `perf/wrap/par.sh 8 1 0` and `… 8 1 500`, each file. Verify: peak, PSS and USS per process in design.md; Q8's lean holds, or the numbers go to @weber.
- [ ] 3.4 The stack: `./downtest.sh --reset && ./uptest.sh && ./runtest.sh e2e`. Verify: passed, with the number skipped; the transform worker's log names the float32 folder.

## 4. Measurement on staging, and the decision

- [ ] 4.1 The commands for @weber in `design/field-tests/search-stack-staging-runbook.md`: the idle check, the build, the measurement containers with staging's network and volume names, the sample variable, and `perf/wrap/lengths.py` on the sample. Verify: @weber's run of the idle check reads as the runbook says.
- [ ] 4.2 @weber runs 3.2's cases and 3.3's memory at 16 processes on staging's own sample, in an idle window; the agent reads the recording. Verify: the tables in design.md with staging's medians, spreads and the sample's token lengths; D6's go rule applied.
- [ ] 4.3 The decision. The numbers go to @weber with a verdict and the strongest argument against. On a yes: the decision-log row in `design/architecture.md`, then `./upstaging.sh --build` in an idle window. On a no: the branch stays unmerged and BACKLOG says why. Verify: the row or the BACKLOG entry; after the deploy, the first indexing batch's log names the float32 folder.

## Workflow follow-up

- The grace benchmark's float32 results (D7), when they come, go into design.md as information; they do not block this change.
- Archive after 4.3, with the spec `embedding-model` synced.
