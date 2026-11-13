# Design

## Context

See proposal.md, "Why". What exists, read in the code on 2026-11-13 (metadata-warehouse at the submodule's `0b461ce`, v1.10.0; data-commons-search at `6c07bdc`; fastembed 0.8.0 as installed by the warehouse's `uv.lock`):

- **The warehouse's remote path.** `transform_core.py:43-44` reads `EMBED_API_KEY` and `EMBED_API_URL`; `transform_batch_impl` passes them to `add_embeddings_to_source` (`transform_core.py:234-241`). When the key, the URL and `EMBEDDING_MODEL` are set (`embedding_utils.py:200`), it calls `_embed` with the model name's last part (`bge-small-en-v1.5`, `:202`), no prefix and the whole batch as one request (`batch_size=len(batch)`, `:204-212`). `_embed` (`:96-167`) posts `{"model", "input"}` to `{base_url}/embeddings` with `Authorization: Bearer` (`:116,125-129`), sorts the answer by `index` (`:154`), retries 4 times with 1, 2, 4 s of backoff or the server's `Retry-After` (`:157-163`), with a timeout of 120 s per attempt (`:106`). On `requests.RequestException` or `RuntimeError` it logs `Embedding API failed after retries with, falling back to local model.` with the traceback and embeds locally (`:214-216`); a success logs `Embeddings calculated for bge-small-en-v1.5 from with API` (`:213`), the local path `calculating embeddings locally` (`:218`). Its error log masks the token (`:141-142`).
- **The catch.** `_embed` cuts each text to `text[:cap]` with `max_chars=1000` (`:104,127`) and halves the cap on a 400 that says `context length` (`:130-137`). The local path cuts nothing itself: fastembed's tokenizer truncates at `model_max_length`, 512 for this model (`fastembed/common/preprocessor_utils.py:39-52`, `tokenizer.enable_truncation(max_length=max_context)`; the model's `tokenizer_config.json`), counting `[CLS]` and `[SEP]`. Then the `[CLS]` token's output (`onnx_embedding.py:316-317`, `embeddings[:, 0]`), normalised (`:322`). A record whose embedding text (titles, subjects and descriptions joined, `embedding_utils.py:26-37`) has more than 1,000 characters but fewer than 512 tokens, or more than 1,000 characters before its 512th token, would get another vector from the remote path. English text has about 4 to 5 characters per token, so the cut at 1,000 characters falls at about 200 to 250 tokens: every long record would be affected.
- **Compose.** `EMBED_API_URL: ""` in `transform` (`docker-compose.yml:319`) and `airflow-worker-transform` (`:590`); `EMBED_API_KEY` is empty in `testconf/secrets/keys.env:5`. Only `airflow-worker-transform` embeds records: the DAG task `run_transform_batch` (`airflow/dags/transform_index.py:77-98`) is the only caller of `TransformResources` and `transform_batch_impl`. Each batch is a fresh process that loads the local model first (`transform_index.py:90-93`, `transform_core.py:64`, with patch 0002's `threads`), whether or not it will embed locally.
- **Stored vectors.** The warehouse stores every record's vector with `embedding_model = EMBEDDING_MODEL` (`transform_core.py:290,307,323`), the same for both paths: the database cannot tell later which path made a vector.
- **The benchmark** (`perf/grace-embedding/`, run on grace 2026-11-13): fastembed-gpu 0.8.0 on onnxruntime-gpu 1.31.1 (CUDA 13), the production file (`qdrant/bge-small-en-v1.5-onnx-q`, `model_optimized.onnx`, float16 weights, pinned revision `aa8f8b060edb00e03bfdd08813a2949946c8ba55`) on the GPU: minimum cosine 0.999989 to production's vectors, the float32 file 0.999990; short texts 50,059 texts/s at 2 workers × batch 256 (quick run, as reported to this change's author; the setup page `embedding-on-grace.md` quotes 68,600 short texts/s for the same day's quick run, to be reconciled with the result files); the tokenizer alone about 94,000 short texts/s on 72 threads. The full run's results will be in `.claude/field-tests/grace-results/` (not there yet when this was written). Its GPU sessions leave ONNX Runtime's CUDA options at their defaults except `gpu_mem_limit` (`bench.py:254-257`), so TF32 is on (`use_tf32`, "Default value: 1", ONNX Runtime's CUDA provider documentation, read 2026-11-13).
- **The tunnel pattern** (`deploy/beatepi/etc/systemd/system/er-c-data-smb.service`): `Type=simple`, `ssh -c aes128-ctr -o ServerAliveInterval=60 -o ExitOnForwardFailure=yes -N -L … -i /var/local/sshvpn/beatepivpn moellenstedtvpn@iff1020…`, `Restart=always`, `RestartSec=30s`, as root (no `User=`), with root's known hosts. Stable in production (@weber).
- **The prototype's setup** (`prototypes/search-stack/embedding-on-grace.md`, @weber, on `crawler` since 7272c1d5): the ports, the tunnel unit `embed-tunnel.service` with its `nologin` account `embedtunnel`, and a test of the tunnel before the service exists. It is the one home of the setup; this design refers to it (D7).
- **Staging's secrets.** `staging.env` sets `MODAMA_SECRETS_DIR=./testconf/secrets`, the committed throwaway values (staging runbook, settings).

