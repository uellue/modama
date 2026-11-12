# Spec Delta

## MODIFIED Requirements

### Requirement: A K2IS tag file and its sector files form one dataset
When a directory holds a `.gtg` file and exactly 8 sector files whose names start with the `.gtg` file's stem and end in `.bin`, the K2IS format SHALL produce one dataset anchored at the `.gtg` file with the sector files as members, and no single-file datasets for them, whatever the `.gtg` file holds (decision 172: a broken tag file with its sectors is a broken capture). The extensions `.gtg` and `.bin` SHALL match in any case.

#### Scenario: A capture with its 8 sectors
- **WHEN** a directory holds `Capture52_.gtg` and `Capture52_1.bin` to `Capture52_8.bin`, each starting with a K2IS block header
- **THEN** the result has one K2IS dataset with 9 members, anchored at `Capture52_.gtg`

#### Scenario: Sector files without their tag file
- **WHEN** a directory holds K2IS sector files and no `.gtg` file with their stem
- **THEN** they are not claimed by the K2IS format, and the crawl reports a warning for the directory

#### Scenario: A tag file without sectors
- **WHEN** a directory holds a `.gtg` file that starts with the DM4 header and no sector files with its stem
- **THEN** the `.gtg` file is a dataset of its own with the `.gtg` type, without a warning

#### Scenario: Extensions in upper case
- **WHEN** a directory holds `UPPER_.GTG` with `UPPER_1.BIN` to `UPPER_8.BIN`, and `mixed_.gtg` with `mixed_1.BIN` to `mixed_8.BIN`
- **THEN** the result has two K2IS datasets of 9 members each, without a warning

#### Scenario: An empty tag file with its 8 sectors
- **WHEN** a directory holds an empty `Capture7_.gtg`, as an interrupted copy leaves it, and `Capture7_1.bin` to `Capture7_8.bin`, each starting with a K2IS block header
- **THEN** the result has one K2IS dataset with 9 members anchored at `Capture7_.gtg`, and the crawl's warnings name `Capture7_.gtg` and the K2IS extraction failure

#### Scenario: A broken capture next to a complete one
- **WHEN** a directory holds `scan_.gtg`, Capture52's tag file, with `scan_1.bin` to `scan_8.bin`, and `scan_2_.gtg` holding `hello\n` with `scan_2_1.bin` to `scan_2_8.bin`
- **THEN** the result has two K2IS datasets of 9 members each, anchored at `scan_.gtg` and `scan_2_.gtg`; the extraction of `scan_.gtg` succeeds; the crawl's only warning names `scan_2_.gtg` and its extraction failure

## ADDED Requirements

### Requirement: A lone tag file needs the DM4 header
The K2IS format SHALL check the DM4 header of a `.gtg` file that has no sector files of its stem. One without it SHALL get the type detection gives without the `.gtg` type (spec `recognition`); a `.gtg` file with sector files of its stem SHALL NOT be checked.

#### Scenario: A text file named like a tag file
- **WHEN** a directory holds `notes.gtg` holding `hello\n` and no sector files
- **THEN** it is a single file of type `text/plain` with the basis `single file; em/k2is: not application/x.dm-gtg, no DM4 header`, its record describes it as a plain text document, and the crawl reports no warning for it

#### Scenario: An empty file named like a tag file
- **WHEN** a directory holds an empty `empty.gtg` and no sector files
- **THEN** it is a single file of type `text/plain`, and the crawl reports no warning for it
