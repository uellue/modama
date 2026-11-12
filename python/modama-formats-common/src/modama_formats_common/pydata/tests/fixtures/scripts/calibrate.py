#!/usr/bin/env python3
"""Calibrate the camera length from a diffraction pattern of a gold standard.

Reads the pattern, fits the ring radii and writes the camera length.
"""

import json
import sys
from pathlib import Path

import numpy as np

from .rings import fit_rings

__version__ = "0.3.1"
__author__ = "Example Author"
__all__ = ["calibrate"]
CONSTANT = 0.0251


def calibrate(path):
    from scipy import ndimage

    pattern = np.load(path)
    radii = fit_rings(ndimage.gaussian_filter(pattern, 2))
    return CONSTANT * radii.mean()


if __name__ == "__main__":
    print(json.dumps({"camera_length": calibrate(Path(sys.argv[1]))}))
