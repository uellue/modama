# Spec Delta

## Purpose

Zarr stores (v2 and v3) and HyperSpy's `.zspy` stores as one collapsed dataset each, described by what their metadata files say, never by reading a chunk or anything outside the store. Known limit: the dataset's stamp is its folder's listing, so a metadata file rewritten below the store's first level, or in place, is extracted again only by the spot check, a change of the top-level listing or of the installation.

## ADDED Requirements

### Requirement: A Zarr store is a described collapsed dataset
With the `common` collection installed, a folder holding `zarr.json`, `.zarray` or `.zgroup` SHALL be one collapsed dataset of the format `common/zarr`, type `application/x-zarr`, with the basis and warnings of the core's `zarr/zarr`, and nothing below it SHALL be visited by the walk.

#### Scenario: A version 2 group store
- **WHEN** a Zarr v2 group with root attributes and an array `array0` of 64 × 64 chunks, written by zarr-python, is crawled
- **THEN** the result has one collapsed dataset of the format `common/zarr` anchored at the store, and no dataset for its chunk files

#### Scenario: Without the common collection
- **WHEN** the same store is crawled with only the crawler's collections enabled
- **THEN** it is one collapsed dataset of the format `zarr/zarr`, as before

#### Scenario: Both zarr.json and .zgroup
- **WHEN** a store's root holds a v3 `zarr.json` and a v2 `.zgroup` with `.zattrs`
- **THEN** its basis names `zarr.json`, as the core's does, and its values are those of `zarr.json`

### Requirement: A HyperSpy Zarr store is typed by name and content
A Zarr store named `*.zspy` whose root attributes have `file_format` `ZSpy` SHALL be a dataset of the format `common/zspy`, type `application/x.zspy`; a store named `*.zspy` without it SHALL be a `common/zarr` store.

#### Scenario: A store written by RosettaSciIO
- **WHEN** a signal saved by RosettaSciIO's zspy writer as `scan.zspy` is crawled
- **THEN** it is one collapsed dataset of type `application/x.zspy`

#### Scenario: A zspy store that HyperSpy did not write
- **WHEN** a Zarr group without HyperSpy's root attributes is named `other.zspy`
- **THEN** it is a dataset of the format `common/zarr`

#### Scenario: A HyperSpy store named zarr
- **WHEN** a store written by RosettaSciIO's zspy writer is named `scan.zarr`
- **THEN** it is a dataset of the format `common/zarr`, described with HyperSpy's skip list and summary line

### Requirement: The extractor of a collapsed store reads below its anchor
The extractor SHALL read the metadata files of the store's nodes below its anchor, which are not members of the collapsed dataset; this is the one exception to the rule that an extractor reads its dataset's members only.

#### Scenario: A metadata file below the first level changes
- **WHEN** an attribute in `a/b/.zattrs` of a stored store is rewritten and the next crawl runs without the spot check picking the store
- **THEN** the store's extraction is reused, and when the spot check picks it, the change shows as a spot-check difference

### Requirement: A store is described by its metadata files
The extractor SHALL walk the store's nodes (folders holding `zarr.json`, `.zarray` or `.zgroup`) from its root and give as `original_metadata`, under the node's dotted path, every attribute of every node, every entry of each array's metadata document as found, objects flattened as `a.b` and `a[2].b`, and the root's `zarr_format`.

#### Scenario: Version 2 and version 3 stores
- **WHEN** a v2 store and a v3 store, each a group with attributes `{"metadata0": {"energy": 300000.0, "axes": {"axis_0": {"units": "Å", "sampling": 0.1}}}}` and an array `array0` of shape [8, 8, 16, 16], `float32`, are extracted
- **THEN** both give `metadata0.energy 300000.0`, `metadata0.axes.axis_0.units Å`, `metadata0.axes.axis_0.sampling 0.1` and `array0.shape [8, 8, 16, 16]`; the v2 store `zarr_format 2`, `array0.dtype <f4`, `array0.chunks` and `array0.compressor.id`, the v3 store `zarr_format 3`, `array0.data_type float32`, `array0.chunk_grid.configuration.chunk_shape` and `array0.codecs[1].name`; no nested node's `zarr_format` or `node_type`

#### Scenario: An entry nobody has seen
- **WHEN** a group's attributes hold `{"made_up_key": "made-up value"}`
- **THEN** `made_up_key made-up value` is in `original_metadata` under the group's path

#### Scenario: A nested store
- **WHEN** a group store holds another group store with an array, as a subfolder
- **THEN** there is one dataset, and the inner store's attributes and array are in its values under the inner folder's name

#### Scenario: An unknown codec and an unknown data type
- **WHEN** a v2 group holds an array whose compressor is `{"id": "imagecodecs_jpeg2k"}` and a v3 group an array whose `data_type` is an extension nobody registered, each beside another array
- **THEN** both arrays are described with their compressor and data type as found, and so are the other arrays

#### Scenario: Consolidated metadata is not read
- **WHEN** a v2 store has a `.zmetadata` whose content differs from its nodes' documents
- **THEN** the values are those of the nodes' documents, and `.zmetadata` is not opened

### Requirement: Only metadata files are read
The extractor SHALL open only the metadata files `zarr.json`, `.zarray`, `.zgroup` and `.zattrs` of the store's nodes and list only its groups' folders, never a chunk and never an array's folder.

