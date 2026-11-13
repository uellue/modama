"""One test per scenario of the spec's service requirements that can run in the VM, with
the CPU provider (change embedding-service-grace, specs/embedding-service/spec.md)."""

import socket
import subprocess
import sys
import threading
import time

import numpy as np
import pytest
import requests

from conftest import SERVER, SERVICE, Service, free_port, model_cache

BOUND = 0.99999  # design D4
WORDS = "beam dose tilt focus aberration detector camera frame series drift lattice defect".split()


def vectors(answer: requests.Response) -> np.ndarray:
    assert answer.status_code == 200, answer.text
    data = answer.json()["data"]
    assert [d["index"] for d in data] == list(range(len(data)))
    return np.array([d["embedding"] for d in data], dtype=np.float64)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def words(n: int, seed: int) -> str:
    rng = np.random.default_rng(seed)
    return " ".join(rng.choice(WORDS, n))


THREE = [
    "HAADF-STEM of ferritin, drift series 12 electron microscopy",
    "graphene lattice defect tilt series materials science",
    "plain text document, 1 file, 2041 B, in zeolite/",
]


# Requirement: The service answers OpenAI's embeddings request
def test_three_texts(service):
    answer = service.post(THREE)
    body = answer.json()
    assert body["object"] == "list" and body["model"] == "bge-small-en-v1.5"
    assert all(d["object"] == "embedding" for d in body["data"])
    v = vectors(answer)
    assert v.shape == (3, 384)
    assert np.allclose(np.linalg.norm(v, axis=1), 1, atol=1e-6)


def test_the_texts_in_another_order(service):
    before = vectors(service.post(THREE))
    after = vectors(service.post(THREE[::-1]))
    assert np.allclose(after[0], before[2], atol=1e-6)
    assert np.allclose(after[2], before[0], atol=1e-6)


# Requirement: Texts longer than the model's window are cut at tokens
def test_a_text_of_2000_tokens(service, local_model):
    text = words(2000, seed=1)
    tokens = len(local_model.model.tokenizer.encode(text, add_special_tokens=False).ids)
    assert tokens == 512  # the tokenizer truncates; the text itself is longer
    v = vectors(service.post([text]))[0]
    local = next(iter(local_model.embed([text])))
    assert cosine(v, local) >= BOUND


def test_only_the_first_512_tokens_count(service):
    shared = words(600, seed=2)
    a, b = shared + " " + words(50, seed=3), shared + " " + words(400, seed=4)
    # in one request, in different sub-batches: 300 texts of lengths between a's and b's
    # (the service sorts by length and runs 256 at a time)
    middle = [shared + " " + words(51 + i, seed=10 + i) for i in range(300)]
    one = vectors(service.post([a, *middle, b]))
    assert cosine(one[0], one[-1]) >= BOUND
    two = vectors(service.post([a])), vectors(service.post([b]))
    assert cosine(two[0][0], two[1][0]) >= BOUND
    assert cosine(one[0], two[0][0]) >= BOUND


# Requirement: Requests need the service's token
def test_no_token(service):
    assert service.post(THREE, token=False).status_code == 401


def test_a_wrong_token(service):
    wrong = "wrong-token-9876543210"
    answer = service.post(THREE, token=wrong)
    assert answer.status_code == 401
    log = service.log()
    assert "status=401" in log
    assert wrong not in log and service.token not in log


# Requirement: The service serves one model
def test_another_model_asked_for(service):
    answer = service.post(THREE, model="nomic-embed-text-v1.5")
    assert answer.status_code == 400
    assert "bge-small-en-v1.5" in answer.json()["error"]["message"]


# Requirement: The service names its model file
def test_the_health_answer(service):
    answer = requests.get(service.url + "/health", timeout=10)
    assert answer.json() == {
        "repository": "qdrant/bge-small-en-v1.5-onnx-q",
        "revision": "aa8f8b060edb00e03bfdd08813a2949946c8ba55",
        "file": "model_optimized.onnx",
        "provider": "CPUExecutionProvider",  # on grace: CUDAExecutionProvider
    }


# Requirement: The service listens on grace's loopback only
def test_from_another_address(service):
    """The default bind is 127.0.0.1: this host's other address is refused."""
    out = subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout
    other = next(a for a in out.split() if ":" not in a and not a.startswith("127."))
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection((other, service.port), timeout=5)


# Requirement: The service does not keep or log the texts
def test_a_marker_in_a_text(service):
    marker = "MARKER-7f3a9c1e-not-to-be-logged"
    assert service.post([f"ferritin {marker} lattice"]).status_code == 200
    assert "status=200 texts=1" in service.log()
    assert marker not in service.log()


# Requirement: The service keeps its GPU memory within a limit. With the CPU provider no
# arena limit applies (ONNX Runtime 1.31.1 does not enforce OrtArenaCfg's max_mem for the
# CPU provider's tensors), so here ONNX Runtime's out-of-memory error stands in, raised by
# the session for a large batch; the limit itself is checked on grace (README.md, runbook).
def test_a_limit_too_small_for_a_batch(tmp_path, monkeypatch):
    model_cache()
    sys.path.insert(0, str(SERVICE))
    import server
    import uvicorn
    from onnxruntime.capi.onnxruntime_pybind11_state import RuntimeException

    creds = tmp_path / "credentials"
    creds.mkdir()
    (creds / "token").write_text("t-0123456789")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(creds))
    monkeypatch.setenv("MODAMA_EMBED_DEVICE", "cpu")
    port = free_port()
    uv = uvicorn.Server(
        uvicorn.Config(server.app, port=port, log_config=None, lifespan="on")
    )
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    while not uv.started:
        time.sleep(0.1)
    try:
        session = server.app.state.model.inner.model
        real = session.run

        def run(names, feed, *a):
            if feed["input_ids"].size > 1000:  # "too large for the limit"
                raise RuntimeException(
                    "[ONNXRuntimeError] : 6 : RUNTIME_EXCEPTION : Non-zero status code returned while "
                    "running MatMul node. Status Message: bfc_arena.cc:359 "
                    "onnxruntime::BFCArena::AllocateRawInternal Failed to allocate memory for "
                    "requested buffer of size 805306368"
                )
            return real(names, feed, *a)

        session.run = run
        url = f"http://127.0.0.1:{port}/v1/embeddings"
        auth = {"Authorization": "Bearer t-0123456789"}
        big = {"model": "bge-small-en-v1.5", "input": [words(600, seed=5)] * 256}
        assert (
            requests.post(url, json=big, headers=auth, timeout=300).status_code == 503
        )
        small = {"model": "bge-small-en-v1.5", "input": THREE}
        assert (
            requests.post(url, json=small, headers=auth, timeout=60).status_code == 200
        )
    finally:
        uv.should_exit = True
        thread.join(30)


# Configuration: a missing token fails at once, before any worker starts
def test_no_token_file(tmp_path):
    s = Service(tmp_path, MODAMA_EMBED_CACHE=str(model_cache()))
    (tmp_path / "credentials" / "token").unlink()
    out = subprocess.run(
        [sys.executable, str(SERVER), "serve", "--port", str(s.port)],
        env=s.env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 2
    assert "cannot read the token" in out.stderr


def test_no_memory_limit_on_the_gpu(tmp_path):
    s = Service(tmp_path, MODAMA_EMBED_DEVICE="cuda")
    out = subprocess.run(
        [sys.executable, str(SERVER), "serve", "--port", str(s.port)],
        env={k: v for k, v in s.env.items() if k != "MODAMA_EMBED_MEM_LIMIT"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 2
    assert "MODAMA_EMBED_MEM_LIMIT is not set" in out.stderr
