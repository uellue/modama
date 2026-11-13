"""Tests of fp32.py (change embedding-fp32-model; spec embedding-model). They need onnx, fastembed and
ONNX Runtime at production's versions and the pinned upstream files, which they fetch from the Hub once:

  uv venv --python 3.13 /var/tmp/fp32-model/venv
  uv pip install --python /var/tmp/fp32-model/venv/bin/python \
    -r prototypes/search-stack/perf/grace-embedding/requirements-cpu.in pytest
  /var/tmp/fp32-model/venv/bin/pytest prototypes/search-stack/embedding-model/ \
    --basetemp /var/tmp/fp32-model/pytest

FP32_MODEL_CACHE (default /var/tmp/fp32-model/hub) keeps the download. Without the network the first run
fails and says so (AGENTS.md, "Fail, don't skip").
"""

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
STACK = HERE.parent
sys.path.insert(0, str(HERE))
import fp32  # noqa: E402

CACHE = Path(os.environ.get("FP32_MODEL_CACHE", "/var/tmp/fp32-model/hub"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="session")
def upstream(tmp_path_factory) -> Path:
    """The five pinned files in one folder, as the image build fetches them."""
    from huggingface_hub import hf_hub_download

    out = tmp_path_factory.mktemp("upstream")
    for name, pin in fp32.PINS.items():
        try:
            got = hf_hub_download(
                fp32.SOURCE, name, revision=fp32.REVISION, cache_dir=CACHE
            )
        except Exception as e:  # noqa: BLE001 - any failure to fetch is the same missing prerequisite
            pytest.fail(
                f"cannot fetch {name} of {fp32.SOURCE} at {fp32.REVISION} (network?): {e}"
            )
        shutil.copyfile(got, out / name)
        assert sha256(out / name) == pin, name
    return out


@pytest.fixture(scope="session")
def converted(upstream, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("fp32") / "bge-small-en-v1.5-fp32"
    fp32.convert(upstream, out)
    return out


@pytest.fixture(scope="session")
def text_sets(tmp_path_factory) -> list[str]:
    """The image build's sets, made as warehouse-airflow.Dockerfile makes them."""
    out = tmp_path_factory.mktemp("texts")
    gen = STACK / "perf" / "grace-embedding" / "gen_texts.py"
    args = []
    for name, n, share, seed in SETS:
        path = out / f"{name}.jsonl"
        subprocess.run(
            [
                sys.executable,
                "-I",
                str(gen),
                str(path),
                "--n",
                n,
                "--long-share",
                share,
                "--seed",
                seed,
            ],
            check=True,
            capture_output=True,
        )
        args.append(f"{name}={path}")
    return args


# name, texts, share of long texts, seed: as in warehouse-airflow.Dockerfile
SETS = [
    ("short", "64", "0", "1"),
    ("mixed", "64", "0.12", "2"),
    ("long", "32", "1", "3"),
]


def test_sets_match_the_dockerfile():
    text = (STACK / "warehouse-airflow.Dockerfile").read_text()
    for name, n, share, seed in SETS:
        assert f"{name}.jsonl --n {n} --long-share {share} --seed {seed}" in text, name


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HERE / "fp32.py"), *args], capture_output=True, text=True
    )


def test_pins_match_the_dockerfile():
    """The Dockerfile's ADD --checksum lines fetch the same revision and hashes as PINS."""
    text = (STACK / "warehouse-airflow.Dockerfile").read_text()
    found = dict(
        (name, digest)
        for digest, rev, name in re.findall(
            r"--checksum=sha256:([0-9a-f]{64})\s+\\?\s*https://huggingface\.co/"
            + re.escape(fp32.SOURCE)
            + r"/resolve/([0-9a-f]{40})/(\S+)",
            text,
        )
        if rev == fp32.REVISION
    )
    assert found == fp32.PINS


