# Spec Delta

## Purpose

NanoMegas ASTAR block files (`.blo`): one file holds a whole scan of diffraction patterns (4D-STEM, precession electron diffraction), recognised by its header and described by the acquisition values in it (staging 2026-11-12: `Stingray16bit_7_11.blo` was `application/octet-stream`, without a description; the survey counted 129 `.blo` files, 0.26 TB).

## ADDED Requirements

### Requirement: Block files are recognised by content
A file that starts with `IMGBLO` SHALL be a single-file dataset of the block file type, whatever its name; a file named `.blo` without it SHALL NOT get that type.

#### Scenario: A block file from ASTAR
- **WHEN** a representative block file is crawled
- **THEN** it is one dataset of the block file type, of the format `em/blockfile`

#### Scenario: A text file named like a block file
- **WHEN** a text file is named `notes.blo`
- **THEN** it does not get the block file type: it is a single file of the type its content gives (`text/plain`), without a warning

### Requirement: Block file metadata is extracted from the header
For a block file dataset, the extractor SHALL yield, from the header as RosettaSciIO's blockfile reader gives it (`file_reader(..., lazy=True)`): the scan size and step with their unit, the diffraction pattern size, the beam energy, the camera length, the scan rotation where it is not 0, and the acquisition date and time; the subjects SHALL say 4D-STEM.

#### Scenario: A representative block file
- **WHEN** a representative block file with a 3×2 scan of 64 nm steps and 5×5 pixel diffraction patterns, 200 kV, a camera length of 2000 (10 × mm) and a scan rotation of 2500 (100 × degrees), acquired on 2015-12-01 at 15:43 is crawled
- **THEN** its record's description starts with `scan of 3×2 positions, step 64.0×64.0 nm, 5×5 pixel diffraction patterns, beam energy 200.0 kV, camera length 0.2 m, scan rotation 25.0°, 2015-12-01 15:43`
- **AND** the beam energy, camera length and rotation are the values of RosettaSciIO's mapping, with the units the header's fields have after its conversion (V × 10⁻³: kV; 10 × mm × 10⁻⁴: m; 100 × degrees × 10⁻²: degrees)
- **AND** its subjects are the format's name and `4D-STEM`

#### Scenario: The header, not the data
- **WHEN** a block file holds its header and nothing after it, as a copy cut short
- **THEN** its description is the same as that of the whole file: the extractor never loads the diffraction patterns
- **AND** of a block file of 16 MiB it reads less than 1 MiB: the header, with the read buffer of the file RosettaSciIO opens (128 KiB, Python's default; 1 MiB on NFS, where `st_blksize` sets it)
