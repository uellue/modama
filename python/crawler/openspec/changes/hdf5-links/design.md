# Design: HDF5 files that link other HDF5 files of their folder

The decision (321, @weber 2026-11-13, five points, approved "with this as a typical example") and @weber's answers to the first version (331 to 334) are in the proposal. This version applies the independent review of commit 299b26da (MUST 1 to 4, SHOULD 5 to 12, the nits); its measurements of the sample agreed with ours (968 reads, 482,967 bytes; no virtual datasets, no soft links; dense link storage). Measurements on the private sample were made with h5py 3.16.0 (HDF5 2.0.0) on 2026-11-13, opening the file read-only and listing links without dereferencing any (`links.iterate`, `links.get_val`); no value of the file is recorded here.

## D1 Where it lives: `common`, part `pydata` (334)

External links and virtual datasets are HDF5 features any writer uses; the walk that must list them is `pydata/hdf5.py`. One format, `common/hdf5links`, type `application/vnd.hdfgroup.hdf5`, priority 62, reacting to `application/vnd.hdfgroup.hdf5`, `application/x.nexus` and `application/x.hspy`: anchors are of the first type only, members of any of the three. It runs before `common/nexus`, `common/hspy` (61) and `common/hdf5` (60), so that a group is claimed before its files are claimed one by one; with 311 fixed (332) the formats after it no longer see what it claimed. NeXus anchors (`.nxs` masters, the common synchrotron layout) need a second format, since the core gives a format's datasets one type: backlog, until a real one is seen (review, SHOULD 5; YAGNI).

## D2 Links in the values, as written, summarised by runs

The walk (`walked`) already lists each group's links in stored order and keeps the hard links. It now also keeps, without opening anything through them:

