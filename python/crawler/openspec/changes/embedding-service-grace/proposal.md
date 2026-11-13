# Proposal

## Why

Indexing is the slow stage of the search stack (finding F7 in `design/field-tests/search-stack-staging-findings.md`). Since patches 0001 to 0003 removed the validator's cost and the oversubscription (F16), its time goes into the embedding: ONNX Runtime is 91 % of a batch's CPU on the VM, a text of 512 tokens costs about 530 ms of CPU (change `cpu-budget`, design.md; summarised in `perf/grace-embedding/README.md`). A full re-index of staging's 1,451,848 records takes 8 to 9 h at run 3's good rate, up to 27 h at its slow one (staging runbook, "Owners' names"). The grace benchmark (`prototypes/search-stack/perf/grace-embedding/`, 2026-11-13) embedded short texts on grace's GPU at 50,059 texts/s (quick run, 2 workers × batch 256), with vectors within a minimum cosine of 0.999989 of production's. **Decision (@weber, item 346, 2026-11-13): option A.** The warehouse's embedding moves to a service on grace; the warehouse calls it, and nothing else of the stack moves. First a prototype behind an SSH tunnel, a real network connection later.

The warehouse can already do this: with `EMBED_API_KEY` and `EMBED_API_URL` set, it posts `{model, input}` in OpenAI's format to `{EMBED_API_URL}/embeddings` and falls back to local embedding on failure (`metadata-warehouse/src/utils/embedding_utils.py:96-167,200-216`, `src/transform/transform_core.py:43-44,238-239`). Two things stop us from switching it on:
- the remote path cuts every text to its first 1,000 characters (`embedding_utils.py:104,127`), while the local path cuts at the model's 512 tokens, so long records would get other vectors than they get today;
- the token would leak: `search-api` reads `keys.env` too and would take `EMBED_API_KEY` as its own, and every reranked search would then send it, with the question and the hits, to EGI's default URL (design, Context; found by the review of 34717466).

## What Changes

