# Spec Delta

## Purpose

Direct Electron acquisitions, written by DE-Server as several files that share a prefix `YYYYMMDD_NNNNN_` in one folder, as one dataset per acquisition, recognised from and described by its `_info.txt`.

## ADDED Requirements

### Requirement: A DE-Server info file and the files sharing its stem form one dataset
When a directory holds a file named `<8 digits>_<anything>_info.txt` that starts with the key `Server Software Version`, the DE format SHALL produce one dataset of type `application/x.de-acquisition`, anchored at that file, whose members are every regular file of the directory whose name starts with the info file's stem (its name without `info.txt`), whatever follows the stem. A file SHALL belong to the longest such stem it starts with.

#### Scenario: An acquisition of DE-Server 2.7.4
- **WHEN** a directory holds `20241021_00405_info.txt`, `20241021_00405_movie.mrc`, `20241021_00405_final.mrc`, `20241021_00405_ext1_Ext 1.mrc`, `20241021_00405_0_Virt 0_sum.mrc` and `20241021_00405_1_Virt 1_sum.mrc`
- **THEN** the result has one dataset of type `application/x.de-acquisition` with these 6 members, anchored at `20241021_00405_info.txt`, and none of them is a single-file dataset

#### Scenario: A numbered movie and a scan coordinate file
- **WHEN** a directory holds `20250429_06699_info.txt`, `20250429_06699_0_movie.mrc` and `20250429_06699_scan_coordinates.csv`
- **THEN** the result has one DE dataset with these 3 members

