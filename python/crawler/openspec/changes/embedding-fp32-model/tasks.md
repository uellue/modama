# Tasks

The tasks assume the leans of design.md, Q1 to Q8 (the reviewer's answers); an answer from @weber changes the tasks named with it. Q3 is decided: no re-index (@weber, 343, 2026-11-13).

Image builds and stack runs on the VM wait for the main session's OK (AGENTS.md, "Parallel coding agents"). The image of this change was built under a tag of its own, `search-stack-airflow:3.3.2-fp32`, so that the shared tag of the stack another agent was running stayed untouched:

```bash
cd prototypes/search-stack
docker buildx build --load -f warehouse-airflow.Dockerfile --build-context budget=cpu-budget \
  --build-context embedding-model=embedding-model --build-context texts=perf/grace-embedding \
  -t search-stack-airflow:3.3.2-fp32 patches/warehouse
``` Scratch files and venvs go under `/var/tmp/fp32-model/`.

On staging, @weber runs every command, and only while `dc exec crawler modama-chain status` shows no harvest and no indexing running (design D6). Every spec scenario is cited by the task that tests it.

## 1. The file and its vectors, before any image change

- [x] 1.1 The pins (D1), the VM's: in design.md, "Context", read from the volume `search-stack_fastembed-airflow` on 2026-11-13. Staging's are task 4.1, step 1, for @weber. Verify: the table in design.md; the Dockerfile and `fp32.py` carry the same (`test_pins_match_the_dockerfile`).
- [x] 1.2 The script of D2 (`convert` with the marker and mode 0644, `check`) and `test_fp32.py`, in `/var/tmp/fp32-model/venv`, made from `perf/grace-embedding/requirements-cpu.in` (not the aarch64 lock `.txt`) plus pytest. Verify:
  - the converted graph and weight file have the same SHA-256 as `prepare_model.py`'s output for the same input;
  - the test checks that every file is mode 0644, that the marker names `BAAI/bge-small-en-v1.5` and the pins, and that `check` exits non-zero on the int8 file, naming the set and the lowest cosine (scenario "A file that changes the vectors");
  - `pytest prototypes/search-stack/embedding-model/` in that venv: 8 passed. It first failed at collection (no `fp32` module), then 3 of 8 failed until the Dockerfile and `prepare_model.py`'s new `bench` import were handled.

  Without the network, the `upstream` fixture fails with "cannot fetch … (network?)"; this path was not run.
- [x] 1.3 The full sets once (D4), with `embedding-model/agreement.py` in the test venv. That venv has production's fastembed 0.8.0 and onnxruntime 1.24.4; the image's own check gave the same numbers for the same texts. Verify: design.md's E6 has these runs' numbers next to the review's; every cosine is at least 0.99999.
- [x] 1.4 Where the float32 file spends its time at 512 tokens (E1): `perf/wrap/run.sh plain 32 500 1 0` with `ORT_PROFILE=1`, both files, and `perf/wrap/ortsum.py`. Verify: the operator table in design.md, E1. FastGelu is fused, and the Casts went from 53 to 2.

## 2. The image and patch 0004

- [x] 2.1 `warehouse-airflow.Dockerfile` (D1), with the named contexts `embedding-model` and `texts` in `docker-compose.yml`:
  - the stage with `ADD --checksum` for the five pinned files, the onnx venv from `embedding-model/requirements-onnx.txt` (hash lock), `convert`, and `check` (64 short, 64 mixed, 32 long);
  - the fastembed description compared with the marker;
  - the final stage copying the folder as root with mode 0644, `ENV EMBEDDING_MODEL_PATH`, and a `RUN` as uid 50000 that opens the graph.

  Verify:
  - the build log shows the check's report per set and `model loads as uid 50000`;
  - with `tokenizer.json`'s pin changed by one digit, the build stops at that `ADD`: `digest mismatch sha256:d241…5c66: sha256:d241…5c67` (scenario "A changed upstream file");
  - `test_check_stops_when_fastembed_names_another_file` (scenario "fastembed names another file");
  - with the script's chmod replaced by `pass`, the build fails at the uid 50000 load with `SystemError : 13` (EACCES) (scenario "The worker's user reads the files"), and passes with it;
  - `ADD --checksum` over HTTP works with Docker 26.1.5 and buildx 0.13.1, through the Hub's redirects.
- [x] 2.2 Patch `patches/warehouse/0004-embedding-model-file.patch` (D3). Verify, in the built image, with `TransformResources()` in a throwaway container (no network, `/var/tmp/fp32-model/resources.py`):
  - the build prints `applying /patches/0004-embedding-model-file.patch`;
  - default: `Setting up embedding transformer with model BAAI/bge-small-en-v1.5 from /opt/modama/models/bge-small-en-v1.5-fp32` (scenario "A batch in the built image");
  - with `-e EMBEDDING_MODEL_PATH=` and the cached download: `… from fastembed's download` (scenario "Going back");
  - with `-e EMBEDDING_MODEL=BAAI/bge-base-en-v1.5`: `ValueError: EMBEDDING_MODEL_PATH /opt/modama/models/bge-small-en-v1.5-fp32 holds BAAI/bge-small-en-v1.5, not EMBEDDING_MODEL BAAI/bge-base-en-v1.5` before any embedding (scenario "Another model configured").
- [x] 2.3 Build time and size (D5). Verify: the numbers in design.md, D5.
- [x] 2.4 Documentation:
  - `prototypes/search-stack/README.md`: a new section "The embedding model", step 6 of "Upgrade", and the "Measurements" table;
  - `python/crawler/BACKLOG.md`.

  Verify: the README's sentences match the spec; `uvx pre-commit run --all-files` from the repo root, after `git add`.
- [x] 2.5 Review by an agent that did not write the stage, the script and the patch (the build writes a model file on its own; AGENTS.md), given the code and the spec, not these conclusions. Done by the main session's reviewer on 960c8a7c: "merge after changes". It found the build deterministic (the same image ID on a rebuild), the check impossible to skip, the way back bitwise identical to the old behaviour, and the marker check failing safe. Verify: its findings verified and acted on, in 2.7.
- [x] 2.6 The order with `embedding-service-grace`'s 0005, which reached `crawler` first and edits the same `TextEmbedding` call. 0004 is kept, and 0005's first hunk is regenerated against 0001 to 0004 (design D3). Verify:
  - GNU patch 2.8 applies 0001 to 0005 in order to upstream's code from `search-stack-airflow-upstream:3.3.2`, without fuzz or offset;
  - the image build (busybox `patch`) prints `applying …0005-embedding-service.patch`;
  - in the rebuilt image, 2.2's three scenarios give the same lines, now with `lazy_load=True`. The model loads at the first embedding, with the float32 file's vector (first component −0.04266914, as before 0005);
  - the service's `tests/test_warehouse.py` and `tests/test_check.py`, which apply `patches/warehouse/` in order with GNU patch: 15 passed (its README's commands, with scratch in `/var/tmp/fp32-model/embed`).