- **An embedding service on grace** (`prototypes/search-stack/embedding-service/`): a small HTTP service of our own around fastembed-gpu on ONNX Runtime's CUDA provider, as benchmarked, on Starlette and uvicorn. It answers OpenAI's `POST /v1/embeddings` for `bge-small-en-v1.5` with the same model file as the local path, truncates at 512 tokens with the same tokenizer, and refuses requests without its token. It listens on grace's `127.0.0.1:7656` only. It runs as a systemd service in an account of its own (decided by @weber, 2026-11-13, for the prototype; Docker with the NVIDIA Container Toolkit stays an option for a permanent service, design D5), from a venv locked like the benchmark's (Python 3.12, `requirements-gpu.txt`), with a cap on its GPU memory and restart on failure. Compared with established servers (Text Embeddings Inference, Infinity, vLLM, Triton) in design D1: none runs this model file on an aarch64 Hopper GPU from a published build, and agreement with the local path decides.
- **Warehouse patch `0005-embedding-service.patch`** (the next free number after `embedding-fp32-model`'s 0004): texts go to the service uncut, so the service truncates them at tokens as the local path does; a timeout of 30 s per wait, so that a service that hangs leads to the local fallback within about two minutes, not eight; no retry of a 400 or 401, which cannot succeed; the local model loaded only when it is needed.
- **The token only where it is used:** a secret file of its own, `embed.env` in `MODAMA_SECRETS_DIR`, read by `airflow-worker-transform` only; `search-api` gets `EMBED_API_KEY: ""` in its environment, which overrides any env file; a test checks that `search-api` never has it. Compose passes `EMBED_API_URL` to the worker from the deployment's env file.
- **The prototype's setup is `prototypes/search-stack/embedding-on-grace.md`** (on `crawler` since 7272c1d5, @weber is following it): the service on grace's `127.0.0.1:7656`; the tunnel on the staging host as `embed-tunnel.service`, `ssh -N -L 172.17.0.1:17656:127.0.0.1:7656` into the `nologin` account `embedtunnel` on grace; the containers reach it as `host.docker.internal:17656` (`extra_hosts` with `host-gateway`). The same tunnel also carries grace's `127.0.0.1:11434` (Ollama, a chat model) to the staging host's `172.17.0.1:11434`, and the key allows both addresses; using that model for AI Mode's chat is a separate decision, not part of this change. This change checked the page's `authorized_keys` options against sshd(8) and a real `sshd` and corrected the page (design D7): the key line gets `command="/usr/sbin/nologin"`; grace's `sshd_config` a `Match User embedtunnel` block with `AllowTcpForwarding local`, `AllowStreamLocalForwarding no`, `PermitOpen` for the two addresses, `PermitTTY no` and `X11Forwarding no`; the unit `-o ConnectTimeout=10`.
- **A reusable template unit in the repository**, derived from that page and from the one instance in Git, `deploy/beatepi/etc/systemd/system/er-c-data-smb.service` (@weber, 2026-11-13: "good point to put the template there"): `deploy/ssh-tunnel/ssh-tunnel@.service` with a README (the far end's account with a `nologin` shell, the key and its restrictions, install, enable, logs). To be checked against the version @weber runs elsewhere, once he sends it.
- **A check instrument** (`embedding-service/check.py`): it sends fixed short, mixed, long and over-length texts to the service, compares the vectors with local fastembed (cosine, largest component difference, a ranking check), measures texts/s and bytes at a given concurrency, and snapshots and compares stored vectors. It runs inside the transform worker's image on staging, and in the tests.
- **Fallbacks made visible:** `field-test/batch-times.sh` gets a column saying which batches were embedded by the service, which fell back and which embedded locally, from upstream's own log lines (`embedding_utils.py:213,215,218`).
- **A prototype measurement on staging, the decisive one:** the benchmark compared grace's CPU with its GPU, while staging and production run on an AMD EPYC (@weber, 2026-11-13). So staging's real indexing throughput before and after the switch decides, at staging's 2,000 records per batch: records/s, wall time and CPU seconds per batch, the time of each transform step, so that it shows which step sets the pace once the embedding no longer takes about 91 % of the CPU (normalising, validating, the OpenSearch and database writes), and the stored vectors of 1,000 records, snapshotted before the switch and compared after (design D9).

Behaviour towards the user:
- **Searchers:** none they can see. New and changed records get vectors from grace's GPU, within design D4's criterion of the local path's. Records indexed before keep theirs. Searching is unchanged; the search API keeps embedding queries locally and never gets the warehouse's token.
- **Operators:**
  - Indexing should take less CPU on staging and less time per batch (to be measured, design D9).
  - A grace outage makes indexing slow, not broken: batches fall back to local embedding, and `batch-times.sh` shows how many did.
  - The way back: an empty `EMBED_API_URL` in the env file and `docker compose up -d airflow-worker-transform`.
  - A new secret file, `embed.env`, for the worker only.
- **People on grace:** the service holds part of the GPU's memory while it runs and uses the GPU during indexing. It shows in `nvidia-smi` and `nvtop` under its own account.
- **Unchanged:** the crawler, the harvest, the search API's behaviour, the index's schema.

## Before anything beyond the demo

Accepted for the demo by @weber (items 349 and 350, 2026-11-13: "let's keep it for now, but make a note to secure it properly. For now it is just a demo and not many people have access to these systems"; "they can see the data anyway in the file system, so nothing new to them"; decision log). The people with accounts on grace and the staging host can already read the record texts on the storage. What "secure it properly" has to cover is what they cannot do today:
- **Integrity of the vectors, at both ends of the tunnel.** The ports are unprivileged: 7656 on grace and 172.17.0.1:17656 on the staging host. While the service or the tunnel is down (a restart, `systemctl stop`, a reboot), any local user could listen there, take the warehouse's requests with the token, and answer with forged vectors that go into the index. Fix: ports below 1024 at both ends (the service with `AmbientCapabilities=CAP_NET_BIND_SERVICE` or a systemd socket unit, the tunnel as root or with the same capability, `permitopen` and `PermitOpen` to match), with the spec's scenario "No one else can listen on the service's port while it is stopped" and its counterpart for the tunnel. 755 to 757 are unassigned in IANA's registry (design D5).
- **Ollama's admin calls.** Ollama on 11434 has no authentication: whoever holds the key, any user on the staging host and any container there can call its `/api/delete`, `/api/pull` and `/api/create`, not only chat. Fix: a token or a proxy in front of it, and a privileged port at the staging end as above. Part of the decision on AI Mode's chat model, not of this change.

The backlog item "Secure the grace tunnel before wider use" points here.

Out of scope:
- The search API's query embedding on grace (design D10 says what it would need).
- Moving any other part of the stack to grace (item 346).
- A real network connection instead of the tunnel; production (`deploy/`).
- The items of "Before anything beyond the demo" (accepted for the demo, 349 and 350).
- Larger transform batches, or more batch processes now that the CPU is freed (a follow-up of the measurement, CPU budget).
- Converting `deploy/beatepi`'s unit to the template.

Serves:
- requirements-pipeline 2.4 (operating conditions: indexing on the machines at hand) and 2.6 (performance);
- requirements-pipeline 2.9 (records stay inside the institute: grace is ER-C's; the token never reaches EGI);
- staging findings F7 and F16 (indexing time);
- @weber, item 346, items 349 and 350, and his remarks on the tunnel template, the far end's account and running on grace (2026-11-13).

## Capabilities

### New Capabilities
- `embedding-service`: the service on grace that embeds the warehouse's texts, what it accepts and answers, how far its vectors may be from the local path's, how it and its token are protected and how it shares the GPU, and what the warehouse does when it is unreachable. Like `cpu-budget` and `embedding-model`, it lives here because the search stack has no OpenSpec of its own.
- `ssh-tunnel`: the reusable systemd template for SSH tunnels: its forwards per instance, restart after failure, a key that opens nothing but its forwards, on an account that has no shell.

### Modified Capabilities
None.

## Impact

- New: `prototypes/search-stack/embedding-service/` (`server.py`, `check.py`, `requirements-gpu.in` and its lock file, `modama-embed.service`, `README.md`, tests).
- New: `deploy/ssh-tunnel/` (`ssh-tunnel@.service`, `README.md`).
- New: `prototypes/search-stack/patches/warehouse/0005-embedding-service.patch`.
- Changed: `prototypes/search-stack/docker-compose.yml` (`airflow-worker-transform`: `embed.env`, `EMBED_API_URL` from the env file, `host.docker.internal` as `host-gateway`; `search-api`: `EMBED_API_KEY: ""`), `testconf/secrets/embed.env` (an empty throwaway; the empty `EMBED_API_KEY=` line leaves `testconf/secrets/keys.env`), `runtest.sh` (the token check), `field-test/batch-times.sh`, `README.md` ("Secrets as files", "Measurements", a section on the service), the staging runbook (the switch and the measurement), `python/crawler/BACKLOG.md`.
- Changed in this change: `prototypes/search-stack/embedding-on-grace.md` (the key line, the full `Match` block, `ConnectTimeout=10`, "Before anything beyond the demo"); `design/architecture.md` (the decision-log row for 349 and 350); `BACKLOG.md` ("Secure the grace tunnel before wider use").
- On grace (by grace's admins, @weber coordinating): the service's account, its systemd unit and its token file outside the repository; the tunnel's account per the setup page, and the `Match` block in `sshd_config`.
- On staging (by @weber): the tunnel per the setup page; `embed.env` in a secrets folder outside the checkout. The runbook's settings put `MODAMA_SECRETS_DIR` at the committed throwaway `testconf/secrets`; staging's `staging.env` may already point to a folder outside, which task 5.4 checks before copying anything (design D11).
- **New dependencies, on grace only (flagged):** Starlette and uvicorn for the service's HTTP side, pinned at releases at least two weeks old (on 2026-11-13: starlette 1.10.0 of 2026-10-24 and uvicorn 0.54.0 of 2026-09-25, both BSD-3-Clause; looked up again at implementation). Starlette is what FastAPI, which upstream's warehouse and search API use, is built on. fastembed-gpu 0.8.0 and onnxruntime-gpu 1.31.1 are the benchmark's, locked with hashes. No new dependency in the stack's images.