- each **external link**: its name, target file name and target path (`links.get_val`: `(filename, path)`, as h5py's `ExternalLink` names them);
- each **virtual dataset's sources** in another file: source file name and source dataset path, from the dataset's creation property list (`get_virtual_filename(i)`, `get_virtual_dsetname(i)`), which the walk reads already before anything else is asked of a dataset (`outside`). A source in the same file (file name `.`) is left out.

**Runs.** Within one group, the external links are sorted by their names' bytes (UTF-8) in memory: the real master's `/entry/data` is stored densely, whose stored order is the names' hash order (`data_000188, data_000302, …`). Links next to each other in that order form a run when they have the same target path, and each one's link name and target file name differ from the previous one's only in one run of decimal digits at the same place, of the same width, whose value is one more. A run of two or more is one entry:

```
entry.data.data_000001 … data_000441.external_link: ["scan_00026_data_000001.h5 … scan_00026_data_000441.h5", "/entry/data/data"]
```

Unpadded numbers do not form runs: in byte order `d10` comes before `d9`, and the widths differ (review, SHOULD 10). A link outside a run is one entry, `entry.data.flatfield.external_link: ["calibration.h5", "/flatfield"]`. A virtual dataset's sources are one entry, a list of `[file, path]` pairs in mapping order, runs collapsed the same way (`entry.data.data.virtual_sources: [["part_001.h5 … part_004.h5", "/entry/data/data"]]`); more than 16 pairs, which `textual` refuses, leave the entry out, and the counts (D3) still say how many there are.

The names and paths are as written, never resolved, normalised or shortened (the full last name is given, not `…_000441.h5`). The run's key and its ` … ` are ours, as are `external_link` and `virtual_sources`: TEMPLATE.md names them as an exception to "no words of ours" (331), with `dangling`.

Each link listed counts as an object of the walk (5,000) and each entry as an entry (1,000): the real master's own walk gives 839 entries today, its links one more.

## D3 Counts, and dangling links

`mapped_metadata` of every HDF5 file with links to other files:

| Key | What it counts |
|---|---|
| `external_links` | external links listed |
| `virtual_sources` | virtual-dataset mappings onto another file |
| `found` | distinct target files that are regular files of the anchor's folder |
| `dangling` | distinct target files that are not |
| `elsewhere` | distinct target files named with a relative folder part (`../x.h5`, `sub/x.h5`) or a printf-style virtual-dataset name (`%b`), never looked up |

A target is named by its bare file name, or by an absolute path, which counts by its last component (A4, Q4). A link to the file's own name counts in `external_links` only. The extractor looks each target name up in the anchor's folder with `lstat` of `<folder>/<name>` (`name` a single path component, never `.` or `..`), which opens nothing (A6, Q12). So `found` and `dangling` are true whatever the membership: a target linked by two anchors, a target that is no HDF5 file, a folder over the bound all count as `found`, and the record's member list says what belongs to the dataset (the first version counted them `dangling`: review, SHOULD 8). A dangling link is normal (321, point 3): no warning.

A count can lag: the extraction is reused while the dataset's members are unchanged, so a target that appears later and does not become a member (no HDF5 file) leaves `dangling` as it was until the next extraction (a new extractor identity, the spot check, or a change of the members).

## D4 Grouping: anchor, members

In the post-order call, for a folder with two to 200 files of the three HDF5 types, the format lists the links of each file of type `application/vnd.hdfgroup.hdf5` (D5) and computes, once, among the folder's HDF5 files:

- a **target** of a file: an HDF5 file of the folder, other than itself, whose name equals the matching name of one of its external links or virtual-dataset sources (D3); a file the worker could not open as HDF5 is no target;
- a **back-link**: a link from one of a file's targets whose only target is that file (a data file that links its master);
- an **anchor** (A5 of the proposal): a file with at least one target that no other file names but through a back-link, and that is not one of two files each the other's only target; its **members** are its targets, minus those another anchor names too;
- two files each the other's only target (a **cycle**) are anchors of nothing: each stays a dataset of its own, with a remark in its basis naming the other. Without that rule, each link would be the other's back-link and both files would anchor each other;
- a target named by **two anchors** belongs to neither: it stays its own dataset (by `common/hdf5` and the others), and each anchor's basis says so, `shared.h5 also linked by b.h5, not a member` (`Directory.note` on the anchor; review, SHOULD 8);
- **chains** (a member that links further) are not followed: a member's own targets are not added. Nobody has seen one.

The name of a file plays no part (321: "Usually called master, but that is not a guarantee"). Each anchor with members is a dataset of `common/hdf5links`, basis `external links to <n> HDF5 files of this folder` (or `virtual-dataset sources in`, or both), as the Merlin format writes `4 frame file(s) acq*.mib`.

**Security.** Target names come from file content. They are compared with the names of the folder's entries, never joined into a path that is opened; the extractor opens `root + member` for the dataset's members only, and `lstat`s bare names in the anchor's folder (D3). Nothing is ever opened through a link, in recognition or extraction: links are listed with `links.get_val`; objects are opened by hard links only; a target path inside a member is followed one component at a time, each checked with `links.get_info` to be a hard link before it is opened, never through `values()`, `items()` or `group[path]` (review, SHOULD 6: an absolute external link, dereferenced, makes HDF5's native driver open the other file by its path). Every HDF5 file is opened through a file object of a descriptor that `files.regular` opened (D5), never by path with HDF5's native driver, in recognition and in extraction alike.

## D5 Recognition inspects files in worker processes, bounded

The link messages of the real master are written at its end (87.0 to 87.2 MiB of 87.2): a reader of first bytes (`Directory.read(entry, n)`) cannot find them, and the decision rules out names. So recognition opens HDF5 files with h5py. Measured through an unbuffered Python file object, listing every link by descending into hard-linked groups:

| File | Reads | Bytes |
|---|---|---|
| the real master, every link (684 objects, 441 external links) | 967 (the reviewer: 968) | 482,885 (482,967) |
| the real master, `/entry/data` only | 50 | 40,461 |
| a synthetic data file: `/entry/data/data` `[10, 64, 64] <u4` chunked, two attributes, three groups | 23 | 8,248 |

Telling a group from a dataset needs each object's header, one read each, so a file costs about one read per object.

