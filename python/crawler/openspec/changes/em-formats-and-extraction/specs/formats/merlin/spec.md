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
