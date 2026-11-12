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
For a Merlin dataset, the extractor SHALL keep as values, first (`original_metadata`, decision 230), every entry of the header as found (requirement "Every header entry is kept"); second (`mapped_metadata`), what it computes: the number of frames, the frame size (from the first frame file, through RosettaSciIO), the counter depth, the readout system and the acquisition time. The description SHALL start with the summary line: the values of the chosen entries `Frames in Acquisition (Number)`, `Counter Depth (number)`, `Readout System` and `Time and Date Stamp …` as the header writes them, a number after its key, a text as it is, and the frame size after its name in `mapped_metadata`, X and Y in the frame header's order (its reader, RosettaSciIO, names no axis); no word or unit of ours, no conversion (decision 230).

#### Scenario: A representative acquisition
- **WHEN** a representative Merlin acquisition is crawled (`single_frame`)
- **THEN** its record's description starts with `Frames in Acquisition (Number) 1, frame 256, 256, Counter Depth (number) 6, Merlin Quad, 15/04/2021 14:43:23; `
- **AND** its values carry the header's 27 entries in `original_metadata` and `frames` 1, `frame` [256, 256], `counter_depth` 6, `readout` `Merlin Quad` and `acquired` `2021-04-15T14:43:23` in `mapped_metadata`

### Requirement: Every header entry is kept
The extractor SHALL keep every `key<TAB>value` line of the header in `original_metadata`, the key without the colon that ends it, the value as text as the file writes it (spaces included), and SHALL NOT keep a list of wanted keys (@weber, 2026-11-12: "we don't keep a positive list, but a negative 'skip these' list"). The skip list: a value not suitable for text (`modama_crawler.formats.values.textual`: too long, or control characters). The `HDR,` line that starts the header and the `End` line that ends it (with its padding) are its frame, not entries; a blank line is skipped, and a line without a tab is a key with an empty value. A value that stands for no file is a value, as found, not a placeholder to skip: `Dead Time File` `Dummy (C:\<NUL>\)` stays, as `Flat Field File` `None` does. An empty value stays as empty text (decision 161).

#### Scenario: Values as the file writes them
- **WHEN** the header of `single_frame` is extracted
- **THEN** `original_metadata` has `Assembly Size (NX1, 2X2)` `   1x1` with its leading spaces, `Humidity (%)` `Board Humidity 14.690918 ` with its trailing space, `Dead Time File` `Dummy (C:\<NUL>\)` and `Flat Field File` `None`

#### Scenario: An entry nobody has seen before
- **WHEN** a header has the made-up lines `Made-up Setting (a, b):<TAB>made-up value` and `Made-up Empty:<TAB>`
- **THEN** `original_metadata` has `Made-up Setting (a, b)` `made-up value` and `Made-up Empty` as empty text, next to the header's other entries

#### Scenario: A value not suitable for text
- **WHEN** a header has the made-up line `Made-up Bytes:<TAB>` followed by the bytes 0x01 0x02 0x03
- **THEN** `original_metadata` has no `Made-up Bytes`, and the header's other entries

#### Scenario: A blank line and a line without a tab
- **WHEN** a header has a blank line and the made-up line `Made-up line without a tab`
- **THEN** the extraction does not fail; `original_metadata` has `Made-up line without a tab` with an empty value, and nothing for the blank line

#### Scenario: A header that is not UTF-8
- **WHEN** a Merlin header holds a byte that is not UTF-8, as the Merlin software writes "µ" as the single byte 0xB5 (staging 2026-11-12: `Sensor Bias (V, µA)`)
- **THEN** the header is read as Latin-1, so that every byte decodes and µ stays µ (`original_metadata` has `Sensor Bias (V, µA)`), and its record is described as any other

#### Scenario: The date key names its fields in another order
- **WHEN** a Merlin header's date key is `Time and Date Stamp (yr, mnth, day, hr, min, s)` with the value `22/02/2019 10:27:28` (staging 2026-11-12)
- **THEN** the key is found by its start `Time and Date Stamp`, the value is read as day/month/year as in `Time and Date Stamp (day, mnth, yr, hr, min, s)`: `acquired` in `mapped_metadata` is `2019-02-22T10:27:28`, and the summary line ends with the value as written, `22/02/2019 10:27:28`

#### Scenario: A date in another form
- **WHEN** a Merlin header's date value is in another form than dd/mm/yyyy hh:mm:ss, for example `22/02/2019 10:27:28 AM`
- **THEN** the extraction does not fail: `original_metadata` and the summary line carry the value as written, `mapped_metadata` has no `acquired`, rather than a guess at its form, and a warning names the value
