# Proposal

## Why

Indexing is the slow stage of the search stack (finding F7 in `design/field-tests/search-stack-staging-findings.md`). Since patches 0001 to 0003 removed the validator's cost and the oversubscription (F16), its time goes into the embedding: ONNX Runtime is 91 % of a batch's CPU on the VM, a text of 512 tokens costs about 530 ms of CPU (change `cpu-budget`, design.md; summarised in `perf/grace-embedding/README.md`). A full re-index of staging's 1,451,848 records takes 8 to 9 h at run 3's good rate, up to 27 h at its slow one (staging runbook, "Owners' names"). The grace benchmark (`prototypes/search-stack/perf/grace-embedding/`, 2026-11-13) embedded short texts on grace's GPU at 50,059 texts/s (quick run, 2 workers × batch 256), with vectors within a minimum cosine of 0.999989 of production's. **Decision (@weber, item 346, 2026-11-13): option A.** The warehouse's embedding moves to a service on grace; the warehouse calls it, and nothing else of the stack moves. First a prototype behind an SSH tunnel, a real network connection later.

The warehouse can already do this: with `EMBED_API_KEY` and `EMBED_API_URL` set, it posts `{model, input}` in OpenAI's format to `{EMBED_API_URL}/embeddings` and falls back to local embedding on failure (`metadata-warehouse/src/utils/embedding_utils.py:96-167,200-216`, `src/transform/transform_core.py:43-44,238-239`). One thing stops us from switching it on: the remote path cuts every text to its first 1,000 characters (`embedding_utils.py:104,127`), while the local path cuts at the model's 512 tokens. Long records would get other vectors than they get today.

## What Changes

