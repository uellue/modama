# Proposal

## Why

Direct Electron's camera server, DE-Server (DE-16, DE-64, Apollo, Celeritas and others), gives each acquisition a *Dataset Name* `YYYYMMDD_NNNNN` and writes every file of it into one folder under that prefix: `_info.txt` (every server property as `key = value`), the frame stack `_movie.mrc` (or `.de5`, `.tif`, `.hspy`), the sum `_final.mrc`, virtual and external detector images, `_scan_coordinates.csv` (research of 2026-11-13, `/docs/research/direct-electron-files.md`). Today the crawler indexes each of these as an unrelated single file, and the one file that says what was acquired, the `_info.txt`, as plain text. @weber, from a browse snapshot of the tree's one DE acquisition (`20200821_92978_info.txt`, `_movie.mrc`, `_processing.log`, in LiberTEM's test data): "In that case the three become one dataset"; decision 302 (2026-11-13): "Yes, sounds good like this! Let's also look if RosettaSciIO picks up all interesting info or if we learn sth from the log, info.txt and any headers present in the actual MRC file that helps with indexing and search". Serves R30 (findable by what the data is: camera, voltage, exposure, scan), R31 and R22 (an acquisition's files as one dataset rather than stray files), R25 (honest types), R15 (metadata from content), decisions 129, 230, 235 and the skip-list rule of 2026-11-12.

The comparison decision 302 asks for is in `design.md`, D1. Its result in short: **RosettaSciIO 0.15.0 keeps every entry of the `_info.txt` as found** (its `original_metadata.de_metadata`, identical to a plain `key = value` parse on all five public files), but **its mapping is thin and partly wrong**: every value stays a string, every axis scale is set to 1 (the pixel sizes are lost), units are assigned that the file does not state (`nm^-1` for `Diffraction Pixel Size`), the electron gain is read from a key that DE-Server 2.7.4 no longer writes, voltage, exposure time, dose rate, processing mode, software version and Dataset Name are not mapped at all, and for a scan that is not a raster (`XY File`, `Random`) it raises unless it is handed the whole scan coordinate file. Reading the movie, it also reads every virtual and external image whole, and names them crosswise. **The movie's MRC header adds nothing to search** that the `_info.txt` lacks (DE writes no labels and no extended header, an uncalibrated cell of −10 × the size, statistics not computed). **The `_processing.log`** is not documented anywhere public; its content is pending @weber's copy (Q4).

## The person's answers (skill step 1)

From decision 302, the research and the brief of 2026-11-13, through the main session:

- Files: written by DE-Server, version unknown for the tree's 2020 acquisition (82 lines, 2,778 bytes, against 252 to 552 lines in 2023 to 2025); public files of DE-Server 2.7.2, 2.7.4 and 2.7.5 in RosettaSciIO's test data.
- Belonging together: the files sharing the prefix in one folder; "the three become one dataset" (302). Read as an example of the rule "an acquisition's files are one dataset", not only of the three names.
- Reader: RosettaSciIO (HyperSpy) reads the `_info.txt` with the movie; LiberTEM ignores it (issue #1675).
- What a search should find: the comparison is to say (302). My reading: camera, processing mode, voltage, exposure, frame rate, scan size, date; the rest in the values.
- Private or GUI settings: none named. The file holds the server's computer name, IP address and configuration paths; they are what the file says (as MRC labels in `em-mrc`, Q-297 there), the credential check applies.
- Names that lie: the tree holds many files named `YYYYMMDD_HHMM[SS]_…` that are not DE's (other programs' exports such as `20240619_1736_HAADF_STEM_4.00_Mx HAADF.mrc`, photos `20220818_140228_Cancellation_ON.png`; 508 names of this form in the private listing of 2026-10-15, one DE acquisition among them). So a prefix alone must never group files: only a DE `_info.txt` does.

## Assumptions and leans (to agree before the code)

- **One dataset per acquisition, anchored at its `_info.txt`** (as Merlin and K2IS are anchored at their header): the `_info.txt` is what makes an acquisition recognisable and what says what it is; an acquisition saved without a movie (`Autosave Movie = Discard`) is still one. Members: every file of the folder whose name starts with the `_info.txt`'s stem, its name without `info.txt` (`20241021_00405_`), whatever follows: movies of any format and number (`_movie.mrc`, `_0_movie.mrc`, `_movie.de5`), `_final.mrc`, `_ext1_….mrc`, `_0_….mrc`, `_scan_coordinates.csv`, `_processing.log` and names nobody has seen. A user-set `Autosave Filename Suffix` sits between the number and the kind (`20241021_00405_sampleA_info.txt`), so it is part of the stem; stems that nest belong to the longest (Merlin's rule).
- **Recognition**: the name by a glob, `[0-9]{8}_*_info.txt` written as shared-mime-info's `[0-9]` classes, typed `application/x.de-info` (a subclass of `text/plain`); the content by its first line, the key `Server Software Version` at byte 0, 64 bytes read (D3). A file of that name without it gets the type it has without the name (`text/plain`), with the reason in its basis. The `Dataset Name = …` line is checked at extraction, not at recognition: it lies 3.6 to 6.3 kB into the file, and a folder of 200 acquisitions would exceed the directory's byte budget of 1 MiB, which skips the format for the whole folder (D3, Q1).
- **A lone movie** (`_movie.mrc` without its `_info.txt`) is a single file, described by `em/mrc` as any MRC file; no warning: the date prefix is shared by other programs' files, so a "missing info" warning would be false for each of them.
- **A lone `_info.txt`** (the movie on another disk, or discarded) is a dataset of one member, fully described.
- **Older DE-Server versions**: the keys differ between versions (2.7.2 has no `Instrument Accelerating Voltage (V)` and no `Local time`; 2.7.4 has 552 entries, 2.7.2 252). Every entry is kept as found, so nothing depends on a version; the summary line leaves out what a file lacks. The 2020 file's first line decides whether the content check holds for it (Q2).
- **`_processing.log`**: a member, not read (Q4).
- **Values** (D4): every `key = value` line of the `_info.txt` as `original_metadata`, key and value as written without the padding, as text, minus a skip list: option lists that describe the user interface, not the acquisition (`… Allowed Values`, `Preset - List`, `… Preset List`) and the shared checks (not suitable for text, credentials). Empty values kept. RosettaSciIO's mapping as `mapped_metadata`, labelled, from its `read_de_metadata_file` on the `_info.txt` only; for a scan that is not a raster it raises without the coordinates, and then there is no mapped part (Q3).
- **The movie is not read**, not even its header (D1: it adds nothing to search; Q5). No member but the `_info.txt` is read.
- **The summary line**: camera model, processing mode, voltage, exposure time, frame rate, scan type and size (when the scan is enabled), local time, as the file writes them, a number after its key, a text bare, an empty or missing entry left out. For RosettaSciIO's 2.7.4 file: `DESim, Integrating, Instrument Accelerating Voltage (V) 300000, Exposure Time (seconds) 0.045712, Frames Per Second 700, Raster, Scan - Size X 8, Scan - Size Y 4, Mon Oct 21 14:36:50 2024`. Subjects: the camera model.
- **Types** (R25): Debian's lists name none for DE or MRC (D6); so `application/x.de-acquisition` (the dataset, "Direct Electron acquisition", no rules, as `application/x.k2is`) and `application/x.de-info` (the `_info.txt`).
- **Claimed files are hidden from later formats** (D2): the runner offers a format only entries no earlier format has claimed, as the `recognition` spec already says ("SHALL NOT be available to formats that run later"); today it offers them and warns "already claimed" at every crawl. Without this, each DE acquisition would bring a warning from `em/mrc` per MRC member, from `common/text` for the log and from `common/structured` for the CSV, and `em/mrc` would read 213 bytes of each movie at recognition.
- **Priority 62**: above `em/mrc` (60), `em/k2is` (61), and the formats of `common/pydata` at 61, which sort before `em/de` by id and would claim a `_movie.hspy` first.

