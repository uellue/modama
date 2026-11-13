# Spec Delta

## MODIFIED Requirements

### Requirement: Formats run in priority order with exclusive claims
Formats SHALL run in descending priority, ties broken by format id, and an entry or child dataset claimed by a dataset SHALL NOT be available to formats that run later: the entries of a type that a later format is offered SHALL leave out claimed entries, and a format whose reacted-to types are present only in claimed entries SHALL NOT be called. A later claim on an already claimed entry, which a format can still name, SHALL be reported as a warning.

#### Scenario: Higher priority wins a shared file
- **WHEN** a format claims `a.txt` with its sibling `a.txt.bak`, and a format of lower priority claims every text file it is offered
- **THEN** the dataset of the higher-priority format exists, the lower one is not offered `a.txt`, and no warning is reported

#### Scenario: A claimed entry named by a later format
- **WHEN** a format claims `a.txt`, and a format of lower priority claims `a.txt` by its name
- **THEN** the second claim is rejected, and a warning names both formats

#### Scenario: Every entry of a format's type is claimed
- **WHEN** every entry of the types a format reacts to is claimed by formats of higher priority
- **THEN** the format is not called
