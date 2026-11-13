# Proposal

## Why

MRC files (cryo-EM micrographs, movies, maps, tomograms and particle stacks: `.mrc`, `.map`, `.mrcs`) are not covered: today each becomes a single-file dataset of no known type, findable only by its path. The tree holds 1,392 `.mrc` files (50.5 GB) and 21 `.map` (the private listing of October): 920 in a cryo-EM project collected with Thermo Fisher EPU (`Images-Disc1/GridSquare_*/Data/FoilHole_*`), 300 in a Medipix3 simulation project, 81 and 61 in two EM groups' folders. Requests: the hallway test of 2026-11-13, task (a), built the first version from public test data; decision 293 (@weber, 2026-11-13): "are there public MRC files we can use? I think there should, it is the format of choice for CryoEM! Let's use that, e.g. from an open datarepo, zenodo or sth." Serves R15 (extract from content), R30 (findable by what the data is), decisions 230 and 234 and the skip-list rule of 2026-11-12.

## The person's answers

Skill step 1, 2026-11-13, through the main session (hallway test):

- Files: maps (`.map`, `.mrc`) from processing and deposition, image stacks (`.mrcs`) from collection and processing software. Program versions unknown.
- Each file is one dataset; grouping with `.mdoc`, `.star` and the like is later.
- `mrcfile` is approved as the reader; pin the current release with its reason.
- A person looks at the dimensions, the mode (data type), the cell and sampling as the header writes them, whether it is an image stack or a volume, and the labels.
- Nothing private or a GUI setting is known. Labels can hold user names and paths: they are what the file says; the credential check applies.
- `.map` is used by other programs (source maps, linker maps).
- No real files can be given: public files or files written with `mrcfile`.

Decision 293 (@weber): real MRC files from open archives as fixtures. Read as: public files of each kind the tree holds (EPU micrographs and movies with FEI extended headers first, then maps, tomograms and stacks), each cut to the bytes the format reads.

Questions put to @weber on 2026-11-13 (295 to 298, through the main session: 295 the summary line, 296 EPU's sidecars, 297 labels, 298 the `FEI1` fixture's licence), open; the leans below are applied meanwhile.

## Public files used (decision 293)

All from EMBL-EBI's archives, CC0 (EMPIAR FAQ; EMBL-EBI's public data-access statement for PDBe, EMDB and EMPIAR), but one; each cut by `mrc/tests/cut-header.sh` to the main header and, for an FEI extended header, its first record:

- EMPIAR-12652 (EPU 2.12, Titan Krios, Falcon): a micrograph `FoilHole_…_Data_….mrc` and a grid square image `GridSquare_….mrc`, the same folder layout as the tree's EPU project; `FEI2`.
- EMPIAR-12018 (EPU, Falcon): a movie `FoilHole_…_Fractions.mrc`, 42 frames, `FEI2` records that hold little but time stamps.
- EMPIAR-11898: a particle stack `.mrcs` written by cryoSPARC.
- EMD-66908: a tomogram, 8-bit (mode 0), as EMDB distributes it.
- EMD-3197: a map, unchanged from `mrcfile`'s test data (the hallway version).
- `fei-extended.mrc` of `mrcfile`'s test data (EPU 1.2, `FEI1`): BSD-3-Clause as `mrcfile`'s repository, contributed "with permission for public distribution" (298). No `FEI1` file was found in EMPIAR quickly.

## Assumptions and leans

