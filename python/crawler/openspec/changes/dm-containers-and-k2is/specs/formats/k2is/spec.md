# Spec Delta

## Purpose

K2IS (Gatan K2 IS camera) acquisitions, which consist of one `.gtg` tag file and 8 `.bin` sector files, as one dataset per acquisition instead of nine single-file records, described by values from the `.gtg` tags.

## ADDED Requirements

### Requirement: A K2IS tag file and its sector files form one dataset
When a directory holds a `.gtg` file and exactly 8 sector files whose names start with the `.gtg` file's stem and end in `.bin`, the K2IS format SHALL produce one dataset anchored at the `.gtg` file with the sector files as members, and no single-file datasets for them. The extensions `.gtg` and `.bin` SHALL match in any case.

#### Scenario: A capture with its 8 sectors
- **WHEN** a directory holds `Capture52_.gtg` and `Capture52_1.bin` to `Capture52_8.bin`, each starting with a K2IS block header
- **THEN** the result has one K2IS dataset with 9 members, anchored at `Capture52_.gtg`

#### Scenario: Sector files without their tag file
- **WHEN** a directory holds K2IS sector files and no `.gtg` file with their stem
- **THEN** they are not claimed by the K2IS format, and the crawl reports a warning for the directory

#### Scenario: A tag file without sectors
- **WHEN** a directory holds a `.gtg` file and no sector files with its stem
- **THEN** the `.gtg` file is a dataset of its own with the `.gtg` type, without a warning

#### Scenario: Extensions in upper case
- **WHEN** a directory holds `UPPER_.GTG` with `UPPER_1.BIN` to `UPPER_8.BIN`, and `mixed_.gtg` with `mixed_1.BIN` to `mixed_8.BIN`
- **THEN** the result has two K2IS datasets of 9 members each, without a warning

### Requirement: An incomplete capture is reported at its tag file
A sector file SHALL belong to the longest stem of a `.gtg` file that its name starts with, whether that `.gtg` file has 8 sector files or not. A `.gtg` file with sector files, but not 8, SHALL get a warning that names it and the number of its sector files, and its files SHALL stay single files.

#### Scenario: A tag file with 7 or 9 sector files
- **WHEN** a directory holds `Capture7_.gtg` with 7 sector files `Capture7_*.bin`, and `Capture9_.gtg` with 9 sector files `Capture9_*.bin`
- **THEN** all of them stay single files, and the crawl reports one warning for each `.gtg` file, naming its number of sector files and the 8 of an acquisition; no warning says that a `.gtg` file is missing

#### Scenario: An incomplete capture next to a complete one
- **WHEN** a directory holds `scan_.gtg` with `scan_1.bin` to `scan_8.bin`, and `scan_2_.gtg` with `scan_2_1.bin` to `scan_2_7.bin`
- **THEN** `scan_.gtg` with its 8 sector files is one K2IS dataset, and `scan_2_.gtg` and its 7 sector files stay single files with a warning for `scan_2_.gtg`

### Requirement: K2IS sector files are recognised by content
A file SHALL be typed as a K2IS sector file when it starts with a K2IS block header (big-endian `0xFFFF0055` at offset 0, width 256 at offset 20, height 1860 at offset 22), whatever its name; the name `*.bin` alone SHALL NOT type a file as a K2IS sector file.

#### Scenario: Another .bin file
- **WHEN** a file named `data.bin` does not start with a K2IS block header
- **THEN** it is not typed as a K2IS sector file

### Requirement: K2IS metadata is extracted from the tag file
For a K2IS dataset, the extractor SHALL keep as values (`original_metadata`) every tag of the `.gtg` file but the user-interface settings (`formats/dm`), with the reader's value, and SHALL NOT read the sector files. The description SHALL start with the summary line of `formats/dm` from the `.gtg` file's root tags; the subjects SHALL carry `Microscope Info.Name` at the root, the imaging mode and the camera model.

#### Scenario: A representative capture
- **WHEN** a representative K2IS capture is crawled
- **THEN** its record's description is `IMAGING, SCANNING, STEM NANOPROBE, 300kV, 320kx, STEM Camera Length 275.0, K2-IS, Exposure Time (s) 0.0025, Search, Size X 35, Size Y 34, 3/29/2018, 1:28:03 PM; K2IS acquisition, 9 files, 27.3 kB, in /`, its values carry the tags of its `.gtg` file with their values as the reader gives them (`DataBar.Device Name` `K2-IS-0001`, `Microscope Info.Stage Position.Stage Alpha` `-2.4043772802208405`), and the extractor reads the `.gtg` file only

#### Scenario: User-interface settings are left out
- **WHEN** the `.gtg` file holds the image viewer's settings (a tag group of class `cm_stdviewerimagedisplayer`: window and screen position, zoom) and the definition of GMS's Session Info form (`Session Info.Items`)
- **THEN** neither is in the values, and the acquisition's processing objects next to the viewer are
