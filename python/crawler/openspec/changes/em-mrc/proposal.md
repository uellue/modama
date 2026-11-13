# Proposal

## Why

MRC files (cryo-EM maps, tomograms and image stacks: `.mrc`, `.map`, `.mrcs`) are not covered: today each becomes a single-file dataset of no known type, findable only by its path. Request (hallway test of 2026-11-13, task (a)): a format for MRC files, read with `mrcfile`, the field's reader. Serves R15 (extract from content), R30 (findable by what the data is), decisions 230 and 234 and the skip-list rule of 2026-11-12.

## The person's answers (skill step 1, 2026-11-13, through the main session)

- Files: maps (`.map`, `.mrc`) from processing and deposition, image stacks (`.mrcs`) from collection and processing software. Program versions unknown.
- Each file is one dataset; grouping with `.mdoc`, `.star` and the like is later.
- `mrcfile` is approved as the reader; pin the current release with its reason.
- A person looks at the dimensions, the mode (data type), the cell and sampling as the header writes them, whether it is an image stack or a volume, and the labels.
- Nothing private or a GUI setting is known. Labels can hold user names and paths: they are what the file says; the credential check applies.
- `.map` is used by other programs (source maps, linker maps).
- No real files can be given: public files or files written with `mrcfile`.

## Assumptions and leans (put to the person before the code)

- **Type**: no established MIME type for MRC exists (none in the vendored shared-mime-info; Debian's `media-types` gives `*.mrc` to `application/marc`, library catalogue records), so the unofficial `application/x.mrc`, with the globs `*.mrc`, `*.mrcs`, `*.map` and a magic rule: `MAP` at byte 208 (the map word; `mrcfile` checks its first three bytes) and the machine stamp's first byte `0x44` (little-endian) or `0x11` (big-endian) at byte 212. One format, `em/mrc`, for all three names: the header says whether a file is an image, a stack or a volume.
- **Content check for every name**: a file named like an MRC file without `MAP` at byte 208 is not MRC and gets the type it has without its name (change `recognition-checks-content`). Against: MRC files written before the map word (MRC2000) lose their extraction; none are known here.
- **Extended header left out** (the person agreed): only the 1024-byte main header is read. FEI/EPU extended headers (`exttyp` `FEI1`, `FEI2`) are hundreds of kB.
- **Program versions unknown**: the format follows MRC2014 as `mrcfile` reads it; no program-specific rules.
- **original_metadata**: every field of the main header, under `mrcfile`'s field names, flat (`cella.x`, `cellb.alpha`, `origin.z`, `label[1]` to `label[10]`, from 1 as in `common/structured`), values as found: numbers as `mrcfile` gives them, text fields with their padding (trailing spaces and NULs) removed, the machine stamp as `mrcfile` prints it (`0x44 0x41 0x00 0x00`). Skip list: `extra1`, `extra2` (unused space). Empty labels kept as empty text (decision 161). Credentials in labels left out (`modama_crawler.formats.values.credential`).
- **mapped_metadata**: what `mrcfile` computes: `data_type` (from `mode`), `voxel_size` (cell over sampling), `kind` (`image`, `image stack`, `volume`, `volume stack`).
- **The summary line**: `nx`, `ny`, `nz`, `mode`, `ispg`, `cella.x/y/z`, `mx/my/mz` as `name value`, then the first label bare. A cell length or sampling of 0 is a placeholder and left out; `mode` and `ispg` are codes where 0 is a value (8-bit; image stack) and are kept.
- **Reader warnings** (a machine stamp `mrcfile` does not know, a missing map word) are logged as warnings of the extraction, as Merlin does for a date; the file is read in `mrcfile`'s permissive mode.

## What Changes

- New area `mrc` of `modama-formats-em` (`src/modama_formats_em/mrc/`): format `em/mrc`, `mrc.xml` with `application/x.mrc`, fixtures (EMDB's EMD-3197 from `mrcfile`'s test data, CC0; files written by `mrcfile` at test time) and tests.
- New dependency of `modama-formats-em`: `mrcfile==1.5.4` (BSD-3-Clause, pure Python, requires numpy).

Behaviour towards the user: a harvester and a searcher see records of `.mrc`, `.mrcs` and `.map` files with the MRC header as a description (summary line and the second description with the header's fields) and the subject `MRC` (the format's display name). A `.map` or `.mrc` file that is not MRC keeps the type it has without its name, with the reason in its basis. A crawl reads 213 bytes of such a file at recognition and 1024 at extraction.

Out of scope: the extended header; grouping with `.mdoc`, `.rawtlt`, `.star`; MRCZ (compressed); `.st`, `.ali`, `.rec` (IMOD's other names for MRC files): none asked for.

## Capabilities

### New Capabilities
- `formats/mrc`: recognition and extraction of MRC files.

### Modified Capabilities
None.

## Impact

- `python/modama-formats-em/`: the subpackage, one import and one `PARTS` entry in `__init__.py`, a README row, `pyproject.toml`'s dependency.
- No migration; the extractor identity changes with the installation, as with every code change.
