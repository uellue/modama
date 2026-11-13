# Spec Delta

## ADDED Requirements

### Requirement: MRC files are datasets of em/mrc
A file named `*.mrc`, `*.mrcs` or `*.map`, or of any name whose bytes 208 to 210 are `MAP` with the machine stamp's first byte `0x44` or `0x11` at byte 212, SHALL be a single-file dataset of the format `em/mrc`, type `application/x.mrc`, whether it holds an image, an image stack, a movie or a volume. The format runs at priority 61, as a format that drops a type (TEMPLATE.md); a format that claims MRC files as members of a larger dataset (Direct Electron's acquisitions, a planned `em/de`) runs above it.

#### Scenario: A map from EMDB
- **WHEN** the fixture `emdb_map` (`EMD-3197.map`) is crawled
- **THEN** it is one dataset of `em/mrc`, type `application/x.mrc`

#### Scenario: Files written by mrcfile
- **WHEN** the fixture `written_by_mrcfile` (`stack.mrcs`, an image stack, and `image.mrc`, one image) is crawled
- **THEN** each file is one dataset of `em/mrc`

#### Scenario: Files of an EPU session
- **WHEN** the fixture `epu_falcon` (an EPU micrograph `FoilHole_…_Data_….mrc` and a grid square image `GridSquare_….mrc`, EMPIAR-12652) is crawled
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
The extractor SHALL read the file's 1024-byte main header and keep every field of it in `original_metadata` under its name as `mrcfile` gives it, flat (`cella.x`, `cellb.alpha`, `origin.z`, `label[1]` to `label[10]`), values as found: numbers as `mrcfile` gives them, widened to Python numbers (a 32-bit 11.4 as `11.399999618530273`, TEMPLATE.md; @weber, 309); the infinities and NaN, which JSON cannot hold, as Python writes them (`nan`, `inf`); `nsymbt` as the file writes it, which `mrcfile` is not given (it would allocate the extended header's declared size, up to 2 GiB, and fails on a negative one); a text field up to its first NUL byte, without trailing spaces, read as Latin-1; the map word as written (`MAP `); the machine stamp as `mrcfile` prints it. The skip list is `extra1` and `extra2` (unused space). Empty values are kept. A label that the shared credential check flags is left out and counted in `mapped_metadata` as `credentials_left_out`. `mapped_metadata` has `data_type` (from `mode`), `voxel_size` (x, y, z; values as above) and `kind` (`image`, `image stack`, `volume` or `volume stack`), as `mrcfile` computes them. The summary line is `nx`, `ny`, `nz`, `mode` as `name value` (0 is a value of each), then the entries of an FEI extended header's record (next requirement), then the first label bare if it is not empty.

#### Scenario: The header of a map from EMDB
- **WHEN** `emdb_map/EMD-3197.map` is extracted
- **THEN** the summary line is `nx 20, ny 20, nz 20, mode 2, ::::EMDATABANK.org::::EMD-3197::::`, `original_metadata` has `machst` `0x44 0x41 0x00 0x00`, `map` `MAP `, `cella.x` 228.0, `label[2]` empty text and no `extra1`, and `mapped_metadata` has `kind` `volume`, `data_type` `float32` and `voxel_size` [11.399999618530273, 11.399999618530273, 11.399999618530273]

#### Scenario: Values that JSON cannot hold
- **WHEN** a copy of `emdb_map/EMD-3197.map` has a NaN as `rms` and 0 as `mx`
- **THEN** `original_metadata` has `rms` `nan` and `mx` 0, `mapped_metadata` has `voxel_size` `inf` for x, and the values can be stored as JSON

#### Scenario: A tomogram from EMDB
- **WHEN** `emdb_tomogram/emd_66908.map` (700 x 700 x 357, 8-bit) is extracted
- **THEN** the summary line is `nx 700, ny 700, nz 357, mode 0, ::::EMDATABANK.org::::EMD-66908::::` and `mapped_metadata` has `kind` `volume` and `data_type` `int8`

#### Scenario: A particle stack
- **WHEN** `particle_stack/…_particles.mrcs` (written by cryoSPARC, EMPIAR-11898) is extracted
- **THEN** the summary line is `nx 540, ny 540, nz 69, mode 2` and `mapped_metadata` has `kind` `image stack`

#### Scenario: An image stack
- **WHEN** `written_by_mrcfile/stack.mrcs` is extracted
- **THEN** `mapped_metadata` has `kind` `image stack`

#### Scenario: One image
- **WHEN** `written_by_mrcfile/image.mrc` (one 16x16 image) is extracted
- **THEN** `mapped_metadata` has `kind` `image`

#### Scenario: A label nobody has seen before
- **WHEN** an MRC file has the label `made-up label 42 zz`
- **THEN** `original_metadata` has it as `label[1]`

