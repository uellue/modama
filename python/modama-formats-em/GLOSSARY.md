# Electron microscopy formats

The words for what the EM formats' extractors read from a file and write into a record's description. Terms follow the EM Glossary (v3.0.0, https://purls.helmholtz-metadaten.de/emg) where it has one; terms it lacks are marked _not in EMG_. Being worked out (2026-11-11); proposals until @weber confirms them.

## Language

**Exposure time** _(proposed; not in EMG)_:
The time period during which a detector integrates the signal of one frame; the acquisition time (EMG_00000055) of one frame. In a 4D-STEM scan with one frame per probe position it equals the dwell time.
_Avoid_: exposure (alone; read as dose), frame time (EMG_00000034: the time to scan a whole frame), integration time

**Dwell time** (EMG_00000015):
The time period during which the beam remains at one position.

**Frame** (EMG_00000060):
One array of data recorded by a detector over one exposure time.
_Avoid_: image (for a frame of a pixelated detector), pattern (unless it is a diffraction pattern, EMG_00000013)

**Electron dose** (EMG_00000073):
The number of electrons passing through a defined area of the specimen. Not the exposure time: the formats' headers give the time, not the dose.
_Avoid_: exposure, counts
