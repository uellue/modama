# Spec Delta

## ADDED Requirements

### Requirement: EMPAD metadata is extracted from the header
For an EMPAD dataset, the extractor SHALL yield the scan size, the frame size and the exposure time where the header holds them.

#### Scenario: A representative EMPAD acquisition
- **WHEN** a representative EMPAD header with its raw file is crawled
- **THEN** its record's description carries the scan size, frame size and exposure time from the header
