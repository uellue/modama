# Proposal

## Why

@weber, 2026-11-13: "/storage/er-c-data/adhoc/livespedescan/DPC/d001_scans/001_LMSTEM_x15k_512x512_5_10msExp_100msFB_nopres.zspy — That is a HyperSpy (or more precise, pyxem) 4D STEM dataset in Zarr format. It should be recognized as one dataset, and the anchor is this path. … The stored record has very little info". Open item 245a and BACKLOG "Zarr attributes": the core's `zarr/zarr` collapses a store into one dataset without an extractor, and the extractor belongs to the format that produced the dataset (`Extraction.extractor` is the format id; `common-pydata`, A3), so nothing describes a store today. The October listing has 132 `.zarr` and 4 `.zspy` stores, all but one Zarr v2 (`.zgroup`, `.zattrs`, `.zarray`; no `.zmetadata`), one v3 (abTEM's `to_zarr`, `zarr.json`); 127 `.zarr` are abTEM 4D-STEM simulations under `adhoc/mpx3/simulation/` (a group with `array0`, root attributes of 2 KiB), 5 are nested in another store. Serves R11 (collapse, kept), R30 (findable by what the data is), R21 (formats outside the core).

I read the named `.zspy` as an example of a rule: every Zarr store, HyperSpy's or not, becomes one described dataset.

## What Changes

The `pydata` area of `modama-formats-common` gets two collapse formats with an extractor:

- **`common/zspy`** (`application/x.zspy`, "HyperSpy Zarr store"): a directory named `*.zspy` that is a Zarr store (the core's markers) and whose root attributes say `file_format` `ZSpy` (RosettaSciIO's zspy writer, `rsciio/zspy/_api.py`; the root `.zattrs` of the four real stores has the 63 bytes that value gives); priority 82.
- **`common/zarr`** (`application/x-zarr`, the core's type): any other Zarr store, recognised exactly as the core's `zarr/zarr` recognises it (same markers, basis and warnings); priority 81, so both run before the core's (80). Without `common` installed, the core's format collapses stores as today.
- **Extraction** (both): a walk of the store's metadata files only (v2 `.zgroup`, `.zarray`, `.zattrs`; v3 `zarr.json`), never a chunk, never a listing of an array's directory. As flat dotted names, as the HDF5 walk names them: each node's attributes (`Experiments.__unnamed__.metadata.General.title`), each array's metadata document as found (`data.shape`, `data.chunks`, `data.dtype`, `data.compressor.id`; v3 `array0.data_type`, `array0.codecs[2].name`); a nested store is a node of the outer one. HyperSpy's skip list as for `.hspy` (`_HyperSpy`, `_None_`) for a store whose root says `ZSpy`, whatever its name.
- **Summary line**: HyperSpy's as for `.hspy` (signal title, signal type, data shape); otherwise the shape and data type of the root array, or of the first array one level down.

## Behaviour towards the user

A `.zspy` store's record gets the type and subject "HyperSpy Zarr store" instead of "Zarr", a summary line and the `name: value` lines of its metadata; a `.zarr` store keeps its type and gets a summary line and its metadata lines. Example, the layout of @weber's `.zspy` (values made up):

```
summary:  4D-STEM scan, electron_diffraction, shape [512, 512, 256, 256]
subject:  HyperSpy Zarr store; electron_diffraction
Experiments.__unnamed__.axis-0.name: x
Experiments.__unnamed__.axis-0.scale: 1.5
Experiments.__unnamed__.axis-0.units: nm
Experiments.__unnamed__.data.chunks: [32, 32, 256, 256]
Experiments.__unnamed__.data.compressor.id: blosc
Experiments.__unnamed__.data.dtype: <u2
Experiments.__unnamed__.metadata.General.title: 4D-STEM scan
Experiments.__unnamed__.original_metadata.Acquisition_parameters.camera_length.value: 120
file_format: ZSpy
file_format_version: 3.3
zarr_format: 2
```

(The `data.chunks` and `data.compressor.id` lines stay, though `.hspy` has none: Q5, 322.)

An abTEM simulation, `.zarr` v3, the layout of the staging sample (values made up):

```
summary:  shape [64, 64, 128, 128], float32
array0.chunk_grid.configuration.chunk_shape: [64, 64, 128, 128]
array0.codecs[2].name: zstd
array0.data_type: float32
metadata0.axes.axis_0.sampling: 0.1
metadata0.axes.axis_0.units: Å
metadata0.data_origin: abTEM_v1.0.10
metadata0.energy: 300000.0
metadata0.semiangle_cutoff: 20
metadata0.type: DiffractionPatterns
zarr_format: 3
```

Each store's metadata files are looked at with `lstat` at every crawl (a v3 node's `zarr.json` read for its node type) and read whole once per crawl in which one of them changed, when the spot check picks the store, and once after this change (the new rule set and extractor identity).

