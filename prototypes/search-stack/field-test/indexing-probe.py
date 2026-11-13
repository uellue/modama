"""Probe of the embedding worker during indexing: where the batches spend their time.

Run inside the worker, reading this file from stdin, output to the run's folder:
  dc exec -T airflow-worker-transform python3 - < field-test/indexing-probe.py > <run folder>/indexing-probe.log 2>&1

Every INTERVAL seconds, one block per sample:
  === <UTC time>  load <1 5 15>  cpus <n>
  <pid> cpu=<% of one core over the interval> thr=<threads> rss=<MiB> age=<s> <command, shortened>
for every process in the container that used CPU in the interval or is a Python process.
Every STACK_EVERY samples, `py-spy dump` of the busiest Python process (with --native if
it works), so that the stacks over a night show where the time goes. Standard library only;
read-only: it writes nothing but its output.

It stops by itself after MAX_HOURS, or when the container stops. Ctrl-C ends only the
`docker compose exec` client; the probe goes on inside the container. To stop it early:
  dc exec -T airflow-worker-transform sh -c 'for p in /proc/[0-9]*; do case "$(tr "\0" " " < $p/cmdline)" in "python3 -"*) kill "${p#/proc/}";; esac; done'
"""

import os
import subprocess
import sys
import time

INTERVAL = 10.0
STACK_EVERY = 3  # a stack dump every 30 s
MAX_HOURS = 16
PY_SPY = "/home/airflow/.local/bin/py-spy"
TICK = os.sysconf("SC_CLK_TCK")
PAGE = os.sysconf("SC_PAGE_SIZE")
ME = os.getpid()


def processes() -> dict[int, tuple[int, int, int, float, str]]:
    """pid -> (cpu ticks, threads, rss bytes, start ticks, command) for every process we can read."""
    out = {}
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == ME:
            continue
        try:
            with open(f"/proc/{name}/stat") as f:
                stat = f.read()
            with open(f"/proc/{name}/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode(errors="replace").strip()
        except OSError:
            continue  # gone
        fields = stat[stat.rindex(")") + 2 :].split()
        # fields[0] is field 3 (state): utime 14, stime 15, num_threads 20, starttime 22, rss 24
        ticks = int(fields[11]) + int(fields[12])
        out[int(name)] = (
            ticks,
            int(fields[17]),
            int(fields[21]) * PAGE,
            int(fields[19]),
            cmd,
        )
    return out


def uptime() -> float:
    with open("/proc/uptime") as f:
        return float(f.read().split()[0])


def stack(pid: int) -> str:
    for args in (
        [PY_SPY, "dump", "--native", "--pid", str(pid)],
        [PY_SPY, "dump", "--pid", str(pid)],
    ):
        try:
            r = subprocess.run(
                args, check=False, capture_output=True, text=True, timeout=20
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            return f"py-spy failed: {e!r}"
        if r.returncode == 0:
            return r.stdout
    return f"py-spy failed ({r.returncode}): {r.stderr.strip()[:300]}"


def main() -> None:
    cpus = os.cpu_count()
    before, t0, n = processes(), time.monotonic(), 0
    print(
        f"indexing probe started, pid {ME}, interval {INTERVAL} s, py-spy every {STACK_EVERY} samples",
        flush=True,
    )
    started = t0
    while time.monotonic() - started < MAX_HOURS * 3600:
        time.sleep(INTERVAL)
        now, t1, n = processes(), time.monotonic(), n + 1
        dt, up = t1 - t0, uptime()
        with open("/proc/loadavg") as f:
            load = " ".join(f.read().split()[:3])
        rows = []
        for pid, (ticks, threads, rss, start, cmd) in now.items():
            used = ticks - before[pid][0] if pid in before else ticks
            cpu = 100.0 * used / TICK / dt
            if cpu >= 1.0 or "python" in cmd:
                rows.append((cpu, pid, threads, rss, up - start / TICK, cmd))
        rows.sort(reverse=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        lines = [f"=== {stamp}  load {load}  cpus {cpus}"]
        lines += [
            f"{pid} cpu={cpu:.0f}% thr={thr} rss={rss / 2**20:.0f}MiB age={age:.0f}s {cmd[:150]}"
            for cpu, pid, thr, rss, age, cmd in rows
        ]
        busy = [
            r for r in rows if r[0] >= 50 and "python" in r[5] and "py-spy" not in r[5]
        ]
        if busy and n % STACK_EVERY == 0:
            lines.append(f"--- py-spy dump of {busy[0][1]} (cpu {busy[0][0]:.0f}%)")
            lines.append(stack(busy[0][1]).rstrip())
        print("\n".join(lines), flush=True)
        before, t0 = now, t1


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        sys.exit(0)