def test_convert_writes_float32_files_readable_by_all(converted):
    """Scenario: The worker's user reads the files (onnx writes the weight file 0600, design E3)."""
    import onnx
    from onnx import TensorProto

    names = sorted(p.name for p in converted.iterdir())
    assert names == sorted(
        [
            "model_optimized.onnx",
            "model_optimized.onnx.data",
            fp32.MARKER,
            *(n for n in fp32.PINS if n != fp32.MODEL_FILE),
        ]
    )
    assert stat.S_IMODE(converted.stat().st_mode) == 0o755
    for p in converted.iterdir():
        assert stat.S_IMODE(p.stat().st_mode) == 0o644, p.name
    m = onnx.load(str(converted / fp32.MODEL_FILE), load_external_data=False)
    assert {t.data_type for t in m.graph.initializer} == {TensorProto.FLOAT}
    assert len(m.graph.initializer) == 149


def test_marker_names_the_model_and_the_pins(converted):
    marker = json.loads((converted / fp32.MARKER).read_text())
    assert marker["model"] == "BAAI/bge-small-en-v1.5"
    assert marker["source"] == fp32.SOURCE
    assert marker["revision"] == fp32.REVISION
    assert marker["model_file"] == fp32.MODEL_FILE
    assert marker["upstream_sha256"] == fp32.PINS


def test_convert_is_prepare_models_conversion(upstream, converted, tmp_path):
    """The grace benchmark's float32 file (perf/grace-embedding/prepare_model.py) is this file, byte for byte."""
    # in a process of its own: prepare_model imports bench.py, which sets cache directories on import
    grace = STACK / "perf" / "grace-embedding"
    code = (
        "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
        "from prepare_model import to_fp32; to_fp32(Path(sys.argv[2]), Path(sys.argv[3]))"
    )
    subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            code,
            str(grace),
            str(upstream / fp32.MODEL_FILE),
            str(tmp_path / fp32.MODEL_FILE),
        ],
        check=True,
        cwd=tmp_path,
        env={**os.environ, "FASTEMBED_CACHE_DIR": str(tmp_path / "cache")},
    )
    for name in (fp32.MODEL_FILE, fp32.MODEL_FILE + ".data"):
        assert sha256(tmp_path / name) == sha256(converted / name), name


def test_check_passes_the_float32_file(upstream, converted, text_sets):
    """Scenario: Short, mixed and long texts."""
    r = run("check", str(upstream), str(converted), *text_sets)
    print(r.stdout)
    assert r.returncode == 0, r.stderr
    for kind in ("short", "mixed", "long"):
        assert re.search(
            rf"^{kind}: \d+ texts, \d+ bitwise identical, largest difference \S+, minimum cosine 0\.99999\d*",
            r.stdout,
            re.M,
        ), r.stdout


def test_check_fails_on_the_int8_file(upstream, converted, text_sets, tmp_path):
    """Scenario: A file that changes the vectors."""
    from onnx import TensorProto
    from onnxruntime.quantization import QuantType, quantize_dynamic

    bad = tmp_path / "int8"
    bad.mkdir()
    for name in fp32.PINS:
        if name != fp32.MODEL_FILE:
            shutil.copyfile(upstream / name, bad / name)
    shutil.copyfile(converted / fp32.MARKER, bad / fp32.MARKER)
    quantize_dynamic(
        str(converted / fp32.MODEL_FILE),
        str(bad / fp32.MODEL_FILE),
        weight_type=QuantType.QInt8,
        extra_options={"DefaultTensorType": TensorProto.FLOAT},
    )
    r = run("check", str(upstream), str(bad), *text_sets)
    assert r.returncode == 1
    assert re.search(
        r"minimum cosine 0\.9\d* in the (short|mixed|long) set, below 0\.99999",
        r.stderr,
    ), r.stderr


def test_check_stops_when_fastembed_names_another_file():
    """Scenario: fastembed names another file."""
    marker = {
        "model": "BAAI/bge-small-en-v1.5",
        "source": fp32.SOURCE,
        "model_file": fp32.MODEL_FILE,
    }

    class Description:
        model = "BAAI/bge-small-en-v1.5"
        model_file = "onnx/model.onnx"

        class sources:
            hf = "qdrant/bge-small-en-v1.5-onnx-q-v2"

    msg = fp32.description_mismatch(marker, [Description])
    assert "qdrant/bge-small-en-v1.5-onnx-q-v2" in msg and fp32.SOURCE in msg
    assert "onnx/model.onnx" in msg and fp32.MODEL_FILE in msg
    Description.sources.hf, Description.model_file = fp32.SOURCE, fp32.MODEL_FILE
    assert fp32.description_mismatch(marker, [Description]) is None