#### Scenario: A store of many chunks
- **WHEN** a v2 store and a v3 store with an array of 4,096 chunks each are extracted
- **THEN** the bytes read (`rchar` of `/proc/self/io`) are at most the sum of the sizes of the store's metadata files

#### Scenario: A folder in a store that is no node
- **WHEN** a store holds `.ipynb_checkpoints/zarr-checkpoint.json`
- **THEN** that folder is not listed, nothing of it is read, and nothing of it is in the values

### Requirement: Nothing is read from outside the store
The extractor SHALL NOT follow a symlink below the store's folder, SHALL open only folders and regular files, and SHALL confirm after opening a file that it is the regular file it looked at.

#### Scenario: A group that is a symlink
- **WHEN** a store holds a group `linked` that is a symlink to a Zarr group outside the store with the attribute `secret`
- **THEN** nothing of `linked` is in the values

#### Scenario: A metadata file that is a symlink
- **WHEN** a group's `.zattrs` is a symlink to a JSON file outside the store
- **THEN** the file is not opened, and the group is described without attributes

#### Scenario: A metadata file that is a FIFO
- **WHEN** a group's `.zattrs` is a named pipe
- **THEN** the extraction does not block, and the group's other entries are described

### Requirement: The walk of a store is bounded
The walk SHALL stop at 1,000 kept entries, 5,000 nodes, a third of the extractor's time limit or 16 MiB read, and say which in `mapped_metadata.walk`; a metadata file over 1 MiB SHALL NOT be read and SHALL be named in `mapped_metadata.not_read`; a group's listing SHALL be read up to one name more than the nodes the walk still has room for; the nodes below a group at depth 100 SHALL NOT be walked, its path named in `mapped_metadata.too_deep`.

#### Scenario: The walk stops at 5000 nodes
- **WHEN** a store holds 6,000 empty groups
- **THEN** `mapped_metadata.walk` says it was cut at the node limit of 5000, and the group's listing was not read beyond 5,001 names

#### Scenario: The walk stops after 16 MiB
- **WHEN** a store holds 20 groups whose `.zattrs` are 1 MiB each
- **THEN** `mapped_metadata.walk` says it was cut at the byte limit of 16 MiB, and at most 16 MiB of them were read

#### Scenario: A metadata file over 1 MiB
- **WHEN** a group's `.zattrs` is 2 MiB
- **THEN** it is not read, its path is in `mapped_metadata.not_read`, and the store's other nodes are described

#### Scenario: A root document over 1 MiB
- **WHEN** a store's root `zarr.json` is 2 MiB
- **THEN** it is not read, `zarr.json` is in `mapped_metadata.not_read`, and the store's other nodes are described

### Requirement: Unreadable metadata is reported
A node whose metadata file is not a JSON object, or is nested too deeply to parse or flatten, SHALL be left out with everything below it and its path named in `mapped_metadata.unreadable`; a store whose root metadata cannot be read SHALL fail its extraction, with the reason.

#### Scenario: A broken nested node
- **WHEN** an array's `.zarray` of a store is not JSON
- **THEN** the array's path is in `mapped_metadata.unreadable`, and the root's attributes are described

#### Scenario: Deep nesting
- **WHEN** a group's `.zattrs` is an object nested 100,000 levels deep, and another chain of groups is 150 folders deep
- **THEN** the first group's path is in `mapped_metadata.unreadable`; the chain is described down to depth 100, the path of its group at depth 100 is in `mapped_metadata.too_deep`, and the extraction does not fail

#### Scenario: A broken root
- **WHEN** a store's `zarr.json` is not JSON
- **THEN** the store is one collapsed dataset with the core's warning, and its extraction fails naming `zarr.json`

### Requirement: What the Zarr walk leaves out
`original_metadata` SHALL leave out `zarr_format` of nested nodes of the root's version, each node's `node_type`, v3's `consolidated_metadata`, and what `textual` and `credential` refuse; for a store whose root attributes have `file_format` `ZSpy`, whatever its name, also HyperSpy's skip list of `.hspy` files: groups named `_HyperSpy` with everything below them, and the value `_None_`.

#### Scenario: HyperSpy's internal state
- **WHEN** a store written by RosettaSciIO is extracted
- **THEN** no name holds `._HyperSpy.` and no value is `_None_`, and its `metadata` and `original_metadata` entries are in the values as `Experiments.<title>.metadata.…` and `Experiments.<title>.original_metadata.…`

#### Scenario: A credential in the attributes
- **WHEN** a group's attributes hold `{"password": "hunter2"}`
- **THEN** the value is not in the values

### Requirement: The summary line of a store
The summary line SHALL be, as found, a HyperSpy signal's title, signal type and data shape (the patterns of `.hspy`); else the `shape` and the data type (`data_type` in v3, `dtype` in v2) of the root array, or of the first array one level down in name order. The subjects SHALL be the HyperSpy signal type, where there is one.

#### Scenario: A HyperSpy store
- **WHEN** a store written by RosettaSciIO of a signal with title `4D-STEM scan`, signal type `electron_diffraction` and data of shape [4, 4, 16, 16] is extracted
- **THEN** the summary is `4D-STEM scan, electron_diffraction, shape [4, 4, 16, 16]` and the subjects hold `electron_diffraction`

#### Scenario: An abTEM-like store
- **WHEN** a v3 group with an array `array0` of shape [8, 8, 16, 16], `float32`, is extracted
- **THEN** the summary is `shape [8, 8, 16, 16], float32`
