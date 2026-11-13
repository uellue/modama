"""The warehouse's embedding on grace's GPU: OpenAI's POST /v1/embeddings for
bge-small-en-v1.5, with fastembed's own tokenizer, truncation, pooling and normalisation
on ONNX Runtime (change embedding-service-grace, python/crawler/openspec/changes/; README.md
next to this file).

  server.py fetch     download the pinned model files into MODAMA_EMBED_CACHE (once, at install)
  server.py serve [--host 127.0.0.1] [--port 7656] [--workers 2]

Environment:
  MODAMA_EMBED_CACHE       the model's files and CUDA's kernel cache (default: ./cache here)
  MODAMA_EMBED_MEM_LIMIT   bytes per worker for ONNX Runtime's arena on the GPU (required for
                           cuda; CUDA's own context of about 0.5 GB comes on top)
  MODAMA_EMBED_DEVICE      cuda (default) or cpu (the tests)
  MODAMA_EMBED_MODEL_FILE  another ONNX file instead of the pinned model_optimized.onnx (the
                           check of a file that moves the vectors; the float32 file later)
  CREDENTIALS_DIRECTORY    systemd's (LoadCredential=token:...): the token is its file `token`
"""

import argparse
import hmac
import json
import logging
import os
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

# the model the warehouse names (EMBEDDING_MODEL's last part, embedding_utils.py), and the
# files fastembed loads for BAAI/bge-small-en-v1.5, pinned as in perf/grace-embedding/bench.py
MODEL = "bge-small-en-v1.5"
FASTEMBED_MODEL = "BAAI/bge-small-en-v1.5"
REPOSITORY = "qdrant/bge-small-en-v1.5-onnx-q"
REVISION = "aa8f8b060edb00e03bfdd08813a2949946c8ba55"
FILES = ["config.json", "tokenizer.json", "tokenizer_config.json"]
FILES += ["special_tokens_map.json", "model_optimized.onnx"]
# texts per run on the device: the benchmark's best for short texts (2 workers x batch 256)
SUB_BATCH = 256
HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("MODAMA_EMBED_CACHE", HERE / "cache"))
# Hugging Face's caches and CUDA's kernel cache in CACHE too, not in a home directory
os.environ["HF_HOME"] = str(CACHE / "hf")
os.environ["HF_XET_CACHE"] = str(CACHE / "hf" / "xet")
os.environ["CUDA_CACHE_PATH"] = str(CACHE / "cuda")

log = logging.getLogger("modama-embed")


class ConfigError(Exception):
    pass


@dataclass
class Settings:
    token: str
    device: str
    mem_limit: int | None
    model_dir: Path
    model_file: Path


def model_dir() -> Path:
    return CACHE / f"models--{REPOSITORY.replace('/', '--')}" / "snapshots" / REVISION


def settings() -> Settings:
    """The settings from the environment; ConfigError names what is wrong."""
    creds = os.environ.get("CREDENTIALS_DIRECTORY")
    if not creds:
        raise ConfigError(
            "no CREDENTIALS_DIRECTORY: start the service with LoadCredential=token:... (modama-embed.service)"
        )
    try:
        token = (Path(creds) / "token").read_text().strip()
    except OSError as e:
        raise ConfigError(f"cannot read the token: {e}") from None
    if not token:
        raise ConfigError(f"the token file {Path(creds) / 'token'} is empty")
    device = os.environ.get("MODAMA_EMBED_DEVICE", "cuda")
    if device not in ("cuda", "cpu"):
        raise ConfigError(f"MODAMA_EMBED_DEVICE is {device!r}, not cuda or cpu")
    raw = os.environ.get("MODAMA_EMBED_MEM_LIMIT", "")
    mem_limit = None
    if raw:
        if not raw.isdigit() or int(raw) == 0:
            raise ConfigError(
                f"MODAMA_EMBED_MEM_LIMIT is {raw!r}, not a number of bytes"
            )
        mem_limit = int(raw)
    elif device == "cuda":
        raise ConfigError(
            "MODAMA_EMBED_MEM_LIMIT is not set: the bytes per worker on the GPU (README.md, Install)"
        )
    folder = model_dir()
    missing = [f for f in FILES if not (folder / f).exists()]
    if missing:
        raise ConfigError(
            f"model files missing in {folder}: {', '.join(missing)}; run `server.py fetch` first"
        )
    file = Path(os.environ.get("MODAMA_EMBED_MODEL_FILE") or folder / FILES[-1])
    if not file.is_file():
        raise ConfigError(f"MODAMA_EMBED_MODEL_FILE {file} is not a file")
    return Settings(token, device, mem_limit, folder, file)


