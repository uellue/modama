"""Fixture generators: MRC files written by mrcfile, the field's reader and writer."""

from pathlib import Path

import mrcfile
import numpy as np


def write(path: Path, data: np.ndarray, *, stack: bool = False, labels=()) -> None:
    """An MRC file of `data` with a voxel size of 1.5 and the given labels."""
    with mrcfile.new(path) as m:
        # mrcfile's own first label has the time of writing; without it the
        # recorded results stay the same from run to run
        m.header.label[0] = b""
        m.header.nlabl = 0
        m.set_data(data)
        if stack:
            m.set_image_stack()
        m.voxel_size = 1.5
        for label in labels:
            m.add_label(label)


def written_by_mrcfile(target: Path) -> None:
    """stack.mrcs, an image stack of 3 frames of 16x16 int16, and image.mrc, one 16x16 float32 image."""
    target.mkdir(parents=True)
    write(
        target / "stack.mrcs",
        np.arange(3 * 16 * 16, dtype=np.int16).reshape(3, 16, 16),
        stack=True,
        labels=["stack written by mrcfile"],
    )
    write(target / "image.mrc", np.zeros((16, 16), dtype=np.float32))
