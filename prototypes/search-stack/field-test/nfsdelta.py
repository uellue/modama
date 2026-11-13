"""Per-interval deltas of an nfs-stats.sh log: operations/s, mean round trip per op, requests in flight, bytes received per open.

usage: python3 nfsdelta.py nfs.log [since HH:MM]
Fields of a per-op line (mountstats): ops trans timeouts bytes_sent bytes_recv queue_ms rtt_ms execute_ms errors
"""

import itertools
import re
import sys
from datetime import datetime

OPS = ("READ", "OPEN_NOATTR", "CLOSE", "ACCESS", "GETATTR", "LOOKUP", "READDIR")
snaps, cur = [], None
with open(sys.argv[1]) as log:
    for line in log:
        if line.startswith("=== "):
            cur = {"t": line.split()[1]}
            snaps.append(cur)
            continue
        m = re.match(r"\s+([A-Z_]+): ([\d ]+)$", line)
        if m and cur is not None and m[1] in OPS:
            cur[m[1]] = [int(x) for x in m[2].split()]
since = sys.argv[2] if len(sys.argv) > 2 else ""
snaps = [s for s in snaps if len(s) > 1 and s["t"][11:16] >= since]
for a, b in itertools.pairwise(snaps):
    d = {
        op: [y - x for x, y in zip(a[op], b[op], strict=True)]
        for op in OPS
        if op in a and op in b
    }
    secs = (
        datetime.fromisoformat(b["t"]) - datetime.fromisoformat(a["t"])
    ).total_seconds() or 1
    total = sum(v[0] for v in d.values())
    rtt = sum(v[6] for v in d.values()) / total if total else 0
    opens = d["OPEN_NOATTR"][0] if "OPEN_NOATTR" in d else 0
    recv = d["READ"][4] if "READ" in d else 0
    parts = " ".join(f"{op}={v[0]}" for op, v in d.items())
    print(
        f"{a['t'][11:19]}-{b['t'][11:19]}  {total / secs:7.0f} ops/s  rtt {rtt:5.2f} ms  "
        f"in flight {total * rtt / 1000 / secs:5.1f}  "
        f"recv/open {recv / opens / 1024 if opens else 0:6.1f} kB  {parts}"
    )