**Why not in the walk's threads** (review, MUST 1 and 2). libhdf5 would parse untrusted files in the crawler's own process, with no limit on its time (a recognition call's time is only measured after it returns): a file that crashes libhdf5 would end the crawl, one that hangs it would hang it. And h5py's global lock serialises every h5py call of the process, so the walk's 32 threads would list one file at a time (the reviewer: 4 threads at 10 ms a read took 2.08 s, against 0.52 s for one). The extraction already runs h5py in spawned processes with a time limit enforced from outside (`extraction._run`); recognition uses the same mechanism.

**Core: `Directory.inspect(entries, fn)`.** A format hands the core a module-level function `fn(f) -> plain data` and entries of its folder; the core runs `fn` once per entry in a worker process, in parallel, and returns one outcome per entry. In the worker, the core:

1. opens the entry with `files.regular(path)`, a helper shared with `walk.py`'s `_opens` and the extractors: `os.open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_NOCTTY)`, then `fstat` and `S_ISREG`; a symlink (`ELOOP`) or anything but a regular file the entry may have become since its listing is not read and gives the outcome *not a regular file* (review, MUST 4);
2. wraps the descriptor in an unbuffered, read-only file object, readahead off, that counts the bytes read against the budget the call has left and raises `BudgetExceeded` on every read past it, the first and all later ones;
3. calls `fn(f)`, which opens h5py on `f` (`h5py.File(f, "r", locking=False)`) in a `with` block, so that h5py's file is closed before `fn` returns; then the core closes the file object and the descriptor, in a `finally`. (The reviewer: a counting `RawIOBase` left unclosed crashed the interpreter at exit with status 139; closed, it exits with 0.)

The outcome per entry, in the format's process: the result; *not a regular file*; *over the budget* (the core discards the call's result, as for any read past the budget, even when the format caught the error h5py made of it); *the file system did not answer* (an `OSError` of a read: `did_not_answer`, so the folder's stored datasets are kept, listing-errors D2); *timed out* after 60 s, treated as the file system not answering ("I/O errors and timeouts (probably report loudly for the admin to handle, report error and mark for retry)", @weber in listing-errors); *died* (the worker process ended, a crash in libhdf5): the file is not listed and the folder gets a warning naming it, and it stays a dataset of its own, whose extraction will fail the same way in its own worker. The bytes each worker read are charged to the call.

**Two layers of time limit** (@weber on 321, 2026-11-13: "yes with time limit, please", pointing to LiberTEM's HDF5 dataset for the same reason). LiberTEM's `_get_datasets(path)` (`src/libertem/io/dataset/hdf5.py`, lines 95 to 118 at commit d6aa0fa8, read 2026-11-13) walks the file with `f.visititems` and checks a deadline in the visitor, `raise TimeoutError` once `current_time() - t0 > timeout` (lines 105 to 107; `timeout` from `LIBERTEM_IO_HDF5_TIMEOUT_DEBUG`, default 3 s, lines 98 to 101); `detect_params` runs it through `executor.run_function` (line 406) and catches `(RuntimeError, TimeoutError, SystemError)` (line 411), `SystemError` "temporarily" for h5py issue 1740 (lines 409 to 410); opening a file that is not HDF5 it catches as `(OSError, KeyError, ValueError, TypeError, DataSetException)` (line 400). A deadline checked between objects cannot stop one libhdf5 call that hangs, nor survive a crash, so the guarantee stays the outside limit: the worker killed past 60 s, as above. LiberTEM's pattern is the inner layer: the listing checks a deadline of 45 s between objects, as the extractor's walk already does (`Walk.over`, a third of the extractor's limit), and a long but healthy listing stops there with what it found, its dataset warned that the links were listed up to the time limit (the real master needs 15 to 42 s on NFS, 968 reads at 16 to 43 ms). `fn` catches, around the open, `OSError`, `KeyError`, `ValueError` and `TypeError` as "not HDF5" (an `OSError` of a read is noted by the core's file object before h5py turns it into its own, so it stays "did not answer"), and around the listing `RuntimeError` and `SystemError` as "not listed" (a warning, the file a dataset of its own). LiberTEM is MIT-licensed (`LICENSE`, "Copyright (c) 2024 LiberTEM creators"), as `modama-formats-common` is, and the deadline is @weber's own code from LiberTEM commit 933f89ada86f4b235e4a08410a447c7d69ee5e35 (settled by @weber, 2026-11-13: it may be lifted). Where code is lifted, a comment credits it with that commit's URL (https://github.com/LiberTEM/LiberTEM/commit/933f89ada86f4b235e4a08410a447c7d69ee5e35) and "MIT", as `cpus.py` credits LiberTEM's `set_num_threads_env`; our walk already checks its time between objects (`Walk.over`), so little more than the exception classes may need lifting.

The pool: spawned processes owned by the walk, as many as the extraction's (`default_workers()`), made at the first `inspect` of a crawl (a crawl of folders without two HDF5 files makes none), killed and made again after a task over its time, as `_run` does; `_run` is generalised to run any module-level task. Each worker has its own h5py and its own lock.

`Format.byte_budget`: a format may declare a larger budget than the core's `BYTE_BUDGET` (1 MiB); `common/hdf5links` declares 32 MiB.

**Bounds of `common/hdf5links`** (proposal A3), each recorded where it cuts:

- two to 200 HDF5 files per folder (the October listing: 305 of the 309 folders with two or more HDF5 files by name hold at most 200, 8,548 files; the largest folder with a `*master*` file holds 170; the four larger ones are simulation outputs of 441 and 1,953 files). Fewer than two: nothing is opened. More than 200: nothing is opened, the folder's HDF5 files stay datasets of their own, and the folder gets a warning;
- 45 s per file between objects (the inner deadline: a partial listing and a warning), 60 s per file from outside (the worker killed);
- at most 5,000 objects and links listed per file (the extractor's `MAX_OBJECTS`); past it, the file groups with the targets found so far, and its dataset gets a warning;
- 32 MiB per call; past it, the core's rule.

**Cost** (333; revised after the review, for @weber, Q14). Only files of type `application/vnd.hdfgroup.hdf5` are listed, the possible anchors. `.emd` files are of that type by their content (`common-pydata`, scenario "HDF5 whatever the name": `velox.emd`), so they are listed: the reviewer's nit that these formats never open `.emd` does not hold. In the October listing, folders with two to 200 HDF5 files by name hold 8,548 files, `.emd` and `.nxs` included. At about 25 reads for a small file and about 1,000 for each of the 25 `*master*` files, a full recognition reads about 240,000 times (the reviewer, without the bound of 200 and counting every HDF5 file: about 370,000). At 16 to 43 ms a read on NFS (decision 2026-11-11), that is 1.1 to 2.9 hours of reads; spread over the 8 worker processes, 8 to 22 minutes, if the NFS server keeps 8 requests in flight as fast as one (the NFS benchmark found the number of requests in flight a main lever; not measured for this pattern). The per-file count for Velox `.emd` files is not measured: they hold more objects than a small data file. This cost comes once per change of a folder's listing, and for the whole tree once per release of the crawler or of any format distribution, since the rules' fingerprint covers all of them (README, "How it works"; the reviewer's nit: not only `modama-formats-common`). Measured on staging before the merge (tasks 6.4).

**Alternatives considered.** Grouping after extraction (the extractor lists links, a later step regroups): the recognition result is the stored form and the oracle (decision 2026-10-16), and a regrouping step would be a second recognition in the core. A byte search for the folder's file names in each file: the names are at the file's end here, a search would read whole files (91 MB), and a name in an attribute is not a link. Grouping by name (`*_master.h5` and `*_data_*.h5`): ruled out by 321. The reviewer found no cheaper trigger that keeps "by content". Listing in the walk's threads: MUST 1 and 2 above.

## D6 The linked data described from the members, bounded

A member belongs to the dataset, so reading it is not reading outside a file (321, point 4). For each run of external links (and each single link), the extractor opens the **first target that is a member**, by its own path through `files.regular` and a file object, never through the link, and finds the object at the target path as written one component at a time by hard links only (D4). Its `shape` and `dtype` go under the first link's dotted name in `original_metadata`, `entry.data.data_000001.shape [N, 2167, 2070]`, `entry.data.data_000001.dtype <u4`, as a reader of the master sees the linked dataset. A target path that crosses a soft or external link inside the member gives nothing. For a virtual dataset, nothing more: its extent comes from its first mapping already (`common-pydata`, "Nothing is read from outside the file"). Reading shapes and dtypes needs no filter plugin: a filter is needed only to read chunks (the Eiger data files are bitshuffle/LZ4, filter 32008 in their pipeline).

The members' own walks (point 4: "each data file's own structure") are not kept for now: the first version put them in a values section `members`, which is stored but rendered nowhere (decision 234 renders `original_metadata` only; review, SHOULD 9). Backlog, with a way to show them.

## D7 The summary line

316's rule as amended (324 to 326), on the anchor's `original_metadata`: a file without a title gets its three largest arrays (`<dotted path> <shape> <dtype>`, most elements first, ties by name), then `*.start_time`, `*.definition` and the root's `file_time`, as found. With D6 the linked data is among the arrays. Two additions:

- **Q5, the detector's description first** (lean). `*.instrument.detector.description` as found, before the arrays of a file without a title. NeXus defines it in `NXdetector`: "description: (optional) NX_CHAR — name/manufacturer/model/etc. information" (NeXus manual, base class NXdetector, https://manual.nexusformat.org/classes/base_classes/NXdetector.html, read 2026-11-13). One more entry on the positive list (decision 2026-11-12), not an exception. The brief's `Eiger 4M` is such a value.
- **The counts last** (331). `external_links`, `virtual_sources`, `dangling` and `elsewhere` from `mapped_metadata`, each `<name> <value>` as `headline` writes any value that is not text, 0 left out, on every HDF5 file's line, with a title or without. `found` is left out: the record's tail gives the number of files.

The real master's line: `<description>, entry.data.data_000001 [N, 2167, 2070] <u4, entry.instrument.detector.detectorSpecific.flatfield [2167, 2070] <f4, entry.instrument.detector.detectorSpecific.pixel_mask [2167, 2070] <u4, external_links 441, dangling 396`, then the core's `HDF5 …, 46 files, <size>, in eiger4m_01/`.

## D8 Order with 311 and `parallel-walk`

311 (332): `run_post` never narrows `d.entries`, so a later format still sees what an earlier one claimed; with `common/hdf5links` at 62, `common/nexus` and `common/hdf5` would each yield a dataset for every member, rejected with a warning. The change that fixes it is being built and also corrects the spec `recognition` to what the code does since commit 6fdd88be: a slow call's result is logged and kept, and "A byte budget bounds every format call" replaces "Budgets bound every format call" (`parallel-walk`'s delta, not yet archived). This change modifies "A byte budget bounds every format call" and depends on both changes archived before its own archive.

## Questions for @weber (each with the lean)

Answered on 2026-11-13: Q1 (334), Q2 (332), Q6 (331), Q10 (333, cost accepted; revised figure in Q14).

- **Q3** A linking file in a collapsed folder: nothing changes, lean (the collapse wins; nothing inside is recognised). Against: a collapsed folder's HDF5 masters stay invisible, as everything else in it.
- **Q4** Absolute target paths: matched by their last component in the folder, lean, as HDF5 itself does when the absolute path does not exist: "If file_name is an absolute pathname, the library will first try to find file_name. If file_name does not exist, file_name is stripped of directory paths to form a new file_name", and the search then tries `HDF5_EXT_PREFIX`, the link access property's prefix, and the path of the linking file (HDF5 reference manual, `H5Lcreate_external`, https://support.hdfgroup.org/documentation/hdf5/latest/group___h5_l.html, read 2026-11-13). Against: where the absolute path exists on the storage, HDF5 would open that file, not the one beside the master; the crawler cannot look (it never reaches outside the folder). Relative paths with a folder part: `elsewhere`.
- **Q5** The detector's `description` first in the summary line of a file without a title, lean yes (NXdetector, cited in D7).
- **Q7** A virtual dataset whose sources are in another folder, or with printf-style `%b` names: listed as written, counted `elsewhere`, no members, lean.
- **Q8** A file linked by two masters: its own dataset, each master's basis saying so, lean. Against: if it is the common data of two views (a summed and a raw master), the user sees three records.
- **Q9** A link to a file of the folder that is not HDF5: not a member, counted `found` (it exists), lean.
- **Q11** Fixtures generated by h5py after the real master's structure (names and shapes), lean; a cut of the real master (structure only, values zeroed, arrays dropped) only with its owner's agreement.
- **Q12** `found` and `dangling` by `lstat` of the target names in the anchor's folder at extraction, lean: true counts whatever the membership, nothing opened. Against: an extractor then looks at more than its members' content (names only), and the count can lag (D3).
- **Q13** A file whose listing times out after 60 s is treated as the file system not answering (the folder's stored datasets kept, tried again next crawl), lean, after @weber's words in listing-errors. Against: a file that hangs libhdf5 every time keeps its folder at the stored state for good, with a warning each crawl.
- **Q14** The revised cost (D5): about 240,000 reads per full recognition, 1.1 to 2.9 hours of reads, 8 to 22 minutes over 8 worker processes if NFS keeps up, per release of any format distribution or the crawler; to be measured on staging.
