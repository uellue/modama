# Design: HDF5 files that link other HDF5 files of their folder

The decision (321, @weber 2026-11-13, five points, approved "with this as a typical example") is in the proposal. This file records how it is met and what was measured. Measurements on the private sample were made with h5py 3.16.0 (HDF5 2.0.0) on 2026-11-13, opening the file read-only and listing links without dereferencing any (`links.iterate`, `links.get_val`); no value of the file is recorded here.

## D1 Where it lives: `common`, part `pydata`

External links and virtual datasets are HDF5 features any writer uses (h5py, NeXus writers, Dectris, MATLAB); the walk that must list them is `pydata/hdf5.py`. The `em` collection could subclass the formats if Eiger-specific values are wanted later (proposal A1, question Q1).

Two formats, one per anchor type, because the core gives a format's datasets the format's type (`_fill`: `type=fmt.type`): `common/hdf5links` (`application/vnd.hdfgroup.hdf5`) and `common/nexuslinks` (`application/x.nexus`), priority 62, reacting to the three HDF5 types of the part (`application/vnd.hdfgroup.hdf5`, `application/x.nexus`, `application/x.hspy`): a NeXus master that links `.h5` data files is the common synchrotron layout, an `.h5` master that links `.nxs` files is possible too. Members may be of any of the three types; HyperSpy and MATLAB 7.3 files are not anchors (nobody has seen one link). They run before `common/nexus`, `common/hspy` (61) and `common/hdf5` (60), so that a group is claimed before its files are claimed one by one.

## D2 Links in the values, as written, summarised by runs

The walk (`walked`) already lists each group's links in stored order and keeps the hard links. It now also keeps, without opening anything through them:

