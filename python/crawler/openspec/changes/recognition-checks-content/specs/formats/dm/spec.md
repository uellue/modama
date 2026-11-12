# Spec Delta

## MODIFIED Requirements

### Requirement: Tag files and workspaces are not DM images
A file named `*.dmw` or `*.gtg` SHALL be typed by its name with a type of its own, a subclass of the DM4 type, and SHALL NOT be described or extracted as a DM image, even when its content has a DM header. One that its format finds without a DM header SHALL get the type detection gives without its name's type (spec `recognition`).

#### Scenario: A .dmw file with the DM4 header
- **WHEN** a file named `conditions_00C.dmw` starts with the DM4 header
- **THEN** its type is the `.dmw` type, it is a dataset of `em/dmw`, its record does not name it a Digital Micrograph image, and no extraction fails for it

#### Scenario: A lone .gtg file
- **WHEN** a file named `IDES_DMS_Config.gtg` starts with the DM4 header and no sector files share its stem
- **THEN** its type is the `.gtg` type and it is a dataset of one file

#### Scenario: A text file named like a workspace
- **WHEN** a directory holds `notes.dmw` holding `hello\n`
- **THEN** it is a single file of type `text/plain` with the basis `single file; em/dmw: not application/x.dm-dmw, no DM header`, its record describes it as a plain text document, and the crawl reports no warning for it

#### Scenario: An empty file named like a workspace
- **WHEN** a directory holds an empty `empty.dmw`
- **THEN** it is a single file of type `text/plain`, the type an empty file without a name rule gets, and the crawl reports no warning for it

## ADDED Requirements

### Requirement: A .dmw file is described by all its tags
The format `em/dmw` SHALL claim each file of the `.dmw` type that starts with the DM3 or the DM4 header as a dataset of one file. Its extractor SHALL yield every tag of the file, under its path of tag names and with the reader's value, in the reader's order, leaving nothing out (decision 173). A `.dmw` file with the DM3 header SHALL carry the note "file of interest" in its basis (decision 174).

#### Scenario: A representative .dmw file
- **WHEN** `conditions_00C.dmw`, the DM4 file of the fixture `cl_image_dm4` under a `.dmw` name, is crawled
- **THEN** its record's description starts with `ApplicationBounds (0, 0, 703, 1102), ` and holds one phrase for each of the file's 298 tags, among them `ImageList.TagGroup1.ImageTags.DataBar.Device Name DigiScan`; its subjects are `Gatan Digital Micrograph workspace`; its basis is `Digital Micrograph header`

#### Scenario: A .dmw file with the DM3 header
- **WHEN** `old_workspace.dmw`, the DM3 file of the fixture `stem_image_dm3` under a `.dmw` name, is crawled
- **THEN** it is a dataset of `em/dmw` of the `.dmw` type with the basis `Digital Micrograph header; file of interest: DM3, no .dmw in DM3 seen yet`, its description holds one phrase for each of its 236 tags, among them `ImageList.TagGroup1.ImageTags.Microscope Info.Name FEI Tecnai Remote`, and the crawl reports no warning for it
