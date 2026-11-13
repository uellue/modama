# The embedding service on grace

The warehouse's embedding on grace's GPU (NVIDIA GH200), reached from the staging host
through an SSH tunnel: OpenAI's `POST /v1/embeddings` for `bge-small-en-v1.5`, with the same
model file, tokenizer, truncation at 512 tokens, pooling and normalisation as the
warehouse's local path (fastembed's own code), on ONNX Runtime's CUDA provider with TF32 off.
It listens on grace's `127.0.0.1:7656` only and needs a token. Change
`embedding-service-grace` in `python/crawler/openspec/changes/`; the setup of the whole
prototype, with the runbook for grace and staging, is
[`../embedding-on-grace.md`](../embedding-on-grace.md).

**For people on grace:** the service runs as `modama-embed.service` under the account
`modama-embed`: `nvidia-smi` and `nvtop` show its two processes as
`/opt/modama-embed/venv/bin/python` of that user. It shares the GPU: its two workers hold
at most `MODAMA_EMBED_MEM_LIMIT` bytes each for ONNX Runtime, plus CUDA's context of about
0.5 GB each, and use the GPU while staging indexes. **Stopping it is always safe**:
`sudo systemctl stop modama-embed`; the warehouse then embeds on staging's CPU, slower, and
loses nothing. `sudo systemctl start modama-embed` brings it back.

## Files

| File | What |
|---|---|
| `server.py` | the service (Starlette and uvicorn); `server.py fetch` downloads the pinned model files |
| `modama-embed.service` | its systemd unit |
| `requirements-gpu.in`, `requirements-gpu.txt` | its packages for grace, and their lock file (aarch64, Python 3.12, with hashes) |
| `measure.py` | on grace, before the switch: TF32 on and off against grace's CPU, the GPU memory of one worker |
| `check.py` | on staging: the service's vectors against the warehouse's local path, its rate, snapshots of stored vectors |
| `requirements-cpu.in`, `requirements-cpu.txt`, `tests/` | the tests in the development VM, on the CPU |

## What it answers

- `POST /v1/embeddings` with `Authorization: Bearer <token>` and `{"model": "bge-small-en-v1.5",
  "input": [texts]}`: `{"object": "list", "data": [{"object": "embedding", "index": i,
  "embedding": [384 numbers]}, …], "model": …, "usage": …}`, one unit vector per text in the
  order of `input`. A text over 512 tokens is embedded from its first 512, as locally.
- 401 without the token or with another; 400 for another model (naming the one it serves),
  a body that is not `{"input": [strings]}`, or an `encoding_format` other than `float`; 503
  when ONNX Runtime runs out of its memory for a request (the warehouse then embeds that
  batch locally).
- `GET /health`, without token: the model's repository, revision, file and the execution
  provider (`CUDAExecutionProvider` on grace).
- One log line per request in the journal: status, texts, tokens, milliseconds. Never a text,
  never a token.

The texts of a request are sorted by length and embedded in sub-batches of 256; each worker
runs one sub-batch on the GPU at a time.

## Install on grace

As root, from a copy of this folder and of `../perf/grace-embedding/gen_texts.py` (for
`check.py` and `measure.py`), for example:

```bash
# on a machine with the checkout:
rsync -aR prototypes/search-stack/./embedding-service prototypes/search-stack/./perf/grace-embedding/gen_texts.py grace:modama-embed-src/
# on grace:
cd ~/modama-embed-src/embedding-service
```

**The venv**, with grace's Python 3.12 (the lock file's; `python3.12 --version`), as for
the benchmark (`../perf/grace-embedding/README.md`, Setup):

<!-- run: grace -->
```bash
install -d -m 755 /opt/modama-embed
python3.12 -m venv /opt/modama-embed/venv
/opt/modama-embed/venv/bin/pip install --no-cache-dir --require-hashes -r requirements-gpu.txt   # about 2 GB of CUDA libraries
/opt/modama-embed/venv/bin/python -c "import onnxruntime as o; o.preload_dlls(); print(o.__version__, o.get_available_providers())"
# 1.31.1 [..., 'CUDAExecutionProvider', 'CPUExecutionProvider']
```

