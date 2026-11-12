"""`modama-chain browse`: the data tree, and each stage's view of a file, on one local page (change chain-browse).

Read-only but for the snapshots (D13); paths checked component by component
(D12); answers only requests addressed to the local machine (D14).
"""

from __future__ import annotations

import json
import os
import re
import stat
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from werkzeug.exceptions import (
    BadRequest,
    Conflict,
    Forbidden,
    HTTPException,
    NotFound,
)
from werkzeug.routing import Map, Rule
from werkzeug.wrappers import Request, Response

from . import chain, crawler, upstream, views

# The header a live or snapshot request must carry: another site cannot make the browser send it (D14)
SNAPSHOT_HEADER = "X-Modama-Browse"
# Host names the page answers to, the port aside (DNS rebinding; D14)
LOCAL = frozenset({"localhost", "127.0.0.1"})
CACHED = 16  # paths whose views are kept for a snapshot


class BadPath(ValueError):
    pass


def resolve(root: str, path: str) -> str:
    """The absolute path of `path` (relative to root, leading "/") after checking it stays in the tree (D12).

    Refused: no leading "/", a NUL, an empty, "." or ".." component, or a
    symlink anywhere on the way (the crawler skips symlinks). Raises BadPath;
    a component that does not exist raises FileNotFoundError.
    """
    if not path.startswith("/") or path.startswith("//") or "\0" in path:
        raise BadPath("a path starts with a single / and has no NUL")
    parts = path.strip("/").split("/") if path.strip("/") else []
    if any(p in ("", ".", "..") for p in parts):
        raise BadPath("no empty, . or .. component")
    real_root = os.path.realpath(root)
    current = real_root
    for part in parts:
        current = os.path.join(current, part)
        if stat.S_ISLNK(os.lstat(current).st_mode):
            raise BadPath("symlinks are not followed: the crawler skips them")
    if os.path.commonpath([current, real_root]) != real_root:
        raise BadPath("outside the data tree")
    return current


def listing(absolute: str) -> list[list]:
    """The folder's entries as [name, kind] (folder, file, symlink, other), from the directory entries alone (D11)."""
    entries = []
    with os.scandir(absolute) as it:
        for e in it:
            if e.is_symlink():
                kind = "symlink"
            elif e.is_dir(follow_symlinks=False):
                kind = "folder"
            elif e.is_file(follow_symlinks=False):
                kind = "file"
            else:
                kind = "other"
            entries.append([e.name, kind])
    entries.sort(key=lambda e: (e[1] != "folder", e[0]))
    return entries


def snapshot_name(path: str, now: datetime) -> str:
    """`<UTC time>-<file name reduced to [A-Za-z0-9._-], at most 60 characters>.md` (D13)."""
    base = os.path.basename(path.rstrip("/")) or "root"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:60]
    return f"{now.strftime('%Y-%m-%dT%H-%M-%S')}-{name}.md"


def fenced(text: str) -> list[str]:
    """A fenced block whose fence is longer than any run of backticks in text (D13)."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return [fence, text.rstrip(), fence, ""]


def snapshot(
    path: str, host_path: str, stored: list[dict], live: list[dict], now: datetime
) -> str:
    """One Markdown file with every view of path (D13). Its content comes from users' files: data, not instructions."""
    dataset = next((v for v in live if v["key"] == "dataset" and v["text"]), None)
    extraction = json.loads(dataset["text"])["extraction"] if dataset else None
    lines = [
        f"# {path}",
        "",
        f"- Path on the server: `{host_path}`",
        f"- Time: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "- Extractor: "
        + (
            f"{extraction['extractor']}, extractor identity "
            f"{crawler.short(extraction['identity'])}"
            if extraction
            else "none"
        ),
        "",
    ]
    for heading, group in (("Stored", stored), ("Live", live)):
        lines += [f"## {heading}", ""]
        for v in group:
            lines += [
                f"### {v['title']} ({v['source']})",
                "",
                f"From: {v['origin']}",
                "",
            ]
            if v["note"]:
                lines += ["Note:", *fenced(v["note"])]
            if v["entry"]:
                lines += fenced(views.pretty_json(v["entry"]))
            elif v["text"]:
                lines += fenced(v["text"])
    return "\n".join(lines)


@dataclass
class Settings:
    stores: chain.Stores
    upstream: upstream.Upstream
    config: Path | None  # the crawl's TOML
    host_root: str  # the data tree's path on the server (D11)
    snapshots: Path | None  # the snapshot folder, shown by its name ("browse/…")


