# Spec Delta

## Purpose

Zarr stores (v2 and v3) and HyperSpy's `.zspy` stores as one collapsed dataset each, described by what their metadata files say, never by reading a chunk or anything outside the store. Known limit: the dataset's stamp is its folder's listing, so a nested metadata file changed in place is extracted again only when the top-level listing or the installation changes.

## ADDED Requirements

### Requirement: A Zarr store is a described collapsed dataset
With the `common` collection installed, a folder holding `zarr.json`, `.zarray` or `.zgroup` SHALL be one collapsed dataset of the format `common/zarr`, type `application/x-zarr`, with the basis and warnings of the core's `zarr/zarr`, and nothing below it SHALL be visited by the walk.

#### Scenario: A version 2 group store
- **WHEN** a Zarr v2 group with root attributes and an array `array0` of 64 × 64 chunks, written by zarr-python, is crawled
- **THEN** the result has one collapsed dataset of the format `common/zarr` anchored at the store, and no dataset for its chunk files

#### Scenario: Without the common collection
- **WHEN** the same store is crawled with only the crawler's collections enabled
- **THEN** it is one collapsed dataset of the format `zarr/zarr`, as before

### Requirement: A HyperSpy Zarr store is typed by name and content
A Zarr store named `*.zspy` whose root attributes have `file_format` `HyperSpy` SHALL be a dataset of the format `common/zspy`, type `application/x.zspy`; a store named `*.zspy` without it SHALL be a `common/zarr` store.

#### Scenario: A store written by RosettaSciIO
- **WHEN** a signal saved by RosettaSciIO's zspy writer as `scan.zspy` is crawled
- **THEN** it is one collapsed dataset of type `application/x.zspy`

#### Scenario: A zspy store that HyperSpy did not write
- **WHEN** a Zarr group without HyperSpy's root attributes is named `other.zspy`
- **THEN** it is a dataset of the format `common/zarr`

### Requirement: A store is described by its metadata files
The extractor SHALL walk the store's nodes (folders holding `zarr.json`, `.zarray` or `.zgroup`) from its root and give as `original_metadata`, under the node's dotted path, every attribute of every node and every entry of each array's metadata document as found, objects flattened as `a.b` and `a[2].b`, and the root's `zarr_format` as `mapped_metadata`.

#### Scenario: Version 2 and version 3 stores
- **WHEN** a v2 store and a v3 store, each a group with attributes `{"metadata0": {"energy": 300000.0, "axes": {"axis_0": {"units": "Å", "sampling": 0.1}}}}` and an array `array0` of shape [8, 8, 16, 16], `float32`, are extracted
- **THEN** both give `metadata0.energy 300000.0`, `metadata0.axes.axis_0.units Å`, `metadata0.axes.axis_0.sampling 0.1` and `array0.shape [8, 8, 16, 16]`; the v2 store `array0.dtype <f4`, `array0.chunks` and `array0.compressor.id`, the v3 store `array0.data_type float32`, `array0.chunk_grid.configuration.chunk_shape` and `array0.codecs[1].name`; `mapped_metadata` is `zarr_format 2` and `zarr_format 3`

#### Scenario: An entry nobody has seen
- **WHEN** a group's attributes hold `{"made_up_key": "made-up value"}`
- **THEN** `made_up_key made-up value` is in `original_metadata` under the group's path

#### Scenario: A nested store
- **WHEN** a group store holds another group store with an array, as a subfolder
- **THEN** there is one dataset, and the inner store's attributes and array are in its values under the inner folder's name

### Requirement: Only metadata files are read
The extractor SHALL open only the metadata files `zarr.json`, `.zarray`, `.zgroup` and `.zattrs` of the store's nodes and list only its groups' folders, never a chunk and never an array's folder.

#### Scenario: A store of many chunks
- **WHEN** a v2 store and a v3 store with an array of 4,096 chunks each are extracted
- **THEN** no chunk file is opened, and the bytes read are those of the metadata files

#### Scenario: A folder in a store that is no node
- **WHEN** a store holds `.ipynb_checkpoints/zarr-checkpoint.json`
- **THEN** that folder is neither listed nor read, and nothing of it is in the values

### Requirement: Nothing is read from outside the store
The extractor SHALL NOT follow a symlink below the store's folder, and SHALL read only regular files.

#### Scenario: A group that is a symlink
- **WHEN** a store holds a group `linked` that is a symlink to a Zarr group outside the store with the attribute `secret`
- **THEN** nothing of `linked` is in the values

#### Scenario: A metadata file that is a FIFO
- **WHEN** a group's `.zattrs` is a named pipe
- **THEN** the extraction does not block, and the group's other entries are described

### Requirement: The walk of a store is bounded
The walk SHALL stop at 1,000 kept entries, 5,000 nodes, a third of the extractor's time limit or 16 MiB read, and say which in `mapped_metadata.walk`; a metadata file over 1 MiB SHALL NOT be read and SHALL be named in `mapped_metadata.not_read`; a group's listing SHALL be read up to 10,000 names.

#### Scenario: The walk stops at 5000 nodes
- **WHEN** a store holds 6,000 empty groups
- **THEN** `mapped_metadata.walk` says it was cut at the node limit of 5000

#### Scenario: A metadata file over 1 MiB
- **WHEN** a group's `.zattrs` is 2 MiB
- **THEN** it is not read, its path is in `mapped_metadata.not_read`, and the store's other nodes are described

### Requirement: Unreadable metadata is reported
A node whose metadata file is not a JSON object SHALL be left out with everything below it and its path named in `mapped_metadata.unreadable`; a store whose root metadata cannot be read SHALL fail its extraction, with the reason.

#### Scenario: A broken nested node
- **WHEN** an array's `.zarray` of a store is not JSON
- **THEN** the array's path is in `mapped_metadata.unreadable`, and the root's attributes are described

#### Scenario: A broken root
- **WHEN** a store's `zarr.json` is not JSON
- **THEN** the store is one collapsed dataset with the core's warning, and its extraction fails naming `zarr.json`

### Requirement: What the Zarr walk leaves out
`original_metadata` SHALL leave out each node's `zarr_format` and `node_type`, v3's `consolidated_metadata`, and what the shared checks `textual` and `credential` refuse; for a store whose root attributes have `file_format` `HyperSpy`, whatever its name, also HyperSpy's skip list of `.hspy` files: groups named `_HyperSpy` with everything below them, and the value `_None_`.

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