## What Changes

- New area `de` of `modama-formats-em` (`src/modama_formats_em/de/`): format `em/de`, `de.xml` with the two types, fixtures (RosettaSciIO's public DE files, GPL-3.0; generated reproducers), tests.
- The runner (`modama_crawler.formats.run_post`, `Directory.of_type`): entries claimed by an earlier format are no longer offered to later ones; a format is not called when every entry of its types is claimed.
- No new dependency (RosettaSciIO 0.15.0 is pinned already).

Behaviour towards the user: a DE acquisition becomes one record instead of one per file: type `application/x.de-acquisition`, subject `Direct Electron acquisition` and the camera model, a description that starts with the summary line above, and the `_info.txt`'s entries as its second description. Its files' former single-file records leave the endpoint without a deletion record (none are published yet, `deletedRecord=no`; BACKLOG, "Deleted records"). A file named like a DE `_info.txt` without DE's first line keeps `text/plain`, with the reason in its basis. For every format, the crawl no longer warns "already claimed" when a later format is offered a file an earlier one claimed (it still warns when a format claims such a file by name); no dataset changes by this.

Out of scope: reading the movie (frames, MRC header, a DE5 movie's HDF5 attributes); the scan coordinates; grouping across folders; DE files saved without the date prefix (RosettaSciIO's renamed test files `Custom_*`, `ROI_Random_Scan_*`); a warning for a movie without its `_info.txt`; hiding adopted child datasets from later collection formats (no case).

## Capabilities

### New Capabilities
- `formats/de`: Direct Electron acquisitions recognised as one dataset from their `_info.txt`, with its entries as metadata.

### Modified Capabilities
- `recognition`: claimed entries are not offered to formats that run later; a later claim of a claimed entry is still a warning.

## Impact

- `python/modama-formats-em/`: the subpackage, one import and one `PARTS` entry, a README row, `LICENSE.fixtures` for the RosettaSciIO files.
- `python/crawler/src/modama_crawler/formats/__init__.py` and `tests/test_formats.py`; the `recognition` spec.
- Depends on `em-mrc` only for the "lone movie" scenario's type (`application/x.mrc`); without it, a lone movie is `application/octet-stream`.
- Every format's recognition: fewer warnings, no other change; the extractor identity changes with the installation, as with every merge.

## Questions (numbered for this change; leans applied meanwhile)

- **Q1** Content check: the first line `Server Software Version` (64 bytes; a folder holds 16,384 acquisitions before the budget), or the `Dataset Name = <prefix>` line (up to 8 KiB; 128 acquisitions)? Lean: the first line, and `Dataset Name` checked at extraction (a warning when it differs from the name). Against: the first line says "DE-Server", not "this acquisition"; a renamed `_info.txt` is grouped by its name.
- **Q2** The 2020 file: does it start with `Server Software Version`, and has it `Dataset Name`? Lean: if not, the check takes the first key of that version too, from the file. Needs @weber's copy (`.claude/field-tests/samples/20200821_92978_info.txt`); not there at the time of writing.
- **Q3** RosettaSciIO's mapping: keep it as `mapped_metadata` (decision 230, as for DM, Merlin, block files), though thin and partly wrong (D1), reported upstream? Lean: keep it, its bugs in BACKLOG, "Sync with upstream". Against: a second section of strings that disagree with the original (scale 1 for 0.1 nm) invites wrong reading; and `read_de_metadata_file` opens the `_info.txt` itself (a small text file, after our size check), against TEMPLATE's "never letting it open the file".
- **Q4** `_processing.log`: read it? Lean: a member, not read, until its content is known; @weber's copy decides. Against: if it holds the processing steps or errors, a search for them finds nothing.
- **Q5** The movie's MRC header: not read (D1). Lean: not read. Against: it is the truth about the file written (an aborted acquisition may have fewer frames than the `_info.txt` says), and costs one 1 KiB read per acquisition.
- **Q6** The skip list: option lists only (`… Allowed Values`, `Preset - List`, `… Preset List`)? Lean: yes. Against: `Preset - Properties` (a copy of entries present anyway, 300 characters) and the hardware telemetry (`System Voltage - …`, `System Temperature - …`, mostly 0; 60 entries in 2.7.4) are noise in the second description.
- **Q7** The date in the summary line: `Local time` as written, only in 2.7.4 of the public files; the others have `Timestamp (seconds since Epoch)` only. Lean: `Local time` when present, else no date (it is in the name). Against: a UTC time computed from the timestamp would give every version one form.
- **Q8** The runner's change inside this change, or a change of its own? Lean: inside, as its first task group (BACKLOG: "Decide in the em/de proposal"); it changes warnings only. Against: a core change reviewed as part of a format.
- **Q9** Fixtures: RosettaSciIO's 2.7.2 and 2.7.5 files renamed to their Dataset Name (`info.txt` to `20230925_01497_info.txt`; `Custom_*` to `20250429_06699_*`), the rename in the manifest's `validity`. And a cut of the 2020 LiberTEM acquisition (its `_info.txt`, `_processing.log`, the movie's first 1 KiB)? Lean: the renamed public files now; the LiberTEM cut only with @weber's OK.
