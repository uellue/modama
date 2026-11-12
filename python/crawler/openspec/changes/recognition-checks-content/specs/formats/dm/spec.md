# Spec Delta

## MODIFIED Requirements

### Requirement: Tag files and workspaces are not DM images
A file named `*.dmw` or `*.gtg` SHALL be typed by its name with a type of its own, a subclass of the DM4 type, and SHALL NOT be described or extracted as a DM image while it keeps that type. A `.dmw` file without the DM3 or the DM4 header, and a `.gtg` file without sector files and without the DM4 header (spec `formats/k2is`), SHALL get the type detection gives without its name's type (spec `recognition`); for a lone `.gtg` with the DM3 header that is the DM3 type (open question 183).

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
The format `em/dmw` SHALL claim each `.dmw` file with the DM3 or the DM4 header as a dataset of one file, whose extractor yields every tag, as `path value` in the reader's order (decision 173). Storage cuts it as every extraction: each phrase to 4,096 characters, the list to 1,000. A DM3 one SHALL carry "file of interest" in its basis (decision 174). Description and subject SHALL name the type "Gatan Digital Micrograph workspace" (open item 184).

#### Scenario: A representative .dmw file
- **WHEN** `conditions_00C.dmw`, the DM4 file of the fixture `cl_image_dm4` under a `.dmw` name, is crawled
- **THEN** its record's description starts with `ApplicationBounds (0, 0, 703, 1102), `, holds one phrase for each of the file's 298 tags, among them `ImageList.TagGroup1.ImageTags.DataBar.Device Name DigiScan`, and ends with `Gatan Digital Micrograph workspace, 1 file, 611.4 kB, in /`; its subjects are `Gatan Digital Micrograph workspace`; its basis is `Digital Micrograph header`

#### Scenario: A tag longer than storage keeps
- **WHEN** `conditions_00C.dmw` is crawled and its extraction stored
- **THEN** the stored description has 298 phrases, and the one of the tag `DocumentObjectList.TagGroup0.ImageDisplayInfo.CLUT` (6,053 characters) is cut to 4,096 characters

#### Scenario: A .dmw file that cannot be read
- **WHEN** a directory holds `conditions_00C.dmw` and `broken.dmw`, and reading `broken.dmw`'s header fails with a stale file handle
- **THEN** `conditions_00C.dmw` is a dataset of `em/dmw`, `broken.dmw` is a single file of the `.dmw` type with the basis `single file`, the crawl's only warning names `broken.dmw` and the error, and the directory is marked to be recognised again on the next crawl

#### Scenario: A .dmw file with the DM3 header
- **WHEN** `old_workspace.dmw`, the DM3 file of the fixture `stem_image_dm3` under a `.dmw` name, is crawled
- **THEN** it is a dataset of `em/dmw` of the `.dmw` type with the basis `Digital Micrograph header; file of interest: DM3, no .dmw in DM3 seen yet`, its description holds one phrase for each of its 236 tags, among them `ImageList.TagGroup1.ImageTags.Microscope Info.Name FEI Tecnai Remote`, and the crawl reports no warning for it