- **An embedding service on grace** (`prototypes/search-stack/embedding-service/`): a small HTTP service of our own around fastembed-gpu on ONNX Runtime's CUDA provider, as benchmarked. It answers OpenAI's `POST /v1/embeddings` for `bge-small-en-v1.5`, truncates at 512 tokens with the same tokenizer as the local path, and refuses requests without its token. It listens on grace's `127.0.0.1:7656` only. It runs as a systemd service in an account of its own (decided by @weber, 2026-11-13, for the prototype; Docker with the NVIDIA Container Toolkit stays an option for a permanent service, design D5), from a venv locked like the benchmark's (Python 3.12, `requirements-gpu.txt`), with a cap on its GPU memory and restart on failure. Compared with established servers (Text Embeddings Inference, Infinity, vLLM, Triton) in design D1: none runs this ONNX file on an aarch64 Hopper GPU from a published build, and agreement with the local path decides.
- **Warehouse patch `0005-embedding-service.patch`** (the next free number after `embedding-fp32-model`'s 0004): texts go to the service uncut, so the service truncates them at tokens as the local path does; a shorter request timeout, so that a service that hangs leads to the local fallback within about two minutes, not eight; the local model loaded only when it is needed. Compose passes `EMBED_API_URL` to `airflow-worker-transform` from the deployment's env file; `EMBED_API_KEY` comes from `keys.env` in `MODAMA_SECRETS_DIR`, as now.
- **The prototype's setup is `prototypes/search-stack/embedding-on-grace.md`** (on `crawler` since 7272c1d5, @weber is following it): the service on grace's `127.0.0.1:7656`; the tunnel on the staging host as `embed-tunnel.service`, `ssh -N -L 172.17.0.1:17656:127.0.0.1:7656` into the `nologin` account `embedtunnel` on grace; the containers reach it as `host.docker.internal:17656` (`extra_hosts` with `host-gateway`). The same tunnel also carries a second forward, grace's `127.0.0.1:11434` (Ollama, a chat model) to the staging host's `172.17.0.1:11434`, and the key allows both addresses; using that model for AI Mode's chat is a separate decision, not part of this change. This change checked the page's `authorized_keys` options against sshd(8) and a real `sshd`, and corrected the page (design D7): `restrict` does not stop commands, and `port-forwarding` allows remote forwards too, so the key line gets `command="/usr/sbin/nologin"` and grace's `sshd_config` a `Match User embedtunnel` block with `AllowTcpForwarding local`.
- **A reusable template unit in the repository**, derived from that page and from the one instance in Git, `deploy/beatepi/etc/systemd/system/er-c-data-smb.service` (@weber, 2026-11-13: "good point to put the template there"): `deploy/ssh-tunnel/ssh-tunnel@.service` with a README (the far end's account with a `nologin` shell, the key and its restrictions, install, enable, logs). To be checked against the version @weber runs elsewhere, once he sends it.
- **A check instrument** (`embedding-service/check.py`): it sends fixed short, mixed, long and over-length texts to the service, compares the vectors with local fastembed and measures texts/s and bytes at a given concurrency. It runs inside the transform worker's image on staging, and in the tests.
- **Fallbacks made visible:** `field-test/batch-times.sh` gets a column saying which batches were embedded by the service and which fell back, from upstream's own log lines (`embedding_utils.py:213,215`).
- **A prototype measurement on staging, the decisive one:** the benchmark compared grace's CPU with its GPU, while staging and production run on an AMD EPYC (@weber, 2026-11-13). So staging's real indexing throughput before and after the switch decides: records/s, wall time and CPU seconds per batch, the time of each transform step, so that it shows which step sets the pace once the embedding no longer takes about 91 % of the CPU (normalising, validating, the OpenSearch and database writes), and the vectors of a sample of real records from both paths.

Behaviour towards the user:
- **Searchers:** none they can see. New and changed records get vectors from grace's GPU, within the agreement bound of design D4 of the local path's. Records indexed before keep theirs. Searching is unchanged; the search API keeps embedding queries locally.
- **Operators:**
  - Indexing should take less CPU on staging and less time per batch (to be measured, design D7).
  - A grace outage makes indexing slow, not broken: batches fall back to local embedding, and `batch-times.sh` shows how many did.
  - The way back: an empty `EMBED_API_URL` in the env file and `docker compose up -d airflow-worker-transform`.
- **People on grace:** the service holds part of the GPU's memory while it runs and uses the GPU during indexing. It shows in `nvidia-smi` and `nvtop` under its own account.
- **Unchanged:** the crawler, the harvest, the search API, the index's schema.

Out of scope:
- The search API's query embedding on grace (design D10 says what it would need).
- Moving any other part of the stack to grace (item 346).
- A real network connection instead of the tunnel; production (`deploy/`).
- Larger transform batches, or more batch processes now that the CPU is freed (a follow-up of the measurement, CPU budget).
- Converting `deploy/beatepi`'s unit to the template.

Serves:
- requirements-pipeline 2.4 (operating conditions: indexing on the machines at hand) and 2.6 (performance);
- requirements-pipeline 2.9 (records stay inside the institute: grace is ER-C's);
- staging findings F7 and F16 (indexing time);
- @weber, item 346, and his remarks on the tunnel template, the far end's account and running on grace (2026-11-13).

## Capabilities

### New Capabilities
- `embedding-service`: the service on grace that embeds the warehouse's texts, what it accepts and answers, how far its vectors may be from the local path's, how it is protected and how it shares the GPU, and what the warehouse does when it is unreachable. Like `cpu-budget` and `embedding-model`, it lives here because the search stack has no OpenSpec of its own.
- `ssh-tunnel`: the reusable systemd template for SSH tunnels: its forwards per instance, restart after failure, a key that opens nothing but its forwards, on an account that has no shell.

### Modified Capabilities
None.

## Impact

- New: `prototypes/search-stack/embedding-service/` (`server.py`, `check.py`, `requirements-gpu.in` and its lock file, `modama-embed.service`, `README.md`, tests).
- New: `deploy/ssh-tunnel/` (`ssh-tunnel@.service`, `README.md`).
- New: `prototypes/search-stack/patches/warehouse/0005-embedding-service.patch`.
- Changed: `prototypes/search-stack/docker-compose.yml` (`airflow-worker-transform`: `EMBED_API_URL` from the env file, `host.docker.internal` as `host-gateway`), `field-test/batch-times.sh`, `README.md` ("Measurements", a section on the service), the staging runbook (the switch and the measurement), `python/crawler/BACKLOG.md`.
- Changed: `prototypes/search-stack/embedding-on-grace.md` (the key line and the `Match` block, checked; done in this change).
- On grace (by @weber or grace's admins): the service's account, its systemd unit and its token file outside the repository; the tunnel's account per the setup page, and the `Match` block in `sshd_config`.
- On staging (by @weber): the tunnel per the setup page. Staging's `MODAMA_SECRETS_DIR` points at the committed throwaway `testconf/secrets` today (staging runbook, settings), so the token must not go there: staging first gets a secrets folder outside the checkout, a copy of `testconf/secrets` as for the end-to-end test (stack README, "Secrets for the end-to-end test"), and the token goes into its `keys.env` (design D11).
- **New dependencies, on grace only (flagged):** FastAPI and uvicorn for the service's HTTP side; their versions are pinned at implementation, at a release at least two weeks old, looked up then (on 2026-11-13: fastapi 0.162.5 of 2026-11-11, MIT; uvicorn 0.54.0 of 2026-09-25, BSD-3-Clause). The upstream warehouse and search API use FastAPI already. fastembed-gpu 0.8.0 and onnxruntime-gpu 1.31.1 are the benchmark's, locked with hashes. No new dependency in the stack's images.
