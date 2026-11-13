"""Measurements on grace before the service is enabled (change embedding-service-grace,
task 2.2 and Q9; README.md, "Runbook"):

  venv/bin/python measure.py [FILE ...]

For each ONNX file (default: the pinned model_optimized.onnx; the float32 file of the
benchmark is ~/grace-embedding/cache/variants/model-fp32.onnx), the 512 texts of the short,
mixed and long sets embedded on the GPU with TF32 off and on, each against the same file on
grace's CPU: the minimum cosine (float64) and the largest component difference. They say
whether TF32 matters (design D3); the deciding comparison is check.py on staging's EPYC
(design D4). Last, this process's GPU memory after the long set in sub-batches of 256 with
TF32 off (ONNX Runtime's arena keeps what it took, CUDA's context of about 0.5 GB included),
for MODAMA_EMBED_MEM_LIMIT: twice that, per worker (design Q9).

Needs MODAMA_EMBED_CACHE with the model files (`server.py fetch`) and the GPU; no token,
no port. Results on stdout, progress on stderr.
"""

import os
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check  # noqa: E402  (the sets: gen_texts.py by seed, as check.py and the benchmark)
import server  # noqa: E402

N = 512


def embed(model: server.Model, texts: list[str]) -> np.ndarray:
    return np.array(model.embed(texts)[0], np.float64)


def gpu_mib() -> str:
    out = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,used_memory",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
    ).stdout
    mine = [
        line.split(",")[1].strip()
        for line in out.splitlines()
        if line.split(",")[0].strip() == str(os.getpid())
    ]
    return mine[0] if mine else "not listed"


def main() -> int:
    files = [Path(f) for f in sys.argv[1:]] or [server.model_dir() / server.FILES[-1]]
    sets = {
        name: check.texts_of(N, *check.SETS[name], 1)
        for name in ("short", "mixed", "long")
    }
    print(f"{'file':<24} {'set':<6} {'TF32':<4} {'min cosine':>12} {'max diff':>10}")
    for file in files:
        s = server.Settings("", "cpu", None, server.model_dir(), file)
        cpu = server.Model(s)
        ref = {name: embed(cpu, texts) for name, texts in sets.items()}
        del cpu
        for tf32 in (False, True):
            print(f"{file.name}: GPU, TF32 {'on' if tf32 else 'off'}", file=sys.stderr)
            gpu = server.Model(
                server.Settings("", "cuda", None, server.model_dir(), file), tf32
            )
            for name, texts in sets.items():
                got = embed(gpu, texts)
                cos = (got * ref[name]).sum(1) / (
                    np.linalg.norm(got, axis=1) * np.linalg.norm(ref[name], axis=1)
                )
                diff = np.abs(got - ref[name]).max()
                print(
                    f"{file.name:<24} {name:<6} {'on' if tf32 else 'off':<4} {cos.min():>12.9f} {diff:>10.2e}",
                    flush=True,
                )
            del gpu
    # a fresh process's arena: the long set in sub-batches of 256, TF32 off, the default file
    out = subprocess.run(
        [sys.executable, __file__, "--memory"], capture_output=True, text=True
    )
    print(out.stdout.strip() or out.stderr.strip())
    return 0


def memory() -> int:
    s = server.Settings(
        "", "cuda", None, server.model_dir(), server.model_dir() / server.FILES[-1]
    )
    model = server.Model(s)
    embed(model, check.texts_of(N, *check.SETS["long"], 1))
    print(
        f"GPU memory of one worker after {N} long texts in sub-batches of {server.SUB_BATCH}: {gpu_mib()} MiB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(memory() if sys.argv[1:] == ["--memory"] else main())