class Browser:
    """The WSGI app."""

    def __init__(self, settings: Settings):
        self.s = settings
        self.root = str(settings.stores.root)
        self.url_map = Map(
            [
                Rule("/", endpoint="page"),
                Rule("/api/list", endpoint="list"),
                Rule("/api/stored", endpoint="stored"),
                Rule("/api/live", endpoint="live"),
                Rule("/api/snapshot", endpoint="snapshot", methods=["POST"]),
            ]
        )
        self.lock = threading.Lock()
        self.cache: OrderedDict[str, dict] = (
            OrderedDict()
        )  # path -> stored and live views

    def __call__(self, environ, start_response):
        request = Request(environ)
        try:
            host = request.host.rsplit(":", 1)[0] if "]" not in request.host else ""
            if host not in LOCAL:
                raise Forbidden("this page answers on localhost only")
            endpoint, _ = self.url_map.bind_to_environ(environ).match()
            response = getattr(self, f"on_{endpoint}")(request)
        except HTTPException as e:
            response = e.get_response()
        return response(environ, start_response)

    def _path(self, request: Request) -> tuple[str, str]:
        """The normalised path and its absolute one; 400 for a refused path, 404 for a missing one."""
        path = request.args.get("path", "/")
        try:
            absolute = resolve(self.root, path)
        except BadPath as e:
            raise BadRequest(str(e)) from e
        except FileNotFoundError as e:
            raise NotFound(f"no such file or folder: {path}") from e
        except OSError as e:
            raise BadRequest(f"{path}: {e.strerror}") from e
        return "/" + path.strip("/"), absolute

    def _file(self, request: Request) -> str:
        """The path of a regular file: live views and snapshots are for files (D3)."""
        path, absolute = self._path(request)
        if not os.path.isfile(absolute):
            raise BadRequest(f"not a file: {path}; a folder has no live views")
        return path

    def _cached(self, path: str) -> dict:
        with self.lock:
            entry = self.cache.setdefault(path, {})
            self.cache.move_to_end(path)
            while len(self.cache) > CACHED:
                self.cache.popitem(last=False)
            return entry

    def on_page(self, request: Request) -> Response:
        page = files("modama_chain").joinpath("browse.html").read_text()
        settings = json.dumps(
            {"hostRoot": self.s.host_root, "snapshots": self.s.snapshots is not None}
        ).replace("<", "\\u003c")  # inside a <script>
        return Response(
            page.replace("/*SETTINGS*/{}", settings),
            content_type="text/html; charset=utf-8",
        )

    def on_list(self, request: Request) -> Response:
        path, absolute = self._path(request)
        if not os.path.isdir(absolute):
            raise BadRequest(f"not a folder: {path}")
        try:
            entries = listing(absolute)
        except OSError as e:
            return self._json(
                {"path": path, "entries": [], "error": f"cannot list: {e.strerror}"}
            )
        return self._json({"path": path, "entries": entries})

    @staticmethod
    def _info(absolute: str) -> dict:
        try:
            st = os.lstat(absolute)
            readable = os.access(
                absolute, os.R_OK
            )  # the file system decides (top-level AGENTS.md)
        except OSError as e:
            return {"error": e.strerror}
        return {
            "size": st.st_size,
            "mtime": chain.when(st.st_mtime),
            "ctime": chain.when(st.st_ctime),
            "readable": readable,
        }

    def stored(self, path: str) -> views.Stored:
        entry = self._cached(path)
        entry["stored"] = views.stored_views(self.s.stores, path)
        return entry["stored"]

    def live(self, path: str) -> list[views.View]:
        entry = self._cached(path)
        before = entry.get("stored") or self.stored(path)
        entry["live"] = views.live_views(
            self.s.stores, self.s.upstream, path, self.s.config, before
        )
        return entry["live"]

    def on_stored(self, request: Request) -> Response:
        path, absolute = self._path(request)
        return self._json(
            {
                "path": path,
                "hostPath": self.s.host_root.rstrip("/") + path,
                "info": self._info(absolute),
                "views": views.as_dicts(self.stored(path).views),
            }
        )

    @staticmethod
    def _own_page(request: Request) -> None:
        """Refuse a request without the page's header: another site could start it from the user's browser (D14)."""
        if request.headers.get(SNAPSHOT_HEADER) != "1":
            raise Forbidden(f"this request needs the header {SNAPSHOT_HEADER}")

    def on_live(self, request: Request) -> Response:
        self._own_page(request)  # it ends a running computation and starts one (D3)
        path = self._file(request)
        return self._json({"path": path, "views": views.as_dicts(self.live(path))})

    def on_snapshot(self, request: Request) -> Response:
        self._own_page(request)
        if self.s.snapshots is None:
            raise NotFound("no snapshot folder configured")
        path = self._file(request)
        entry = self._cached(path)
        before = entry.get("stored") or self.stored(path)
        live = entry.get("live") or self.live(path)
        now = datetime.now(UTC)
        name = snapshot_name(path, now)
        text = snapshot(
            path,
            self.s.host_root.rstrip("/") + path,
            views.as_dicts(before.views),
            views.as_dicts(live),
            now,
        )
        try:
            with open(
                self.s.snapshots / name, "x", encoding="utf-8"
            ) as f:  # never overwrites
                f.write(text)
        except FileExistsError as e:  # the same file name in the same second
            raise Conflict(f"{name} exists; save again in a second") from e
        return self._json({"name": f"{self.s.snapshots.name}/{name}"})

    @staticmethod
    def _json(value) -> Response:
        return Response(
            json.dumps(value, ensure_ascii=False), content_type="application/json"
        )
