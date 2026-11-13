"""Writes the fixture `fixtures/zspy/scan.zspy` with RosettaSciIO's zspy writer, once.

RosettaSciIO 0.15.0's zspy writer needs zarr 2 (its extra `zspy` requires
`zarr<3`), which cannot share a venv with the tests' zarr 3; so the store was
written once, on 2026-11-13, and is committed. Its module imports h5py, which
the extra `zspy` does not bring, and the extra `hdf5` does (there is no extra
`hspy`). To write it again, into a new folder:

    uv run --no-project --python 3.12 --with "rosettasciio[zspy,hdf5]==0.15.0" \
        python write_zspy.py TARGET

(it ran with zarr 2.18.7, numcodecs 0.15.2, h5py 3.16.0). A signal dictionary
as HyperSpy hands one to the writer, shaped like a pyxem 4D-STEM scan (signal
type electron_diffraction): 4 x 4 scan positions of 16 x 16 pixels of uint16;
every value made up, with one entry nobody has seen and HyperSpy's placeholder
`_None_`. Without consolidated metadata, as the stores in the ER-C tree were
written.
"""

import sys
from pathlib import Path

import numpy
from rsciio.zspy import file_writer


def axis(name, size, scale, units, navigate):
    return {
        "_type": "UniformDataAxis",
        "name": name,
        "units": units,
        "navigate": navigate,
        "is_binned": False,
        "size": size,
        "scale": scale,
        "offset": 0.0,
    }


signal = {
    "data": numpy.arange(4 * 4 * 16 * 16, dtype="uint16").reshape(4, 4, 16, 16),
    "axes": [
        axis("x", 4, 1.5, "nm", True),
        axis("y", 4, 1.5, "nm", True),
        axis("kx", 16, 0.05, "1/nm", False),
        axis("ky", 16, 0.05, "1/nm", False),
    ],
    "metadata": {
        "General": {"title": "4D-STEM scan", "original_filename": "scan.mib"},
        "Signal": {"signal_type": "electron_diffraction", "quantity": "Counts"},
        "Acquisition_instrument": {
            "TEM": {"beam_energy": 300.0, "camera_length": 120.0}
        },
        "_HyperSpy": {"Folding": {"unfolded": False, "signal_unfolded": False}},
    },
    "original_metadata": {
        "Acquisition_parameters": {
            "camera_length": {"value": 120, "unit": "mm"},
            "Dwelltime": {"value": 10, "unit": "ms"},
        },
        "made_up_section": {"made_up_key": "made-up value"},
        "placeholder": "_None_",
    },
    "learning_results": {},
    "attributes": {"_lazy": False},
    "models": {},
    "package_info": {"package": "pyxem", "package_version": "0.0.0"},
}

target = Path(sys.argv[1])
file_writer(
    str(target / "scan.zspy"), signal, consolidate=False, show_progressbar=False
)
print("written", target / "scan.zspy")
