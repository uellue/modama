"""check.py against server.py on the CPU provider, run in the transform venv (change
embedding-service-grace, tasks 3.2 and 3.3; the snapshot itself needs the warehouse's
database and is run in the test deployment, README.md)."""

import json
import os
import subprocess
import sys

import pytest

from conftest import SERVICE, Service, model_cache

CHECK = SERVICE / "check.py"


def check(service, warehouse, *args, env=None):
    return subprocess.run(
        [sys.executable, str(CHECK), "--warehouse-src", str(warehouse / "src"), *args],
        env={
            **os.environ,
            "EMBED_API_URL": service.url + "/v1",
            "EMBED_API_KEY": service.token,
            **(env or {}),
        },
        capture_output=True,
        text=True,
        timeout=900,
    )


def rows(out: str) -> dict[str, list[str]]:
    return {
        line.split()[0]: line.split()
        for line in out.splitlines()
        if line.split() and line.split()[-1] in ("pass", "FAIL")
    }


# Requirement: The service's vectors agree with the local path's (short, mixed, long and
# over-length texts)
def test_short_mixed_and_long_texts(service, warehouse):
    out = check(service, warehouse, "sets", "--n", "32")
    assert out.returncode == 0, out.stdout + out.stderr
    got = rows(out.stdout)
    assert sorted(got) == ["long", "mixed", "over", "short"]
    assert all(r[1] == "32" and r[-1] == "pass" for r in got.values())


def test_a_file_that_moves_the_vectors(tmp_path, warehouse):
    int8 = model_cache() / "variants" / "model-int8.onnx"
    if not int8.exists():
        pytest.fail(
            f"{int8} is missing: FASTEMBED_CACHE_DIR={model_cache()} python ../perf/grace-embedding/prepare_model.py (README.md, Tests)"
        )
    s = Service(tmp_path, MODAMA_EMBED_MODEL_FILE=str(int8)).start()
    try:
        out = check(s, warehouse, "sets", "--n", "32", "--sets", "short,long")
    finally:
        s.stop()
    assert out.returncode == 1, out.stdout + out.stderr
    assert "outside design D4: short, long" in out.stderr
    assert all(r[-1] == "FAIL" for r in rows(out.stdout).values())


def test_rate(service, warehouse):
    out = check(service, warehouse, "rate", "--texts", "16", "--callers", "1,2")
    assert out.returncode == 0, out.stderr
    lines = [line.split() for line in out.stdout.splitlines()[1:]]
    assert [(r[0], r[1]) for r in lines] == [("1", "2"), ("2", "4")]


def test_compare(service, warehouse, tmp_path):
    """Two snapshots: the vectors before from the local path, after from the service; a
    record whose datestamp changed is left out."""
    sys.path.insert(0, str(SERVICE))
    import check as c

    texts = c.texts_of(21, *c.SETS["mixed"], 1)
    model, embed_locally = c.local_model(str(warehouse / "src"))
    before = embed_locally(texts, model)
    after = service.post(texts).json()["data"]
    stamp = "2026-11-13T10:00:00+00:00"
    with (
        open(tmp_path / "before.jsonl", "w") as b,
        open(tmp_path / "after.jsonl", "w") as a,
    ):
        for i, t in enumerate(texts):
            b.write(
                json.dumps({"id": f"r{i}", "datestamp": stamp, "vector": before[i]})
                + "\n"
            )
            changed = "2026-11-14T10:00:00+00:00" if i == 0 else stamp
            a.write(
                json.dumps(
                    {
                        "id": f"r{i}",
                        "datestamp": changed,
                        "vector": after[i]["embedding"],
                    }
                )
                + "\n"
            )
    out = check(
        service,
        warehouse,
        "compare",
        str(tmp_path / "before.jsonl"),
        str(tmp_path / "after.jsonl"),
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert "21 records before, 21 after, 20 with the same datestamp" in out.stderr
    assert rows(out.stdout)["records"][1] == "20"
