"""Fixture generators: reproducers made of RosettaSciIO's DE-Server 2.7.4 acquisition (fixtures/acquisition_274), renamed or edited."""

import shutil
from pathlib import Path

ACQUISITION = Path(__file__).parent / "fixtures" / "acquisition_274"
STEM = "20241021_00405_"


def _copy(target: Path, kind: str, name: str) -> None:
    """The acquisition's file STEM + kind, as target/name."""
    shutil.copyfile(ACQUISITION / f"{STEM}{kind}", target / name)


def with_suffix(target: Path) -> None:
    """The info file, movie and sum with a user-set filename suffix: 20241021_00405_sampleA_*."""
    target.mkdir(parents=True)
    for kind in ("info.txt", "movie.mrc", "final.mrc"):
        _copy(target, kind, f"{STEM}sampleA_{kind}")


def nested_stems(target: Path) -> None:
    """Two acquisitions whose stems nest: 20241021_00405_ and 20241021_00405_x_, each an info file and a movie."""
    target.mkdir(parents=True)
    for stem in (STEM, f"{STEM}x_"):
        _copy(target, "info.txt", f"{stem}info.txt")
        _copy(target, "movie.mrc", f"{stem}movie.mrc")


def with_log(target: Path) -> None:
    """The info file and movie with a made-up 20241021_00405_processing.log, a kind of file no public source names."""
    target.mkdir(parents=True)
    _copy(target, "info.txt", f"{STEM}info.txt")
    _copy(target, "movie.mrc", f"{STEM}movie.mrc")
    (target / f"{STEM}processing.log").write_text("a made-up log line\n")


def other_program(target: Path) -> None:
    """Another program's files with a date prefix: a text 20240619_1736_info.txt and an MRC file 20240619_1736_HAADF.mrc."""
    target.mkdir(parents=True)
    (target / "20240619_1736_info.txt").write_text("Sample: lamella 3\n")
    _copy(target, "final.mrc", "20240619_1736_HAADF.mrc")


def lone_movie(target: Path) -> None:
    """The movie without its info file."""
    target.mkdir(parents=True)
    _copy(target, "movie.mrc", f"{STEM}movie.mrc")


def renamed_info(target: Path) -> None:
    """The info file (Dataset Name 20241021_00405) named 20241021_00406_info.txt."""
    target.mkdir(parents=True)
    _copy(target, "info.txt", "20241021_00406_info.txt")


def new_entry(target: Path) -> None:
    """The info file with one more line that no DE-Server version is known to write."""
    target.mkdir(parents=True)
    text = (ACQUISITION / f"{STEM}info.txt").read_bytes()
    (target / f"{STEM}info.txt").write_bytes(text + b"Made Up Entry (units) = 42\n")