class Model:
    """fastembed's TextEmbedding with a session of ours: the same tokenizer, truncation at
    512 tokens, [CLS] pooling and normalisation as the warehouse's local path; ONNX Runtime's
    CUDA provider with TF32 off and the arena's limit (tf32: on, for measure.py only)."""

    def __init__(self, s: Settings, tf32: bool = False):
        import onnxruntime as ort
        from fastembed import TextEmbedding
        from fastembed.common.preprocessor_utils import load_tokenizer

        if s.device == "cuda":
            options = {"use_tf32": "1" if tf32 else "0"}
            if s.mem_limit:
                options["gpu_mem_limit"] = str(s.mem_limit)
            providers = [("CUDAExecutionProvider", options)]
        else:
            providers = ["CPUExecutionProvider"]
        outer = TextEmbedding(
            FASTEMBED_MODEL,
            cache_dir=str(CACHE),
            specific_model_path=str(s.model_dir),
            lazy_load=True,
        )
        self.inner = outer.model
        so = ort.SessionOptions()  # as fastembed sets it up
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.inner.tokenizer, self.inner.special_token_to_id = load_tokenizer(
            s.model_dir
        )
        self.inner.model = ort.InferenceSession(
            str(s.model_file), sess_options=so, providers=providers
        )
        self.provider = self.inner.model.get_providers()[0]
        if s.device == "cuda" and self.provider != "CUDAExecutionProvider":
            raise ConfigError(
                f"the session runs on {self.provider}, not on the GPU (ONNX Runtime fell back)"
            )
        self.file = s.model_file.name
        # one run on the device at a time in this worker; the other worker tokenizes meanwhile
        self.lock = threading.Lock()

    def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        """The vectors in the order of `texts`, and the number of tokens: sorted by length
        and run in sub-batches, so that a sub-batch is padded to texts of similar length."""
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        vectors: list[list[float]] = [[] for _ in texts]
        tokens = 0
        for start in range(0, len(order), SUB_BATCH):
            part = order[start : start + SUB_BATCH]
            with self.lock:
                out = self.inner.onnx_embed([texts[i] for i in part])
            tokens += int(out.attention_mask.sum())
            for i, v in zip(
                part, self.inner._post_process_onnx_output(out), strict=True
            ):
                vectors[i] = v.tolist()
        return vectors, tokens


def out_of_memory(e: Exception) -> bool:
    """ONNX Runtime's error when the arena's limit or the device's memory is reached."""
    text = str(e)
    return "Failed to allocate memory" in text or "out of memory" in text


def error(status: int, message: str) -> JSONResponse:
    # OpenAI's error body
    kind = "authentication_error" if status == 401 else "invalid_request_error"
    if status >= 500:
        kind = "server_error"
    return JSONResponse(
        {"error": {"message": message, "type": kind}}, status_code=status
    )


def parse(body: bytes) -> tuple[str | None, list[str] | str]:
    """The model and the texts of a request, or (None, the reason it is refused)."""
    try:
        data = json.loads(body)
    except ValueError:
        return None, "the body is not JSON"
    if not isinstance(data, dict):
        return None, "the body is not a JSON object"
    texts = data.get("input")
    if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
        return None, "input must be a list of strings"
    if data.get("encoding_format", "float") != "float":
        return None, "only encoding_format float is served"
    return str(data.get("model")), texts


