"""Playground: the crawl's I/O (list, lstat, MIME with a header read) with N threads.

Uses the crawler's own MIME classifier (mime.detect_with_tie), with its `open`
replaced by one of the read modes below. Not the crawler: no formats, no records.

  pywalk.py ROOT --threads N --mode {plain,fadvise,odirect} [--access] [--out FILE]
"""

import argparse
import mmap
import os
import resource
import stat
import sys
import tempfile
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

from modama_crawler import mime, mimedb, selection
from xdg import Mime


class Reader:
    """A file-like object with read(n) that does one pread, as the mode asks."""

    def __init__(self, path, mode):
        self.mode = mode
        flags = os.O_RDONLY | (os.O_DIRECT if mode == "odirect" else 0)
        self.fd = os.open(path, flags)
        if mode == "fadvise":
            os.posix_fadvise(self.fd, 0, 0, os.POSIX_FADV_RANDOM)

    def read(self, n):
        if self.mode == "odirect":
            size = (n + 4095) // 4096 * 4096
            buf = mmap.mmap(-1, size)  # page-aligned
            got = os.preadv(self.fd, [buf], 0)
            return bytes(buf[: min(got, n)])
        return os.pread(self.fd, n, 0)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        os.close(self.fd)


def _init_worker():
    global _worker_tmp
    _worker_tmp = tempfile.TemporaryDirectory(prefix="pywalk-mime-")
    config = selection.load_config(None)
    defs = selection.enabled_collections(selection.discover().values(), config)
    mimedb.build(defs, Path(_worker_tmp.name))


def _match(data):
    t = Mime.magic.match_data(data)
    return None if t is None else str(t)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("root")
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--mode", default="plain", choices=["plain", "fadvise", "odirect"])
    p.add_argument(
        "--access", action="store_true", help="os.access per file, as the crawler"
    )
    p.add_argument(
        "--procs", type=int, default=0, help="worker processes for magic matching"
    )
    p.add_argument(
        "--defer-stat",
        action="store_true",
        help="lstat in the file task, not the directory's",
    )
    p.add_argument("--out", help="write rel<TAB>mime per file here")
    a = p.parse_args()

    tmp = tempfile.TemporaryDirectory(prefix="pywalk-mime-")
    config = selection.load_config(None)
    defs = selection.enabled_collections(selection.discover().values(), config)
    mimedb.build(defs, Path(tmp.name))
    # a module global shadows the builtin
    mime.open = lambda path, *args, **kw: Reader(path, a.mode)
    print(f"magic maxlen {Mime.magic.maxlen}", file=sys.stderr)
    # magic matching (CPU, holds the GIL) in worker processes; I/O stays in threads
    if a.procs:
        procs = ProcessPoolExecutor(a.procs, initializer=_init_worker)

        def match_data(data, max_pri=100, min_pri=0, possible=None):
            name = procs.submit(_match, data).result()
            return None if name is None else Mime.lookup(name)

        Mime.magic.match_data = match_data

    root = os.path.abspath(a.root)
    lock = threading.Lock()
    done = threading.Event()
    pending = [0]
    counts = {"dirs": 0, "files": 0, "errors": 0}
    results = []
    pool = ThreadPoolExecutor(a.threads)

    def submit(fn, *args):
        with lock:
            pending[0] += 1
        pool.submit(run, fn, *args)

    def run(fn, *args):
        try:
            fn(*args)
        except OSError as e:
            with lock:
                counts["errors"] += 1
            print(f"{args[0]}: {e}", file=sys.stderr)
        finally:
            with lock:
                pending[0] -= 1
                if pending[0] == 0:
                    done.set()

    def visit_dir(path):
        with os.scandir(path) as it:
            entries = sorted(it, key=lambda e: e.name)
        with lock:
            counts["dirs"] += 1
        if a.defer_stat:  # d_type from READDIR; lstat in the file's own task
            for e in entries:
                if e.is_dir(follow_symlinks=False):
                    submit(visit_dir, e.path)
                elif e.is_file(follow_symlinks=False):
                    submit(visit_file, e.path)
            return
        for name in (e.name for e in entries):
            child = os.path.join(path, name)
            st = os.lstat(child)
            if stat.S_ISDIR(st.st_mode):
                submit(visit_dir, child)
            elif stat.S_ISREG(st.st_mode):
                submit(visit_file, child)

    def visit_file(path):
        if a.defer_stat:
            os.lstat(path)  # the crawler needs size, times and owner of every file
        if a.access and not os.access(path, os.R_OK):
            return
        detected, _ = mime.detect_with_tie(path)
        with lock:
            counts["files"] += 1
            results.append((path[len(root) :], detected))

    t0 = time.monotonic()
    submit(visit_dir, root)
    done.wait()
    wall = time.monotonic() - t0
    pool.shutdown()
    ru = resource.getrusage(resource.RUSAGE_SELF)
    print(
        f"threads {a.threads} mode {a.mode} access {a.access}: "
        f"{counts['dirs']} dirs, {counts['files']} files, {counts['errors']} errors, "
        f"{wall:.2f} s, {counts['files'] / wall:.1f} files/s, "
        f"cpu user {ru.ru_utime:.2f} s sys {ru.ru_stime:.2f} s, maxrss {ru.ru_maxrss / 1024:.0f} MB",
        file=sys.stderr,
    )
    if a.out:
        with open(a.out, "w") as f:
            f.writelines(f"{rel}\t{m}\n" for rel, m in sorted(results))


if __name__ == "__main__":
    main()