- **Type**: no established MIME type for MRC exists (none in the vendored shared-mime-info; Debian's `media-types` gives `*.mrc` to `application/marc`, library catalogue records), so the unofficial `application/x.mrc`, with the globs `*.mrc`, `*.mrcs`, `*.map` and a magic rule: `MAP` at byte 208 (the map word; `mrcfile` checks its first three bytes) and the machine stamp's first byte `0x44` (little-endian) or `0x11` (big-endian) at byte 212. One format, `em/mrc`, for all three names: the header says whether a file is an image, a stack or a volume.
- **Content check for every name**: a file named like an MRC file without `MAP` at byte 208 is not MRC and gets the type it has without its name (change `recognition-checks-content`). Against: MRC files written before the map word (MRC2000) lose their extraction; none are known here, and a crawl shows them with the reason in their basis.
- **The extended header, first record only** (new, decision 293's files): EPU writes the instrument's metadata (microscope, voltage, dose, pixel size, camera, defocus, stage) into an FEI extended header (`exttyp` `FEI1` or `FEI2`), one record per frame (768 or 888 bytes) and padding to 786432 or 909312 bytes. The extractor reads the first record only, interprets it with `mrcfile`'s description (`mrcfile.dtypes.get_ext_header_dtype`; `np.frombuffer`, not `MrcObject.indexed_extended_header`, which reads all records and sets a dtype in the way NumPy 2.5 deprecates) and keeps its fields as `extended_header.<name>`. Against: a movie's later frames may differ (their records are not read); in the public movie they hold time stamps only.
- **Skip list of an FEI record**: `Unused range` (binary, unused space) and the reserved placeholders `Camera param reserved 0`–`9`, `STEM param reserved 0`–`4`. The bitmasks, which say which fields are valid, are kept as numbers and not interpreted: interpreting needs FEI's table of bits, and the record's values are what the file says.
- **Text is a C string**: a fixed-size text field ends at its first NUL byte. EPU leaves bytes after it (`Detector commercial name` `BM-Falcon\x00fC` in EMPIAR-12652); without this, the shared check would drop the field for its control characters.
- **32-bit floats** (decided by @weber, 309: "let's keep the full value I think, just for consistency"): the main header's floats (`cella`, `dmin`, `rms` …) and the voxel size are 32-bit; they are kept as `mrcfile` widens them to Python floats (`11.399999618530273` for a stored 11.4), as TEMPLATE.md says and the DM reader's values show. The lean before was the shortest decimal (`11.4`); the review found that JSON's `11.4` is another number unless the reader knows the field was 32-bit. (The hallway tester's open question 16.)
- **Values JSON cannot hold**: a NaN or an infinity (a NaN `rms`; a voxel size from a sampling of 0) as Python writes it (`nan`, `inf`), as `dm.kept` and `common/structured` do; the extraction stores JSON without them (review finding 2).
- **The extended header's size**: `mrcfile` allocates `nsymbt` bytes even with `header_only` (2 GiB for 2147483647; a negative size fails), so it gets the main header with `nsymbt` 0, and `nsymbt` is kept as the file writes it; the extractor reads the FEI record itself, bounded (review finding 3).
- **Priority 61** (review finding 7): a format that drops a type runs at 61 or more (TEMPLATE.md); a format that claims MRC files as members of a larger dataset (`em/de`, decision 302, pending) runs above it.
- **original_metadata**: every field of the main header, under `mrcfile`'s field names, flat (`cella.x`, `cellb.alpha`, `origin.z`, `label[1]` to `label[10]`, from 1 as in `common/structured`), values as found, the machine stamp as `mrcfile` prints it (`0x44 0x41 0x00 0x00`), the map word with its space (`MAP `). Skip list: `extra1`, `extra2` (unused space). Empty values kept (decision 161). Credentials in labels left out (`modama_crawler.formats.values.credential`). Labels kept as the file says (297).
- **mapped_metadata**: what `mrcfile` computes: `data_type` (from `mode`), `voxel_size` (cell over sampling), `kind` (`image`, `image stack`, `volume`, `volume stack`).
- **The summary line** (295): a few chosen entries, as TEMPLATE says (the hallway version had 11 values and a label; the grader found it too long): `nx`, `ny`, `nz`, `mode` as `name value` (0 is a value of each: mode 0 is 8-bit), then from an FEI record `Microscope type` and `Camera name` bare and `HT` and `Pixel size X` after their names with `(unit unknown)` (an empty text or a 0 left out), then the first label bare. `mrcfile` gives no units; FEI's MRC2014 description says SI units, but the rule is the reader's word (EM README, "Values and units"). For example `nx 4096, ny 4096, nz 1, mode 6, TITAN52336460, HT 300000.0 (unit unknown), Pixel size X 8.674088530780111e-11 (unit unknown), BM-Falcon`, and for a map `nx 20, ny 20, nz 20, mode 2, ::::EMDATABANK.org::::EMD-3197::::`. Against: a map's line has no cell or voxel size (they are in the values).
- **EPU's sidecars** (296): `FoilHole_…_Data_….xml`, `.jpg` and `_Fractions.xml` beside each micrograph stay datasets of their own here; grouping them with the MRC file is a later change. Against: the XML holds what the MRC lacks (dose on the camera, aperture names).
- **Reader warnings** (a machine stamp `mrcfile` does not know, a missing map word) and an extended header that is not of its type are logged as warnings of the extraction, as Merlin does for a date; the file is read in `mrcfile`'s permissive mode.

## What Changes

- New area `mrc` of `modama-formats-em` (`src/modama_formats_em/mrc/`): format `em/mrc`, `mrc.xml` with `application/x.mrc`, fixtures (above; files written by `mrcfile` at test time; a linker map named `.map`), `cut-header.sh` and tests.
- New dependency of `modama-formats-em`: `mrcfile==1.5.4` (BSD-3-Clause, pure Python, requires numpy).

Behaviour towards the user: a harvester and a searcher see records of `.mrc`, `.mrcs` and `.map` files with the MRC header as a description (summary line and the second description with the header's fields and, for EPU's files, the extended header's first record) and the subject `MRC` (the format's display name). A `.map` or `.mrc` file that is not MRC keeps the type it has without its name, with the reason in its basis. A crawl reads 213 bytes of such a file at recognition and at most 1024 + 888 at extraction.

Out of scope: Direct Electron acquisitions (`YYYYMMDD_NNNNN_movie.mrc`, `_final.mrc` with their `_info.txt` and the rest: one dataset of a planned format `em/de`, decision 302, pending, with a priority above em/mrc's 61; `/docs/research/direct-electron-files.md`); the extended header's further records and the other extended header types (`CCP4`, `SERI`, `AGAR`, `MRCO`, `HDF5`); grouping with `.xml`, `.jpg`, `.mdoc`, `.rawtlt`, `.star`; MRCZ (compressed); `.st`, `.ali`, `.rec` (IMOD's other names for MRC files; not in the tree's listing; recognised by their content anyway: an MRC file named `.st`, `.ali`, `.rec` or `.preali` is a dataset of `em/mrc` with all installed collections, checked with `modama-crawler records --verbose` on 2026-11-13).

## Capabilities

### New Capabilities
- `formats/mrc`: recognition and extraction of MRC files.

### Modified Capabilities
None.

## Impact

- `python/modama-formats-em/`: the subpackage, one import and one `PARTS` entry in `__init__.py`, a README row, `pyproject.toml`'s dependency.
- The search stack's crawler and browse images need a rebuild for the new dependency.
- No migration; the extractor identity changes with the installation, as with every code change.
