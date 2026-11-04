# formats/empad Specification

## Purpose

EMPAD acquisitions, which consist of an XML header and the raw frame file it names, as one dataset anchored at the header. Known limits, from headers seen in the wild (2026-10-27): the raw file is looked up by base name beside the header (one 2017 header names it by absolute path); a header that does not start with `<root name=` within 64 bytes is not an EMPAD header; the raw file's size is not checked.

## Requirements

### Requirement: Header and raw file form one dataset
When an XML file is an EMPAD header and the raw file it names exists in the same directory, the EMPAD format SHALL produce one dataset of type `application/x.empad+xml` anchored at the XML with the raw file as its other member.

#### Scenario: Complete pair
- **WHEN** a directory contains an EMPAD header naming `scan_x4_y4.raw` and that file
- **THEN** the result has one EMPAD dataset with both files as members, anchored at the XML, and no single-file datasets for them

### Requirement: Headers are recognised by content
An EMPAD header SHALL be recognised by its content, not by its name, so that other XML files are not read by the EMPAD format.

#### Scenario: Header with an XML declaration
- **WHEN** a header has been re-saved with an XML declaration before `<root name=`, as hand-edited copies in the wild have
- **THEN** it is still recognised and paired with its raw file

#### Scenario: Unrelated XML
- **WHEN** a directory contains an XML file that is not an EMPAD header
- **THEN** it is a single-file dataset of type `application/xml` and the EMPAD format does not claim it

### Requirement: Incomplete pairs are reported
When an EMPAD header names a raw file that is absent, the header SHALL remain a single-file dataset and the result SHALL carry a warning naming the missing file.

#### Scenario: Raw file not yet copied
- **WHEN** a directory contains an EMPAD header whose raw file is missing
- **THEN** the header is a dataset of type `application/x.empad+xml` on its own and a warning names the raw file

### Requirement: Raw frame files alone keep their type
A raw frame file whose name follows the EMPAD convention but has no header SHALL be a single-file dataset of type `application/x.empad-raw`.

#### Scenario: Orphan raw file
- **WHEN** a directory contains `series_x1234.raw` and no header
- **THEN** the result has a single-file dataset of type `application/x.empad-raw`
