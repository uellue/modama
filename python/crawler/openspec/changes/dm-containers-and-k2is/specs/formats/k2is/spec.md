# Spec Delta

## Purpose

K2IS (Gatan K2 IS camera) acquisitions, which consist of one `.gtg` tag file and 8 `.bin` sector files, as one dataset per acquisition instead of nine single-file records, described by values from the `.gtg` tags.

## ADDED Requirements

### Requirement: A K2IS tag file and its sector files form one dataset
When a directory holds a `.gtg` file and exactly 8 sector files whose names start with the `.gtg` file's stem and end in `.bin`, the K2IS format SHALL produce one dataset anchored at the `.gtg` file with the sector files as members, and no single-file datasets for them.

#### Scenario: A capture with its 8 sectors
- **WHEN** a directory holds `Capture52_.gtg` and `Capture52_1.bin` to `Capture52_8.bin`, each starting with a K2IS block header
- **THEN** the result has one K2IS dataset with 9 members, anchored at `Capture52_.gtg`

#### Scenario: Sector files without their tag file
- **WHEN** a directory holds K2IS sector files and no `.gtg` file with their stem
- **THEN** they are not claimed by the K2IS format, and the crawl reports a warning for the directory

#### Scenario: A tag file without sectors
- **WHEN** a directory holds a `.gtg` file and no sector files with its stem
- **THEN** the `.gtg` file is a dataset of its own with the `.gtg` type, without a warning

### Requirement: K2IS sector files are recognised by content
A file SHALL be typed as a K2IS sector file when it starts with a K2IS block header (big-endian `0xFFFF0055` at offset 0, width 256 at offset 20, height 1860 at offset 22), whatever its name; the name `*.bin` alone SHALL NOT type a file as a K2IS sector file.

#### Scenario: Another .bin file
- **WHEN** a file named `data.bin` does not start with a K2IS block header
- **THEN** it is not typed as a K2IS sector file

### Requirement: K2IS metadata is extracted from the tag file
For a K2IS dataset, the extractor SHALL yield, where the `.gtg` file's tags hold them, the scan shape tags and the microscope tags under the reader's names and with the reader's values; it SHALL NOT read the sector files. (The number of files and their size are in every record's basic description.)

#### Scenario: A representative capture
- **WHEN** a representative K2IS capture is crawled
- **THEN** its record's description carries the scan shape tags of its `.gtg` file, then the acquisition's type, 9 files and their size, and the extractor reads the `.gtg` file only