- [x] 2.7 The code review of 960c8a7c, findings acted on:
  - M1: 0005 committed, rebuilt, and 2.2's scenarios run again (2.6);
  - M2: section 4 and D6 — merge first, the measurement confirms, and the way back is `EMBEDDING_MODEL_PATH=`;
  - S1: `perf/wrap/run.sh` takes the read-only role from `$MODAMA_SECRETS_DIR/chain.env`, and 4.2's loop shows errors;
  - S2: the spread is defined in D6;
  - the nits: `check` fails when every vector is bitwise identical (`test_check_fails_when_nothing_was_converted`, which failed first), the build checks mode 0644 itself, and the numbers in the README, 0004's header and BACKLOG match E6.

  Verify: `test_fp32.py` 9 passed; the rebuilt image; `run.sh` against the VM's stack with `MODAMA_SECRETS_DIR=testconf/secrets`.

## 3. Measurement on the VM

- [x] 3.1 The instruments (D6, Q7):
  - `perf/batch-memory.py`: `SAMPLE=1`, `CUT`, PSS and USS;
  - `perf/wrap/embcmp.py`: the largest difference;
  - `perf/wrap/run.sh`: `PROJECT`, `IMAGE`, `BEFORE`.

  Verify, on the VM's 19 records:
  - unset, the same lines as before plus PSS and USS;
  - `SAMPLE=1` loads the same 20 events (`xml 2575 chars/event`) in both runs;
  - `CUT=60` gives 19 to 25 tokens;
  - `embcmp.py` on a body against itself: `20 documents, 20 identical; … largest difference 0`;
  - before against after: `20 documents, 0 identical; cosine min 0.99999931 …; largest difference 0.000345`.