**The account, the service's file and the model files** (the pinned revision of the file
the warehouse's local path loads; `server.py`'s `REPOSITORY`, `REVISION`):

<!-- run: grace -->
```bash
getent passwd modama-embed || useradd --system --create-home --shell /usr/sbin/nologin modama-embed
install -m 644 server.py /opt/modama-embed/server.py
install -d -m 755 -o modama-embed -g modama-embed /opt/modama-embed/cache
runuser -u modama-embed -- env MODAMA_EMBED_CACHE=/opt/modama-embed/cache /opt/modama-embed/venv/bin/python /opt/modama-embed/server.py fetch
```

**The memory limit**, before the first start: `measure.py` (as yourself, about 5 minutes,
on the GPU; it also says whether TF32 matters, task 2.2 of the change):

```bash
MODAMA_EMBED_CACHE=/opt/modama-embed/cache /opt/modama-embed/venv/bin/python measure.py \
    ~/grace-embedding/cache/variants/model-fp32.onnx /opt/modama-embed/cache/models--qdrant--bge-small-en-v1.5-onnx-q/snapshots/aa8f8b060edb00e03bfdd08813a2949946c8ba55/model_optimized.onnx
```

Its last line, `GPU memory of one worker after 512 long texts in sub-batches of 256: N MiB`,
gives the limit: twice N, in bytes (`limit=$((2 * N * 1024 * 1024))`), per worker (design
Q9).

**The token, the unit and the limit**, then start:

<!-- run: grace -->
```bash
limit=<twice N MiB, in bytes>
install -d -m 700 /etc/modama-embed
(umask 077 && openssl rand -hex 32 > /etc/modama-embed/token)
install -m 644 modama-embed.service /etc/systemd/system/modama-embed.service
mkdir -p /etc/systemd/system/modama-embed.service.d
printf '[Service]\nEnvironment=MODAMA_EMBED_MEM_LIMIT=%s\n' "$limit" > /etc/systemd/system/modama-embed.service.d/limit.conf
systemctl daemon-reload
systemctl enable --now modama-embed
```

The token never goes into the repository, an environment or a command line: the unit hands
it to the service with `LoadCredential` (only the unit's user can read it, systemd.exec(5);
systemd 247 or newer, `systemctl --version`). The same token goes into staging's `embed.env`
(`../embedding-on-grace.md`, runbook); copy it without printing it to a terminal that is
recorded.

## Check, logs, stop

```bash
systemctl status --no-pager modama-embed
curl -s 127.0.0.1:7656/health        # ..."provider":"CUDAExecutionProvider"
ss -ltn | grep 7656                  # 127.0.0.1:7656 only
nvidia-smi                           # two processes /opt/modama-embed/venv/bin/python
journalctl -u modama-embed -f        # one line per request
sudo systemctl stop modama-embed     # always safe: the warehouse falls back
```

At start each worker logs the model, its provider, its limit and the other processes on the
GPU (no busy check: the GPU is shared). The service restarts 30 s after it ends without a
stop (`Restart=always`). It writes only to `/opt/modama-embed/cache` (CUDA's kernel cache),
with no home and no new privileges (`ProtectSystem=strict`, `ProtectHome`,
`NoNewPrivileges`, `PrivateTmp`); if a start fails with a read-only file system, those lines
of the unit are the place to look.

## Before anything beyond the demo

The port is unprivileged for the demo (@weber, 2026-11-13, item 349): while the service is
stopped, any user on grace could listen on `127.0.0.1:7656` and receive the warehouse's
requests with the token, or answer with forged vectors. The next step: a port below 1024
(755 to 757 are unassigned at IANA), with the capability to bind it, and `permitopen`,
`PermitOpen` and the tunnel's forward changed to match:

```ini
# systemctl edit modama-embed
[Service]
AmbientCapabilities=CAP_NET_BIND_SERVICE
ExecStart=
ExecStart=/opt/modama-embed/venv/bin/python /opt/modama-embed/server.py serve --host 127.0.0.1 --port 755 --workers 2
```

(`net.ipv4.ip_unprivileged_port_start` must be at its default of 1024 on grace.)

## check.py on staging

Inside the transform worker's image, with its environment (the token from `embed.env`, never
on the command line), in a one-off container that leaves the running worker alone; from
`prototypes/search-stack/` on the staging host, with the runbook's `dc` shorthand:

