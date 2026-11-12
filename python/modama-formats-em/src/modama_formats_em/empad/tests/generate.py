"""Fixture generators of EMPAD acquisitions around a vendor-written header."""

import shutil
from pathlib import Path

HERE = Path(__file__).parent
FRAME_BYTES = 130 * 128 * 4  # 128x128 float32 and two footer rows


def scan_v1_2_2(target: Path) -> None:
    """RosettaSciIO's header of a 32x64 scan by the EMPAD software 1.2.2, with its raw
    file as a sparse file of the right size: the crawler reads only the header."""
    target.mkdir(parents=True)
    shutil.copy(HERE / "rsciio" / "EMPAD_v1.2.2_x32_y64_size0.8.xml", target)
    with open(target / "scan_x32_y64.raw", "wb") as f:
        f.truncate(32 * 64 * FRAME_BYTES)
