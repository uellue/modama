"""Fixtures: the service as a real process (uvicorn, CPU provider), its log, its token.

MODAMA_EMBED_CACHE must hold the pinned model files (`server.py fetch`); the tests fail,
not skip, without them (README.md, Tests)."""

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

HERE = Path(__file__).resolve().parent
SERVICE = HERE.parent
SERVER = SERVICE / "server.py"
STACK = SERVICE.parent
UPSTREAM = STACK.parent / "EOSC-Data-Commons" / "metadata-warehouse"
# the service's venv (Starlette, uvicorn); the warehouse's and check.py's tests run in the
# transform venv and start the service with this Python
SERVICE_PYTHON = os.environ.get("EMBED_SERVICE_PYTHON", sys.executable)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Service:
    def __init__(self, tmp: Path, token: str = "test-token-0123456789", **env: str):
        self.token = token
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        creds = tmp / "credentials"
        creds.mkdir(exist_ok=True)
        (creds / "token").write_text(token + "\n")
        self.log_path = tmp / f"service-{self.port}.log"
        self.env = {
            **os.environ,
            "MODAMA_EMBED_CACHE": str(model_cache()),
            "CREDENTIALS_DIRECTORY": str(creds),
            "MODAMA_EMBED_DEVICE": "cpu",
            **env,
        }
        self.proc: subprocess.Popen | None = None

    def start(self, *args: str, wait: bool = True) -> "Service":
        self.log_file = open(self.log_path, "w")
        self.proc = subprocess.Popen(
            [SERVICE_PYTHON, str(SERVER), "serve", "--port", str(self.port), *args],
            env=self.env,
            stdout=self.log_file,
            stderr=subprocess.STDOUT,
        )
        if wait:
            self.wait()
        return self

    def wait(self, timeout: float = 120) -> None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.proc.poll() is not None:
                raise RuntimeError(f"the service ended:\n{self.log()}")
            try:
                if requests.get(self.url + "/health", timeout=2).ok:
                    # both workers loaded: two "ready" lines
                    if self.log().count(" ready: ") >= self.workers():
                        return
            except requests.ConnectionError:
                pass
            time.sleep(0.5)
        raise RuntimeError(
            f"the service did not answer within {timeout} s:\n{self.log()}"
        )

    def workers(self) -> int:
        args = self.proc.args
        return int(args[args.index("--workers") + 1]) if "--workers" in args else 2

    def log(self) -> str:
        return self.log_path.read_text()

    def post(self, texts, model="bge-small-en-v1.5", token=None, **kw):
        headers = {}
        if token is not False:
            headers["Authorization"] = f"Bearer {token or self.token}"
        return requests.post(
            self.url + "/v1/embeddings",
            json={"model": model, "input": texts},
            headers=headers,
            timeout=300,
            **kw,
        )

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.log_file.close()


def model_cache() -> Path:
    cache = os.environ.get("MODAMA_EMBED_CACHE")
    if not cache:
        pytest.fail(
            "MODAMA_EMBED_CACHE is not set: the folder with the pinned model files (server.py fetch; README.md, Tests)"
        )
    return Path(cache)


@pytest.fixture(scope="session")
def warehouse(tmp_path_factory) -> Path:
    """Upstream's warehouse code with patches/warehouse/ applied in order, as
    warehouse-airflow.Dockerfile applies them; on sys.path as in the transform worker."""
    if not (UPSTREAM / "src").is_dir():
        pytest.fail(
            f"{UPSTREAM} is empty: git submodule update --init prototypes/EOSC-Data-Commons/metadata-warehouse"
        )
    root = tmp_path_factory.mktemp("warehouse")
    shutil.copytree(UPSTREAM / "src", root / "src")
    shutil.copytree(UPSTREAM / "config", root / "config")
    shutil.copytree(UPSTREAM / "airflow" / "dags", root / "airflow" / "dags")
    for p in sorted((STACK / "patches" / "warehouse").glob("*.patch")):
        out = subprocess.run(
            ["patch", "-p1", "-i", str(p)], cwd=root, capture_output=True, text=True
        )
        if out.returncode:
            pytest.fail(f"{p.name} does not apply:\n{out.stdout}{out.stderr}")
    sys.path[:0] = [str(root / "src"), str(root)]
    return root


@pytest.fixture(scope="session")
def service(tmp_path_factory):
    model_cache()
    s = Service(tmp_path_factory.mktemp("service")).start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def local_model():
    """fastembed's TextEmbedding from the same pinned files, as the warehouse's local path
    loads it (CPU)."""
    sys.path.insert(0, str(SERVICE))
    import server
    from fastembed import TextEmbedding

    return TextEmbedding(
        server.FASTEMBED_MODEL,
        cache_dir=str(model_cache()),
        specific_model_path=str(server.model_dir()),
    )
