# Spec Delta

## ADDED Requirements

### Requirement: Tag files and workspaces are not DM images
A file named `*.dmw` or `*.gtg` SHALL be typed by its name with a type of its own, a subclass of the DM4 type, and SHALL NOT be described or extracted as a DM image, even when its content has the DM4 header.

#### Scenario: A .dmw file with the DM4 header
- **WHEN** a file named `conditions_00C.dmw` starts with the DM4 header and holds no image
- **THEN** its type is the `.dmw` type, its record does not name it a Digital Micrograph image, and no extraction fails for it

#### Scenario: A lone .gtg file
- **WHEN** a file named `IDES_DMS_Config.gtg` starts with the DM4 header and no sector files share its stem
- **THEN** its type is the `.gtg` type and it is a dataset of one file
