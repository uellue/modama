"""A small EMPAD acquisition for tests: a real header reduced to four frames and a zero-filled raw file.

The header is an ER-C acquisition's, with the frame count set to 4 and the raw
file name adjusted. The raw file is 4 frames of 130x128 float32 zeros, the
layout that EMPAD readers expect (the last two rows of each frame are a footer).
Only the header is read by the crawler, so this stands in for a real pair.
"""

from pathlib import Path

FRAMES = 4
FRAME_BYTES = 130 * 128 * 4
RAW_NAME = f"series_x{FRAMES}.raw"

HEADER = (
    '<root name="SCA2_rings"><timestamp timestamp="1651505319.775119" '
    'isoformat="2022-05-02T17:28:39.775119"/><software_version>0.7.12  (2019-10-01)</software_version>'
    '<reconstructions Sentinel="Test  "/><type>series</type>'
    f'<count>{FRAMES}</count><raw_file filename="{RAW_NAME}"/>'
    '<background_image timestamp="1651504157.950859" '
    'absolute_filename=" /home/empad/backgrounds/img_exp_1_frm_0_cnt_1000_0002"/>'
    "<exposure_time>1.0</exposure_time><post_exposure_time>0</post_exposure_time>"
    "<camserver_parameters><camserver_inserted>True</camserver_inserted>"
    "<camserver_connected>True</camserver_connected>"
    "<camserver_acquisition_pending>False</camserver_acquisition_pending>"
    "<camserver_scan_enabled>True</camserver_scan_enabled><camserver_poweron>True</camserver_poweron>"
    "<camserver_scan_focus>False</camserver_scan_focus></camserver_parameters>"
    f"<scan_parameters><series_count>{FRAMES}</series_count></scan_parameters></root>"
)


def pair(target: Path) -> None:
    target.mkdir(parents=True)
    (target / "SCA2_rings.xml").write_text(HEADER)
    (target / RAW_NAME).write_bytes(bytes(FRAMES * FRAME_BYTES))


def pair_declaration(target: Path) -> None:
    """The pair with the header re-saved with an XML declaration and a newline, as hand-edited copies in the wild have it."""
    pair(target)
    (target / "SCA2_rings.xml").write_text('<?xml version="1.0"?>\n' + HEADER + "\n")


def pair_scan(target: Path) -> None:
    """The pair with the raw file named like a 4D STEM scan (scan_x*_y*.raw), the other glob of the raw type."""
    target.mkdir(parents=True)
    raw = "scan_x4_y4.raw"
    (target / "SCA2_rings.xml").write_text(HEADER.replace(RAW_NAME, raw))
    (target / raw).write_bytes(bytes(FRAMES * FRAME_BYTES))


def header_only(target: Path) -> None:
    target.mkdir(parents=True)
    (target / "SCA2_rings.xml").write_text(HEADER)


def orphan_raw(target: Path) -> None:
    target.mkdir(parents=True)
    (target / "series_x1234.raw").write_bytes(bytes(FRAME_BYTES))
    (target / "unrelated.xml").write_text('<?xml version="1.0"?>\n<data/>\n')