- each **external link**: its name, target file name and target path (`links.get_val`: `(filename, path)`, as h5py's `ExternalLink` names them);
- each **virtual dataset's sources** that are in another file: source file name and source dataset path, from the dataset's creation property list (`get_virtual_filename(i)`, `get_virtual_dsetname(i)`), which the walk reads already before anything else is asked of a dataset (`outside`). A source in the same file (file name `.`) is not a link to another file and is left out.

**Runs.** Within one group, the external links are taken in name order (sorted in memory: the real master's `/entry/data` is stored in HDF5's dense form, whose stored order is the names' hash order, `data_000188, data_000302, …`). Consecutive links form a run when they have the same target path and each one's link name and target file name differ from the previous one's only in one run of decimal digits at the same place, whose value is one more. A run of two or more is one entry:

```
entry.data.data_000001 … data_000441.external_link: ["scan_00026_data_000001.h5 … scan_00026_data_000441.h5", "/entry/data/data"]
```

A link outside a run is one entry, `entry.data.flatfield.external_link: ["calibration.h5", "/flatfield"]`. A virtual dataset's sources are one entry, a list of `[file, path]` pairs in mapping order, runs collapsed the same way (`entry.data.data.virtual_sources: [["scan_data_000001.h5 … scan_data_000100.h5", "/entry/data/data"]]`); more than 16 pairs, which `textual` refuses, leave the entry out, and the counts (D3) still say how many there are.

The key's last part (`external_link`, `virtual_sources`) is a name of ours, as `shape` and `dtype` are (A5 of `common-pydata`: an attribute of the same name would take its place; none seen). The values are as written: names and paths are not resolved, normalised or shortened (`…_000441.h5` would be an abbreviation of ours, so the full last name is given).

Each link listed counts as an object of the walk (5,000) and each entry as an entry (1,000): the real master's own walk gives 839 entries today, its links one more.

## D3 Counts, and dangling links

`mapped_metadata` (what we compute) of every HDF5 file with links to other files:

| Key | What it counts |
|---|---|
| `external_links` | external links listed |
| `virtual_sources` | virtual-dataset mappings to another file |
| `found` | distinct target files that are members of this dataset |
| `dangling` | distinct target files named by a bare file name that are not members |
| `elsewhere` | distinct target files named with a folder part (`../x.h5`, `sub/x.h5`, an absolute path) or a printf-style virtual-dataset name (`%b`), never looked up |

The counts are made by the extractor against the dataset's members, not by looking at the folder again (an extractor reads the dataset's members only, `Format.extract`). In the usual case a target that is not a member is absent from the folder: a stopped acquisition, which is normal (321, point 3) and not a warning. The other reasons a bare-named target is not a member (it is not an HDF5 file, Q9; two anchors name it, Q8; recognition gave up on the folder, D5) leave a remark or a warning where recognition decided it. For a single HDF5 file that links, `found` is 0 and every bare-named target is `dangling`, which is right whenever its folder holds no other HDF5 file it names.

## D4 Grouping: anchor, members

In the post-order call, for a folder with two or more files of the three HDF5 types (one alone has nothing to link to), the format lists the links of each (D5) and builds, among the folder's HDF5 files:

- a **target** of a file: an HDF5 file of the folder whose name equals a bare target file name of one of its external links or virtual-dataset sources;
- an **anchor**: a file with at least one target that is the target of no other file; its **members** are its targets, minus those that another anchor names too;
- a target named by **two anchors** belongs to neither: it stays its own dataset (by `common/hdf5` and the others), with a remark in its basis naming the anchors (`Directory.note`); an accidental split beats an accidental grouping (R30, decision 2026-10-16);
- **chains** (a member that links further) and **cycles** are not followed: a member's links are listed in its own walk (D6); its targets are not added, a cycle has no anchor. Nobody has seen either.

The name of a file plays no part (321: "Usually called master, but that is not a guarantee"). Each anchor with members is a dataset of `common/hdf5links` or `common/nexuslinks` by its own type, basis `external links to <n> HDF5 files of this folder` (or `virtual-dataset sources in`, or both), as the Merlin format writes `4 frame file(s) acq*.mib`. A file h5py cannot open is not HDF5 for this purpose: neither anchor nor member; the formats after it see it as before (with 311 fixed, A2).

**Security.** Target names come from file content. They are compared with the names of the folder's entries, never joined into a path and opened; the extractor opens `root + member` for the dataset's members only. Nothing is ever opened through a link, in recognition or extraction: links are listed with `links.get_val`, objects opened by hard links only (decision of `common-pydata`, review blocker; TEMPLATE.md, "Never read outside the file"). A target named `../../etc/x` matches no entry and counts as `elsewhere`.

## D5 Recognition reads files at any offset, bounded

The link messages of the real master are written at its end (87.0 to 87.2 MiB of 87.2): a reader of first bytes (`Directory.read(entry, n)`) cannot find them, and the decision rules out names. So recognition opens HDF5 files with h5py. Measured through an unbuffered Python file object (what recognition would hand h5py), listing every link by descending into hard-linked groups:

| File | Reads | Bytes |
|---|---|---|
| the real master, every link (684 objects, 441 external links) | 967 | 482,885 |
| the real master, `/entry/data` only | 50 | 40,461 |
| a synthetic data file: `/entry/data/data` `[10, 64, 64] <u4` chunked, two attributes, three groups | 23 | 8,248 |

(HDF5's own driver issued 975 and 31 `pread64` calls for the same two files under `strace`, about the same.) Telling a group from a dataset needs each object's header, one read each, so a file costs about one read per object. The real folder (master and 45 data files) costs about 2,000 reads, 850 KB: on NFS, at 16 to 43 ms a round trip (decision 2026-11-11, extraction apart from recognition), 30 to 90 s in one format call.

Core changes, MODIFIED in `specs/recognition`:

- `Directory.opened(entry)`: a read-only file object of an entry of the folder, unbuffered, readahead off, whose reads at any offset count against the call's byte budget; h5py opens it with its file-object driver (`h5py.File(fileobj, "r", locking=False)`). A read past the budget raises `BudgetExceeded`, which h5py turns into its own error: the Directory notes the breach so that the core discards the call's result even when the format caught h5py's error, as it notes a read error (`did_not_answer`).
  An I/O error of the file object's read is noted the same way (`did_not_answer`, as `Directory.read` does), so that a failing NFS read inside h5py keeps the folder's stored datasets (listing-errors D2), while a file h5py refuses because it is no HDF5 (an `OSError` of h5py's with no read error noted) is only "not HDF5" for the format (D4).
- `Format.byte_budget`: a format may declare a larger budget than the core's `BYTE_BUDGET` (1 MiB); the link formats declare 32 MiB.

A gap found on the way, like 311: the spec `recognition` says a call over the time limit has its result discarded ("A slow format's result is discarded"), but `_call` only logs it and keeps the result (`formats/__init__.py`, `elapsed > slow`), as the comment above `SLOW` says ("a call slower than SLOW is logged and keeps its result"). The link formats rely on the code's behaviour: a folder of 170 files on NFS takes minutes. The spec's scenario is left as it is here; which of the two is right is a question for the change that fixes 311 (BACKLOG).

Bounds of the link formats (proposal A4), each recorded where it cuts:

- at most 200 HDF5 files per folder (the October listing: 305 of the 309 folders with two or more HDF5 files by name hold at most 200, 8,548 files; the largest folder with a `*master*` file holds 170; the four larger ones are simulation outputs of 441 and 1,953 files). Past it, nothing is opened, the folder's HDF5 files stay single datasets, and the folder gets a warning (`hdf5links: 1,953 HDF5 files, over 200: links not listed`);
- at most 5,000 objects and links listed per file (the extractor's `MAX_OBJECTS`). Past it, the file groups with the targets found so far, and its dataset gets a warning;
- 32 MiB per call. Past it, the core discards the format's result for the folder with a warning, as for any format, and the files stay single datasets.

The time is not bounded beyond the core's (a call over `SLOW`, 5 s, is logged with its time); a folder of 170 files may take minutes on NFS, once per change of its listing and once per release of `modama-formats-common`, which makes the whole tree be recognised again (Q10).

**Alternatives considered.** Grouping after extraction (the extractor lists links, a later step regroups): the recognition result is the stored form and the oracle (decision 2026-10-16), and a regrouping step would be a second recognition in the core. A byte search for the folder's file names in each file: the names are at the file's end here, a search would read whole files (91 MB), and a name in an attribute is not a link. Grouping by name (`*_master.h5` and `*_data_*.h5`): ruled out by 321.

## D6 Members described from themselves, bounded

A member belongs to the dataset, so reading it is not reading outside a file (321, point 4). Two things are read, from the member opened by its own path, never through the link, and no array:

- for each run of external links (and each single link), the **target object of the first existing target**, at the target path as written, by hard links only (a target path that crosses a soft or external link inside the member gives nothing): its `shape` and `dtype` under the first link's dotted name in `original_metadata`, `entry.data.data_000001.shape [N, 2167, 2070]`, `entry.data.data_000001.dtype <u4`, as a reader of the master sees the linked dataset (`f["entry/data/data_000001"].shape`). For a virtual dataset, nothing more: its extent comes from its first mapping already (`common-pydata`, "Nothing is read from outside the file");
- each **member's own walk** (the HDF5 walk of `common/hdf5`, links included) in a values section `members`, keyed by the member's file name, in name order, with one set of limits for all members together (1,000 entries, 5,000 objects, a third of the extractor's time limit), `mapped_metadata.members_walk` saying which limit cut it. The anchor's walk keeps its own limits, so the members never push the anchor's values out.

`members` is stored with the dataset but not rendered: the record's second description renders `original_metadata` only (decision 234). Reading shapes and dtypes needs no filter plugin: a filter is needed only to read chunks (the Eiger data files are bitshuffle/LZ4, filter 32008 in their pipeline).

## D7 The summary line

316's rule, on the anchor's `original_metadata`, unchanged: a file without a title gets its three largest arrays (`<dotted path> <shape> <dtype>`, most elements first, ties by name), then the root's `file_time` as found. With D6 the linked data is among the arrays. For the real master (no title, no `file_time`): `entry.data.data_000001 [N, 2167, 2070] <u4, entry.instrument.detector.detectorSpecific.flatfield [2167, 2070] <f4, entry.instrument.detector.detectorSpecific.pixel_mask [2167, 2070] <u4`.

Two additions, both leans for @weber:

- **Q5, the detector's description first.** `*.instrument.detector.description` (NeXus NXdetector's `description`, "name/manufacturer/model"; the field name to be checked against the NeXus manual before building), as found, before the arrays of a file without a title. It is one more entry on the positive list (the summary line's chosen entries are the only positive list, decision 2026-11-12), not an exception to "no words of ours". The brief's `Eiger 4M` is such a value.
- **Q6, the counts last.** `external_links 441, dangling 396` (and `virtual_sources`, `elsewhere` when not 0), from `mapped_metadata`, each `<name> <value>` as `headline` writes any value that is not text, 0 left out. The names are ours, as `shape` in 316's line and NumPy's mapped `dtype` in the `.npy` line are; no new exception. The brief's wording `45 of 441 data files` would be words of ours, a third exception beside "(unit unknown)" and "(encrypted)": the lean is against it. The record's tail already says `46 files`.

The real master's line with both: `<description>, entry.data.data_000001 [N, 2167, 2070] <u4, entry.instrument.detector.detectorSpecific.flatfield [2167, 2070] <f4, entry.instrument.detector.detectorSpecific.pixel_mask [2167, 2070] <u4, external_links 441, dangling 396`, then the core's `HDF5 …, 46 files, <size>, in eiger4m_01/`.

## D8 Order with 311

311: `run_post` never narrows `d.entries`, so a later format still sees what an earlier one claimed; its claim is then rejected with "already claimed by" (a warning), although the spec `recognition` says claimed entries "SHALL NOT be available to formats that run later". With the link formats at 62, `common/nexus` and `common/hdf5` would each yield a dataset for every member: 45 false warnings for the real folder, the outcome right. The fix is in the core (later formats see the unclaimed entries and child datasets only; `of_type`, `entry`, `entries` narrowed), small, and the spec already asks for it: a change of its own, merged before this one (proposal A2, Q2). Without it, this change works with one warning per member, which would make the run's warning count meaningless for HDF5 folders.

## Questions for @weber (each with the lean)

- **Q1** Collection: `common` (`pydata`), lean; or `em`, since Eiger is a detector. Against the lean: the motivating case is a detector's, and Eiger-specific values (frame counts) would later belong in `em`.
- **Q2** Fix 311 first as a small change of its own, lean; or live with one false warning per member until it is fixed.
- **Q3** A linking file in a collapsed folder: nothing changes, lean (the collapse wins; nothing inside is recognised). Against: a collapsed folder's HDF5 masters stay invisible, as everything else in it.
- **Q4** Links with an absolute path or `..` or a subfolder: listed as written, counted `elsewhere`, never matched, lean. Against: a writer that stores the absolute path of the acquisition computer (`/data/scan/scan_data_000001.h5`) would not group even when the file sits beside the master; whether HDF5 itself would find it there is to be checked in HDF5's documentation of external link lookup before deciding, with a real case.
- **Q5** The detector's `description` first in the summary line of a file without a title, lean yes.
- **Q6** `external_links 441, dangling 396` at the end of the summary line, lean; or the brief's `45 of 441 data files` as a third exception to "no words of ours"; or no counts in the line (the tail says `46 files`).
- **Q7** A virtual dataset whose sources are in another folder: listed as written, counted `elsewhere`, no members, lean (claims stay within the folder; architecture A). A printf-style source name (`%b`) likewise, never expanded.
- **Q8** A file linked by two masters: its own dataset, with a remark naming both, lean. Against: if it is the common data of two views (a summed and a raw master), the user sees three records.
- **Q9** A link to a file of the folder that is not HDF5: not a member, counted `dangling`, lean (HDF5 cannot resolve it either). Against: "dangling" then also means "not HDF5", explained by a remark only.
- **Q10** Recognition cost: opening every HDF5 file of folders with two to 200 of them (8,548 files in the October listing, about one read per object, 23 for a small data file, 967 for the real master), once per listing change and once per release, lean, to be measured on staging before the merge. Against: a release then costs a full re-read of those files' structure on NFS, on top of the extraction.
- **Q11** Fixtures generated by h5py after the real master's structure (names and shapes), lean; a cut of the real master (structure only, values zeroed, arrays dropped) only with its owner's agreement.
