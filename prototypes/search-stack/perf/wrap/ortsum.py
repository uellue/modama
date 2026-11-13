"""Sum an ONNX Runtime profile (JSON) by operator type: kernel time, share of the model runs' time."""

import collections
import json
import sys
from pathlib import Path

ev = json.loads(Path(sys.argv[1]).read_text())
ops = collections.Counter()
count = collections.Counter()
runs = 0.0
nruns = 0
for e in ev:
    if e.get("cat") == "Node" and e["name"].endswith("_kernel_time"):
        ops[e["args"]["op_name"]] += e["dur"]
        count[e["args"]["op_name"]] += 1
    elif e.get("cat") == "Session" and e["name"] == "model_run":
        runs += e["dur"]
        nruns += 1
total = sum(ops.values())
print(f"model runs {nruns}, {runs / 1e6:.1f} s; kernels {total / 1e6:.1f} s")
for op, d in ops.most_common(15):
    print(f"{op:28} {d / 1e6:7.1f} s {100 * d / runs:5.1f} %  ({count[op]} calls)")
