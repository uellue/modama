"""Fixture generators of the collapse collection: the real producers write the trees at test time."""

import py_compile
import subprocess
import sys
from pathlib import Path


def venv(target: Path) -> None:
    target.mkdir(parents=True)
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(target / "env")], check=True
    )
    (target / "notes.txt").write_text("next to an environment\n")


def git(target: Path) -> None:
    target.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    (target / "notes.txt").write_text("a work tree\n")


def caches(target: Path) -> None:
    target.mkdir(parents=True)
    module = target / "module.py"
    module.write_text("x = 1\n")
    py_compile.compile(
        str(module), cfile=str(target / "__pycache__" / "module.cpython-314.pyc")
    )
    (target / ".ipynb_checkpoints").mkdir()
    (target / ".ipynb_checkpoints" / "a-checkpoint.ipynb").write_text("{}\n")
    (target / "node_modules" / "left-pad").mkdir(parents=True)
    (target / "node_modules" / "left-pad" / "index.js").write_text(
        "module.exports = s => s;\n"
    )
    (target / "conda" / "conda-meta").mkdir(parents=True)
    (target / "conda" / "conda-meta" / "history").write_text("==> 2026-10-16 <==\n")
    (target / "conda" / "bin").mkdir()
    (target / "conda" / "bin" / "python").write_text("")


def venv_without_lib(target: Path) -> None:
    target.mkdir(parents=True)
    (target / "env").mkdir()
    (target / "env" / "pyvenv.cfg").write_text("home = /usr/bin\nversion = 3.14.0\n")