#### Scenario: A file nobody has seen with the stem
- **WHEN** a directory holds a DE acquisition `20241021_00405_info.txt` with `20241021_00405_movie.mrc` and `20241021_00405_processing.log` (as the tree's 2020 acquisition has one)
- **THEN** the log is a member of the acquisition's dataset

#### Scenario: A filename suffix set by the user
- **WHEN** a directory holds `20241021_00405_sampleA_info.txt`, `20241021_00405_sampleA_movie.mrc` and `20241021_00405_sampleA_final.mrc`
- **THEN** the result has one DE dataset with these 3 members

#### Scenario: Stems that nest
- **WHEN** a directory holds `20241021_00405_info.txt` with `20241021_00405_movie.mrc`, and `20241021_00405_x_info.txt` with `20241021_00405_x_movie.mrc`
- **THEN** the result has two DE datasets of 2 members each, the `_x_` movie in the `_x_` acquisition

#### Scenario: Many acquisitions in one folder
- **WHEN** a directory holds 16,000 acquisitions of an info file and a movie each
- **THEN** they are 16,000 DE datasets of 2 members each, recognised in a time that grows with the number of files, not its square (under 5 s on the development VM)

### Requirement: A file of the stem claimed by another format is flagged
A file with an acquisition's stem that a format of higher priority claimed SHALL NOT be a member of the acquisition; the crawl SHALL warn at the info file of the acquisition it would belong to, by the longest stem as for members, that two formats want it (spec `recognition`, "A file two formats want is flagged for review"), and the acquisition SHALL be built of its other files.

#### Scenario: The sum claimed by another format
- **WHEN** a format of higher priority claims `20241021_00405_final.mrc` of the acquisition `20241021_00405`
- **THEN** the DE dataset has the other 5 files as members, and the crawl warns at `20241021_00405_info.txt`: `em/de: 20241021_00405_final.mrc is claimed by <that format>; two formats want it`

#### Scenario: A claimed file of a longer stem
- **WHEN** a directory holds the nesting acquisitions `20241021_00405_` and `20241021_00405_x_`, and a format of higher priority claims `20241021_00405_x_movie.mrc`
- **THEN** the crawl warns at `20241021_00405_x_info.txt` only, and `20241021_00405_` keeps its 2 members

#### Scenario: An unread info file of a longer stem
- **WHEN** a directory holds the nesting acquisitions `20241021_00405_` and `20241021_00405_x_`, and `20241021_00405_x_info.txt` cannot be read (a read error, or refused over the read limit)
- **THEN** `20241021_00405_` keeps its 2 members, the files of `20241021_00405_x_` stay as they are without the DE format, and the DE format gives no "two formats want it" warning for that stem (test `test_an_unread_info_file_of_a_longer_stem`)

### Requirement: An info file of another program is not a DE info file
A file named like a DE info file that does not start with the key `Server Software Version` SHALL get the type it has without its name, with the reason in its basis, and SHALL NOT group any file. Files sharing a date prefix without a DE info file SHALL stay as they are, without a warning from the DE format.

#### Scenario: Another program's files with a date prefix
- **WHEN** a directory holds `20240619_1736_info.txt` holding `Sample: lamella 3` and `20240619_1736_HAADF.mrc`
- **THEN** `20240619_1736_info.txt` is a single-file dataset of type `text/plain` whose basis names the missing DE-Server first line, `20240619_1736_HAADF.mrc` is a dataset of its own, and the crawl reports no warning of the DE format

#### Scenario: A movie without its info file
- **WHEN** a directory holds `20241021_00405_movie.mrc` and no `_info.txt` with its stem
- **THEN** the movie is a single-file dataset of the type its MRC rules give, without a warning of the DE format

### Requirement: A lone DE info file is a dataset of its own
A DE info file without other files of its stem SHALL be a DE dataset of one member, described as any DE dataset.

#### Scenario: An info file of DE-Server 2.7.2 alone
- **WHEN** a directory holds `20230925_01497_info.txt` of DE-Server 2.7.2 (CRLF line ends) and nothing else
- **THEN** the result has one DE dataset with 1 member, and its description starts with `CeleritasXS, Integrating, Exposure Time (seconds) 0.3325952, Frames Per Second 40000, Raster, Scan - Size X 8, Scan - Size Y 32`

### Requirement: DE metadata is extracted from the info file only
For a DE dataset, the extractor SHALL keep as values (`original_metadata`) every `key = value` line of the info file, key and value as written without the padding around them, as text, in the file's order, empty values included, except the DE skip list (keys ending in ` Allowed Values`, the key `Preset - List`, keys ending in ` Preset List`) and values the shared checks find not suitable for text or a credential. It SHALL read no member but the info file.

#### Scenario: A representative acquisition's values
- **WHEN** the acquisition `20241021_00405` of DE-Server 2.7.4 is extracted
- **THEN** its values carry `Server Software Version` `2.7.4.10190 (Debug Build)`, `Exposure Rate (e-/pix/s)` `212.755735` and `Camera SN` with an empty value

#### Scenario: An entry nobody has seen
- **WHEN** the info file holds a line `Made Up Entry (units) = 42` that no DE-Server version is known to write
- **THEN** the values carry `Made Up Entry (units)` `42`

#### Scenario: Option lists are left out
- **WHEN** the info file holds `Instrument Accelerating Voltage (V) Allowed Values = 300000,200000,120000,80000,0`, `Preset - List = …` and `Scan - Preset List = …`
- **THEN** none of them is in the values, and `Instrument Accelerating Voltage (V)` and `Preset - Current` are

#### Scenario: The movie is not read
- **WHEN** an acquisition's movie member is 1 GiB
- **THEN** the extraction reads at most twice the info file's size plus 64 KiB

### Requirement: The summary line gives a few chosen entries as written
The description SHALL start with the summary line: `Camera Model` and `Image Processing - Mode` bare; `Instrument Accelerating Voltage (V)`, `Exposure Time (seconds)` and `Frames Per Second` after their keys; when `Scan - Enable` is `Enable`, `Scan - Type` bare and `Scan - Size X`, `Scan - Size Y` after their keys; then `Local time` bare; an entry missing or empty left out. The subjects SHALL carry `Camera Model`.

#### Scenario: A representative acquisition
- **WHEN** the acquisition `20241021_00405` of DE-Server 2.7.4 is crawled
- **THEN** its record's description starts with `DESim, Integrating, Instrument Accelerating Voltage (V) 300000, Exposure Time (seconds) 0.045712, Frames Per Second 700, Raster, Scan - Size X 8, Scan - Size Y 4, Mon Oct 21 14:36:50 2024`, and its subjects carry `DESim`

#### Scenario: An acquisition without a scan
- **WHEN** an info file of DE-Server 2.7.2 says `Scan - Enable = Disable`
- **THEN** its description starts with `CeleritasXS, Integrating, Exposure Time (seconds) 0.3325952, Frames Per Second 40000;`, without the scan's entries

### Requirement: RosettaSciIO's mapping is a second, labelled section
The extractor SHALL keep RosettaSciIO's mapping of the info file (its metadata and axes) as `mapped_metadata`, separate from `original_metadata`, and SHALL NOT hand it any other member. Where RosettaSciIO cannot map the info file, whatever its error, the dataset SHALL keep its `original_metadata` and summary line, without `mapped_metadata`, and the extraction worker SHALL log RosettaSciIO's error as a warning (in its log only; BACKLOG, "Merlin and EMPAD values").

#### Scenario: A mapping RosettaSciIO cannot make
- **WHEN** an info file has `Frames Per Second = 0` with the scan disabled, or `ADUs Per Electron Bin1x = 0`, or a STEM raster scan without `Scan - Repeat Delay (seconds)` (RosettaSciIO 0.15.0 raises a `ZeroDivisionError` or a `TypeError`)
- **THEN** its values have `original_metadata` and no `mapped_metadata`, its summary line is as for any info file, and a warning names RosettaSciIO's error

### Requirement: RosettaSciIO's own warnings go into the worker's log as text
RosettaSciIO's warnings while it maps the info file SHALL be logged by the extraction worker as plain text, with the dataset's anchor instead of the file's path, and SHALL NOT be written to the output by RosettaSciIO's own handler.

#### Scenario: A line RosettaSciIO cannot parse
- **WHEN** the info file holds a line `Note = a = b`
- **THEN** the values carry `Note` `a = b`, a warning `<anchor>: RosettaSciIO: Could not parse line: Note = a = b …` is logged without colour codes or the file's path, and RosettaSciIO writes nothing to the output

#### Scenario: A raster scan
- **WHEN** the acquisition `20241021_00405` is extracted
- **THEN** `mapped_metadata` carries RosettaSciIO's `Acquisition_instrument.TEM.detector` `DESim` and the axes' sizes

#### Scenario: A scan that is not a raster
- **WHEN** the acquisition `20250429_06699` (`Scan - Type = XY File`) is extracted
- **THEN** its values have `original_metadata` and no `mapped_metadata`, its description starts with `DESim, Integrating, Instrument Accelerating Voltage (V) 300000, Exposure Time (seconds) 30, Frames Per Second 1, XY File, Scan - Size X 5, Scan - Size Y 5`, a warning is logged, and the scan coordinate file is not read

### Requirement: The Dataset Name is checked against the file name
When the info file's `Dataset Name` does not start its file name, the extraction worker SHALL log a warning naming both; when the info file has no `Dataset Name` (or an empty one), a warning that the entry is missing. The values SHALL be kept.

#### Scenario: A renamed info file
- **WHEN** an info file holding `Dataset Name = 20241021_00405` is named `20241021_00406_info.txt`
- **THEN** a warning naming `20241021_00405` and `20241021_00406_info.txt` is logged, and the values are kept

#### Scenario: An info file without a Dataset Name
- **WHEN** an info file has no `Dataset Name` line
- **THEN** the warning `<anchor>: no Dataset Name entry` is logged, and the values are kept
