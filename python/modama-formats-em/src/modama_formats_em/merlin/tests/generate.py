"""Fixture generators: the vendor-written files of the fixture single_frame, arranged as other acquisitions are."""

import shutil
from pathlib import Path

SINGLE = Path(__file__).parent / "fixtures" / "single_frame"
HDR = SINGLE / "Single_1_Frame_CounterDepth_6_Rows_256.hdr"
MIB = SINGLE / "Single_1_Frame_CounterDepth_6_Rows_256.mib"


def frame_series(target: Path) -> None:
    """acq.hdr with 200 frame files acq_1.mib to acq_200.mib, the shape of libertem-test-data's many_mib."""
    target.mkdir(parents=True)
    shutil.copy(HDR, target / "acq.hdr")
    for n in range(1, 201):
        shutil.copy(MIB, target / f"acq_{n}.mib")


def frames_without_header(target: Path) -> None:
    """Two frame files and no header, as when only the .mib files were copied."""
    target.mkdir(parents=True)
    shutil.copy(MIB, target / "acq_1.mib")
    shutil.copy(MIB, target / "acq_2.mib")
