# Spec Delta

## MODIFIED Requirements

### Requirement: Tag files and workspaces are not DM images
A file named `*.dmw` or `*.gtg` SHALL be typed by its name with a type of its own, a subclass of the DM4 type, and SHALL NOT be described or extracted as a DM image while it keeps that type. A `.dmw` file, and a `.gtg` file without sector files (spec `formats/k2is`), without the DM3 or the DM4 header SHALL get the type detection gives without its name's type (spec `recognition`). One with the DM3 header keeps its type and is a file of interest (decisions 174, 183).

#### Scenario: A .dmw file with the DM4 header
- **WHEN** a file named `exemplary_workspace.dmw`, a workspace as Gatan Microscopy Suite writes it, starts with the DM4 header
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
The format `em/dmw` SHALL claim each `.dmw` file with the DM3 or the DM4 header as a dataset of one file, whose extractor yields every tag, as `path value` in the reader's order (decision 173). Storage cuts it as every extraction: each phrase to 4,096 characters, the list to 1,000. A DM3 one SHALL carry "file of interest" in its basis (decision 174). Description and subject SHALL name the type "Gatan Digital Micrograph workspace" (184). The images it names are not grouped with it (189).

#### Scenario: A representative .dmw file
- **WHEN** `exemplary_workspace.dmw`, saved by Gatan Microscopy Suite with two images open, is crawled without the images beside it
- **THEN** its record's description is `File count 2, File name 0 .\exemplary_workspace\h1.dm4, File name 1 .\exemplary_workspace\100 deg C.dm4, Frame 0 None, Frame 1 None, Window 0 (217, 84, 646, 536), Window 1 (641, -17, 835, 207), Workspace name exemplary_workspace; Gatan Digital Micrograph workspace, 1 file, 846 B, in /`, as stored; its subjects are `Gatan Digital Micrograph workspace`; its basis is `Digital Micrograph header`

#### Scenario: A tag longer than storage keeps
- **WHEN** `old_workspace.dmw`, the DM3 file of the fixture `stem_image_dm3` under a `.dmw` name, is crawled and its extraction stored
- **THEN** the stored description has 236 phrases, and the one of the tag `DocumentObjectList.TagGroup0.ImageDisplayInfo.CLUT` (6,053 characters) is cut to 4,096 characters

#### Scenario: A .dmw file that cannot be read
- **WHEN** a directory holds `exemplary_workspace.dmw` and `broken.dmw`, and reading `broken.dmw`'s header fails with a stale file handle
- **THEN** `exemplary_workspace.dmw` is a dataset of `em/dmw`, `broken.dmw` is a single file of the `.dmw` type with the basis `single file`, the crawl's only warning names `broken.dmw` and the error, and the directory is marked to be recognised again on the next crawl

#### Scenario: A .dmw file with the DM3 header
- **WHEN** `old_workspace.dmw`, the DM3 file of the fixture `stem_image_dm3` under a `.dmw` name, is crawled
- **THEN** it is a dataset of `em/dmw` of the `.dmw` type with the basis `Digital Micrograph header; file of interest: DM3, no .dmw in DM3 seen yet`, its description holds one phrase for each of its 236 tags, among them `ImageList.TagGroup1.ImageTags.Microscope Info.Name FEI Tecnai Remote`, and the crawl reports no warning for it

### Requirement: A compressed workspace is described by its workspace and its members
A `*.dmwx` file SHALL be typed by its name as a compressed workspace, a subclass of the ZIP type. `em/dmwx` SHALL claim one whose first member is a `*.dmw` as a dataset of one file; any other SHALL get the type it has without its name's type (spec `recognition`). Its extractor SHALL yield the inner workspace's tags as `em/dmw` does, then each member's name and size, reading the central directory and the inner `.dmw` only, no image (decision 190).

#### Scenario: A representative compressed workspace
- **WHEN** `exemplary_workspace.dmwx` is crawled, a ZIP as Gatan Microscopy Suite writes it, holding `exemplary_workspace/exemplary_workspace.dmw`, the directory `exemplary_workspace/files/` and a DM4 image in it
- **THEN** it is a dataset of `em/dmwx` whose description starts with the inner workspace's tags (`File count 2, `) and names each member with its size, whose subject is `Gatan Digital Micrograph workspace (compressed)`, and the extractor reads less of the file than the image's compressed size

#### Scenario: A text file named like a compressed workspace
- **WHEN** a directory holds `notes.dmwx` holding `hello\n`
- **THEN** it is a single file of type `text/plain` with the basis `single file; em/dmwx: not application/x.dm-dmwx, no .dmw first in a ZIP`, and the crawl reports no warning for it

#### Scenario: A ZIP without a workspace first
- **WHEN** a directory holds `other.dmwx`, a ZIP whose first member is `readme.txt`
- **THEN** it is a single file of the ZIP type with the basis `single file; em/dmwx: not application/x.dm-dmwx, no .dmw first in a ZIP`
