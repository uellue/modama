"""Fixture generators: a vendor-written DM3 file under a .dmw name (decision 174), files misnamed .dmw and .dmwx, and a compressed workspace composed of fixtures."""

import shutil
import zipfile
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
DM3 = FIXTURES / "stem_image_dm3" / "test_STEM_image.dm3"
DM4 = FIXTURES / "cl_image_dm4" / "test-MonarcCL_mono-image.dm4"
WORKSPACE = FIXTURES / "workspace" / "exemplary_workspace.dmw"


def compressed_workspace(target: Path) -> None:
    """A .dmwx laid out as Gatan Microscopy Suite writes one (observed 2026-11-12): the
    workspace first, then the directory files/ with an image, all deflated."""
    target.mkdir(parents=True)
    with zipfile.ZipFile(
        target / "exemplary_workspace.dmwx", "w", zipfile.ZIP_DEFLATED
    ) as z:
        z.write(WORKSPACE, "exemplary_workspace/exemplary_workspace.dmw")
        z.mkdir("exemplary_workspace/files/")
        z.write(DM4, f"exemplary_workspace/files/{DM4.name}")


def text_dmwx(target: Path) -> None:
    """A text file named like a compressed workspace."""
    target.mkdir(parents=True)
    (target / "notes.dmwx").write_text("hello\n")


def zip_without_workspace(target: Path) -> None:
    """A ZIP named like a compressed workspace whose first member is not a .dmw."""
    target.mkdir(parents=True)
    with zipfile.ZipFile(target / "other.dmwx", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("readme.txt", "hello\n")
        z.write(WORKSPACE, "exemplary_workspace.dmw")


def dm3_dmw(target: Path) -> None:
    """A DM3 file under a .dmw name, as a DM3 workspace would be named (decision 174)."""
    target.mkdir(parents=True)
    shutil.copy(DM3, target / "old_workspace.dmw")


def text_dmw(target: Path) -> None:
    """A text file named like a workspace."""
    target.mkdir(parents=True)
    (target / "notes.dmw").write_text("hello\n")


def empty_dmw(target: Path) -> None:
    """An empty file named like a workspace, as an interrupted copy leaves it."""
    target.mkdir(parents=True)
    (target / "empty.dmw").write_bytes(b"")
