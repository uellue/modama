"""Fixture generators: the vendor-written files of the fixture single_frame, arranged as other acquisitions are, and a composed acquisition."""

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


def not_utf8(target: Path) -> None:
    """acq.hdr and acq.mib, composed: a header with µ as the byte 0xB5 and the date key in the order (yr, mnth, day, ...).

    The header has single_frame's lines in its order with neutral values,
    except the lines of a staging header quoted in an error message (Chip ID,
    the date, the Sensor Bias key without a colon, Readout System, Software
    Version). The frame file is one 256x256 frame of zeros behind a
    single-chip frame header with the fields RosettaSciIO's MIBProperties reads.
    """
    target.mkdir(parents=True)
    lines = [
        "HDR,\t",
        "Time and Date Stamp (yr, mnth, day, hr, min, s):\t22/02/2019 10:27:28",
        "Chip ID:\tW529_F5,-,-,-",
        "Chip Type (Medipix 3.0, Medipix 3.1, Medipix 3RX):\tMedipix 3RX",
        "Assembly Size (NX1, 2X2):\t   1x1",
        "Chip Mode  (SPM, CSM, CM, CSCM):\tSPM",
        "Counter Depth (number):\t6",
        "Gain:\tSLGM",
        "Active Counters:\tCounter 0",
        "Thresholds (keV):\t0.000000E+0",
        "DACs:\t000",
        "bpc File:\tNone",
        "DAC File:\tNone",
        "Gap Fill Mode:\tNone",
        "Flat Field File:\tNone",
        "Dead Time File:\tNone",
        "Acquisition Type (Normal, Th_scan, Config):\tNormal",
        "Frames in Acquisition (Number):\t1",
        "Frames per Trigger (Number):\t1",
        "Trigger Start (Positive, Negative, Internal):\tInternal",
        "Trigger Stop (Positive, Negative, Internal):\tInternal",
        "Sensor Bias (V, µA)\t120 V",
        "Sensor Polarity (Positive, Negative):\tPositive",
        "Temperature (C):\tBoard Temp 40.000000 Deg C",
        "Humidity (%):\tBoard Humidity 10.000000 ",
        "Medipix Clock (MHz):\t120MHz",
        "Readout System:\tMerlin Quad",
        "Software Version:\t0.67.0.1",
    ]
    header = "\r\n".join(lines).encode("latin-1") + b"\r\nEnd\t"
    (target / "acq.hdr").write_bytes(header.ljust(2048, b" "))
    fields = [
        "MQ1", "000001", "00384", "01", "0256", "0256", "U08", "   1x1", "01",
        "2019-02-22 10:27:28.000000", "0.001000", "0", "0", "0",
        "MQ1A", "2019-02-22T09:27:28.000000000Z", "1000000ns", "6", "",
    ]  # fmt: skip
    frame = ",".join(fields).encode("ascii").ljust(384, b"\0")
    (target / "acq.mib").write_bytes(frame + bytes(256 * 256))
