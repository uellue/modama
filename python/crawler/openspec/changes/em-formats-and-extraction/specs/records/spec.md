# Spec Delta

## ADDED Requirements

### Requirement: Every record carries a description
Every record SHALL carry one `dc:description`, a readable summary on one line. For a dataset with extracted metadata it SHALL start with the extracted values; otherwise it SHALL state the type's human-readable name, the number of files and their total size, and the folder the dataset is in.

#### Scenario: A file without an extractor
- **WHEN** a plain text file of 1,234 bytes in `notes/` is a dataset
- **THEN** its record's `dc:description` names the type as plain text, one file of 1.2 kB, in `notes/`

#### Scenario: A file with extracted metadata
- **WHEN** a dataset's extractor yields an acceleration voltage of 300 kV and a magnification of 50,000
- **THEN** its record's `dc:description` starts with those values, before the type, size and folder

### Requirement: Short terms go into subjects
A record with extracted metadata SHALL carry `dc:subject` elements for its short descriptive terms (the format's display name, the technique, the instrument where known), one term per element. The format's display name SHALL be the one the format declares, else its MIME type's comment, else its format id (@weber, 2026-11-11).

#### Scenario: Subjects of an extracted record
- **WHEN** a dataset's extractor yields the instrument name and the technique
- **THEN** the record has one `dc:subject` for each of them and one for the format's display name

#### Scenario: A DM file's format is named for people
- **WHEN** a DM3 file's metadata is extracted
- **THEN** its record's first `dc:subject` is `Gatan Digital Micrograph`, not the format id `dm3`
