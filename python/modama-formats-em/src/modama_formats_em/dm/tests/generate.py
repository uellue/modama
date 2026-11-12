"""Fixture generators: vendor-written DM files under a name that decides another type (F15), and files misnamed .dmw."""

import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
DM4 = FIXTURES / "cl_image_dm4" / "test-MonarcCL_mono-image.dm4"
DM3 = FIXTURES / "stem_image_dm3" / "test_STEM_image.dm3"


def dmw_file(target: Path) -> None:
    """A DM4 file named as staging's .dmw files are."""
    target.mkdir(parents=True)
    shutil.copy(DM4, target / "conditions_00C.dmw")


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
