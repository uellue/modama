"""The warehouse's side with patches/warehouse/ applied (0005-embedding-service.patch), one
test per scenario of the spec's warehouse requirements, run in the transform venv against
server.py on the CPU provider (change embedding-service-grace, task 5.1), and
field-test/batch-times.sh against task logs of the three kinds of batch (task 5.3)."""

import json
import logging
import os
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import numpy as np
import pytest
import requests

from conftest import STACK, free_port, model_cache

BOUND = 0.99999  # design D4
MODEL = "BAAI/bge-small-en-v1.5"


class Recorder:
    """An HTTP server in a thread that records each request's body, then forwards it to
    `target` or answers `status` with `body`."""

    def __init__(self, target: str | None = None, status: int = 200, body: str = ""):
        self.requests: list[dict] = []
        rec = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                data = self.rfile.read(int(self.headers["Content-Length"]))
                rec.requests.append(json.loads(data))
                if target:
                    r = requests.post(
                        target + self.path,
                        data=data,
                        headers={
                            "Authorization": self.headers.get("Authorization", ""),
                            "Content-Type": "application/json",
                        },
                        timeout=300,
                    )
                    code, out = r.status_code, r.content
                else:
                    code, out = status, body.encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                if code == 429:
                    self.send_header("Retry-After", "0")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


class Local:
    """The local model, noting when the batch starts embedding locally."""

    def __init__(self, model):
        self.model, self.started = model, None

    def embed(self, texts, **kw):
        self.started = time.monotonic()
        return self.model.embed(texts, **kw)


@pytest.fixture(scope="module")
def utils(warehouse):
    from utils import embedding_utils

    return embedding_utils


@pytest.fixture(scope="module")
def local(warehouse):
    from fastembed import TextEmbedding

    # the pinned files, as the service loads them
    folder = (
        model_cache()
        / "models--qdrant--bge-small-en-v1.5-onnx-q/snapshots/aa8f8b060edb00e03bfdd08813a2949946c8ba55"
    )
    return TextEmbedding(
        MODEL, cache_dir=str(model_cache()), specific_model_path=str(folder)
    )


def batch_of(utils, texts):
    event = SimpleNamespace(additional_metadata=None, code="c", harvest_url="h")
    return [utils.SourceWithEmbeddingText({}, t, event) for t in texts]


TEXTS = [
    "HAADF-STEM of ferritin, drift series 12 electron microscopy",
    "plain text document, 1 file, 2041 B, in zeolite/",
]


def run(utils, local, texts, url, key="test-token-0123456789", model=MODEL):
    """add_embeddings_to_source as transform_batch_impl calls it; the vectors, the time
    from the call to the start of local embedding (None: not local), the log."""
    logger = logging.getLogger("transform.transform_core")
    lines: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda r: lines.append(r.levelname + " " + r.getMessage())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    model_ = Local(local)
    t0 = time.monotonic()
    try:
        out = utils.add_embeddings_to_source(
            batch=batch_of(utils, texts),
            logger=logger,
            embedding_model=model_,
            api_key=key,
            base_url=url,
            model_name=model,
        )
    finally:
        logger.removeHandler(handler)
    vecs = np.array([o.src["emb"] for o in out])
    started = None if model_.started is None else model_.started - t0
    return vecs, started, "\n".join(lines)


def cosines(a, b):
    return (a * b).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))


# Requirement: The warehouse sends its texts uncut
def test_a_long_description(utils, local, service):
    long = " ".join(["The lattice of the specimen was imaged at 300 kV."] * 200)[:5000]
    assert len(long) == 5000
    rec = Recorder(target=service.url)
    try:
        vecs, started, log = run(utils, local, [*TEXTS, long], rec.url, service.token)
    finally:
        rec.close()
    assert started is None, log
    assert "from with API" in log
    assert len(rec.requests) == 1
    assert rec.requests[0]["input"][2] == long
    ref = np.array(utils._embed_locally([*TEXTS, long], local))
    assert cosines(vecs, ref).min() >= BOUND


# Requirement: The warehouse embeds locally when the service fails
def test_the_tunnel_is_down(utils, local):
    vecs, started, log = run(utils, local, TEXTS, f"http://127.0.0.1:{free_port()}/v1")
    assert started is not None and started < 10, started
    assert "falling back to local model" in log
    assert vecs.shape == (2, 384)


def test_the_service_does_not_answer(utils, local):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(16)  # accepts (the kernel does), never answers
    try:
        url = f"http://127.0.0.1:{s.getsockname()[1]}/v1"
        vecs, started, log = run(utils, local, TEXTS, url)
    finally:
        s.close()
    # 4 waits of 30 s and 7 s of backoff, not 4 x 120 s
    assert started is not None and 120 < started < 180, started
    assert "falling back to local model" in log
    assert vecs.shape == (2, 384)


