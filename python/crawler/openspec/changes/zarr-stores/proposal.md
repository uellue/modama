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

(With Q5 as main leans, the `data.chunks` and `data.compressor.id` lines go, as `.hspy` has none.)

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

Each store's metadata files are read once per crawl in which its top-level listing changed, when the spot check picks it, and once after this change (the new rule set and extractor identity).

## Assumptions and leans (main's leans, reviewed; Q1–Q6 with @weber)

- **A1** Collapse formats in `pydata`, above the core's: as above. Deviation from main's lean: a v2 store is recognised by `.zgroup` or `.zarray` only, as the core does, not by `.zattrs` alone, which the Zarr v2 spec allows only next to one of them; otherwise the core and `common` would disagree about which folders are stores.
- **A2** `.zspy` by name *and* content (root attributes `file_format: ZSpy`; first written here as `HyperSpy`, corrected from RosettaSciIO's source before the review), as `.hspy` (name plus `HyperSpy` in the first 4 KiB); a `.zspy` store without them is a `common/zarr` store, and a HyperSpy store named `.zarr` keeps `application/x-zarr` with HyperSpy's skip list and summary, as an older HyperSpy `.hdf5` file does. `application/x.zspy`: no type in use was found (Debian's `/etc/mime.types`, shared-mime-info, RosettaSciIO's documentation).
- **A3** The reader is Python's `json` on the metadata files, per the Zarr v2 and v3 specifications, not zarr-python (`design.md`, D1, measured): zarr-python reads only metadata files (good), but follows a symlink in the store to a folder outside it and puts that folder's attributes into the result, and fails the whole listing of a group when one array has a codec or data type it does not know (`imagecodecs_jpeg2k`, a v3 extension type). zarr-python stays a test dependency (it writes the fixtures), no new runtime dependency. This deviates from decision 265, which names zarr as an established reader: for @weber (Q6); if agreed, a decision-log row and the zarr-python behaviours in BACKLOG "Sync with upstream".
- **A4** Nothing is read from outside the store: every name below the anchor is first looked at with `lstat` relative to its open parent folder (`os.stat(name, dir_fd=…, follow_symlinks=False)`), only a folder or a regular file is opened, relative to its parent and with `O_NOFOLLOW`, and the open file is confirmed with `fstat` (the same inode, a regular file), as the walk does (`walk.py`, `_stat`); a symlink, a FIFO named `.zattrs` or a device is neither opened nor read.
- **A5** Bounded as the HDF5 walk (1,000 entries, 5,000 nodes, a third of the extractor's time limit), plus bytes: a metadata file over 1 MiB is not read (named in `mapped_metadata.not_read`), and the walk stops after 16 MiB read. A group's listing follows the HDF5 walk's room rule (`hdf5.py`, `hard_links`): it is read until it holds one name more than the nodes the walk still has room for (`5000 −` nodes walked), then walked in name order. Nodes below depth 100 are not walked (the path of the group at depth 100 in `mapped_metadata.too_deep`): a chain of thousands of nested groups would otherwise exhaust Python's stack or the open folders' file descriptors, one per level (the nodes of the real stores are at most 9 levels deep, `Experiments/__unnamed__/metadata/_HyperSpy/_sig_navigator/metadata/General/FileIO/0`).
- **A6** Skip list of the Zarr walk: `zarr_format` of every node but the root and nested stores of another version than the root's (the root's is kept in `original_metadata`), each node's `node_type`, v3's `consolidated_metadata` (a copy of the nodes' documents), and what `textual` and `credential` refuse; HyperSpy's in addition for a HyperSpy store. Everything else of a node's document is kept (`fill_value`, `order`, `filters`, `dimension_separator`, `chunk_key_encoding`, `storage_transformers`, `dimension_names`); whether a `.zspy` store's arrays keep these storage parameters is Q5.
- **A7** Members: none, as now (a collapsed dataset). This deviates from the rule that an extractor reads its dataset's members only (`formats/__init__.py`, `Format.extract`; TEMPLATE.md, "Extracting metadata"): the extractor of a collapsed dataset reads metadata files below its anchor, which the spec and TEMPLATE.md say. The stamp of a collapsed dataset is its folder's listing digest (`walk.py`, "the D3 limit for collapsed trees"), which covers the top-level metadata files and the subfolders' times. A metadata file rewritten by rename (zarr-python's writes) changes the mtime of its own folder only, so the stamp sees it for nodes at depth 1; a deeper one, or one written in place, is extracted again only by the spot check (20 reused datasets per format and crawl, `extraction.SAMPLE`, decision 258), where the store then shows as a spot-check difference, or after an installation change. Q3.
- **A8** A node whose metadata file is not a JSON object, or is nested too deeply to parse or flatten (`RecursionError`, `MemoryError`), is left out with everything below it, its path in `mapped_metadata.unreadable`; an unreadable root fails the extraction (a warning, retried next crawl), as the core warns at a corrupt `zarr.json`.
- **A9** Fixtures: a `.zspy` written once by RosettaSciIO 0.15.0's zspy writer (it needs `zarr<3`, which cannot share a venv with the crawler's test dependency on zarr 3; installed as `rosettasciio[zspy,hspy]==0.15.0`, since the writer imports h5py, which the extra `zspy` does not bring) from a signal dictionary shaped like pyxem's (signal type `electron_diffraction`, made-up original metadata with an entry nobody has seen; the keys `package_info`, `learning_results`, `attributes` and `models` the writer requires), with `consolidate=False` as the real stores have no `.zmetadata` (RosettaSciIO's default writes one), committed with its generator script and the sha256 of each file in `fixtures.toml` (the writer is deterministic); plain stores, v2 and v3 (abTEM-like attributes rebuilt with made-up values), a nested store, a store with `.zmetadata`, and the reproducers generated at test time with zarr-python. The staging sample is never copied.
- **A10** `.ipynb_checkpoints/` inside a store (the staging sample has one): the store's collapse covers it (the walk never enters the store), and the extractor enters only subfolders with a Zarr metadata file, so it is neither listed nor read.

