"""The per-deployment MIME database, built from the enabled collections only (Q12)."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

import xdg.BaseDirectory
from xdg import Mime

from . import mime
from .formats import Collection


def build(collections: Iterable[Collection], directory: Path) -> Path:
    """Assemble the collections' XML into directory/mime, compile it, and make it the only database."""
    packages = Path(directory) / "mime" / "packages"
    packages.mkdir(parents=True, exist_ok=True)
    for collection in collections:
        for xml in collection.mime_files:
            shutil.copyfile(xml, packages / f"{collection.name}-{xml.name}")
    try:
        subprocess.run(
            ["update-mime-database", str(packages.parent)],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "update-mime-database not found; install shared-mime-info"
        ) from None
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"update-mime-database failed: {e.stderr}") from None
    activate(Path(directory))
    return Path(directory)


def activate(directory: Path) -> None:
    """Point pyxdg at directory and nothing else, and reload its caches."""
    # pyxdg reads these module attributes on every lookup; the environment is left alone
    xdg.BaseDirectory.xdg_data_home = str(directory)
    xdg.BaseDirectory.xdg_data_dirs = [str(directory)]
    Mime._cache_uptodate = False  # no public way to make pyxdg reload yet
    Mime.update_cache()
    mime._glob_index.cache_clear()
    mime.database = Path(directory)