#### Scenario: A credential in a label
- **WHEN** an MRC file has the label `--password hunter2`
- **THEN** that label is not in `original_metadata` nor in the summary line, and `mapped_metadata` has `credentials_left_out` 1

### Requirement: The first record of an FEI extended header is extracted
For a file whose `exttyp` is `FEI1` or `FEI2` (written by Thermo Fisher's EPU, Tomo and Velox), the extractor SHALL read the extended header's first record only (one per frame; 768 bytes for `FEI1`, 888 for `FEI2`, at most the header's `nsymbt`), interpret it with `mrcfile`'s description of that type (`mrcfile.dtypes.get_ext_header_dtype`) and keep every field in `original_metadata` as `extended_header.<name>` under `mrcfile`'s name (`extended_header.Microscope type`, `extended_header.HT`), values as found as for the main header (64-bit floats as Python floats, booleans as booleans, text up to its first NUL byte). The skip list is `Unused range` (unused space, binary) and the reserved fields `Camera param reserved 0` to `9` and `STEM param reserved 0` to `4` (placeholders). The bitmasks are kept as numbers, not interpreted. A record that is shorter than its type or whose `Metadata size` is not its type's size is not read, with a warning of the extraction; the main header is extracted as before. Other extended headers (`CCP4`, `SERI`, `AGAR`, `MRCO`, `HDF5`, none) are not read. The summary line has, after `mode`, the record's `Microscope type` and `Camera name` bare and its `HT` and `Pixel size X` after their names with `(unit unknown)` (`mrcfile` gives no unit), an empty text or a 0 left out.

#### Scenario: An EPU micrograph from a Falcon camera
- **WHEN** `epu_falcon/FoilHole_4551046_Data_4541935_4541937_20220507_103020.mrc` (`FEI2`, EPU 2.12) is extracted
- **THEN** the summary line is `nx 4096, ny 4096, nz 1, mode 6, TITAN52336460, HT 300000.0 (unit unknown), Pixel size X 8.674088530780111e-11 (unit unknown), BM-Falcon`, and `original_metadata` has `extended_header.Application` `EPU`, `extended_header.Application version` `2.12.1.2782`, `extended_header.Detector commercial name` `BM-Falcon` (the bytes after its first NUL left out), `extended_header.Direct detector electron counting` true, `extended_header.Bitmask 1` 4294955007, and no `extended_header.Unused range` nor `extended_header.Camera param reserved 0`

#### Scenario: An FEI1 header from EPU 1.2
- **WHEN** `fei1/fei-extended.mrc` (`FEI1`) is extracted
- **THEN** the summary line is `nx 3710, ny 3838, nz 1, mode 6, TITAN52336320, HT 300000.0 (unit unknown), Pixel size X 8.537755225024313e-11 (unit unknown), EF-CCD`, `original_metadata` has `extended_header.Application` `Fei EPU`, and no `extended_header.Scan rotation` (an `FEI2` field)

#### Scenario: An EPU movie with nearly empty records
- **WHEN** `epu_movie/FoilHole_20147964_Data_20151868_20151870_20220520_172819_Fractions.mrc` (`FEI2`, 42 frames, a record per frame that holds little but its time stamps) is extracted
- **THEN** the summary line is `nx 4096, ny 4096, nz 42, mode 1`, and `original_metadata` has `extended_header.Timestamp` 44701.72802132257, `extended_header.Acquisition time stamp` 1653085701042270 and `extended_header.HT` 0.0 (empty values kept)

#### Scenario: An extended header that is not of its type
- **WHEN** an MRC file says `exttyp` `FEI2` and its extended header's first 4 bytes, the record's `Metadata size`, are not 888
- **THEN** `original_metadata` has the main header and no `extended_header.` entry, and the extraction warns `extended header is not FEI2`

### Requirement: Only the headers are read
The extractor SHALL read the main header and, for `FEI1` and `FEI2`, the extended header's first record, nothing else of the file.

#### Scenario: Only the header is read
- **WHEN** an MRC file has a 1 GiB data block
- **THEN** the extraction reads at most 1024 bytes of it plus 4096 for the reader's imports

#### Scenario: Only the first record is read
- **WHEN** an MRC file has an `FEI2` extended header of 909312 bytes, as EPU writes it, and a 1 GiB data block
- **THEN** the extraction reads at most 1024 + 888 bytes of it plus 4096 for the reader's imports

#### Scenario: An extended header of 2 GiB
- **WHEN** a copy of the `epu_falcon` micrograph says `nsymbt` 2147483647
- **THEN** the extraction's peak memory grows by less than 64 MiB, `original_metadata` has `nsymbt` 2147483647 and the FEI record's fields

#### Scenario: A negative extended header size
- **WHEN** a copy of the `epu_falcon` micrograph says `nsymbt` -5
- **THEN** `original_metadata` has the main header with `nsymbt` -5 and no `extended_header.` entry
