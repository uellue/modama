## ADDED Requirements

### Requirement: External links are listed as written
The HDF5 walk SHALL list each external link of a walked group as `<dotted link name>.external_link` with the value `[<target file name>, <target path>]` as written: never resolved, normalised or shortened, and never followed. Each link SHALL count as an object of the walk.

#### Scenario: A run of external links
- **WHEN** the fixture `linked_scan` is crawled: a folder holding `scan_master.h5` (written with `libver="latest"`, so that its link group is stored densely, as the real master's is; an NXentry `entry`; an NXdata `entry/data` with 12 external links `data_000001` … `data_000012` to `/entry/data/data` in `scan_data_000001.h5` … `scan_data_000012.h5`; an NXdetector `entry/instrument/detector` with a scalar `description` `Test detector 4M` and datasets `detectorSpecific/flatfield` `[8, 6] <f4` and `detectorSpecific/pixel_mask` `[8, 6] <u4`; no title) and `scan_data_000001.h5` to `scan_data_000003.h5`, each with `/entry/data/data` `[2, 8, 6] <u4`, chunked, the bitshuffle filter (32008) in its pipeline, and attributes `image_nr_low`, `image_nr_high`
- **THEN** the master's `original_metadata` has `entry.data.data_000001 … data_000012.external_link` `["scan_data_000001.h5 … scan_data_000012.h5", "/entry/data/data"]`, and no other entry for these links

#### Scenario: Links outside a run
- **WHEN** an HDF5 file has external links `a` to `one.h5:/x`, `b` to `two.h5:/x`, `c3` to `c3.h5:/y`, `c4` to `c4.h5:/z`, and `d9`, `d10` to `/x` in `d9.h5` and `d10.h5`
- **THEN** each of the six links is an entry of its own, `a.external_link ["one.h5", "/x"]` and so on

#### Scenario: A link is never followed
- **WHEN** an HDF5 file in a folder has an external link to `../elsewhere/secret.h5`, an external link to the absolute path of the same file, whose scalar `/value` holds 42, and a virtual dataset mapped onto it
- **THEN** the links and the source are listed as written, 42 is nowhere in the values, and `secret.h5` is not opened

### Requirement: Virtual-dataset sources are listed as written
The HDF5 walk SHALL list a virtual dataset's mappings onto other files as `<dotted dataset name>.virtual_sources`, a list of `[<source file name>, <source dataset path>]` in mapping order, as written, from the dataset's creation property list; a mapping onto the same file (`.`) SHALL be left out, and no source file SHALL be opened.

#### Scenario: A virtual dataset's sources
- **WHEN** an HDF5 file has a virtual dataset `entry/data/data` mapped onto `/entry/data/data` of `part_001.h5` to `part_004.h5` and onto a dataset `/mask` of its own file
- **THEN** `original_metadata` has `entry.data.data.virtual_sources [["part_001.h5 … part_004.h5", "/entry/data/data"]]`, and no source file is opened through the virtual dataset

### Requirement: A run of links is one entry
Within a group, external links sorted by their names' bytes whose target paths are equal, and whose link names and target file names each differ from the previous one's only in one run of decimal digits at the same place and of the same width, one more, SHALL be one entry `<dotted first name> … <last name>.external_link` with the value `[<first file> … <last file>, <target path>]`. A virtual dataset's consecutive mappings SHALL be collapsed alike.

#### Scenario: Runs whatever the stored order
- **WHEN** the master of `linked_scan`, whose dense link group stores its links in the order of their names' hashes, is extracted
- **THEN** its 12 links are one entry, from `data_000001` to `data_000012`

### Requirement: Links are counted
The extractor of an HDF5 file with links to other files SHALL give in `mapped_metadata` the number of external links (`external_links`) and of mappings onto other files (`virtual_sources`), and by distinct target file other than itself: `found`, a regular file of that name in the file's folder; `dangling`, none; `elsewhere`, named with a relative folder part or a `%` pattern, never looked up. An absolute target counts by its last component. Names SHALL be looked up with `lstat` only.

#### Scenario: A master whose data files are all missing
- **WHEN** `scan_master.h5` of `linked_scan` is crawled alone in a folder
- **THEN** it is a dataset of `common/hdf5` with `external_links 12` and `dangling 12`

#### Scenario: Targets in other folders
- **WHEN** an HDF5 file links `../raw/a.h5`, `sub/c.h5` and `/acquisition/pc/b.h5`, and the files `c.h5` and `b.h5` are in its folder
- **THEN** `elsewhere` is 2 and `found` 1, and `c.h5` is a dataset of its own

### Requirement: Dangling links are no error
A link whose target is not in the folder SHALL NOT be a warning or an error: it is counted (requirement "Links are counted"), as for a stopped acquisition.

#### Scenario: A stopped acquisition
- **WHEN** `linked_scan` is crawled
- **THEN** the master's dataset has `external_links 12`, `found 3` and `dangling 9` in `mapped_metadata`, and neither the dataset nor the crawl has a warning about the links

### Requirement: HDF5 files linked by a file of their folder are one dataset
A file of type `application/vnd.hdfgroup.hdf5` whose links name other HDF5 files of its folder that h5py opens (its targets), which no other file names but a target whose only target it is, and which is not one of two files each the other's only target, SHALL anchor one dataset of the format `common/hdf5links` with its targets as members, whatever its name.

#### Scenario: An acquisition with its master
- **WHEN** `linked_scan` is crawled
- **THEN** there is one dataset of `common/hdf5links`, of type `application/vnd.hdfgroup.hdf5`, anchored at `scan_master.h5`, with the members `scan_data_000001.h5` to `scan_data_000003.h5`, the basis `external links to 3 HDF5 files of this folder`, and no other dataset in the folder

#### Scenario: Not by name
- **WHEN** the master of `linked_scan` is named `run7.h5`, and the folder also holds an HDF5 file `run7_master.h5` without links
- **THEN** `run7.h5` anchors the dataset with the three data files, and `run7_master.h5` is a dataset of `common/hdf5` of its own

#### Scenario: A NeXus file is no anchor
- **WHEN** the master of `linked_scan` is named `scan.nxs`
- **THEN** it is a dataset of `common/nexus` and each data file a dataset of its own

#### Scenario: A virtual dataset over files of the folder
- **WHEN** a folder holds `vds.h5`, whose virtual dataset is mapped onto `part_001.h5` to `part_004.h5`, and those four files
- **THEN** `vds.h5` anchors one dataset with the four as members

#### Scenario: A self-link
- **WHEN** a folder holds `m.h5` with an external link to `m.h5` and one to `d1.h5`, and `d1.h5`
- **THEN** `m.h5` anchors a dataset with `d1.h5`, and its `found` counts `d1.h5` only

#### Scenario: A link back to the master
- **WHEN** `scan_data_000001.h5` of `linked_scan` also has an external link to `scan_master.h5`
- **THEN** `scan_master.h5` still anchors the dataset with the three data files

#### Scenario: Two files that name each other
- **WHEN** a folder holds `a.h5` linking `b.h5` and `b.h5` linking `a.h5`, and nothing else
- **THEN** each is a dataset of `common/hdf5` of its own, and each one's basis names the other

#### Scenario: A target that is not HDF5
- **WHEN** a folder holds `m.h5` linking `d1.h5` and `d2.h5`, `d1.h5` an HDF5 file and `d2.h5` a text file
- **THEN** `m.h5` anchors a dataset with `d1.h5` only, `d2.h5` is a dataset of its own type, and `m.h5` has `found 2`

#### Scenario: A file with an HDF5 name that HDF5 cannot open
- **WHEN** a folder holds `m.h5` linking `d1.h5`, `d1.h5`, and `broken.h5`, which has the HDF5 signature and is cut after 100 bytes
- **THEN** `m.h5` anchors a dataset with `d1.h5`, and `broken.h5` is a dataset of `common/hdf5` of its own

### Requirement: A file that two anchors name stays its own dataset
A file named by two anchors SHALL be a member of neither, and each anchor's basis SHALL name it and the other anchor. A member's own targets SHALL NOT be added to the dataset.

#### Scenario: A file two masters link
- **WHEN** a folder holds `a.h5` linking `shared.h5` and `only_a.h5`, and `b.h5` linking `shared.h5`
- **THEN** `a.h5` anchors a dataset with `only_a.h5`, whose basis says `shared.h5` is also linked by `b.h5`; `b.h5` and `shared.h5` are datasets of their own, the basis of `b.h5` says `shared.h5` is also linked by `a.h5`, and both count `shared.h5` as `found`

### Requirement: A target name is never opened
Recognition and extraction SHALL compare a target name with the names of the folder's entries only, SHALL NOT open a path built from it, and SHALL NOT open anything through a link; every HDF5 file SHALL be opened through a file object of a descriptor opened without following a symlink.

#### Scenario: A target name that climbs out
- **WHEN** a folder holds `m.h5` linking `../../outside/x.h5` and `x.h5`, and a file `x.h5` exists in the folder and in `../../outside/`
- **THEN** `m.h5` anchors a dataset with the folder's `x.h5`, `elsewhere` is 1, and `../../outside/x.h5` is not opened

### Requirement: Recognition of links is bounded
`common/hdf5links` SHALL list links in worker processes (the core's inspection) only in a folder with two to 200 HDF5 files, within a byte budget of 32 MiB per folder, at most 5,000 objects and links per file, and a deadline of 45 s per file checked between objects, inside the core's outside limit of 60 s; a limit that cuts SHALL be named in a warning.

#### Scenario: One HDF5 file alone is not opened
- **WHEN** a folder holds one HDF5 file and a text file
- **THEN** recognition reads nothing of the HDF5 file

#### Scenario: Too many HDF5 files in a folder
- **WHEN** a folder holds 201 HDF5 files, one of which links two others
- **THEN** none is opened by recognition, each is a dataset of its own, and the folder has a warning saying 201 HDF5 files are over the limit of 200

#### Scenario: A file of many objects
- **WHEN** a file has at its root an external link `c` to `c.h5` of its folder and a group `deep` holding 6,000 empty groups and one group with an external link to `d.h5` of its folder
- **THEN** it anchors a dataset with `c.h5`, `d.h5` is a dataset of its own, and the dataset has a warning saying its links were listed up to 5,000 objects

#### Scenario: A listing past its deadline
- **WHEN** the listing of a file reaches its deadline after its link to `c.h5` and before its link to `d.h5`
- **THEN** it anchors a dataset with `c.h5`, and the dataset has a warning saying its links were listed up to the time limit

#### Scenario: Recognition in a process of its own ends cleanly
- **WHEN** `linked_scan` is recognised by `modama-crawler records` in a subprocess
- **THEN** the subprocess exits with status 0

### Requirement: The linked data is described from the members
The extractor of `common/hdf5links` SHALL give, for each entry of external links, the `shape` and `dtype` of the object at the target path in the first target that is a member, opened by its own path and reached one component at a time by hard links only, under the first link's dotted name. No array SHALL be read.

#### Scenario: The linked data's structure
- **WHEN** `linked_scan` is crawled and the master's dataset extracted, without the bitshuffle filter installed
- **THEN** `original_metadata` has `entry.data.data_000001.shape [2, 8, 6]` and `entry.data.data_000001.dtype <u4`, and no chunk of a data file is read

#### Scenario: A target path that leaves the member
- **WHEN** the target path `/entry/data/data` of the first data file is a soft link to `/raw`, or an external link to a file outside the folder
- **THEN** `original_metadata` has no `entry.data.data_000001.shape`, and nothing is opened through the link

## MODIFIED Requirements

### Requirement: The walk of an HDF5 file is bounded
The extractor SHALL open the file through a file object of a descriptor opened without following a symlink, without file locking and with readahead off; read a value only of at most 16 elements of at most 4,000 bytes each (4 bytes a character `textual` keeps), not of an array type; never follow an external or a soft link, nor enter an object on the skip list; and stop at 1,000 entries, 5,000 objects (links included) or a third of the extractor's time limit (20 s), `mapped_metadata.walk` saying which limit cut it.

#### Scenario: Arrays are never read
- **WHEN** an HDF5 file of 32 MB holding one array dataset with attributes is extracted
- **THEN** its shape, dtype and attributes are given, and fewer than 256 KiB are read

#### Scenario: The walk stops at 1,000 entries
- **WHEN** an HDF5 file has 1,500 groups with one attribute each, and another has one group with 1,500 attributes
- **THEN** each gives 1,000 entries in `original_metadata`, and `mapped_metadata.walk` says that the entry limit of 1,000 cut it

#### Scenario: The walk stops at 5,000 objects
- **WHEN** an HDF5 file has 6,000 groups without attributes
- **THEN** `original_metadata` is empty, and `mapped_metadata.walk` says that the object limit of 5,000 cut it

#### Scenario: A group on the skip list is not entered
- **WHEN** a MATLAB 7.3 file has 6,000 groups under `#refs#` and a variable `x`
- **THEN** `x` is described and the walk is not cut

#### Scenario: The walk stops after its time
- **WHEN** the walk's time is up before the walk ends
- **THEN** the entries found so far are given, and `mapped_metadata.walk` says that the time limit cut it

#### Scenario: External links are not followed
- **WHEN** an HDF5 file links `/counts` in `other.h5` of another folder, which has an attribute `other_file`
- **THEN** `original_metadata` has the link as written, `linked.external_link ["../other/other.h5", "/counts"]`, nothing of `other.h5` (no `other_file`, no shape of `counts`), and `other.h5` is not opened

### Requirement: An HDF5 file without a title is summarised by its structure
An HDF5, NeXus or HyperSpy file without a title (`*.title`, `Experiments.*.metadata.General.title`; empty counts as none) SHALL have its structure as the summary line (decision 316): the detector's description (`*.instrument.detector.description`) as found, if any; the three datasets of one dimension or more with the most elements, ties by dotted name, each `<dotted name> <shape> <dtype>` (decision 326: a compound as NumPy's descr list); then `*.start_time`, `*.definition` (decision 324) and the root's `file_time`, as found, if any. A file with a title SHALL keep its line. Either line SHALL end with the link counts but `found` (331), each `<name> <value>`, 0 left out.

#### Scenario: A NeXus file without a title
- **WHEN** a NeXus file `scan.nxs` as a beamline writes it (an NXentry `entry` with an NXdata `data` of 1-D arrays `value1` to `value4` `<i4` and `exposuretime` `<f4` of 10 elements each and scalars `vfcconversion1` to `vfcconversion5`; root attributes `NX_class`, `file_name`, `file_time 2026-01-02T03:04:05`, `file_update_time`) has no `title`
- **THEN** the summary is `entry.data.exposuretime [10] <f4, entry.data.value1 [10] <i4, entry.data.value2 [10] <i4, 2026-01-02T03:04:05`

#### Scenario: A NeXus file without a title with a definition and start time
- **WHEN** the NeXus file of "A NeXus file without a title" has `entry.definition` `NXmonopd` and `entry.start_time` `2026-01-02T02:59:00`
- **THEN** the summary is `entry.data.exposuretime [10] <f4, entry.data.value1 [10] <i4, entry.data.value2 [10] <i4, 2026-01-02T02:59:00, NXmonopd, 2026-01-02T03:04:05`

#### Scenario: An HDF5 file without a title
- **WHEN** an HDF5 file has datasets `e` `[4, 4] <u2`, `d` `[100] <f8`, `b` `[4, 4] <u2`, `a` `[2] <i4` and a scalar `scalar`, and no title
- **THEN** the summary is `d [100] <f8, b [4, 4] <u2, e [4, 4] <u2`

#### Scenario: A compound array without a title
- **WHEN** an HDF5 file without a title has one dataset `events` of 5 elements of the compound dtype `x <f4, y <i2`
- **THEN** the summary is `events [5] [['x', '<f4'], ['y', '<i2']]`

#### Scenario: A HyperSpy file without a title
- **WHEN** RosettaSciIO's `with_lists_etc.hdf5`, whose signal's title is empty, is extracted as `untitled.hspy`
- **THEN** the summary is `Experiments.__unnamed__.data [10] <i8`, then the variance signal's `data` `[10] <i8`, by their dotted names; none of HyperSpy's encoded lists, the only other arrays

#### Scenario: A file with a title keeps its line
- **WHEN** the NeXus file of "A NeXus file without a title" has `entry.title` `Energy scan`
- **THEN** the summary is `Energy scan`

#### Scenario: A master with dangling links
- **WHEN** `linked_scan` is crawled and the master's dataset extracted
- **THEN** the summary is `Test detector 4M, entry.data.data_000001 [2, 8, 6] <u4, entry.instrument.detector.detectorSpecific.flatfield [8, 6] <f4, entry.instrument.detector.detectorSpecific.pixel_mask [8, 6] <u4, external_links 12, dangling 9`