## Assumptions and leans (main's leans, reviewed; Q1–Q6 answered by @weber, 2026-11-13)

- **A1** Collapse formats in `pydata`, above the core's: as above. Deviation from main's lean: a v2 store is recognised by `.zgroup` or `.zarray` only, as the core does, not by `.zattrs` alone, which the Zarr v2 spec allows only next to one of them; otherwise the core and `common` would disagree about which folders are stores.
- **A2** `.zspy` by name *and* content (root attributes `file_format: ZSpy`; first written here as `HyperSpy`, corrected from RosettaSciIO's source before the review), as `.hspy` (name plus `HyperSpy` in the first 4 KiB); a `.zspy` store without them is a `common/zarr` store, and a HyperSpy store named `.zarr` keeps `application/x-zarr` with HyperSpy's skip list and summary, as an older HyperSpy `.hdf5` file does. `application/x.zspy`: no type in use was found (Debian's `/etc/mime.types`, shared-mime-info, RosettaSciIO's documentation).
- **A3** The reader is Python's `json` on the metadata files, per the Zarr v2 and v3 specifications, not zarr-python (`design.md`, D1, measured): zarr-python reads only metadata files (good), but follows a symlink in the store to a folder outside it and puts that folder's attributes into the result, and fails the whole listing of a group when one array has a codec or data type it does not know (`imagecodecs_jpeg2k`, a v3 extension type). zarr-python stays a test dependency (it writes the fixtures), no new runtime dependency. This deviates from decision 265, which names zarr as an established reader: decided by @weber (Q6, 323), with its reasons in the code and in design D1 and a decision-log row of its own; reporting upstream is main's, separately.
- **A4** Nothing is read from outside the store: every name below the anchor is first looked at with `lstat` relative to its open parent folder (`os.stat(name, dir_fd=…, follow_symlinks=False)`), only a folder or a regular file is opened, relative to its parent and with `O_NOFOLLOW`, and the open file is confirmed with `fstat` (the same inode, a regular file), as the walk does (`walk.py`, `_stat`); a symlink, a FIFO named `.zattrs` or a device is neither opened nor read.
- **A5** (Q4, 320: "Yes sounds reasonable") Bounded as the HDF5 walk (1,000 entries, 5,000 nodes, a third of the extractor's time limit), plus bytes: a metadata file over 1 MiB is not read (named in `mapped_metadata.not_read`), and the walk stops after 16 MiB read. A group's listing follows the HDF5 walk's room rule (`hdf5.py`, `hard_links`): it is read until it holds one name more than the nodes the walk still has room for (`5000 −` nodes walked), then walked in name order. Nodes below depth 100 are not walked (the path of the group at depth 100 in `mapped_metadata.too_deep`): a chain of thousands of nested groups would otherwise exhaust Python's stack or the open folders' file descriptors, one per level (the nodes of the real stores are at most 9 levels deep, `Experiments/__unnamed__/metadata/_HyperSpy/_sig_navigator/metadata/General/FileIO/0`).
- **A6** Skip list of the Zarr walk: `zarr_format` of every node but the root and nested stores of another version than the root's (the root's is kept in `original_metadata`), each node's `node_type`, v3's `consolidated_metadata` (a copy of the nodes' documents), and what `textual` and `credential` refuse; HyperSpy's in addition for a HyperSpy store. Everything else of a node's document is kept (`fill_value`, `order`, `filters`, `dimension_separator`, `chunk_key_encoding`, `storage_transformers`, `dimension_names`), in a `.zspy` store too (Q5, 322: @weber, "the additional info is valuable").
- **A7** Members: none, as now (a collapsed dataset). This deviates from the rule that an extractor reads its dataset's members only (`formats/__init__.py`, `Format.extract`; TEMPLATE.md, "Extracting metadata"): the extractor of a collapsed dataset reads metadata files below its anchor, which the spec and TEMPLATE.md say. The stamp (Q3, 319: "Yes, let's include the metadata files in checking for changes"): a collapsed dataset's stamp was its folder's listing digest alone (`walk.py`, "the D3 limit for collapsed trees"), which missed a metadata file rewritten in place, or by rename below the store's first level (a rename changes only its own folder's time). Now a format may give a digest of what its extractor reads below the folder, `Format.collapsed_state(path)`, which the walk folds into the stamp at every crawl, also for a folder taken over with an unchanged listing (a core change of about 20 lines in `formats/__init__.py` and `walk.py`, with a test of its own, `tests/test_walk.py::test_a_file_deep_below_a_collapsed_directory_changes`; spec `crawl`). `common/zarr`'s digest covers the name, size and times of every metadata file of the nodes its extractor walks, found by `lstat`, listing only groups' folders as the extractor does, and reading a v3 node's `zarr.json` (bounded as A5) for its node type so that an array's folder is never listed; no chunk. The limit "stale until the spot check" is gone.
- **A8** A node whose metadata file is not a JSON object, or is nested too deeply to parse or flatten (`RecursionError`, `MemoryError`), is left out with everything below it, its path in `mapped_metadata.unreadable`; an unreadable root fails the extraction (a warning, retried next crawl), as the core warns at a corrupt `zarr.json`.
- **A9** Fixtures: a `.zspy` written once by RosettaSciIO 0.15.0's zspy writer (it needs `zarr<3`, which cannot share a venv with the crawler's test dependency on zarr 3; installed as `rosettasciio[zspy,hdf5]==0.15.0`, since the writer imports h5py, which the extra `zspy` does not bring; the review's `hspy` is no extra of 0.15.0) from a signal dictionary shaped like pyxem's (signal type `electron_diffraction`, made-up original metadata with an entry nobody has seen; the keys `package_info`, `learning_results`, `attributes` and `models` the writer requires), with `consolidate=False` as the real stores have no `.zmetadata` (RosettaSciIO's default writes one), committed with its generator script and the sha256 of its tree in `fixtures.toml` (the writer is deterministic: written twice, identical); plain stores, v2 and v3 (abTEM-like attributes rebuilt with made-up values), a nested store, a store with `.zmetadata`, and the reproducers generated at test time with zarr-python. The staging sample is never copied.
- **A10** `.ipynb_checkpoints/` inside a store (the staging sample has one): the store's collapse covers it (the walk never enters the store), and the extractor enters only subfolders with a Zarr metadata file, so it is neither listed nor read.

## Questions

Numbered for @weber as 317–320, 322 and 323.

- **Q1 (317)** The type of `.zspy` stores: `application/x.zspy`, displayed "HyperSpy Zarr store" (lean; the reviewer agrees), or the core's `application/x-zarr` with HyperSpy in the subject only? **Answered**: "Own type, it is pretty distinct": `application/x.zspy`.
- **Q2 (318)** The summary line of a plain store: shape and data type of the first array, as found (lean; the reviewer agrees: 131 of 132 stores are v2, so it reads `<f4`). abTEM's `metadata0.type`, `energy`, `semiangle_cutoff` are in the `name: value` lines and searchable there; an abTEM format of its own is a later change. **Answered**: "yes, let's go with that, and make a note to look for specific zarr subtypes other than zspy that are common": BACKLOG "Zarr subtypes beyond ZSpy".
- **Q3 (319)** Nested metadata changes (A7): accept the limit, the spot check catching them over time (my lean), or make the stamp cover every group's metadata files (main's lean). **Answered**: "Yes, let's include the metadata files in checking for changes" (A7).
- **Q4 (320, changed by the review)** The bounds (A5): 1 MiB per file and 16 MiB per store, the listing by the HDF5 walk's room rule instead of 10,000 names, and a depth of 100 levels. **Answered**: "Yes sounds reasonable".
- **Q5 (322, review finding 1)** A `.zspy` store's arrays give a dozen lines each (`chunks`, `compressor.*`, `dimension_separator`, `fill_value`, `filters`, `order`, …) where the same signal in `.hspy` gives two (`shape`, `dtype`), and RosettaSciIO stores many metadata lists as such arrays; so D3's "the same names as `.hspy`" holds for the names, not for the number of lines. Main's lean was the storage parameters on the ZSpy skip list. **Answered** (@weber, 2026-11-13): keep them, "the additional info is valuable"; nothing goes on the skip list for this, and D3 says that a `.zspy` gives more lines than `.hspy`. Decision-log row.
- **Q6 (323, review finding 5)** Reading the JSON ourselves (A3) instead of zarr-python, which decision 265 names. **Answered** (@weber, 2026-11-13): read the metadata JSON ourselves, with a note in the code and the design saying why (the symlinked group, the unknown codec or v3 data type), and a decision-log row; upstream reporting is handled separately by main.

## Out of scope

Reading chunks; reading `.zmetadata` (consolidated v2 metadata: no store in the listing has one, RosettaSciIO writes one by default; the walk of the nodes is authoritative, and a `.zmetadata` is neither read nor described); a `.zspy` written into a ZIP (one file in the listing; it keeps the core's type); OME-Zarr and abTEM as formats of their own; Zarr in other stores (S3, ZIP); `modama-chain browse`'s view of a store's folder (another change).

## Capabilities

### New Capabilities
- `formats/pydata-zarr`: recognition and metadata extraction of Zarr stores and HyperSpy's `.zspy` stores in the `pydata` area (to join `formats/pydata` when both are archived).

### Modified Capabilities
- `crawl`: a collapsed directory is stamped with what its format reads below it (319).

## Impact

`python/modama-formats-common/src/modama_formats_common/pydata/`: `zarrstore.py` (the walk), two formats in `__init__.py`, HyperSpy's skip list moved from `hdf5.py` to `values.py` (its second user), fixtures and tests; README rows; `zarr` pinned in the package's `[test]` extra. `python/crawler/BACKLOG.md`: "Zarr attributes" replaced by "Zarr subtypes beyond ZSpy" (318); zarr-python under "Sync with upstream" (323). `python/crawler/src/modama_crawler/formats/TEMPLATE.md` and `README.md`: the extractor and the stamp of a collapsed dataset (A7). `python/crawler/design/architecture.md`: decision-log rows (319, 322, 323). The crawler's code: `Format.collapsed_state` and the walk's `_stamped` (A7, 319), with a test and a delta of spec `crawl`. The crawler's own CLI tests that named `zarr/zarr` as the format of a store (`tests/test_cli.py`) ran with every installed collection, so with `common` installed the store is `common/zarr`'s: they name the format independently of what else is installed (task 3.2).

## Review (independent, of a1536f48 with the ZSpy correction)

Applied to the proposal, design, spec and tasks (findings by number): (2) RosettaSciIO's default `.zmetadata`: the fixture without it, a generated case with it, a scenario; (3) deep nesting: per node `RecursionError` and `MemoryError` as unreadable, the walk's depth bounded at 100 (A5), a scenario; (4) the stamp limit restated with the spot check and the depth-1 rule, the members-only deviation named (A7); (6) `lstat` before open, `fstat` after (A4); (7) scenarios for an unknown codec and data type, a `.zattrs` symlink, `zarr.json` beside `.zgroup`, a ZSpy store named `.zarr`, the byte limit and the room rule, a root document over 1 MiB, deep nesting, `.zmetadata`; (8) bytes by `rchar` against the metadata files' sizes; (9) `ZSpy` in the tasks, the writer's install and dictionary keys, sha256 in the manifest; (10) the root's `zarr_format` kept; (11) the room rule instead of 10,000 names; (12) the counts of groups in design.md. To @weber: (1) as Q5, (5) as Q6.

## Code review (of the build, "merge after changes")

Applied, each with a test that failed first: (M1) a failing `collapsed_state` is a warning naming the format, the stamp a fixed marker (`test_a_failing_collapsed_state`); (S1) the summary's shape and data type from the same array's document, not from any two-part name (`test_attributes_named_like_an_arrays`); (S2) the stamp's walk bounded by counts only (`test_the_stamp_of_a_walk_cut_by_its_time`); (S3) refused names in `unreadable` and the stamp, other errors fail (`test_a_subgroup_the_crawler_may_not_read`, `test_an_input_output_error_in_the_store`); (S4) the bytes-read helper of the pydata tests takes off its own read of `/proc/self/io` exactly, no margin (`test_bytes_read_when_the_counter_gains_a_digit`; 200,000 back-to-back reads: the counter grew by exactly the size of the read before, every time); nits: a file that grew while read is not read, an object `zarr_format` kept as found, `numcodecs` pinned. Noted in BACKLOG: a collapsed part whose stamp changes under an unchanged listing.
