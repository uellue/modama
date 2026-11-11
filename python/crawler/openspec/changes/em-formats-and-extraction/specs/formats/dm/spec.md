# Spec Delta

## Purpose

Gatan Digital Micrograph images (DM3 and DM4), the largest population of single-file electron microscopy data at ER-C, recognised by content and described by the acquisition values in their tags.

## ADDED Requirements

### Requirement: DM3 and DM4 files are recognised by content
A file whose header is that of a Digital Micrograph file of version 3 or 4 SHALL be a single-file dataset of the matching DM type, whatever its name; a file named `.dm3` or `.dm4` without that header SHALL NOT get the DM type.

#### Scenario: A DM4 file from an instrument
- **WHEN** a representative DM4 file is crawled
- **THEN** it is one dataset of the DM4 type

#### Scenario: A misnamed file
- **WHEN** a text file is named `image.dm4`
- **THEN** it does not get the DM4 type

### Requirement: DM metadata is extracted from the tags
For a DM3 or DM4 dataset, the extractor SHALL yield, where the file's tags hold them: the acceleration voltage, the magnification or camera length, the pixel size with its unit, the image dimensions, the detector or signal name, the instrument or microscope name, and the acquisition date and time.

#### Scenario: A representative DM4 image
- **WHEN** a representative DM4 file with known tags is crawled
- **THEN** its record's description and subjects carry the voltage, magnification, pixel size, dimensions and instrument that the file's tags hold
