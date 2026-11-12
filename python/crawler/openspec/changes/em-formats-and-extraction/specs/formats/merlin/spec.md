# Spec Delta

## Purpose

Merlin (Medipix/Timepix) acquisitions, which consist of one `.hdr` header and many `.mib` frame files, as one dataset per acquisition instead of one record per frame, described by the acquisition values in the header.

## ADDED Requirements

### Requirement: A Merlin header and its frames form one dataset
When a directory holds a Merlin `.hdr` header and `.mib` frame files of the same acquisition, the Merlin format SHALL produce one dataset anchored at the header with the frames as members, and no single-file datasets for them.

#### Scenario: A frame series with its header
- **WHEN** a directory holds `acq.hdr` and 200 frames `acq_1.mib` to `acq_200.mib`
- **THEN** the result has one Merlin dataset with 201 members, anchored at `acq.hdr`

#### Scenario: Frames without a header
- **WHEN** a directory holds `.mib` files and no `.hdr`
- **THEN** they are not claimed by the Merlin format, and the crawl reports a warning for the directory

### Requirement: Merlin metadata is extracted from the header
For a Merlin dataset, the extractor SHALL yield the number of frames, the frame size, the bit depth and the acquisition time where the header holds them.

#### Scenario: A representative acquisition
- **WHEN** a representative Merlin acquisition is crawled
- **THEN** its record's description carries the number of frames, the frame size and the bit depth from the header

#### Scenario: A header that is not UTF-8
- **WHEN** a Merlin header holds a byte that is not UTF-8, as the Merlin software writes "µ" as the single byte 0xB5 (staging 2026-11-12: `Sensor Bias (V, µA)`)
- **THEN** the header is read as Latin-1, so that every byte decodes and µ stays µ, and its record is described as any other

#### Scenario: The date key names its fields in another order
- **WHEN** a Merlin header's date key is `Time and Date Stamp (yr, mnth, day, hr, min, s)` with the value `22/02/2019 10:27:28` (staging 2026-11-12)
- **THEN** the key is found by its start `Time and Date Stamp`, the value is read as day/month/year as in `Time and Date Stamp (day, mnth, yr, hr, min, s)`, and the description ends with `2019-02-22 10:27`
- **AND** a value in another form fails the extraction with a message that names the value, so that it is retried and visible, rather than a guess at its form