## Goals / Non-Goals

Goals: the warehouse's vectors from grace's GPU, within D4's bound of the local path's, for every text length; an outage of grace or the tunnel costs time, never records, and shows; a tunnel template others can reuse.

Non-goals: a service for anyone but the warehouse (one model, one client); TLS and a network connection without the tunnel; tuning the warehouse around the freed CPU (larger batches, more processes), which follows from the measurement (D9).

## Decisions

### D1. The server: a small service of our own around fastembed-gpu

Agreement with the local path decides, then whether it runs on grace today, then how much of it is ours.

| | Our service (fastembed-gpu, onnxruntime-gpu) | Text Embeddings Inference (Hugging Face) | Infinity (michaelfeil) | vLLM | Triton Inference Server (NVIDIA) |
|---|---|---|---|---|---|
| Runs on GH200 (aarch64, Hopper) | yes: measured on grace, 2026-11-13 | no published image: aarch64 only as CPU (`cpu-arm64-1.9`) and Blackwell 12.1 (`121-1.9`, experimental); Hopper only x86_64 (`hopper-1.9`). For ARM64 with NVIDIA GPUs the README describes building `Dockerfile-cuda` with `--platform linux/arm64`; not tried | v3 image shown for NVIDIA SM80+, no arm64 named; v2 (`infinity-emb` 0.0.80) pins `onnxruntime-gpu<1.24,>=1.23.2`, which has no aarch64 wheels (those start at 1.29.0) | aarch64 only by building the image from source ("A docker container can be built for aarch64 systems such as the Nvidia Grace-Hopper", docs v0.25.0) | an arm64 (SBSA) container exists (release notes 2.67.0); not checked on GH200 |
| Model file and pipeline | the same ONNX file, tokenizer, truncation, `[CLS]` pooling and normalisation as the local path (fastembed's own code) | the CUDA backend is Candle, from the model's safetensors (`BAAI/bge-small-en-v1.5`); ONNX through `ort` is the CPU backend. Truncation at the model's maximum (`--auto-truncate`, default true); pooling from `1_Pooling/config.json` or `--pooling cls` | v3 LibTorch; v2 torch or optimum/ONNX | PyTorch weights; pooling models are supported "primarily for convenience" | the ONNX file through the ONNX Runtime backend; tokenizing, pooling and normalising would be a Python backend of ours |
| Vectors against the local path | measured: 0.999989 (production file), 0.999990 (float32 file) | not measured: other weights (float32 safetensors, run in float16 by default on GPU), other kernels | not measured | not measured | the same file; agreement depends on our pre- and post-processing |
| Protocol | OpenAI `/v1/embeddings`, as the warehouse speaks | OpenAI-compatible `/v1/embeddings` | `/v1/embeddings` | OpenAI-compatible | KServe v2: the warehouse's client would change |
| Licence | ours; fastembed Apache-2.0, ONNX Runtime MIT | Apache-2.0 | v3: "Infinity Restricted MIT License 1.0", "a custom source-available license"; v2 MIT | Apache-2.0 | BSD-3-Clause |

Sources, read 2026-11-13: TEI's [README](https://github.com/huggingface/text-embeddings-inference) and [supported models and hardware](https://huggingface.co/docs/text-embeddings-inference/supported_models) (version 1.9); Infinity's [README](https://github.com/michaelfeil/infinity) and [PyPI JSON](https://pypi.org/pypi/infinity-emb/json) (0.0.80); [vLLM docker docs v0.25.0](https://docs.vllm.ai/en/v0.25.0/deployment/docker/), and [pooling models](https://docs.vllm.ai/en/latest/models/pooling_models.html) as quoted in `docs/research/embedding-throughput.md` (not read again); Triton's arm64 container from search results on its release notes (for example [25.08](https://docs.nvidia.com/deeplearning/triton-inference-server/release-notes/rel-25-08.html); not read in full); Triton's licence from GitHub's licence API for `triton-inference-server/server`; onnxruntime-gpu's aarch64 wheels from `perf/grace-embedding/requirements-gpu.in`. `docs/research/embedding-throughput.md` has the throughput side of TEI, Infinity and vLLM.

**Lean: our own service.** It is the only option that runs on grace's GPU today from published packages, and the only one whose vectors are measured: it runs the code the local path runs, on the same file, so tokenizer, truncation, pooling and normalisation agree by construction and only the device's arithmetic differs (D4). Ours is the thin part: an HTTP endpoint in OpenAI's format (FastAPI and uvicorn, which upstream's warehouse and search API use), a token check, sorting by length and a lock. The rest is fastembed and ONNX Runtime.

**The strongest argument against:** "no new inventions". TEI is the established embeddings server, Apache-2.0, speaks the same protocol, batches by tokens without padding, and others maintain it. But on the GH200 it means building its CUDA image from source for aarch64 and compute capability 9.0, which nobody here has done, and its vectors come from other weights through other kernels, so the agreement would have to be measured from scratch. Our GPU does 50,000 short texts/s against staging's tens of records per second per process (D8): TEI's speed buys nothing here. **Re-evaluate** when TEI publishes an aarch64 Hopper image: the check instrument (D9) measures agreement and rate of any server that speaks the protocol, so a swap is one measurement.

### D2. Texts go uncut; the service truncates at tokens

The patch passes `max_chars=None` to `_embed`, which then sends each text whole; the service's tokenizer cuts at 512 tokens as the local one does (D1). On a 400 that says `context length` (a server that refuses long texts), the patch raises at once, and the batch falls back to local embedding, instead of halving a cap that no longer exists.

Alternatives:
- **Cut at tokens in the patch** (tokenize locally, keep 510 tokens, decode): decoding is not the inverse of tokenizing (spacing, accents, unknown tokens), so the vectors would move; and it costs tokenizer CPU on staging.
- **Send token IDs** (OpenAI's API allows arrays of token IDs as `input`): exact, but staging tokenizes again, the service must accept IDs, and our protocol would differ from what other servers commonly take as text.
- **Keep the 1,000 characters**: changes every long record's vector (Context).

The cost: long texts travel whole. A description of 20 kB in a batch of 250 adds 20 kB to a request of about 100 to 500 kB (texts) against a 2.1 MB answer (D8).

### D3. The same model file as the local path, with TF32 off

The service loads the pinned revision of `qdrant/bge-small-en-v1.5-onnx-q`, and the **float32 file** made from it (the benchmark's `prepare_model.py`, `to_fp32`; the change `embedding-fp32-model` makes the same file at image build with a script derived from it, its design D2), with ONNX Runtime's `use_tf32` off.

- **Relation to `embedding-fp32-model`** (worktree `agent-ac33b9c29c181d3e1`, not merged): that change moves the CPU path, and so the local fallback, to the float32 file (minimum cosine 0.99999963 to the production file, its E4/E5). This change does not depend on it: the service uses the float32 file either way, and its vectors are checked against whichever file the local path uses. If both land, the service and the fallback run the same file. The service takes the conversion script from that change once it is merged, and the benchmark's until then; the marker file of that change's D3 names the model in both places.
- **Why not the production file on the GPU:** it has float16 weights, so the GPU computes in float16. Its 0.999989 is below the bound of D4.
- **Why TF32 off:** with TF32 on (ONNX Runtime's default), float32 matrix products round their inputs to 10 bits of mantissa ("float32 inputs are rounded with 10 bits of mantissa", CUDA provider docs). That would explain why the float32 file gave only 0.999990 on the GPU against 0.99999963 on the CPU. A hypothesis, measured first (task 2.2).
- **Speed:** float32 without TF32 is slower than float16; the full run reports the float32 file at the GPU's best setting. At D8's rates even a tenth of 50,000 texts/s is far more than staging sends.

### D4. The bound: 0.99999, as `embedding-fp32-model`

Every pair of vectors, service against local, SHALL have a cosine of at least 0.99999 in float64 (spec, "The service's vectors agree with the local path's"). The same bound as the image build's check in `embedding-fp32-model` (its D4), so that one number governs what may sit side by side in the index. The benchmark's 0.9999 is ten times looser.

If the float32 file with TF32 off does not reach 0.99999 on the GPU (task 2.2), the choice goes to @weber (Q2): the looser 0.9999, backed by a ranking comparison like `embedding-fp32-model`'s E6 (the top results of fixed queries, the largest component difference against OpenSearch's scalar quantisation step), or float32 with whatever is left of the difference. The spec's number changes only with that decision.

### D5. On grace: systemd, an account of its own, a locked venv

**Decided (@weber, 2026-11-13): systemd for the prototype.** The service runs as `modama-embed.service`, a system unit with `User=modama-embed`, from a venv made with grace's Python 3.12 from the lock file (`requirements-gpu.txt`: the benchmark's packages plus FastAPI and uvicorn, with hashes). In `nvidia-smi` and `nvtop` its processes show under that account and the venv's path (`/opt/modama-embed/venv/bin/python …`), so people on grace see what holds the GPU. Users outside it keep using the GPU as before (@weber's condition).

- **Token:** a random token (`openssl rand -hex 32`) in `/etc/modama-embed/token`, root's, mode 0600, passed with `LoadCredential=token:/etc/modama-embed/token`; the service reads `$CREDENTIALS_DIRECTORY/token` ("The data is only accessible to the user associated with the unit", systemd.exec(5), "Added in version 247"; Ubuntu 24.04 has systemd 255, to check with `systemctl --version`). Not in the repository, not in the environment, not on a command line.
- **Restart:** `Restart=always`, `RestartSec=30s`, as the tunnel. With 30 s between starts, systemd's default start limit (5 starts in 10 s) is never reached.
- **GPU sharing:** the GPU stays shared: ONNX Runtime claims memory, not the device. NVIDIA's container FAQ: sharing a GPU "is no different than sharing a GPU between multiple processes outside of containers"; exclusive access only through the compute mode or MIG, which nobody sets for this. Each of the two workers caps its ONNX Runtime arena with `gpu_mem_limit` ("The size limit of the device memory arena in bytes … The total device memory usage may be higher", the CUDA context of about 0.5 GB per process on top). Lean for the value: twice the peak the full run measured at batch 256 for long texts, per worker (Q9). A batch beyond it gets 503, the warehouse falls back (spec).
- **No busy check.** The benchmark refuses to start while another process uses the GPU, for clean numbers. The service must not: sharing is the point. At start it logs the other compute processes `nvidia-smi --query-compute-apps` lists, for the record. When others need the whole GPU, `sudo systemctl stop modama-embed` is always safe: the warehouse falls back.
- **Two workers, one batch each at a time.** uvicorn with `--workers 2`, the benchmark's best for short texts (2 workers × batch 256); each worker holds one session and runs one batch on the GPU at a time (a lock), while the other tokenizes. Each request's texts are sorted by length and embedded in sub-batches of 256, the vectors returned in the request's order, as patch 0002 does locally.

**Docker later**, for a permanent service, with the NVIDIA Container Toolkit. Checked in NVIDIA's and Docker's documentation on 2026-11-13:
- The toolkit has arm64 packages: `nvidia-container-toolkit` 1.20.1-1 and 1.20.2-1 for `arm64` in NVIDIA's apt repository (`https://nvidia.github.io/libnvidia-container/stable/deb/arm64/Packages`); the supported-platforms table lists `arm64 / aarch64` (whether its Ubuntu 24.04 row covers arm64 could not be read from the page's text; the apt repository is per architecture, not per release).
- Setup: `sudo nvidia-ctk runtime configure --runtime=docker`, which "modifies the `/etc/docker/daemon.json` file", then `sudo systemctl restart docker` ([install guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html), toolkit 1.20.1-1). Docker's restart stops grace's running containers: "By default, when the Docker daemon terminates, it shuts down running containers"; live restore keeps them, but "If any of these daemon-level configuration options have changed, the live restore may not work" ([live restore](https://docs.docker.com/engine/daemon/live-restore/)). So the setup needs a window agreed with whoever runs containers on grace, unless the toolkit is configured there already (`docker info | grep -i runtimes`).
- A container gets the GPU with `--gpus all`, or in compose `deploy.resources.reservations.devices` with `driver: nvidia`, `count` or `device_ids`, `capabilities: [gpu]` ([compose GPU support](https://docs.docker.com/compose/how-tos/gpu-support/)); the page does not call this exclusive, and NVIDIA's FAQ says sharing works as between processes.
- Visibility: "`nvidia-smi` and NVML are not compatible with PID namespaces. We recommend monitoring your processes on the host or inside a container using `--pid=host`" ([toolkit FAQ](https://nvidia.github.io/container-wiki/toolkit/faq.html)). So the service's processes show in the host's `nvidia-smi` (and, presumably, `nvtop`, if it reads the processes through NVML as well: not checked), while a busy check run inside the container would see no processes, its own and others' alike.
- NVIDIA's test: `sudo docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi` ([sample workload](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/sample-workload.html)).

### D6. The service's interface

Spec, `embedding-service`. In short: `POST /v1/embeddings` (OpenAI's request and answer, `float` encoding only), Bearer token compared in constant time (`hmac.compare_digest`), 400 for another model, 503 when the GPU's memory runs out, `GET /health` without token (repository, revision, file, provider), bound to `127.0.0.1:7656` (the setup page's port, next to the crawler's 7654 and browse's 7655). One log line per request: texts, tokens, milliseconds, status; never text.

### D7. The tunnel: the setup page's, checked, and a template derived from it

**The prototype's tunnel is decided and set up** by @weber: `prototypes/search-stack/embedding-on-grace.md` (one home for the setup; not repeated here). The staging host runs `embed-tunnel.service` (`ssh -N -L 172.17.0.1:17656:127.0.0.1:7656`, plus `-L 172.17.0.1:11434:127.0.0.1:11434` for grace's chat model, which is not part of this change), as root with the key in `/var/local/sshvpn/`, into the `nologin` account `embedtunnel` on grace; the containers reach it as `host.docker.internal:17656` through `extra_hosts` with `host-gateway`. So the side that needs the service starts the connection, as beatepi does towards iff1020, and the account with the restricted key is on grace. The opposite direction (grace running `ssh -R` into staging) would put the key on grace, which several people share, and a stolen key could listen on staging's port in the service's place.

**The key's options, checked** against sshd(8) ("AUTHORIZED_KEYS FILE FORMAT") and sshd_config(5), OpenBSD's manual pages read 2026-11-13, and against OpenSSH 10.0p2's `sshd` in the VM: a throwaway server on 127.0.0.1 (non-root, `UsePAM no`, its own host key and `authorized_keys`), the real `ssh` client, two `socat` listeners as the permitted and a forbidden destination. Results, with the page's line (`restrict,port-forwarding,permitopen=…`) and an account that has a shell (the VM's user):

| Attempt | Page's line | + `command="/usr/sbin/nologin"`, a second `permitopen` | + `Match` block `AllowTcpForwarding local` |
|---|---|---|---|
| `ssh host id -un` | **ran** (`dev`) | refused: "This account is currently not available." | refused |
| `-N -L` to the permitted address | works | works, both addresses | works |
| `-N -L` to another port | refused ("the request was denied" in the log) | refused | refused |
| `-N -L` naming `localhost` instead of `127.0.0.1` | refused | refused | refused |
| `-N -R 127.0.0.1:47656:…` | **listener opened on the far end** | **opened** | refused ("remote port forwarding failed") |

- `restrict`: "Enable all restrictions, i.e. disable port, agent and X11 forwarding, as well as disabling PTY allocation and execution of ~/.ssh/rc". It does not stop a command or a shell: the page's "turns off everything (shell, …)" was wrong. `nologin` as the shell stops them, and the forced command `command="/usr/sbin/nologin"` ("the command is executed whenever this key is used for authentication. The command supplied by the user (if any) is ignored") stops them even if the shell were changed. The tunnel's `-N` ("Do not execute a remote command. This is useful for just forwarding ports", ssh(1)) opens no session, so the forced command never runs for it.
- `port-forwarding`: "Enable port forwarding previously disabled by the restrict option", in both directions: `no-port-forwarding` "Forbids TCP forwarding", and the test opened a remote listener. `permitopen` limits only `-L`; `permitlisten` would limit `-R`, but `permitlisten="none"` is not accepted in a key line (the key was rejected). sshd_config(5) has it: `AllowTcpForwarding local` ("to allow local (from the perspective of ssh(1)) forwarding only"), allowed in a `Match` block. Without it, someone with the key could listen on grace's `127.0.0.1:7656` while the service is down, and the warehouse's requests, token and texts would go to them.
- `permitopen="host:port"`: "No pattern matching or name lookup is performed on the specified hostnames, they must be literal host names and/or addresses", so the unit's `-L` names `127.0.0.1` as the key line does. "Multiple permitopen options may be applied separated by commas": checked, both forwards worked.
- So the far end gets: `restrict,port-forwarding,permitopen="127.0.0.1:7656",permitopen="127.0.0.1:11434",command="/usr/sbin/nologin"` and, in `sshd_config`, `Match User embedtunnel` / `AllowTcpForwarding local`. **Done in this change:** the setup page corrected accordingly (its section "On grace: the tunnel's account").
- Lean (Q10), beyond that: `from="<staging's address>"` ("in addition to public key authentication, either the canonical name of the remote host or its IP address must be present"), so that the key works only from the staging host.
- grace's `sshd` must allow local forwarding for the account at all: `sudo sshd -T -C user=embedtunnel | grep -iE 'allowtcpforwarding|disableforwarding|permitopen'` shows what applies to it.

**The template**, `deploy/ssh-tunnel/ssh-tunnel@.service`, derived from the page's unit and beatepi's, with what a reusable unit needs on top:

```ini
[Unit]
Description=SSH tunnel %i (forwards in /etc/ssh-tunnel/%i.conf)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=ssh-tunnel
EnvironmentFile=/etc/ssh-tunnel/%i.conf
ExecStart=/usr/bin/ssh -N -i /etc/ssh-tunnel/%i/key \
    -o BatchMode=yes -o IdentitiesOnly=yes \
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
- New against the page's and beatepi's units (lean, Q15): `User=ssh-tunnel` instead of root, since `ssh` needs no privilege for ports above 1024; `BatchMode=yes` and `StrictHostKeyChecking=yes` with a known-hosts file per instance, filled from `ssh-keyscan` and compared with the far end's fingerprint, instead of accepting the host key once by hand as root (fail rather than wait for a prompt or take a new host key; ssh_config(5)); `IdentitiesOnly=yes` (only this key). A port below 1024, as beatepi's 445, needs a drop-in with `AmbientCapabilities=CAP_NET_BIND_SERVICE`; an address that exists only once Docker is up gets `After=docker.service` in a drop-in, as the page's unit has it, and otherwise the restart every 30 s covers it.
- `ServerAliveInterval=60` with the default `ServerAliveCountMax` of 3: a dead connection ends `ssh` after about 3 minutes (spec: within about 4).
- **To check against @weber's version** from his other hosts once he sends it (task 4.5): the differences go into the README or the template.

The README (`deploy/ssh-tunnel/README.md`), derived from the setup page's steps: the far end's account (`useradd --system --create-home --shell /usr/sbin/nologin <account>`, its `.ssh` 0700 and `authorized_keys` 0600, owned by it), the key line with the options above and the `Match` block, what each does (the table above, shortened), the key (`ssh-keygen -t ed25519 -N ''`, made on the client, never copied elsewhere), the known-hosts line, install, `systemctl enable --now ssh-tunnel@NAME`, logs (`journalctl -u ssh-tunnel@NAME`), and how to check the restrictions (the spec's scenarios, by hand). The setup page then points to it for the general part, so that each fact has one home.

### D8. Throughput and transfer

**Answer size,** measured with Python's `json` on 250 unit vectors of 384 float32 values, written as the warehouse's `tolist()` writes them (each value widened to a double): 2,119,420 bytes per 250 vectors, 8.5 kB per vector; with zlib at level 1, 0.97 MB; as base64 of the float32 bytes (OpenAI's `encoding_format: "base64"`), 0.53 MB, 2.1 kB per vector. (The "about 1 MB per 250" estimated when this change was asked for is about what compression, or a writer of the shortest float32 representation, gives.)

**Estimates, not measured:**
- What the GPU could deliver, 50,000 short texts/s, is 425 MB/s as JSON: more than a 1 Gbit/s link (about 117 MB/s, about 14,000 vectors/s as JSON, 55,000 as base64), and probably more than one SSH connection's encryption on one core. So at the GPU's speed the tunnel caps it.
- What staging sends is far less. Today a batch process does tens of records per second (F9: 33 records/s per process, measured before patches 0001 to 0003; since then the embedding is about 91 % of a batch's CPU). Without the embedding, a batch of 250 is the process start, the normalising, validating and the writes: if that is 1 to 3 s, 16 processes send 1,300 to 4,000 records/s, 11 to 34 MB/s of JSON, within a 1 Gbit/s link and, plausibly, one SSH connection. The GPU then idles most of the time.
- So the tunnel is not expected to cap the indexing; the warehouse's other steps are (D9 measures it). base64 halves nothing that matters until then; it stays a lever (a patch reading `encoding_format: "base64"`) if the measurement shows transfer above a tenth of a batch's time.
- The link between staging and grace and the SSH connection's rate are unknown: the check instrument measures MB/s through the tunnel at 1, 4 and 16 concurrent requests (task 3.2).

### D9. The prototype's measurement on staging

@weber (2026-11-13): the benchmark compared grace's CPU with its GPU; staging and production run on an AMD EPYC, so staging's real indexing throughput before and after decides. And once the embedding is no longer about 91 % of the transform's CPU, the other steps set the pace: the measurement must show which.

Instruments, existing first: `field-test/batch-times.sh` (per batch: model load, batch time; with this change, service or fallback), `field-test/indexing-probe.py` (each batch process's CPU, threads, memory every 10 s; `py-spy dump` of the busiest), `perf/phase-timer.py` (wall and CPU seconds per transform step on one real batch, without writing: XML parse and normalise, validate, embedding text, embed, bulk preparation; the writes are the batch time less the steps' sum), `monitor.sh` (each container's CPU: the warehouse's PostgreSQL and OpenSearch), `modama-chain status` (no crawl, harvest or indexing running), on grace `nvidia-smi dmon -s um` and the service's request log, and the new `check.py` (agreement, rate and MB/s through the tunnel).

Steps (the runbook gets them as commands, task 7):
1. Quiet: `modama-chain status` shows no crawl, harvest or indexing running; the timer's next crawl is hours away.
2. Before: a re-index of the last full harvest run, `warehouse_transform_index` with that `harvest_run_id` and `reuse_embeddings` off, with the probes running, for 30 minutes; then the run is stopped. `phase-timer.py` on one batch of 250.
3. Switch: `EMBED_API_URL` in `staging.env`, the token in the new secrets folder's `keys.env`, `docker compose up -d airflow-worker-transform`; `check.py` from inside the worker: agreement and rate through the tunnel.
4. After: the same re-index from the start, the same probes, 30 minutes, then let it finish (which gives every record a vector from the service; Q4). `phase-timer.py` on the same batch.
5. An outage on purpose: `sudo systemctl stop embed-tunnel` for 10 minutes during the re-index: batches fall back (`batch-times.sh`), none fails; start it again.
6. Vectors: the stored vectors of the same 1,000 records from steps 2 and 4 (by record identifier, `perf/wrap/embcmp.py`'s comparison), minimum cosine and largest component difference.

What it reports: records/s over the two windows, wall and CPU seconds per batch on staging, the per-step table before and after (which step is now the largest), the PostgreSQL's and OpenSearch's CPU, the GPU's busy share, MB/s through the tunnel, fallbacks, the vectors' agreement. Into `design/field-tests/search-stack-staging-findings.md` as a finding.

### D10. The search API's query embedding: later, and what it would need

`data-commons-search` embeds a query through the API only when `embed_api_model` is set (`mcp_server.py:133-146`), with `embed_api_url` and `embed_api_key` (`config.py:80-81`), `httpx`, 30 s timeout, 3 attempts, then the local model (`embeddings.py:20-24,46-84,87-109`). It would need: `EMBED_API_MODEL=bge-small-en-v1.5`, the URL and a token for the search API (a second token, so either side can be revoked alone), the tunnel's port reachable from `search-api`, and a shorter timeout, since a query waits for it: a hanging service would hold a search for up to about 90 s before the fallback. A catch: the same URL and key also send `/rerank` (`embeddings.py:138-155`, `_post("rerank", …)` to `embed_api_url`), which our service does not answer; today, without a key, reranking is skipped, and with one each search would log a failed rerank. The gain is small: a query embeds in 8 to 17 ms on one thread on the VM (stack README, "CPU budget"). Lean: leave it local, unless grace also serves a reranker.

### D11. Security

- **Record texts travel to grace**, which is ER-C's: inside the institute (requirements-pipeline 2.9). Over the network inside SSH; on grace over the loopback to the service, which keeps nothing and logs no text. grace's administrators can see a running process's memory: they are ER-C's.
- **The token** guards the service against other users and processes on grace, which reach `127.0.0.1:7656` too, and against anyone on the staging host or in its containers who reaches `172.17.0.1:17656`. It lives in `/etc/modama-embed/token` on grace (root, 0600, given to the service by `LoadCredential`) and in `keys.env` of staging's secrets folder. **Staging's secrets folder moves out of the checkout first**: today `MODAMA_SECRETS_DIR=./testconf/secrets`, committed, in the shared checkout that staging builds from, so a token there would show in `git status` and could be committed. Like the end-to-end test's key: a copy in `~/.config/modama/staging-secrets` (mode 700), `MODAMA_SECRETS_DIR` pointing there. To check that it is set without printing it: `grep -c '^EMBED_API_KEY=.' <folder>/keys.env`.
- **The SSH key** is made on the staging host and never leaves it (root's, in `/var/local/sshvpn/`, per the setup page); on grace it opens only the local forwards to the service's and the chat model's ports, with no command and no remote forward, on an account without a shell (D7, checked). grace's host key is accepted once by hand per the page; the template pins it in a known-hosts file per instance (Q15).
- **No secrets in Git:** the repository holds the unit files, the README and examples with placeholders; tests make throwaway keys and tokens in temporary folders.
- **Later, a network connection without the tunnel** needs TLS and a firewall rule, and the service then listens on more than loopback: out of scope here, a change of its own.

## Risks / Trade-offs

- [The float32 file with TF32 off does not reach 0.99999 on the GPU] → measured first (task 2.2); then Q2 for @weber, with a ranking comparison.
- [A hanging service makes every batch wait] → the patch's timeout of 30 s per attempt: at most about 2 minutes per batch before the fallback (4 attempts, 1 + 2 + 4 s between them), against 8 minutes with upstream's 120 s. A batch runs at most an hour (`execution_timeout`). Visible in `batch-times.sh`.
- [All batch processes fall back at once] → the CPU budget still sizes them for local embedding (README, "CPU budget"), so that is today's load, not more.
- [Fallback vectors and service vectors side by side] → the same model and file, within the bound (D4); the database labels both `BAAI/bge-small-en-v1.5` and cannot tell them apart, the batch logs can.
- [Others on grace need the GPU] → the memory cap, the service visible under its own account, and `systemctl stop` as the always-safe way out.
- [The tunnel binds an address that only exists once Docker is up] → `ExitOnForwardFailure` and a restart every 30 s; a drop-in `After=docker.service`.
- [The template's differences from @weber's running version] → checked when he sends it (task 4.5).
- [Grace's `sshd` forbids forwarding globally, or its admins do not want the `Match` block] → checked first (task 1.2); a change there is grace's admins' decision. Without the block, the key allows remote forwards (D7): then the service must not be the only thing that guards its port while it is down, a reason to keep it running or to stop the tunnel with it.

## Migration Plan

1. grace: the tunnel's account corrected, the service's account, the venv, the model files, the token, the unit (tasks 1, 2.4); the service answers `GET /health` through the tunnel.
2. staging: the secrets folder outside the checkout, the tunnel instance (task 5), the before measurement, the switch, the after measurement (D9).
3. **Rollback** at any time: `EMBED_API_URL=` (empty) in `staging.env`, `docker compose up -d airflow-worker-transform`; the next batches embed locally (spec, "The way back is an empty URL"). Vectors already indexed from the service stay; they agree within the bound. The tunnel and the service can stay or go: `systemctl disable --now embed-tunnel` on staging (it also carries the chat model's forward), `systemctl disable --now modama-embed` on grace.

## Open Questions

Each with the lean the tasks assume; @weber decides.

- **Q1. Our service or TEI built from source?** Lean: our service (D1). Against: TEI is the established server; re-evaluate when it publishes an aarch64 Hopper image.
- **Q2. The bound if float32 without TF32 misses 0.99999 on the GPU.** Lean: measure first; if it misses, 0.9999 with a ranking comparison (D4).
- **Q3. The model file.** Lean: the float32 file on the GPU with TF32 off, whatever the local path uses (D3); the service takes `embedding-fp32-model`'s script once that is merged.
- **Q4. Re-index after the switch?** Lean: no extra re-index; the after measurement's full run (D9, step 4) re-embeds every record anyway. Afterwards only changed records get new vectors, as now.
- **Q5, Q6 and Q11, decided** by @weber's setup page: the staging host runs the tunnel into `embedtunnel` on grace; it listens on `172.17.0.1:17656`, reached as `host.docker.internal`; the service's port is 7656.
- **Q7. Load the local model only when needed?** Lean: yes, `lazy_load=True` in the patch: a batch that the service embeds then skips the 0.2 to 0.3 s model load (F9) and the model's memory; a fallback loads it then.
- **Q8. The warehouse's timeout per attempt.** Lean: 30 s (a batch of 250 takes well under a second on the GPU), so a hang costs about 2 minutes per batch.
- **Q9. The GPU memory limit per worker.** Lean: twice the peak the full run measured at batch 256 for long texts.
- **Q10. `from=` on the key line, beyond the corrected line?** Lean: yes, the staging host's address.
- **Q12. Who on grace creates the service's account, installs its unit and adds the `Match` block to `sshd_config`** (root needed)? @weber or grace's admins.
- **Q13. JSON or base64 vectors.** Lean: JSON, as the warehouse reads it today; base64 only if D9 shows transfer above a tenth of a batch's time.
- **Q14. The search API's queries on grace.** Lean: not now (D10).
- **Q15. The template against the running unit.** Lean: the template runs as an account `ssh-tunnel`, not root, with a pinned known-hosts file per instance and `BatchMode`; `embed-tunnel.service` moves to `ssh-tunnel@embed` once the template's tests pass and @weber agrees. Against: root with the key in `/var/local/sshvpn/` is what runs, stable, on beatepi.
