"""The CPUs this process may use, and one thread per math library in the worker processes (R43, spec `cpu-budget`).

The count is the CPUs of the affinity (a cpuset included), capped by the own
cgroup v2 group's CPU quota, rounded up; not the machine's `os.cpu_count()`,
and not `os.process_cpu_count()`, which also obeys `PYTHON_CPU_COUNT`.
Modelled on `dask.system.cpu_count`, not copied (design D2).

`set_num_threads_env` is copied from LiberTEM, src/libertem/common/threading.py
at commit d6aa0fa (https://github.com/LiberTEM/LiberTEM), without its numba
branch; under LiberTEM's licence:

    Copyright (c) 2024 LiberTEM creators

    Permission is hereby granted, free of charge, to any person obtaining a copy of
    this software and associated documentation files (the "Software"), to deal in
    the Software without restriction, including without limitation the rights to
    use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
    the Software, and to permit persons to whom the Software is furnished to do so,
    subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
    FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
    COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
    IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
    CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import math
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Usable:
    """The CPUs of the affinity and the CPU quota (None: none, or not read)."""

    affinity: int
    quota: float | None
    cgroup_v2: bool

    @property
    def cpus(self) -> int:
        if self.quota is None:
            return self.affinity
        return min(self.affinity, math.ceil(self.quota))

    def __str__(self) -> str:
        if not self.cgroup_v2:
            quota = "quota not read: no cgroup v2"
        elif self.quota is None:
            quota = "no quota"
        else:
            quota = f"quota {self.quota:g}"
        return f"{self.cpus} CPUs usable (affinity {self.affinity}, {quota})"


def usable(root: Path = Path("/")) -> Usable:
    """The CPUs this process may use; `root` is where `proc` and `sys` are (tests)."""
    affinity = len(os.sched_getaffinity(0))
    group = _group(root)
    if group is None:
        return Usable(affinity, None, False)
    return Usable(affinity, _quota(root / "sys/fs/cgroup" / group / "cpu.max"), True)


def _group(root: Path) -> str | None:
    """The own cgroup v2 group, from the `0::` line of /proc/self/cgroup, relative to the hierarchy's root."""
    for line in (root / "proc/self/cgroup").read_text().splitlines():
        if line.startswith("0::"):
            return line[3:].lstrip("/")
    return None


def _quota(cpu_max: Path) -> float | None:
    """CPUs per period from `cpu.max` (`max 100000`, `250000 100000`); None for `max` or no file (the root group)."""
    try:
        quota, period = cpu_max.read_text().split()
    except FileNotFoundError:
        return None
    return None if quota == "max" else int(quota) / int(period)


@contextmanager
def set_num_threads_env(n=1):
    """Set the maximum number of threads via environment variables.
    Currently sets variables for MKL, OMP and OPENBLAS.

    This is needed if you want to limit the number of threads that
    are created at startup of those libraries, because the other
    methods usually only limit the number of threads that are _used_,
    not the number of threads that are created.

    Parameters
    ----------
    n : int
        The maximum number of threads
    """
    try:
        env_keys = ["MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"]
        old_env = {k: os.environ[k] for k in env_keys if k in os.environ}
        os.environ.update({k: str(n) for k in env_keys})
        yield
    finally:
        os.environ.update(old_env)
        for key in env_keys:
            if key not in old_env:
                del os.environ[key]
