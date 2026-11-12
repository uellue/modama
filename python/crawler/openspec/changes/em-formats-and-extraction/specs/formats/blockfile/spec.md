# Spec Delta

## Purpose

NanoMegas block files (`.blo`): one file holds a whole scan of diffraction patterns (4D-STEM, precession electron diffraction), recognised by its header and described by the acquisition values in it (staging 2026-11-12: `Stingray16bit_7_11.blo` was `application/octet-stream`, without a description; the survey counted 129 `.blo` files, 0.26 TB).

## ADDED Requirements

### Requirement: Block files are recognised by content
A file that starts with `IMGBLO` SHALL be a single-file dataset of the block file type, whatever its name; a file named `.blo` without it SHALL NOT get that type.

#### Scenario: A block file from an instrument
- **WHEN** a representative block file is crawled
- **THEN** it is one dataset of the block file type, of the format `em/blockfile`

#### Scenario: A text file named like a block file
- **WHEN** a text file is named `notes.blo`
- **THEN** it does not get the block file type: it is a single file of the type its content gives (`text/plain`), without a warning

### Requirement: Block file metadata is extracted from the header
For a block file dataset, the extractor SHALL read the header with RosettaSciIO's blockfile reader (`file_reader(..., lazy=True)`) and yield its fields as the reader gives them (decision 230): the summary shows the scan size and step, the diffraction pattern size, the beam energy and the camera length, the scan rotation where it is not 0, under the header's names and as found, then the acquisition date and time; the subjects say 4D-STEM.

#### Scenario: A representative block file
- **WHEN** a representative block file with a 3×2 scan, `SX` and `SY` 64.0, `DP_SZ` 5, `Beam_energy` 200000, `Camera_length` 2000 and `Scan_rotation` 2500, acquired on 2015-12-01 at 15:43 is crawled
- **THEN** its record's description starts with `NX 3, NY 2, SX 64.0, SY 64.0, DP_SZ 5, Beam_energy 200000, Camera_length 2000, Scan_rotation 2500, 2015-12-01 15:43`, with no unit added
- **AND** its values hold every field the reader gives first, flat under its dotted path (`blockfile_header.Beam_energy`), minus the skip list: values not suitable for text display (`modama_crawler.formats.values.textual`: binary data, text of more than 1,000 characters or with control characters, more than 16 items; for example a note of binary bytes); the header has no GUI settings or arrays to skip, and the mapped metadata (HyperSpy's names, RosettaSciIO's conversions) as a second, labelled section
- **AND** its subjects are the format's name and `4D-STEM`

#### Scenario: The acquisition time as written
- **WHEN** a block file is extracted in a process whose local time zone is not UTC
- **THEN** its date and time are those of the header's serial date, as for UTC: the file states no time zone, and the reader's conversion to the local one is not used

#### Scenario: The 16-bit variant
- **WHEN** a block file's header has MAGIC 259, as the 16-bit files LiberTEM reads (the header of `Stingray16bit_7_11.blo` on staging), which RosettaSciIO's reader does not know
- **THEN** it is described as any other, starting with `NX 7, NY 11, SX 12.5, SY 12.5, DP_SZ 576, Beam_energy 60000, Camera_length 6000, 2024-09-17 00:00`, and the reader's warning ("Blockfile has unrecognized header signature …") is in its description and values

#### Scenario: The header, not the data
- **WHEN** a block file holds its header and nothing after it, as a copy cut short
- **THEN** its description is the same as that of the whole file: the extractor never decodes the diffraction patterns
- **AND** of a block file of 16 MiB it reads the header plus one read buffer of the file RosettaSciIO opens (about 132 KiB here; about 1 MiB and 8 KiB on NFS, where `st_blksize` sets the buffer): patterns are read into the buffer, never decoded