```bash
chk() { dc run --rm --no-deps -T -v "$PWD:/stack:ro" --entrypoint /opt/airflow/transform-venv/bin/python airflow-worker-transform /stack/embedding-service/check.py "$@"; }
chk sets             # agreement, 512 texts per set (short, mixed, long, over 512 tokens); exit 0: all pass
chk rate             # texts/s and MB/s, requests of 2,000 texts, 1, 4 and 16 at once
```

`sets` prints per set the minimum cosine, the largest component difference and the top-10
overlap of the ranking check, and passes a set by design D4: minimum cosine at least
0.99999, or largest difference below 1e-3 and overlap at least 0.997. The local side is the
warehouse's `_embed_locally` on staging's CPU, the production path.

Snapshots of stored vectors, with the read-only role in the crawler's container, into a
folder outside the checkout:

```bash
mkdir -p ~/embed-check
dc exec -T crawler python - snapshot < embedding-service/check.py > ~/embed-check/before.jsonl
# ... after the re-index:
dc exec -T crawler python - snapshot < embedding-service/check.py > ~/embed-check/after.jsonl
dc run --rm --no-deps -T -v "$PWD:/stack:ro" -v ~/embed-check:/check:ro --entrypoint /opt/airflow/transform-venv/bin/python \
    airflow-worker-transform /stack/embedding-service/check.py compare /check/before.jsonl /check/after.jsonl
```

`snapshot` takes 1,000 records chosen by the hash of their identifiers (`md5`), the same ones
each time; `compare` compares those whose datestamp did not change.

## Tests (development VM, CPU)

```bash
cd prototypes/search-stack/embedding-service
export TMPDIR=/var/tmp/embed/tmp MODAMA_EMBED_CACHE=/var/tmp/embed/cache FASTEMBED_CACHE_DIR=/var/tmp/embed/fastembed
mkdir -p "$TMPDIR"
uv venv --seed --python 3.12 /var/tmp/embed/venv
/var/tmp/embed/venv/bin/pip install --require-hashes -r requirements-cpu.txt
/var/tmp/embed/venv/bin/python server.py fetch
/var/tmp/embed/venv/bin/pip install onnx==1.23.2 && FASTEMBED_CACHE_DIR=$MODAMA_EMBED_CACHE /var/tmp/embed/venv/bin/python ../perf/grace-embedding/prepare_model.py   # the int8 file of test_check.py
/var/tmp/embed/venv/bin/python -m pytest --basetemp /var/tmp/embed/pytest tests/test_server.py
# the warehouse's side and check.py in a venv like the image's transform venv (its uv.lock), with the patched code:
cp ../../EOSC-Data-Commons/metadata-warehouse/{pyproject.toml,uv.lock} /var/tmp/embed/
UV_PROJECT_ENVIRONMENT=/var/tmp/embed/transform-venv uv sync --project /var/tmp/embed --frozen --no-dev --no-install-project
uv pip install --python /var/tmp/embed/transform-venv/bin/python pytest==9.0.2
EMBED_SERVICE_PYTHON=/var/tmp/embed/venv/bin/python /var/tmp/embed/transform-venv/bin/python -m pytest --basetemp /var/tmp/embed/pytest tests/test_warehouse.py tests/test_check.py
tests/unit.sh        # the unit in a throwaway systemd container, on the CPU (Docker)
rm -rf /var/tmp/embed
```

The tests start the service as a real process and talk to it with `requests`, the
warehouse's client; the warehouse's tests apply `../patches/warehouse/` to the submodule's
code in order, as the image build does. Without `MODAMA_EMBED_CACHE` and its model files they
fail, saying so. `test_warehouse.py`'s hanging server takes about 2 minutes (4 waits of 30 s).
With the CPU provider ONNX Runtime enforces no arena limit, so the memory test raises ONNX
Runtime's out-of-memory error in place of the GPU's; the limit itself is checked on grace.
