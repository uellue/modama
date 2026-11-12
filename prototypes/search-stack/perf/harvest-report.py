"""Phases of the harvest's two Python processes from perf/harvest-bench.sh's py-spy records (standard library only).

  python3 harvest-report.py OUT
harvester.raw: the harvester process (one thread does the whole harvest); api.raw: the warehouse API (`transform`),
all its threads, idle ones included (--idle), so only the request-handling stacks are split up.
"""

import sys
from collections import Counter
from pathlib import Path

out = Path(sys.argv[1])

HARVESTER = [  # first match wins
    (
        "POST /harvest_event to the warehouse API, waiting",
        lambda s: "send_harvest_event" in s,
    ),
    ("XSLT apply (oai_dc to DataCite)", lambda s: "apply_xslt_transform" in s),
    (
        "XSLT parse + compile, again for every record",
        lambda s: "transformation_and_additional_metadata" in s,
    ),
    ("process_record, rest (tostring, payload)", lambda s: "process_record" in s),
    (
        "OAI-PMH page request to the crawler, waiting",
        lambda s: "run_harvest_loop" in s and "httpx" in s,
    ),
    ("OAI-PMH response parsing (Scythe, lxml)", lambda s: "run_harvest_loop" in s),
    ("imports", lambda s: "_find_and_load" in s),
    ("no Python frame", lambda s: not s.strip()),
    ("other", lambda s: True),
]
API = [
    (
        "request: psycopg.connect (a new connection per request)",
        lambda s: "create_harvest_event" in s and "connect (psycopg" in s,
    ),
    (
        "request: INSERT ... RETURNING (executemany)",
        lambda s: "create_harvest_event" in s and "executemany" in s,
    ),
    (
        "request: commit and close",
        lambda s: "create_harvest_event" in s and "__exit__" in s,
    ),
    ("request: rest", lambda s: "create_harvest_event" in s),
    (
        "event loop: HTTP, routing, pydantic",
        lambda s: (
            ("uvicorn" in s or "starlette" in s or "fastapi" in s)
            and "select (selectors" not in s
            and "run_sync_in_worker_thread" not in s
            # the event loop waiting in native code shows as its Python caller
            and not s.endswith("run (asyncio/runners.py:118)")
        ),
    ),
    ("idle (event loop select, worker threads waiting)", lambda s: True),
]


def summary(name: str, rules) -> None:
    raw = out / name
    if not raw.exists() or not raw.stat().st_size:
        print(f"{name}: no profile")
        return
    counts, leaves = Counter(), {}
    for line in raw.read_text().splitlines():
        stack, _, n = line.rpartition(" ")
        if not n.isdigit():
            continue
        phase = next(p for p, match in rules if match(stack))
        counts[phase] += int(n)
        leaves.setdefault(phase, Counter())[stack.split(";")[-1]] += int(n)
    total = sum(counts.values())
    print(
        f"{name}: {total} samples at 100 Hz ({total / 100:.1f} s summed over the threads sampled)"
    )
    for phase, _ in rules:
        if counts[phase]:
            top = ", ".join(f"{leaf} {c}" for leaf, c in leaves[phase].most_common(2))
            print(
                f"  {phase:58} {counts[phase] / 100:7.1f} s {counts[phase] / total:6.1%}   [{top[:150]}]"
            )


summary("harvester.raw", HARVESTER)
summary("api.raw", API)
