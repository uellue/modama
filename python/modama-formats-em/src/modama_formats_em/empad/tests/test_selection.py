"""The crawler's format selection with this collection (spec format-selection,
"A collection switched off as a whole"), run as a subprocess like a user would."""

import subprocess
import sys

from lxml import etree

from .. import cheat

DC = "{http://purl.org/dc/elements/1.1/}"


def formats(*args) -> list[str]:
    run = subprocess.run(
        [sys.executable, "-m", "modama_crawler", "records", *args],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return sorted(e.text for e in etree.fromstring(run.stdout).iter(f"{DC}format"))


def test_a_collection_switched_off_as_a_whole(tmp_path):
    cheat.pair(tmp_path / "scan")
    assert formats(str(tmp_path)) == ["application/x.empad+xml"]
    # Its MIME definitions are off too: the raw file is not application/x.empad-raw
    assert formats("--ignore", "em", str(tmp_path)) == [
        "application/octet-stream",
        "application/xml",
    ]
    # Only the format ignored: the definitions stay, the files are classified by name
    assert formats("--ignore", "em/empad", str(tmp_path)) == [
        "application/x.empad+xml",
        "application/x.empad-raw",
    ]
