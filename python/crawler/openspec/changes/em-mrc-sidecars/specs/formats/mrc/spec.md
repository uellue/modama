# Spec Delta

## ADDED Requirements

### Requirement: EPU's sidecars belong to their MRC file
A dataset of `em/mrc` whose file is `<stem>.<ext>` SHALL have as further members the files `<stem>.xml` and `<stem>.jpg` of its folder where they exist, as EPU writes them beside an image and a movie (`…_Fractions.mrc` with `…_Fractions.xml`); the MRC file stays the anchor, the sidecars are not read, a missing one is no warning, and one claimed by a format that ran earlier is named in the warning of decision 344. Recognition version 2.

#### Scenario: A micrograph and its movie from EPU
- **WHEN** the fixture `epu_data` (EMPIAR-12652: `FoilHole_4551075_Data_4541935_4541937_20220507_110208.mrc` with its `.xml` and `.jpg`, and `…_Fractions.mrc` with `…_Fractions.xml`) is crawled
- **THEN** it is two datasets of `em/mrc`: the micrograph with its `.xml` and `.jpg` as members, and the movie with its `_Fractions.xml`, each anchored at its MRC file, and each extracted from its MRC file as before

#### Scenario: A micrograph without its XML
- **WHEN** the micrograph's `.xml` is missing, as for one of 4830 micrographs in EMPIAR-12652
- **THEN** its dataset has the MRC file and its `.jpg` as members, without a warning

#### Scenario: A movie's XML without the movie
- **WHEN** `…_Fractions.xml` is there and `…_Fractions.mrc` is not, as for 3326 in EMPIAR-12652
- **THEN** the XML is not a member of an `em/mrc` dataset

#### Scenario: A sidecar claimed by another format
- **WHEN** a format that runs before em/mrc claims the micrograph's `.xml`
- **THEN** the micrograph's dataset has the MRC file and its `.jpg`, and the warning at the MRC file is `em/mrc: FoilHole_4551075_Data_4541935_4541937_20220507_110208.xml is claimed by probe/claim; two formats want it`
