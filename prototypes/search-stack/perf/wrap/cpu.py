"""Runs a script (argv[1:]) and appends wall and process CPU time (all threads) to every line it prints.

WAIT=<s>        sleep first, so that perf can attach before the script starts
ORT_PROFILE=1   ONNX Runtime's per-operator profile, written to /tmp/ort_*.json at exit
SORT=1          hypothesis: embed the texts sorted by length (characters), results back in the given order
ORT_ARENA=0     hypothesis: ONNX Runtime without the CPU memory arena
ORT_OPT=<level> hypothesis: graph optimisation level (disable, basic, extended, all; fastembed sets all)
"""

import atexit
import builtins
import os
import runpy
import sys
import time

time.sleep(float(os.environ.get("WAIT", "0")))
_print = builtins.print
t0 = time.monotonic()


def stamped(*a, **k):
    _print(
        *a,
        f"| wall {time.monotonic() - t0:.1f} s, cpu {time.process_time():.1f} s",
        **k,
    )


builtins.print = stamped

if (
    os.environ.get("ORT_PROFILE")
    or os.environ.get("ORT_ARENA")
    or os.environ.get("ORT_OPT")
):
    import onnxruntime as ort

    _SessionOptions = ort.SessionOptions
    levels = {
        "disable": ort.GraphOptimizationLevel.ORT_DISABLE_ALL,
        "basic": ort.GraphOptimizationLevel.ORT_ENABLE_BASIC,
        "extended": ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED,
        "all": ort.GraphOptimizationLevel.ORT_ENABLE_ALL,
    }

    class SessionOptions(_SessionOptions):
        def __setattr__(self, name, value):
            # fastembed sets the level after creating the options: the hypothesis' level wins
            if name == "graph_optimization_level" and os.environ.get("ORT_OPT"):
                value = levels[os.environ["ORT_OPT"]]
            super().__setattr__(name, value)

        def __init__(self):
            super().__init__()
            if os.environ.get("ORT_PROFILE"):
                self.enable_profiling = True
                self.profile_file_prefix = "/tmp/ort"
            if os.environ.get("ORT_ARENA") == "0":
                self.enable_cpu_mem_arena = False

    ort.SessionOptions = SessionOptions
    _Session = ort.InferenceSession

    class InferenceSession(_Session):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            if os.environ.get("ORT_PROFILE"):
                atexit.register(lambda: _print("ORT profile", self.end_profiling()))

    ort.InferenceSession = InferenceSession

if os.environ.get("SORT"):
    from fastembed import TextEmbedding

    _embed = TextEmbedding.embed

    def embed(self, documents, batch_size=256, **k):
        docs = list(documents)
        order = sorted(range(len(docs)), key=lambda i: len(docs[i]))
        out = list(_embed(self, [docs[i] for i in order], batch_size=batch_size, **k))
        result = [None] * len(docs)
        for j, i in enumerate(order):
            result[i] = out[j]
        return iter(result)

    TextEmbedding.embed = embed

sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