- [ ] 3.2 CPU per record with the built image (D6): short, mixed and long; A B B A B A; `BULK_OUT` for both files. Not run: the VM was loaded by another agent's stack (load average 15 to 32), so no timing from it would answer the question. Run it when the VM is free, with 4.2's loop, `PROJECT` and `ENVFILE` unset, and `IMAGE=search-stack-airflow:3.3.2-fp32 MODAMA_SECRETS_DIR=testconf/secrets`. Verify: the medians and spreads in design.md next to E5; `embcmp.py` per set, every cosine at least 0.99999.
- [ ] 3.3 Memory at 8 processes (D5, Q8): `BEFORE=1 IMAGE=search-stack-airflow:3.3.2-fp32 perf/wrap/par.sh 8 1 500`, and the same without `BEFORE`. Not run, for the same reason: it would take the whole VM from the other agent's stack. Verify: peak, PSS and USS per process in design.md; Q8's lean holds, or the numbers go to @weber.
- [ ] 3.4 The stack: `./downtest.sh --reset && ./uptest.sh && ./runtest.sh e2e`. Not run: one stack per VM, and another agent's was up. Verify: passed, with the number skipped; the transform worker's log names the float32 folder.

## 4. Staging: deploy, confirm, or go back

Order (main session's decision, in line with @weber's "faster is better", 283, and no re-index, 343): merge first, deploy, then measure. The measurement confirms the gain rather than gating the merge. On a "no", the way back is `EMBEDDING_MODEL_PATH=` (empty) for `airflow-worker-transform`, with no rebuild (design D6).

- [ ] 4.1 For @weber, after the merge: deploy. On the dev server, from `prototypes/search-stack` of the shared checkout, with the runbook's `dc` shorthand (step 12), only while nothing is harvested or indexed.

  ```bash
  # 0. only while nothing is harvested or indexed
  dc exec crawler modama-chain status

  # 1. staging's pins: the snapshot folder must be aa8f8b060edb00e03bfdd08813a2949946c8ba55,
  #    the hashes those of design.md, "Context" (a throwaway container, read-only)
  docker run --rm --network none -v search-staging_fastembed-airflow:/c:ro --entrypoint sh \
    search-stack-airflow:3.3.2 -c 'cd /c/models--qdrant--bge-small-en-v1.5-onnx-q/snapshots && ls && sha256sum */*'

  # 2. build and start; the build log has the vector check and the load as uid 50000
  ./upstaging.sh --build 2>&1 | tee ~/fp32-up.log
  grep -E 'short:|mixed:|long:|model loads|ERROR' ~/fp32-up.log
  ```

  If `upstaging.sh` prints its build quietly, `dc build airflow-worker-transform 2>&1 | grep -E 'short:|mixed:|long:|model loads'` shows the same lines; with the cache warm they show as `CACHED`.

  Verify:
  - step 0 shows no harvest and no indexing running;
  - step 1 prints the pinned revision and hashes;
  - step 2 ends with the stack up;
  - after the first indexing batch, `dc exec airflow-worker-transform grep -rh 'Setting up embedding transformer' /opt/airflow/logs | tail -1` names `/opt/modama/models/bge-small-en-v1.5-fp32`.
