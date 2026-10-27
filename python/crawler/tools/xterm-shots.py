#!/usr/bin/env python3
"""Drive a real xterm under a virtual X server and take screenshots of it.

    term.py start NAME [--cols N] [--rows N] -- COMMAND...   run COMMAND in a fresh xterm (bash -c)
    term.py key NAME KEY...        send keys (xdotool names: space, Page_Down, slash, Return, q, ctrl+c)
    term.py type NAME TEXT         type text
    term.py shot NAME OUT.png      screenshot the terminal into OUT.png
    term.py stop NAME              close the terminal and its X server

Each NAME has its own X display. The shell stays open after COMMAND exits
and prints [exit N], so the final screen can be captured.
"""

import json
import os
import shlex
import subprocess
import sys
import time
import zlib
from pathlib import Path

STATE = Path(os.environ.get("XTERM_SHOTS_STATE", "/tmp/xterm-shots"))


def _display(name: str) -> str:
    return f":{100 + zlib.crc32(name.encode()) % 800}"


def _state(name: str) -> Path:
    return STATE / f"{name}.json"


def start(name: str, cols: int, rows: int, command: list[str]) -> None:
    STATE.mkdir(exist_ok=True)
    if _state(name).exists():
        sys.exit(f"{name} is already running; stop it first")
    display = _display(name)
    xvfb = subprocess.Popen(
        [
            "Xvfb",
            display,
            "-screen",
            "0",
            f"{cols * 10 + 40}x{rows * 22 + 40}x24",
            "-nolisten",
            "tcp",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.0)
    env = dict(
        os.environ, DISPLAY=display, TERM="xterm-256color", LANG="C.UTF-8", LESS=""
    )
    script = (
        " ".join(shlex.quote(c) for c in command) if len(command) > 1 else command[0]
    )
    shell = f'{script}; echo; echo "[exit $?]"; exec bash --norc'
    xterm = subprocess.Popen(
        [
            "xterm",
            "-geometry",
            f"{cols}x{rows}+0+0",
            "-fa",
            "DejaVu Sans Mono",
            "-fs",
            "11",
            "-bg",
            "black",
            "-fg",
            "white",
            "+sb",
            "-e",
            "bash",
            "-c",
            shell,
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)
    _state(name).write_text(
        json.dumps({"display": display, "xvfb": xvfb.pid, "xterm": xterm.pid})
    )
    print(f"{name}: display {display}, {cols}x{rows}")


def _load(name: str) -> dict:
    try:
        return json.loads(_state(name).read_text())
    except FileNotFoundError:
        sys.exit(f"{name} is not running")


def _window(st: dict) -> str:
    out = subprocess.run(
        ["xdotool", "search", "--class", "xterm"],
        env=dict(os.environ, DISPLAY=st["display"]),
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    if not out:
        sys.exit("no xterm window found")
    return out[-1]


def _focus(st: dict) -> dict:
    env = dict(os.environ, DISPLAY=st["display"])
    subprocess.run(
        ["xdotool", "windowfocus", "--sync", _window(st)], env=env, check=True
    )
    return env


def key(name: str, keys: list[str]) -> None:
    env = _focus(_load(name))
    subprocess.run(["xdotool", "key", "--delay", "80", *keys], env=env, check=True)
    time.sleep(0.7)


def type_(name: str, text: str) -> None:
    env = _focus(_load(name))
    subprocess.run(["xdotool", "type", "--delay", "30", text], env=env, check=True)
    time.sleep(0.7)


def shot(name: str, out: str) -> None:
    st = _load(name)
    time.sleep(0.5)
    subprocess.run(
        ["import", "-display", st["display"], "-window", _window(st), out], check=True
    )
    print(out)


def stop(name: str) -> None:
    st = _load(name)
    for pid in (st["xterm"], st["xvfb"]):
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass
    _state(name).unlink()
    print(f"{name}: stopped")


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        sys.exit(__doc__)
    cmd, name = argv[0], argv[1]
    rest = argv[2:]
    if cmd == "start":
        cols, rows = 120, 40
        while rest and rest[0] in ("--cols", "--rows"):
            if rest[0] == "--cols":
                cols = int(rest[1])
            else:
                rows = int(rest[1])
            rest = rest[2:]
        if rest and rest[0] == "--":
            rest = rest[1:]
        if not rest:
            sys.exit("no command")
        start(name, cols, rows, rest)
    elif cmd == "key":
        key(name, rest)
    elif cmd == "type":
        type_(name, " ".join(rest))
    elif cmd == "shot":
        shot(name, rest[0])
    elif cmd == "stop":
        stop(name)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
