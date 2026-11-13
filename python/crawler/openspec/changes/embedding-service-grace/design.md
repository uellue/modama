# Design

## Context

See proposal.md, "Why". What exists, read in the code on 2026-11-13 (metadata-warehouse at the submodule's `0b461ce`, v1.10.0; data-commons-search at `6c07bdc`; fastembed 0.8.0 as installed by the warehouse's `uv.lock`):

- **The warehouse's remote path.** `transform_core.py:43-44` reads `EMBED_API_KEY` and `EMBED_API_URL`; `transform_batch_impl` passes them to `add_embeddings_to_source` (`transform_core.py:234-241`). When the key, the URL and `EMBEDDING_MODEL` are set (`embedding_utils.py:200`), it calls `_embed` with the model name's last part (`bge-small-en-v1.5`, `:202`), no prefix and the whole batch as one request (`batch_size=len(batch)`, `:204-212`). `_embed` (`:96-167`) posts `{"model", "input"}` to `{base_url}/embeddings` with `Authorization: Bearer` (`:116,125-129`), sorts the answer by `index` (`:154`), retries 4 times with 1, 2, 4 s of backoff or the server's `Retry-After` (`:157-163`), with a timeout of 120 s per attempt (`:106`). Any error status raises in `raise_for_status` (`:152`) and is retried like a network error, a 401 or a 400 included. On `requests.RequestException` or `RuntimeError` it logs `Embedding API failed after retries with, falling back to local model.` with the traceback and embeds locally (`:214-216`); a success logs `Embeddings calculated for bge-small-en-v1.5 from with API` (`:213`), the local path `calculating embeddings locally` (`:218`). Its error log masks the token (`:141-142`).
- **The catch.** `_embed` cuts each text to `text[:cap]` with `max_chars=1000` (`:104,127`) and halves the cap on a 400 that says `context length` (`:130-137`). The local path cuts nothing itself: fastembed's tokenizer truncates at `model_max_length`, 512 for this model (`fastembed/common/preprocessor_utils.py:39-52`, `tokenizer.enable_truncation(max_length=max_context)`; the model's `tokenizer_config.json`), counting `[CLS]` and `[SEP]`. Then the `[CLS]` token's output (`onnx_embedding.py:316-317`, `embeddings[:, 0]`), normalised (`:322`). English text has about 4 to 5 characters per token, so the cut at 1,000 characters falls at about 200 to 250 tokens: every record whose embedding text (titles, subjects and descriptions joined, `embedding_utils.py:26-37`) is longer would get another vector.
- **Compose.** `EMBED_API_URL: ""` in `transform` (`docker-compose.yml:319`) and `airflow-worker-transform` (`:590`). `keys.env` is read by `transform` (`:314`), `search-api` (`:396`) and `airflow-worker-transform` (`:585`); `testconf/secrets/keys.env:5` has an empty `EMBED_API_KEY`. Only `airflow-worker-transform` embeds records: the DAG task `run_transform_batch` (`airflow/dags/transform_index.py:77-98`) is the only caller of `TransformResources` and `transform_batch_impl`. Each batch is a fresh process that loads the local model first (`transform_index.py:90-93`, `transform_core.py:64`, with patch 0002's `threads`), whether or not it will embed locally.
- **The search API would take the token too.** Its settings read the environment without a prefix (`data_commons_search/config.py:147-151`, `SettingsConfigDict` without `env_prefix`), so `EMBED_API_KEY` in `keys.env` becomes its `embed_api_key`, and its `embed_api_url` defaults to `https://llm.ai.egi.eu/v1` (`config.py:80`). Every search that reranks (`mcp_server.py:117`) then posts to EGI with `Authorization: Bearer <key>` (`embeddings.py:51-52,155`), with the question and the hits' titles and descriptions. (Found by the review of 34717466.)
- **Stored vectors.** The warehouse stores every record's vector with `embedding_model = EMBEDDING_MODEL` (`transform_core.py:290,307,323`), the same for both paths: the database cannot tell later which path made a vector. A re-index overwrites them (`ON CONFLICT … DO UPDATE SET … embeddings = EXCLUDED.embeddings`, `:301-307`).
- **The index** quantises the vectors: HNSW (lucene) with `encoder: sq` (`metadata-warehouse/config/opensearch_mapping.json:15-21`), a step of about 1e-3 to 3e-3 per component (`embedding-fp32-model`, E6, a rough 7-bit stand-in).
- **The benchmark** (`perf/grace-embedding/`, run on grace 2026-11-13): fastembed-gpu 0.8.0 on onnxruntime-gpu 1.31.1 (CUDA 13), the production file (`qdrant/bge-small-en-v1.5-onnx-q`, `model_optimized.onnx`, float16 weights, pinned revision `aa8f8b060edb00e03bfdd08813a2949946c8ba55`) on the GPU: minimum cosine 0.999989 to production's vectors, the float32 file 0.999990; short texts 50,059 texts/s at 2 workers × batch 256 (quick run, as reported to this change's author; the setup page quotes 68,600 for the same day's quick run, to be reconciled with the result files); the tokenizer alone about 94,000 short texts/s on 72 threads. The full run's results will be in `.claude/field-tests/grace-results/`. Its GPU sessions leave ONNX Runtime's CUDA options at their defaults except `gpu_mem_limit` (`bench.py:254-257`), so TF32 is on (`use_tf32`, "Default value: 1", ONNX Runtime's CUDA provider documentation, read 2026-11-13).
- **Staging's batches** have 2,000 records (`CELERY_BATCH_SIZE=2000`, staging runbook, "Larger indexing batches"; @weber, 2026-11-10, after F9), not upstream's 250.
- **The tunnel pattern** (`deploy/beatepi/etc/systemd/system/er-c-data-smb.service`): `ssh -c aes128-ctr -o ServerAliveInterval=60 -o ExitOnForwardFailure=yes -N -L …`, `Restart=always`, `RestartSec=30s`, as root, with root's known hosts. Stable in production (@weber).
- **The prototype's setup** (`prototypes/search-stack/embedding-on-grace.md`, @weber, on `crawler` since 7272c1d5): the ports, the tunnel unit `embed-tunnel.service` with its `nologin` account `embedtunnel`, a test of the tunnel before the service exists. It is the one home of the setup; this design refers to it (D7).
- **Staging's secrets.** The runbook's settings write `MODAMA_SECRETS_DIR=./testconf/secrets`, the committed throwaway values; staging's gitignored `staging.env` may point elsewhere by now (the review saw a folder outside the checkout there). Task 5.4 checks first.

