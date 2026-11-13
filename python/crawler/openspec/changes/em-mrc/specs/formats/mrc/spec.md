# Spec Delta

## ADDED Requirements

### Requirement: MRC files are datasets of em/mrc
A file named `*.mrc`, `*.mrcs` or `*.map`, or of any name whose bytes 208 to 210 are `MAP` with the machine stamp's first byte `0x44` or `0x11` at byte 212, SHALL be a single-file dataset of the format `em/mrc`, type `application/x.mrc`, whether it holds an image, an image stack or a volume.

#### Scenario: A map from EMDB
- **WHEN** the fixture `emdb_map` (`EMD-3197.map`) is crawled
- **THEN** it is one dataset of `em/mrc`, type `application/x.mrc`

#### Scenario: Files written by mrcfile
- **WHEN** the fixture `written_by_mrcfile` (`stack.mrcs`, an image stack, and `image.mrc`, one image) is crawled
- **THEN** each file is one dataset of `em/mrc`

#### Scenario: A renamed copy
- **WHEN** an MRC file is renamed without its extension
- **THEN** it is still a dataset of `em/mrc`, by its content

### Requirement: A name that lies falls back to the content's type
A file named like an MRC file whose bytes 208 to 210 are not `MAP` SHALL get the type it has without its name rule, with the reason in its basis (change `recognition-checks-content`).

#### Scenario: A linker map named .map
- **WHEN** `misnamed/program.map` is a text file, as a linker writes one
- **THEN** it is a dataset of type `text/plain`, not of `em/mrc`, and its basis says `no MAP at byte 208`

### Requirement: The MRC header is extracted
The extractor SHALL read the file's first 1024 bytes only (the main header; the extended header is not read) and keep every field of the header in `original_metadata` under its name as `mrcfile` gives it, flat (`cella.x`, `cellb.alpha`, `origin.z`, `label[1]` to `label[10]`), values as found: numbers as the reader gives them, text fields without their padding, the machine stamp as `mrcfile` prints it. The skip list is `extra1` and `extra2` (unused space). Empty values are kept. A label that the shared credential check flags is left out and counted in `mapped_metadata` as `credentials_left_out`. `mapped_metadata` has `data_type` (from `mode`), `voxel_size` (x, y, z) and `kind` (`image`, `image stack`, `volume` or `volume stack`), as `mrcfile` computes them. The summary line is `nx`, `ny`, `nz`, `mode`, `ispg`, `cella.x`, `cella.y`, `cella.z`, `mx`, `my`, `mz` as `name value`, a cell length or sampling of 0 left out, then the first label bare if it is not empty.

#### Scenario: The header of a map from EMDB
- **WHEN** `emdb_map/EMD-3197.map` is extracted
- **THEN** the summary line is `nx 20, ny 20, nz 20, mode 2, ispg 1, cella.x 228.0, cella.y 228.0, cella.z 228.0, mx 20, my 20, mz 20, ::::EMDATABANK.org::::EMD-3197::::`, `original_metadata` has `machst` `0x44 0x41 0x00 0x00`, `map` `MAP `, `label[2]` empty text and no `extra1`, and `mapped_metadata` has `kind` `volume`, `data_type` `float32` and `voxel_size` [11.399999618530273, 11.399999618530273, 11.399999618530273] (`mrcfile`'s float32, unrounded)

#### Scenario: An image stack
- **WHEN** `written_by_mrcfile/stack.mrcs` is extracted
- **THEN** `mapped_metadata` has `kind` `image stack` and the summary line has `ispg 0`

#### Scenario: One image
- **WHEN** `written_by_mrcfile/image.mrc` (one 16x16 image) is extracted
- **THEN** `mapped_metadata` has `kind` `image`

#### Scenario: A label nobody has seen before
- **WHEN** an MRC file has the label `made-up label 42 zz`
- **THEN** `original_metadata` has it as `label[1]`

#### Scenario: A credential in a label
- **WHEN** an MRC file has the label `--password hunter2`
- **THEN** that label is not in `original_metadata` nor in the summary line, and `mapped_metadata` has `credentials_left_out` 1

#### Scenario: Only the header is read
- **WHEN** an MRC file has a 1 GiB data block
- **THEN** the extraction reads at most 1024 bytes of it plus 4096 for the reader's imports
