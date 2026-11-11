"""Fixture generators: the vendor-written DM4 file of the fixture cl_image_dm4 under a name that decides another type (F15)."""

import shutil
from pathlib import Path

DM4 = (
    Path(__file__).parent / "fixtures" / "cl_image_dm4" / "test-MonarcCL_mono-image.dm4"
)


def dmw_file(target: Path) -> None:
    """A DM4 file named as staging's .dmw files are."""
    target.mkdir(parents=True)
    shutil.copy(DM4, target / "conditions_00C.dmw")