## Goals / Non-Goals

Goals: the warehouse's vectors from grace's GPU, within D4's criterion of the local path's, for every text length; the token only where it is used; an outage of grace or the tunnel costs time, never records, and shows; a tunnel template others can reuse.

Non-goals: a service for anyone but the warehouse (one model, one client); TLS and a network connection without the tunnel; what proposal.md lists under "Before anything beyond the demo"; tuning the warehouse around the freed CPU (larger batches, more processes), which follows from the measurement (D9).

## Decisions

### D1. The server: a small service of our own around fastembed-gpu

Agreement with the local path decides, then whether it runs on grace today, then how much of it is ours.

| | Our service (fastembed-gpu, onnxruntime-gpu) | Text Embeddings Inference (Hugging Face) | Infinity (michaelfeil) | vLLM | Triton Inference Server (NVIDIA) |
|---|---|---|---|---|---|
| Runs on GH200 (aarch64, Hopper) | yes: measured on grace, 2026-11-13 | no published image: aarch64 only as CPU (`cpu-arm64-1.9`) and Blackwell 12.1 (`121-1.9`, experimental); Hopper only x86_64 (`hopper-1.9`). For ARM64 with NVIDIA GPUs the README describes building `Dockerfile-cuda` with `--platform linux/arm64`; not tried | v3 image shown for NVIDIA SM80+, no arm64 named; v2 (`infinity-emb` 0.0.80) pins `onnxruntime-gpu<1.24,>=1.23.2`, which has no aarch64 wheels (those start at 1.29.0) | an aarch64 wheel on PyPI (`vllm-0.33.0-cp38-abi3-manylinux_2_28_aarch64.whl`, 2026-11-02); the Docker image for Grace Hopper is built from source (docs v0.25.0); not tried | an arm64 (SBSA) container exists (release notes 2.67.0); not checked on GH200 |
| Model file and pipeline | the same ONNX file, tokenizer, truncation, `[CLS]` pooling and normalisation as the local path (fastembed's own code) | the CUDA backend is Candle, from the model's safetensors (`BAAI/bge-small-en-v1.5`); ONNX through `ort` is the CPU backend. Truncation at the model's maximum (`--auto-truncate`, default true); pooling from `1_Pooling/config.json` or `--pooling cls` | v3 LibTorch; v2 torch or optimum/ONNX | PyTorch weights; pooling models are supported "primarily for convenience" | the ONNX file through the ONNX Runtime backend; tokenizing, pooling and normalising would be a Python backend of ours |
| Vectors against the local path | measured: 0.999989 (production file), 0.999990 (float32 file) | not measured: other weights (float32 safetensors, run in float16 by default on GPU), other kernels | not measured | not measured | the same file; agreement depends on our pre- and post-processing |
| Protocol | OpenAI `/v1/embeddings`, as the warehouse speaks | OpenAI-compatible `/v1/embeddings` | `/v1/embeddings` | OpenAI-compatible | KServe v2: the warehouse's client would change |
| Licence | ours; fastembed Apache-2.0, ONNX Runtime MIT | Apache-2.0 | v3: "Infinity Restricted MIT License 1.0", "a custom source-available license"; v2 MIT | Apache-2.0 | BSD-3-Clause |

Sources, read 2026-11-13: TEI's [README](https://github.com/huggingface/text-embeddings-inference) and [supported models and hardware](https://huggingface.co/docs/text-embeddings-inference/supported_models) (version 1.9); Infinity's [README](https://github.com/michaelfeil/infinity) and [PyPI JSON](https://pypi.org/pypi/infinity-emb/json) (0.0.80); vLLM's [PyPI JSON](https://pypi.org/pypi/vllm/0.33.0/json) (Apache-2.0), [docker docs v0.25.0](https://docs.vllm.ai/en/v0.25.0/deployment/docker/), and [pooling models](https://docs.vllm.ai/en/latest/models/pooling_models.html) as quoted in `docs/research/embedding-throughput.md` (not read again); Triton's arm64 container from search results on its release notes (for example [25.08](https://docs.nvidia.com/deeplearning/triton-inference-server/release-notes/rel-25-08.html); not read in full); Triton's licence from GitHub's licence API for `triton-inference-server/server`; onnxruntime-gpu's aarch64 wheels from `perf/grace-embedding/requirements-gpu.in`. `docs/research/embedding-throughput.md` has the throughput side of TEI, Infinity and vLLM.

**Decision (lean, confirmed by the review): our own service.** It is the only option that runs on grace's GPU today with the model file the local path uses, and the only one whose vectors are measured: it runs the code the local path runs, so tokenizer, truncation, pooling and normalisation agree by construction and only the device's arithmetic differs (D4). Ours is the thin part: an HTTP endpoint in OpenAI's format on Starlette and uvicorn (Starlette is what FastAPI, which upstream's warehouse and search API use, is built on; it needs no pydantic for two routes), a token check, sorting by length and a lock. The rest is fastembed and ONNX Runtime.

**The strongest argument against:** "no new inventions". TEI is the established embeddings server, Apache-2.0, speaks the same protocol, batches by tokens without padding, and others maintain it. But on the GH200 it means building its CUDA image from source for aarch64 and compute capability 9.0, which nobody here has done, and its vectors come from other weights through other kernels, so the agreement would have to be measured from scratch. vLLM's aarch64 wheel changes nothing there: other weights again, and pooling "primarily for convenience". Our GPU does 50,000 short texts/s against staging's tens of records per second per process (D8): speed buys nothing here. **Re-evaluate** when TEI publishes an aarch64 Hopper image: the check instrument measures agreement and rate of any server that speaks the protocol, so a swap is one measurement.

### D2. Texts go uncut; the service truncates at tokens; no retry where a retry cannot help

The patch passes `max_chars=None` to `_embed`, which then sends each text whole; the service's tokenizer cuts at 512 tokens as the local one does (D1). On a 400 that says `context length` (a server that refuses long texts), the patch raises at once, and the batch falls back to local embedding, instead of halving a cap that no longer exists.

**No retry of 400 and 401** (review S7): a wrong token or a refused request fails the same way four times and costs 7 s of backoff per batch. The patch retries only network errors, timeouts, 429 and 5xx, as the search API's client already does (`data-commons-search` `embeddings.py:68-72`), and falls back at once on any other 4xx.

**The timeout:** 30 s instead of 120 s (Q8). In `requests` a timeout limits the connection and each wait for bytes, not the whole answer, so a hanging service costs 4 × 30 s + 1 + 2 + 4 s ≈ 127 s per batch before the fallback; one that drips bytes could take longer, bounded by Airflow's `execution_timeout` of an hour. A batch of 2,000 long texts takes well under a second on the GPU (D8).

Alternatives:
- **Cut at tokens in the patch** (tokenize locally, keep 510 tokens, decode): decoding is not the inverse of tokenizing (spacing, accents, unknown tokens), so the vectors would move; and it costs tokenizer CPU on staging.
- **Send token IDs** (OpenAI's API allows arrays of token IDs as `input`): exact, but staging tokenizes again, the service must accept IDs, and our protocol would differ from what other servers commonly take as text.
- **Keep the 1,000 characters**: changes every long record's vector (Context).

The cost: long texts travel whole. A description of 20 kB adds 20 kB to a request of a batch of 2,000 against a 17 MB answer (D8).

### D3. One rule for the model file: the local path's file, TF32 off

The service loads **the same file the local path loads**: today the production file at the pinned revision; the float32 file once `embedding-fp32-model` puts it into the transform image. ONNX Runtime's `use_tf32` is off. (Review M3: an earlier draft argued for the float32 file on the GPU regardless; the measured cosines, 0.999990 against 0.999989, do not support a difference.)

- **Relation to `embedding-fp32-model`** (worktree `agent-ac33b9c29c181d3e1`, not merged): that change moves the CPU path, and so the local fallback, to the float32 file (minimum cosine 0.99999963 to the production file, its E4/E5), made at image build from the pinned upstream files. When it lands, the service takes the same file from the same script and pin, and its marker (that change's D3) names the model in both places. Until then the service loads the production file. Either way service and fallback run one file, and the check compares the two paths on it.
- **TF32 off:** with TF32 on (ONNX Runtime's default), float32 matrix products round their inputs to 10 bits of mantissa ("float32 inputs are rounded with 10 bits of mantissa", CUDA provider docs). For the float32 file that may be what limits the GPU to 0.999990 against 0.99999963 on the CPU: a hypothesis, measured first (task 2.2). With the production file's float16 weights it changes nothing measurable, and costs nothing to set.
- **Speed:** float32 without TF32 is slower than float16; the full run reports the float32 file at the GPU's best setting. At D8's rates even a tenth of 50,000 texts/s is far more than staging sends.

### D4. Agreement: the bound, and the criterion if a pairing misses it

**The bound:** every pair of vectors, service against local, has a cosine of at least 0.99999 in float64, the bound of `embedding-fp32-model` (its D4), so that one number governs what may sit side by side in the index.

**The criterion when a pairing misses it, decided now** (review S6; the production file on the GPU measured 0.999989): the service's vectors are accepted if, on the same texts,
- the largest component difference to the local path's vectors is below 1e-3, the lower estimate of the index's `sq` step, so the index's own quantisation moves a vector more than the device does; and
- a ranking check agrees: for fixed queries over a corpus of staging's records, the top-10 sets from the service's and from the local path's vectors, both quantised by `embedding-fp32-model`'s 7-bit stand-in (its E6), overlap by at least 0.997, the overlap measured there between the float32 and the production file.

**The deciding numbers** come from `check.py` inside `airflow-worker-transform` on staging (the local side on staging's EPYC, the production path), not from grace's CPU. If either condition fails, the switch waits for @weber (Q2). The spec states both.

### D5. On grace: systemd, an account of its own, a locked venv

**Decided (@weber, 2026-11-13): systemd for the prototype.** The service runs as `modama-embed.service`, a system unit with `User=modama-embed`, from a venv made with grace's Python 3.12 from the lock file (`requirements-gpu.txt`: the benchmark's packages plus Starlette and uvicorn, with hashes). In `nvidia-smi` and `nvtop` its processes show under that account and the venv's path (`/opt/modama-embed/venv/bin/python …`), so people on grace see what holds the GPU. Users outside it keep using the GPU as before (@weber's condition).

- **Token:** a random token (`openssl rand -hex 32`) in `/etc/modama-embed/token`, root's, mode 0600, passed with `LoadCredential=token:/etc/modama-embed/token`; the service reads `$CREDENTIALS_DIRECTORY/token` ("The data is only accessible to the user associated with the unit", systemd.exec(5), "Added in version 247"; Ubuntu 24.04 has systemd 255, to check with `systemctl --version`). Not in the repository, not in the environment, not on a command line.
- **Restart:** `Restart=always`, `RestartSec=30s`, as the tunnel. With 30 s between starts, systemd's default start limit (5 starts in 10 s) is never reached.
- **The port:** `127.0.0.1:7656`, unprivileged, for the demo (@weber, 349; proposal, "Before anything beyond the demo"). Before wider use: a port below 1024 with `AmbientCapabilities=CAP_NET_BIND_SERVICE`, so that no other user can listen there while the service is stopped (requires `net.ipv4.ip_unprivileged_port_start` at its default of 1024 on grace). 755 to 757 are unassigned in IANA's registry (read 2026-11-13). A systemd `.socket` unit, which holds the port while the service is down, is the alternative; uvicorn would take the socket with `--fd`, not tried with two workers.
- **GPU sharing:** the GPU stays shared: ONNX Runtime claims memory, not the device. NVIDIA's container FAQ: sharing a GPU "is no different than sharing a GPU between multiple processes outside of containers"; exclusive access only through the compute mode or orchestration, which nobody sets for this. Each of the two workers caps its ONNX Runtime arena with `gpu_mem_limit` ("The size limit of the device memory arena in bytes … The total device memory usage may be higher", the CUDA context of about 0.5 GB per process on top). The value: twice the peak the full run measured at batch 256 for long texts, per worker (Q9). A batch beyond it gets 503, the warehouse falls back (spec).
- **No busy check.** The benchmark refuses to start while another process uses the GPU, for clean numbers. The service must not: sharing is the point. At start it logs the other compute processes `nvidia-smi --query-compute-apps` lists, for the record. When others need the whole GPU, `sudo systemctl stop modama-embed` is always safe: the warehouse falls back.
- **Two workers, one GPU batch each at a time.** uvicorn with `--workers 2`, the benchmark's best for short texts (2 workers × batch 256); each worker holds one session and runs one sub-batch on the GPU at a time (a lock), while the other tokenizes. A request's texts (2,000 per staging batch) are sorted by length and embedded in sub-batches of 256, the vectors returned in the request's order, as patch 0002 does locally.

**Docker later**, for a permanent service, with the NVIDIA Container Toolkit. Checked in NVIDIA's and Docker's documentation on 2026-11-13:
- The toolkit has arm64 packages: `nvidia-container-toolkit` 1.20.1-1 and 1.20.2-1 for `arm64` in NVIDIA's apt repository (`https://nvidia.github.io/libnvidia-container/stable/deb/arm64/Packages`); the supported-platforms table lists `arm64 / aarch64` (whether its Ubuntu 24.04 row covers arm64 could not be read from the page's text; the apt repository is per architecture, not per release).
- Setup: `sudo nvidia-ctk runtime configure --runtime=docker`, which "modifies the `/etc/docker/daemon.json` file", then `sudo systemctl restart docker` ([install guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html), toolkit 1.20.1-1). Docker's restart stops grace's running containers: "By default, when the Docker daemon terminates, it shuts down running containers"; live restore keeps them, but "If any of these daemon-level configuration options have changed, the live restore may not work" ([live restore](https://docs.docker.com/engine/daemon/live-restore/)). So the setup needs a window agreed with whoever runs containers on grace, unless the toolkit is configured there already (`docker info | grep -i runtimes`).
- A container gets the GPU with `--gpus all`, or in compose `deploy.resources.reservations.devices` with `driver: nvidia`, `count` or `device_ids`, `capabilities: [gpu]` ([compose GPU support](https://docs.docker.com/compose/how-tos/gpu-support/)); the page does not call this exclusive, and NVIDIA's FAQ says sharing works as between processes.
- Visibility: "`nvidia-smi` and NVML are not compatible with PID namespaces. We recommend monitoring your processes on the host or inside a container using `--pid=host`" ([toolkit FAQ](https://nvidia.github.io/container-wiki/toolkit/faq.html)). So the service's processes show in the host's `nvidia-smi` (and, presumably, `nvtop`, if it reads the processes through NVML as well: not checked), while a busy check run inside the container would see no processes, its own and others' alike.
- NVIDIA's test: `sudo docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi` ([sample workload](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/sample-workload.html)).

### D6. The service's interface

Spec, `embedding-service`. In short: `POST /v1/embeddings` (OpenAI's request and answer, `float` encoding only), Bearer token compared in constant time (`hmac.compare_digest`), 400 for another model, 503 when the GPU's memory runs out, `GET /health` without token (repository, revision, file, provider), bound to `127.0.0.1:7656`. One log line per request: texts, tokens, milliseconds, status; never text.

### D7. The tunnel: the setup page's, checked, and a template derived from it

**The prototype's tunnel is decided and set up** by @weber: `prototypes/search-stack/embedding-on-grace.md` (one home for the setup; not repeated here). The staging host runs `embed-tunnel.service` (`ssh -N -L 172.17.0.1:17656:127.0.0.1:7656`, plus `-L 172.17.0.1:11434:127.0.0.1:11434` for grace's chat model, which is not part of this change), as root with the key in `/var/local/sshvpn/`, into the `nologin` account `embedtunnel` on grace; the containers reach it as `host.docker.internal:17656` through `extra_hosts` with `host-gateway`. So the side that needs the service starts the connection, as beatepi does towards iff1020, and the account with the restricted key is on grace. The opposite direction (grace running `ssh -R` into staging) would put the key on grace, which several people share, and a stolen key could listen on staging's port in the service's place.

**The key's options and the `Match` block, checked** against sshd(8) ("AUTHORIZED_KEYS FILE FORMAT") and sshd_config(5), OpenBSD's manual pages read 2026-11-13, and against OpenSSH 10.0p2's `sshd` in the VM: a throwaway server on 127.0.0.1 (non-root, `UsePAM no`, its own host key and `authorized_keys`), the real `ssh` client with `-F none`, `socat` listeners as the permitted TCP destination, a forbidden one and a Unix socket. With an account that has a shell (the VM's user):

| Attempt | Page's first line `restrict,port-forwarding,permitopen=…` | key line + `command="/usr/sbin/nologin"`, two `permitopen` | + `Match`: `AllowTcpForwarding local` | + `Match`: also `AllowStreamLocalForwarding no`, `PermitOpen`, `PermitTTY no`, `X11Forwarding no` |
|---|---|---|---|---|
| `ssh host id -un` | **ran** (`dev`) | refused: "This account is currently not available." | refused | refused |
| `ssh -tt host` | not tried | PTY refused | PTY refused | PTY refused |
| `-N -L` to a permitted address | works | works, both addresses | works | works |
| `-N -L` to another port | refused ("the request was denied") | refused | refused | refused |
| `-N -L` naming `localhost` instead of `127.0.0.1` | refused | refused | refused | refused |
| `-N -L port:/path/of/a/unix.socket` | not tried | refused | refused | refused |
| `-N -R 127.0.0.1:47656:…` | **listener opened on the far end** | **opened** | refused ("remote port forwarding failed") | not tried again |
| `-N -R /path/of/a/new.socket:…` | not tried | **socket created on the far end** | refused | refused |

- `restrict`: "Enable all restrictions, i.e. disable port, agent and X11 forwarding, as well as disabling PTY allocation and execution of ~/.ssh/rc". It does not stop a command: `nologin` as the shell does, and the forced command `command="/usr/sbin/nologin"` ("the command is executed whenever this key is used for authentication. The command supplied by the user (if any) is ignored") does even if the shell were changed. The tunnel's `-N` ("Do not execute a remote command. This is useful for just forwarding ports", ssh(1)) opens no session, so the forced command never runs for it.
- `port-forwarding`: "Enable port forwarding previously disabled by the restrict option", in both directions: `no-port-forwarding` "Forbids TCP forwarding", and the test opened a remote listener and a remote Unix socket. `permitopen` limits only `-L`; `permitlisten="none"` is not accepted in a key line (the key was rejected). sshd_config(5): `AllowTcpForwarding local` ("to allow local (from the perspective of ssh(1)) forwarding only"), allowed in a `Match` block; with it, both remote forwards were refused.
- `permitopen="host:port"`: "No pattern matching or name lookup is performed on the specified hostnames, they must be literal host names and/or addresses", so the unit's `-L` names `127.0.0.1` as the key line does. "Multiple permitopen options may be applied separated by commas": both forwards worked.
- **The full `Match` block** (review S5): `AllowTcpForwarding local`, `AllowStreamLocalForwarding no`, `PermitOpen 127.0.0.1:7656 127.0.0.1:11434`, `PermitTTY no`, `X11Forwarding no`. In OpenSSH 10.0 the extra lines changed no outcome above (the key options already refused them), but they hold on the server side whatever the key line says, and on whatever version grace runs: Ubuntu 24.04 ships OpenSSH 9.6, not tested here. So the scenarios run once more on grace itself (task 1.2), with `sudo sshd -T -C user=embedtunnel` showing what applies to the account (checked here: `-C user=…` applies the `Match` block).
- **Done in this change:** the setup page carries the key line, the full `Match` block and `ConnectTimeout=10` (its section "On grace: the tunnel's account" and its unit).
- Q10, beyond that: `from="<staging host's address>"` ("in addition to public key authentication, either the canonical name of the remote host or its IP address must be present"), so that the key works only from the staging host.

**The template**, `deploy/ssh-tunnel/ssh-tunnel@.service`, derived from the page's unit and beatepi's:

```ini
[Unit]
Description=SSH tunnel %i (forwards in /etc/ssh-tunnel/%i.conf)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=ssh-tunnel
EnvironmentFile=/etc/ssh-tunnel/%i.conf
ExecStart=/usr/bin/ssh -F none -N -i /etc/ssh-tunnel/%i/key \
    -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 \
    -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/ssh-tunnel/%i/known_hosts \
    -o ExitOnForwardFailure=yes -o ServerAliveInterval=60 \
    $SSH_OPTIONS $FORWARDS ${DESTINATION}
Restart=always
RestartSec=30s

[Install]
WantedBy=multi-user.target
```

and the page's tunnel as an instance, `/etc/ssh-tunnel/embed.conf`:

```
DESTINATION=embedtunnel@<grace>
FORWARDS=-L 172.17.0.1:17656:127.0.0.1:7656 -L 172.17.0.1:11434:127.0.0.1:11434
SSH_OPTIONS=
```

The running `embed-tunnel.service` stays as the page has it until the template is tested; moving it to `ssh-tunnel@embed` is @weber's call (Q15).

- `%i` is the instance name ("the string between the first "@" character and the type suffix", systemd.unit(5)). `$FORWARDS` is split at whitespace into several arguments and `${DESTINATION}` stays one ("`$FOO` … split at whitespace, resulting in zero or more arguments"; "`${FOO}` … always resulting in exactly a single argument", systemd.service(5)), so one file holds any number of `-L`, and an empty `SSH_OPTIONS` adds nothing. beatepi's `-c aes128-ctr` would go into `SSH_OPTIONS`.
- New against the page's and beatepi's units (Q15, the review's answer): `User=ssh-tunnel` instead of root; `-F none` (no user or system `ssh_config` applies, and no warning about the account's missing home); `BatchMode=yes` and `StrictHostKeyChecking=yes` with a known-hosts file per instance, its line compared with the fingerprint read on the far end itself (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` there), instead of accepting the host key once by hand (fail rather than wait for a prompt or take a new host key; ssh_config(5)); `IdentitiesOnly=yes`; `ConnectTimeout=10` (review S4: without it, a far end that is down holds each attempt for about 2 minutes before the 30 s pause). A port below 1024, as beatepi's 445 or the hardened ports of "Before anything beyond the demo", needs a drop-in with `AmbientCapabilities=CAP_NET_BIND_SERVICE`; an address that exists only once Docker is up gets `After=docker.service` in a drop-in, as the page's unit has it, and otherwise the restart every 30 s covers it.
- `ServerAliveInterval=60` with the default `ServerAliveCountMax` of 3: a dead connection ends `ssh` after about 3 minutes (spec: within about 4).
- **To check against @weber's version** from his other hosts once he sends it (task 4.5): the differences go into the README or the template.

The README (`deploy/ssh-tunnel/README.md`), derived from the setup page's steps: the far end's account (`useradd --system --create-home --shell /usr/sbin/nologin <account>`, its `.ssh` 0700 and `authorized_keys` 0600, owned by it), the key line and the `Match` block with what each part does (the table above, shortened), the key (`ssh-keygen -t ed25519 -N ''`, made on the client, never copied elsewhere), the known-hosts line and its fingerprint check, install, `systemctl enable --now ssh-tunnel@NAME`, logs (`journalctl -u ssh-tunnel@NAME`), and how to check the restrictions (the spec's scenarios, by hand). The setup page then points to it for the general part, so that each fact has one home.

### D8. Throughput and transfer, at staging's 2,000 records per batch

**Answer size,** measured with Python's `json` on unit vectors of 384 float32 values, written as the warehouse's `tolist()` writes them (each value widened to a double): 8.5 kB per vector, 2,119,420 bytes per 250; per staging batch of 2,000, 16,955,126 bytes (the review's measurement), about 17 MB in one answer. As base64 of the float32 bytes (OpenAI's `encoding_format: "base64"`), 2.1 kB per vector, about 4.2 MB per batch; with zlib at level 1, about 46 % of the JSON.

**Estimates, not measured:**
- What the GPU could deliver, 50,000 short texts/s, is 425 MB/s as JSON: more than a 1 Gbit/s link (about 117 MB/s, about 14,000 vectors/s as JSON, 55,000 as base64), and probably more than one SSH connection's encryption on one core. So at the GPU's speed the tunnel caps it.
- What staging sends is far less. A batch process did 33 records/s in F9 (measured before patches 0001 to 0003; since then the embedding is about 91 % of a batch's CPU). Without the embedding, a batch of 2,000 is the process start, the normalising, validating and the writes: if that is 4 to 12 ms per record (a guess, measured in D9), a batch takes 8 to 24 s, and 4 to 16 batch processes (staging's CPU budget with `AIRFLOW_TASK_LIMIT=16`) send 330 to 4,000 records/s: 3 to 34 MB/s of JSON, within a 1 Gbit/s link and, plausibly, one SSH connection. One answer of 17 MB takes about 0.15 s at 1 Gbit/s. The GPU idles most of the time.
- So the tunnel is not expected to cap the indexing; the warehouse's other steps are (D9 measures it). base64 stays a lever (a patch reading `encoding_format: "base64"`, Q13) if the measurement shows transfer above a tenth of a batch's time.
- The link between the staging host and grace and the SSH connection's rate are unknown: the check instrument measures MB/s through the tunnel with requests of 2,000 texts at 1, 4 and 16 at once (task 3.2).

### D9. The prototype's measurement on staging

@weber (2026-11-13): the benchmark compared grace's CPU with its GPU; staging and production run on an AMD EPYC, so staging's real indexing throughput before and after decides. And once the embedding is no longer about 91 % of the transform's CPU, the other steps set the pace: the measurement must show which.

Instruments, existing first: `field-test/batch-times.sh` (per batch: model load, batch time; with this change, service, fallback or local), `field-test/index-tasks.sh` (the indexing run's tasks with queued, started, ended), `field-test/indexing-probe.py` (each batch process's CPU, threads, memory every 10 s; `py-spy dump` of the busiest), `perf/phase-timer.py` (wall and CPU seconds per transform step on one real batch, without writing: XML parse and normalise, validate, embedding text, embed, bulk preparation; the writes are the batch time less the steps' sum), `monitor.sh` (each container's CPU: the warehouse's PostgreSQL and OpenSearch), `modama-chain status` (no crawl, harvest or indexing running), on grace `nvidia-smi dmon -s um` and the service's request log, and the new `check.py` (agreement, rate and MB/s through the tunnel; the snapshot of stored vectors).

Steps (the runbook gets them as commands, task 6.2):
1. Quiet: `modama-chain status` shows no crawl, harvest or indexing running; the timer's next crawl is hours away.
2. Before: the throughput of local embedding from the last indexing run under the current image, if its task logs are still there (`batch-times.sh`, `index-tasks.sh`); otherwise a re-index of the last full harvest run (`warehouse_transform_index` with its `harvest_run_id`, `reuse_embeddings` off) for 30 minutes, then stopped. `phase-timer.py` on one batch of 2,000. (Review M4: a full before re-index is not needed.)
3. **Snapshot before the switch** (review M4): `check.py snapshot` writes the stored vectors and datestamps of 1,000 records, chosen by a hash of their identifiers, from the warehouse's `records` table with the read-only role, to a file outside the checkout. The re-index of step 5 overwrites them (`ON CONFLICT … DO UPDATE`).
4. Switch: the token into the worker's own secret file, `EMBED_API_URL` in `staging.env`, `docker compose up -d airflow-worker-transform`; `check.py` from inside the worker: agreement (D4's numbers) and rate through the tunnel.
5. After: a re-index of the same harvest run with the service, the same probes; let it finish (it gives every record a vector from the service; Q4). `phase-timer.py` on the same batch.
6. An outage on purpose: `sudo systemctl stop embed-tunnel` for 10 minutes during the re-index: batches fall back (`batch-times.sh`), none fails; start it again.
7. Vectors: `check.py compare` against the snapshot, for the records whose datestamp has not changed since: minimum cosine, largest component difference, the ranking check of D4.

What it reports: records/s before and after, wall and CPU seconds per batch on staging, the per-step table before and after (which step is now the largest), PostgreSQL's and OpenSearch's CPU, the GPU's busy share, MB/s through the tunnel, fallbacks, the vectors' agreement. Into `design/field-tests/search-stack-staging-findings.md` as a finding.

### D10. The search API's query embedding: later, and what it would need

`data-commons-search` embeds a query through the API only when `embed_api_model` is set (`mcp_server.py:133-146`), with `embed_api_url` and `embed_api_key` (`config.py:80-81`), `httpx`, 30 s timeout, 3 attempts, then the local model (`embeddings.py:20-24,46-84,87-109`). The same URL and key also serve `/rerank` (`embeddings.py:138-155`), which our service does not answer. So, if ever (Q14, the review's answer): its own URL and its own token for the search API, not the warehouse's settings, a short timeout (a query waits for it), and a decision on reranking. The gain is small: a query embeds in 8 to 17 ms on one thread on the VM (stack README, "CPU budget"). Not now.

### D11. Security

- **The token reaches only the transform worker** (review M1). It goes into its own file, `embed.env` in `MODAMA_SECRETS_DIR`, which only `airflow-worker-transform` reads, not into `keys.env`, which `transform` and `search-api` read too. The worker lists `embed.env` after `keys.env`, so its value wins over the empty `EMBED_API_KEY=` line `keys.env` carries today (compose takes the last file's value); that line is removed from `testconf/secrets/keys.env`. And `search-api` gets `EMBED_API_KEY: ""` in its `environment`, which overrides any env file, so a token left in `keys.env` by habit still does not reach it. A test checks both (task 5.2). Without this, every reranked search would send the token, the question and the hits to EGI (Context).
- **Record texts travel to grace**, which is ER-C's: inside the institute (requirements-pipeline 2.9). Over the network inside SSH; on grace over the loopback to the service, which keeps nothing and logs no text. The people with accounts on grace and on the staging host can read the same texts on the storage already (@weber, 350: "they can see the data anyway in the file system, so nothing new to them").
- **The token** guards the service against other users and processes on grace, which reach `127.0.0.1:7656` too, and against anyone on the staging host or in its containers who reaches `172.17.0.1:17656`. It lives in `/etc/modama-embed/token` on grace (root, 0600, given to the service by `LoadCredential`) and in `embed.env` of staging's secrets folder, which must be outside the checkout: the runbook's settings put `MODAMA_SECRETS_DIR` at the committed `testconf/secrets`, and a token there would show in `git status` and could be committed. Staging may already have a folder outside (Context); task 5.4 checks before copying. To check that the token is set without printing it: `grep -c '^EMBED_API_KEY=.' <folder>/embed.env`.
- **Accepted for the demo** (@weber, 349 and 350, 2026-11-13; decision log): the unprivileged ports at both ends, where any local user could listen while the service or the tunnel is down and receive the requests, token included, or answer with forged vectors; and Ollama's port forwarded without authentication. What "secure it properly" has to cover is in proposal.md, "Before anything beyond the demo".
- **The SSH key** is made on the staging host and never leaves it (root's, in `/var/local/sshvpn/`, per the setup page); on grace it opens only the local TCP forwards to the service's and the chat model's ports: no command, no terminal, no remote forward, no Unix socket (D7, checked). grace's host key is accepted once by hand per the page; the template pins it against a fingerprint read on grace (Q15).
- **No secrets in Git:** the repository holds the unit files, the README and examples with placeholders; tests make throwaway keys and tokens in temporary folders.
- **Later, a network connection without the tunnel** needs TLS and a firewall rule, and the service then listens on more than loopback: out of scope here, a change of its own.

## Risks / Trade-offs

- [A pairing misses 0.99999 on the GPU] → D4's criterion, decided now, with the numbers from the EPYC; if it fails too, the switch waits for @weber (Q2).
- [A hanging service makes every batch wait] → the timeout of 30 s per wait: about 2 minutes per batch before the fallback, against 8 with upstream's 120 s; no retry on 400 and 401. Visible in `batch-times.sh`.
- [All batch processes fall back at once] → the CPU budget still sizes them for local embedding (README, "CPU budget"), so that is today's load, not more.
- [Fallback vectors and service vectors side by side] → the same file, within D4; the database labels both `BAAI/bge-small-en-v1.5` and cannot tell them apart, the batch logs can.
- [Others on grace need the GPU] → the memory cap, the service visible under its own account, and `systemctl stop` as the always-safe way out.
- [A local user listens on a freed port at either end] → accepted for the demo (349); privileged ports before anything beyond it.
- [The tunnel binds an address that only exists once Docker is up] → `ExitOnForwardFailure` and a restart every 30 s; `After=docker.service`.
- [grace's OpenSSH 9.6 behaves otherwise than 10.0 here] → the `Match` block holds server-side; the scenarios run again on grace (task 1.2).
- [The template's differences from @weber's running version] → checked when he sends it (task 4.5).

## Migration Plan

1. grace: the tunnel's account with the corrected key line and the full `Match` block, the service's account, the venv, the model files, the token, the unit (tasks 1, 2.4); the service answers `GET /health` through the tunnel.
2. staging: the secrets folder outside the checkout (checked first), `embed.env`, the before numbers, the snapshot, the switch, the after measurement (D9).
3. **Rollback** at any time: `EMBED_API_URL=` (empty) in `staging.env`, `docker compose up -d airflow-worker-transform`; the next batches embed locally (spec, "The way back is an empty URL"). Vectors already indexed from the service stay; they agree within D4. The tunnel and the service can stay or go: `systemctl disable --now embed-tunnel` on staging (it also carries the chat model's forward), `systemctl disable --now modama-embed` on grace.

## Open Questions

Each with the lean the tasks assume, and the review's answer (review of 34717466); @weber decides.

- **Q1. Our service or TEI built from source?** Our service (D1); review: the same.
- **Q2. A pairing below 0.99999.** D4's criterion, decided now (component difference below 1e-3 and top-10 overlap at least 0.997, measured on the EPYC); if that fails too, @weber.
- **Q3. The model file.** The local path's file, TF32 off (D3); review: the same.
- **Q4. Re-index after the switch?** No extra one; the snapshot comes first (D9); review: the same.
- **Q5, Q6 and Q11, decided** by @weber's setup page; the ports kept for the demo (349).
- **Q7. Load the local model only when needed?** Yes, `lazy_load=True`; review: yes.
- **Q8. The timeout per wait.** 30 s, no retry on 400 and 401; review: the same.
- **Q9. The GPU memory limit per worker.** Twice the measured peak; review: the same.
- **Q10. `from=` on the key line?** Yes, the staging host's address; review: yes.
- **Q12. Who on grace creates the service's account, installs its unit and adds the `Match` block?** Grace's admins, @weber coordinates (review).
- **Q13. JSON or base64 vectors.** JSON; review: JSON.
- **Q14. The search API's queries on grace.** Not now; if ever, its own URL and token (D10).
- **Q15. The template against the running unit.** User `ssh-tunnel`, the host key pinned against a fingerprint read on grace, `ConnectTimeout`; review: the same. `embed-tunnel.service` moves to `ssh-tunnel@embed` when @weber agrees.