def test_a_wrong_token(utils, local, service):
    rec = Recorder(target=service.url)
    wrong = "wrong-token-9876543210"
    try:
        _, started, log = run(utils, local, TEXTS, rec.url, key=wrong)
    finally:
        rec.close()
    assert len(rec.requests) == 1
    assert started is not None and started < 1, started  # no retry, no backoff
    assert "401" in log and "falling back to local model" in log
    assert wrong not in log


def test_another_model(utils, local, service):
    rec = Recorder(target=service.url)
    try:
        _, started, log = run(
            utils,
            local,
            TEXTS,
            rec.url,
            service.token,
            "nomic-ai/nomic-embed-text-v1.5",
        )
    finally:
        rec.close()
    assert len(rec.requests) == 1
    assert started is not None and started < 1, started
    assert "400" in log


def test_a_server_that_refuses_long_texts(utils, local):
    """A 400 that says `context length`: no second request with a halved cap."""
    rec = Recorder(status=400, body='{"error": "maximum context length exceeded"}')
    try:
        _, started, _ = run(utils, local, TEXTS, rec.url)
    finally:
        rec.close()
    assert len(rec.requests) == 1
    assert started is not None and started < 1, started


@pytest.mark.parametrize("status", [429, 503])
def test_429_and_5xx_are_retried(utils, local, status):
    rec = Recorder(status=status, body="{}")
    try:
        _, started, log = run(utils, local, TEXTS, rec.url)
    finally:
        rec.close()
    assert len(rec.requests) == 4
    assert started is not None, log


# Requirement: The way back is an empty URL
def test_switched_off(utils, local):
    _, started, log = run(utils, local, TEXTS, "")
    assert started is not None
    assert "calculating embeddings locally" in log


# Design Q7: the local model is loaded only when a batch embeds locally
def test_the_local_model_loads_only_when_needed(warehouse, monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL", MODEL)
    monkeypatch.setenv("FASTEMBED_CACHE_DIR", str(model_cache() / "fastembed"))
    # what TransformResources reads, as in the worker (no connection is made)
    for name, value in {
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
        "POSTGRES_DB": "d",
        "POSTGRES_ADDRESS_DOCKER": "127.0.0.1",
        "POSTGRES_PORT_DOCKER": "5432",
        "OPENSEARCH_ADDRESS_DOCKER": "127.0.0.1",
        "OPENSEARCH_PORT_DOCKER": "9200",
    }.items():
        monkeypatch.setenv(name, value)
    import importlib

    from transform import transform_core

    importlib.reload(transform_core)
    resources = transform_core.TransformResources()
    # fastembed sets the session (`model`) only when it loads it
    assert getattr(resources.embedding_transformer.model, "model", None) is None


# field-test/batch-times.sh: service, fallback or local per batch (task 5.3)
def test_batch_times(utils, local, service, tmp_path):
    kinds = {
        "service": (service.url + "/v1", service.token),
        "fallback": (f"http://127.0.0.1:{free_port()}/v1", "x"),
        "local": ("", None),
    }
    for i, (kind, (url, key)) in enumerate(kinds.items()):
        _, _, log = run(utils, local, TEXTS, url, key)
        folder = (
            tmp_path
            / "dag_id=warehouse_transform_index/run_id=manual__x/task_id=run_transform_batch"
            / f"map_index={i}"
        )
        folder.mkdir(parents=True)
        lines = [f"Transform resources ready after {i + 0.5}s"]
        lines += [line.split(" ", 1)[1] for line in log.split("\n")]
        lines.append(f"Transformed batch in {i + 1.5}s, 2 documents indexed")
        with open(folder / "attempt=1.log", "w") as f:
            for n, event in enumerate(lines):
                f.write(
                    json.dumps(
                        {
                            "timestamp": f"2026-11-13T10:0{i}:{n:02d}.000000Z",
                            "level": "info",
                            "event": event,
                            "task_id": "run_transform_batch",
                        },
                        separators=(",", ":"),  # as Airflow writes them
                    )
                    + "\n"
                )
    out = subprocess.run(
        ["bash", "-s", str(tmp_path)],
        stdin=open(STACK / "field-test" / "batch-times.sh"),
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C"},
    )
    assert out.returncode == 0, out.stderr
    rows = [line.split() for line in out.stdout.splitlines() if line[:1].isdigit()]
    assert [r[-1] for r in rows] == ["service", "fallback", "local"], out.stdout
    assert "fallback 1 of 3" in out.stdout, out.stdout