- [ ] 4.2 For @weber: the before/after on staging's own sample, with the deployed image, in an idle window (design D6). A is the old file (`BEFORE=1`, the same image with `EMBEDDING_MODEL_PATH=`), B the float32 file. Each set runs A B B A B A, 250 records, 1 thread; about 25 minutes, most of it the long set. The read-only role comes from staging's secrets (`ENVFILE=staging.env` → `$MODAMA_SECRETS_DIR/chain.env`). Errors and tracebacks are printed too, so a failed case shows in `~/fp32-cpu.txt` instead of leaving it empty.

  ```bash
  export PROJECT=search-staging ENVFILE=staging.env SAMPLE=1 PERF_OUT=$HOME/fp32-perf
  for set in short mixed long; do
    for run in A1 B1 B2 A2 B3 A3; do
      before=; [ "${run:0:1}" = A ] && before=1
      cut=; fill=0; [ "$set" = short ] && cut=200; [ "$set" = long ] && fill=500
      BEFORE=$before CUT=$cut TAG=$set-$run BULK_OUT=/tmp/bulk.ndjson \
        perf/wrap/run.sh plain 250 "$fill" 1 0 2>&1 \
        | grep -E '^(transformed|tokens)|Error|Traceback|run.sh:' | sed "s/^/$set $run /"
    done
  done | tee ~/fp32-cpu.txt
  for set in short mixed long; do
    python3 perf/wrap/embcmp.py "$PERF_OUT/tmp-plain-250-$([ $set = long ] && echo 500 || echo 0)-1-0-$set-A1/bulk.ndjson" \
      "$PERF_OUT/tmp-plain-250-$([ $set = long ] && echo 500 || echo 0)-1-0-$set-B1/bulk.ndjson"
  done | tee -a ~/fp32-cpu.txt
  # memory at staging's 16 processes, long texts, each file
  BEFORE=1 perf/wrap/par.sh 16 1 500 | tee ~/fp32-mem.txt
  perf/wrap/par.sh 16 1 500 | tee -a ~/fp32-mem.txt
  ```

  Paste `~/fp32-cpu.txt` and `~/fp32-mem.txt` into the chat, or point to the recording.

  Verify, by the agent:
  - every case has a `transformed` line (no `Error` or `Traceback`);
  - the CPU per record (the `cpu` of each `transformed` line ÷ 250) per set as medians and spreads in design.md, next to E5, with the sample's token lengths (the `tokens` lines);
  - every cosine at least 0.99999;
  - peak, PSS and USS at 16 processes.
- [ ] 4.3 Keep or go back (D6's keep rule). Keep if the mixed set's gain is at least 5 % and more than twice the spread. The gain is the median CPU per record of A minus B's, as a share of A's. The spread is max − min of the three repeats, per file, the larger of the two.
  - On a keep: the decision-log row in `design/architecture.md`.
  - On a no, for @weber, in an idle window, without a rebuild: `EMBEDDING_MODEL_PATH: ""` under `airflow-worker-transform`'s `environment:` in `docker-compose.staging.yml` (committed, so later `upstaging.sh` runs keep it), then `dc up -d airflow-worker-transform`. BACKLOG says why.

  Verify: the row, or the compose line and the BACKLOG entry; after a way back, the next batch's line (4.1's grep) says `from fastembed's download`.

## Workflow follow-up

- The grace benchmark's float32 results (D7), when they come, go into design.md as information; they do not block this change.
- `embedding-service-grace`'s service loads the same folder through `EMBEDDING_MODEL_PATH` and the marker once this change is merged; its patch is `0005`.
- Archive after 4.3, with the spec `embedding-model` synced.
