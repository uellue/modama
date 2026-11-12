# Spec Delta

## MODIFIED Requirements

### Requirement: Routine datasets are counted, not commented
A single file that no format produced SHALL get no comment in the verbose document, unless a format said it is not of the type its name gave it: then it SHALL get a recognition comment with its type and basis. The closing comment SHALL count all single files, so that a large tree is not drowned in routine lines.

#### Scenario: Large series directory
- **WHEN** `records --verbose PATH | less` is run on a directory of hundreds of image files of one type
- **THEN** no comment per file appears, and the closing comment counts them as single files by type

#### Scenario: Verbose document validates
- **WHEN** the output of `records --verbose PATH` is given to a schema validator
- **THEN** it validates against the OAI-PMH and `oai_dc` schemas

#### Scenario: A single file whose name type was dropped
- **WHEN** `records --verbose PATH` is run with the `em` collection enabled on a directory holding `notes.gtg` holding `hello\n` and no K2IS sector files
- **THEN** the comment `/notes.gtg: text/plain, basis: single file; em/k2is: not application/x.dm-gtg, no DM4 header` stands directly before its record, and the closing comment counts it among the single files