## Questions

Numbered for @weber as 317–320, 322 and 323.

- **Q1 (317)** The type of `.zspy` stores: `application/x.zspy`, displayed "HyperSpy Zarr store" (lean; the reviewer agrees), or the core's `application/x-zarr` with HyperSpy in the subject only? For: as `.hspy`, a search and the record name the format. Against: one more type that only we use.
- **Q2 (318)** The summary line of a plain store: shape and data type of the first array, as found (lean; the reviewer agrees: 131 of 132 stores are v2, so it reads `<f4`). abTEM's `metadata0.type`, `energy`, `semiangle_cutoff` are in the `name: value` lines and searchable there; an abTEM format of its own that puts them into the summary is a later change (lean). Against: 127 of 132 stores are abTEM's, so the summary is the same few words for all of them now.
- **Q3 (319)** Nested metadata changes (A7): accept the limit, the spot check catching them over time (my lean), or make the stamp cover every group's metadata files (main's lean: a listing of each group at crawl time, about the cost of the walk itself, against the walk's rule that a collapsed folder's content is not listed). Against accepting: an edited `.zattrs` deeper than one level stays stale until the spot check picks the store.
- **Q4 (320, changed by the review)** The bounds (A5): 1 MiB per file and 16 MiB per store (lean; the reviewer agrees), the listing by the HDF5 walk's room rule instead of 10,000 names, and a depth of 100 levels (new, review finding 3). Against: three more numbers; the largest metadata file in the listing is 3.4 KiB, the deepest node 9 levels down.
- **Q5 (322, review finding 1)** A `.zspy` store's arrays give a dozen lines each (`chunks`, `compressor.*`, `dimension_separator`, `fill_value`, `filters`, `order`, …) where the same signal in `.hspy` gives two (`shape`, `dtype`), and RosettaSciIO stores many metadata lists as such arrays; so D3's "the same names as `.hspy`" holds for the names, not for the number of lines. Main's lean: the storage parameters on the ZSpy skip list, so that `.zspy` and `.hspy` give the same lines, and kept for a plain `.zarr`. Against: a skip list that differs by writer, and the compressor of a `.zspy` is what the file says.
- **Q6 (323, review finding 5)** Reading the JSON ourselves (A3) instead of zarr-python, which decision 265 names. Main's lean and mine: yes, with a decision-log row and the zarr-python behaviours in BACKLOG "Sync with upstream". Against: a reader of our own for a format with an established library; the Zarr specifications make it a JSON document per node, which keeps it small.

## Out of scope

Reading chunks; reading `.zmetadata` (consolidated v2 metadata: no store in the listing has one, RosettaSciIO writes one by default; the walk of the nodes is authoritative, and a `.zmetadata` is neither read nor described); a `.zspy` written into a ZIP (one file in the listing; it keeps the core's type); OME-Zarr and abTEM as formats of their own; Zarr in other stores (S3, ZIP); `modama-chain browse`'s view of a store's folder (another change).

## Capabilities

### New Capabilities
- `formats/pydata-zarr`: recognition and metadata extraction of Zarr stores and HyperSpy's `.zspy` stores in the `pydata` area (to join `formats/pydata` when both are archived).

## Impact

`python/modama-formats-common/src/modama_formats_common/pydata/`: `zarrstore.py` (the walk), two formats in `__init__.py`, HyperSpy's skip list moved from `hdf5.py` to `values.py` (its second user), fixtures and tests; README rows; `zarr` pinned in the package's `[test]` extra. `python/crawler/BACKLOG.md`: "Zarr attributes" replaced by the limit of A7. `python/crawler/src/modama_crawler/formats/TEMPLATE.md`: the extractor of a collapsed dataset (A7). No change to the crawler's code. The crawler's own CLI tests that name `zarr/zarr` as the format of a store (`tests/test_cli.py`) run with every installed collection, so with `common` installed the store is `common/zarr`'s: they are to name the format independently of what else is installed.

## Review (independent, of a1536f48 with the ZSpy correction)

Applied to the proposal, design, spec and tasks (findings by number): (2) RosettaSciIO's default `.zmetadata`: the fixture without it, a generated case with it, a scenario; (3) deep nesting: per node `RecursionError` and `MemoryError` as unreadable, the walk's depth bounded at 100 (A5), a scenario; (4) the stamp limit restated with the spot check and the depth-1 rule, the members-only deviation named (A7); (6) `lstat` before open, `fstat` after (A4); (7) scenarios for an unknown codec and data type, a `.zattrs` symlink, `zarr.json` beside `.zgroup`, a ZSpy store named `.zarr`, the byte limit and the room rule, a root document over 1 MiB, deep nesting, `.zmetadata`; (8) bytes by `rchar` against the metadata files' sizes; (9) `ZSpy` in the tasks, the writer's install and dictionary keys, sha256 in the manifest; (10) the root's `zarr_format` kept; (11) the room rule instead of 10,000 names; (12) the counts of groups in design.md. To @weber: (1) as Q5, (5) as Q6.