async def embeddings(request: Request) -> JSONResponse:
    started = time.monotonic()
    status, texts, tokens = 200, None, None
    state = request.app.state
    try:
        given = request.headers.get("authorization", "").encode()
        if not hmac.compare_digest(given, f"Bearer {state.token}".encode()):
            status = 401
            return error(401, "a valid token is needed")
        model, parsed = parse(await request.body())
        if model is None:
            status = 400
            return error(400, str(parsed))
        texts = len(parsed)
        if model != MODEL:
            status = 400
            return error(400, f"this service serves {MODEL}, not {model}")
        try:
            vectors, tokens = await run_in_threadpool(state.model.embed, parsed)
        except Exception as e:
            if not out_of_memory(e):
                raise
            status = 503
            return error(503, "out of memory on the device for this request")
        data = [
            {"object": "embedding", "index": i, "embedding": v}
            for i, v in enumerate(vectors)
        ]
        return JSONResponse(
            {
                "object": "list",
                "data": data,
                "model": MODEL,
                "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
            }
        )
    except Exception:
        status = 500
        raise
    finally:
        # one line per request, never text (spec: the service does not keep or log the texts)
        ms = (time.monotonic() - started) * 1000
        log.info(
            "embeddings status=%d texts=%s tokens=%s ms=%.0f",
            status,
            "-" if texts is None else texts,
            "-" if tokens is None else tokens,
            ms,
        )


async def health(request: Request) -> JSONResponse:
    m = request.app.state.model
    return JSONResponse(
        {
            "repository": REPOSITORY,
            "revision": REVISION,
            "file": m.file,
            "provider": m.provider,
        }
    )


def others_on_the_gpu() -> str:
    """The compute processes nvidia-smi lists, for the record: no busy check, the GPU is
    shared (design D5)."""
    cmd = [
        "nvidia-smi",
        "--query-compute-apps=pid,process_name,used_memory",
        "--format=csv,noheader",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"unknown ({e})"
    if out.returncode:
        return f"unknown (nvidia-smi: {out.stderr.strip()})"
    return "; ".join(out.stdout.split("\n")).strip("; ") or "none"


@asynccontextmanager
async def lifespan(app: Starlette):
    s = settings()
    app.state.token = s.token
    app.state.model = Model(s)
    gpu = ""
    if s.device == "cuda":
        gpu = f", arena limit {s.mem_limit} bytes; other processes on the GPU: {others_on_the_gpu()}"
    log.info(
        "worker %d ready: %s at %s, %s on %s%s",
        os.getpid(),
        REPOSITORY,
        REVISION,
        app.state.model.file,
        app.state.model.provider,
        gpu,
    )
    yield


app = Starlette(
    routes=[
        Route("/v1/embeddings", embeddings, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
    ],
    lifespan=lifespan,
)


def fetch() -> None:
    from huggingface_hub import snapshot_download

    path = snapshot_download(
        REPOSITORY, revision=REVISION, cache_dir=str(CACHE), allow_patterns=FILES
    )
    print(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch", help="download the pinned model files into the cache")
    serve = sub.add_parser("serve", help="run the service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=7656)
    serve.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    if a.command == "fetch":
        fetch()
        return 0
    try:
        settings()  # fail here, once, before any worker starts
    except ConfigError as e:
        print(f"modama-embed: {e}", file=sys.stderr)
        return 2
    import uvicorn

    # no access log: our own line per request (spec: never text)
    uvicorn.run(
        "server:app",
        app_dir=str(HERE),
        host=a.host,
        port=a.port,
        workers=a.workers,
        access_log=False,
        log_config=None,
    )
    return 0


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    sys.exit(main())
