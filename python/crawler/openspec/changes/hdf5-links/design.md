# Design: HDF5 files that link other HDF5 files of their folder

The decision (321, @weber 2026-11-13, five points, approved "with this as a typical example") and @weber's answers (331 to 334) are in the proposal. This version applies the second independent review (of bd59e547: M1 to M3, S1 to S4, the nits); the first review (of 299b26da) is answered in the proposal. Measurements on the private sample were made with h5py 3.16.0 (HDF5 2.0.0) on 2026-11-13, opening the file read-only and listing links without dereferencing any (`links.iterate`, `links.get_val`); no value of the file is recorded here. Counts of files come from the October listing (`.claude/survey/listing-2026-10-15.tsv.gz`), by name.

## D1 Where it lives: `common`, part `pydata` (334)

External links and virtual datasets are HDF5 features any writer uses; the walk that must list them is `pydata/hdf5.py`. One format, `common/hdf5links`, type `application/vnd.hdfgroup.hdf5`, priority 62, reacting to `application/vnd.hdfgroup.hdf5`, `application/x.nexus` and `application/x.hspy`. It runs before `common/nexus`, `common/hspy` (61) and `common/hdf5` (60), so that a group is claimed before its files are claimed one by one; with 311 fixed (332) the formats after it no longer see what it claimed.

**Which files are listed: `*.h5` files of type `application/vnd.hdfgroup.hdf5` only** (second review, S4; Q16). They are the possible anchors. Members may be any HDF5 file of the folder, of the three types and any name. In folders with two to 200 HDF5 files, the October listing has 8,574 HDF5 files by name, 4,397 of them `.emd` (51 %), 2,855 `.h5`, 1,231 `.nxs`, 66 `.hdf5`, 25 `.hspy`; Velox `.emd` files hold many more objects than a detector's data file (the reviewer: 200 to 1,000 reads each), and no `.emd` or `.nxs` master has been seen. The extension decides which files may anchor, not the master's name, which 321 rules out ("Usually called master, but that is not a guarantee"): an `.h5` file named anything anchors by its links. NeXus anchors (`.nxs` masters, the common synchrotron layout) need a second format, since the core gives a format's datasets one type, and links from `.emd`, `.nxs` and `.hdf5` files are not listed: backlog, until a real case is seen (YAGNI).

## D2 Links in the values, as written, summarised by runs

The walk (`walked`) already lists each group's links in stored order and keeps the hard links. It now also keeps, without opening anything through them:

- each **external link**: its name, target file name and target path (`links.get_val`: `(filename, path)`, as h5py's `ExternalLink` names them);
- each **virtual dataset's sources** in another file: source file name and source dataset path, from the dataset's creation property list (`get_virtual_filename(i)`, `get_virtual_dsetname(i)`), which the walk reads already before anything else is asked of a dataset (`outside`). A source in the same file (file name `.`) is left out.

This is the extractor's walk, of every HDF5 file, whatever its name; D1's restriction is recognition's only.

**Runs.** Within one group, the external links are sorted by their names' bytes (UTF-8) in memory: the real master's `/entry/data` is stored densely, whose stored order is the names' hash order (`data_000188, data_000302, …`). Links next to each other in that order form a run when they have the same target path, and each one's link name and target file name differ from the previous one's only in one run of decimal digits at the same place, of the same width, whose value is one more. A run of two or more is one entry:

```
entry.data.data_000001 … data_000441.external_link: ["scan_00026_data_000001.h5 … scan_00026_data_000441.h5", "/entry/data/data"]
```

Unpadded numbers do not form runs: in byte order `d10` comes before `d9`, and the widths differ. A link outside a run is one entry, `entry.data.flatfield.external_link: ["calibration.h5", "/flatfield"]`. A virtual dataset's sources are one entry, a list of `[file, path]` pairs in mapping order, runs collapsed the same way (`entry.data.data.virtual_sources: [["part_001.h5 … part_004.h5", "/entry/data/data"]]`); more than 16 pairs, which `textual` refuses, leave the entry out, and the counts (D3) still say how many there are.

The names and paths are as written, never resolved, normalised or shortened (the full last name is given, not `…_000441.h5`). The run's key and its ` … ` are ours, as are `external_link` and `virtual_sources`: TEMPLATE.md names them as an exception to "no words of ours" (331), with `dangling`.

Each link listed counts as an object of the walk (5,000) and each entry as an entry (1,000): the real master's own walk gives 839 entries today, its links one more.

## D3 Target names, counts, and dangling links

**The name a target is matched by** (Q4, 341):

| Target file name as written | Matched by | Counted as |
|---|---|---|
| a bare name, `scan_data_000001.h5` | itself | `found` or `dangling` |
| an absolute path, `/acquisition/pc/scan_data_000001.h5` | its last part, `scan_data_000001.h5` | `found` or `dangling` |
| a relative path with a folder part, `../raw/x.h5`, `sub/x.h5`, `./x.h5` | nothing | `elsewhere` |
| a printf-style virtual-dataset name, `data_%b.h5` | nothing | `elsewhere` |
| a Windows path, `C:\data\x.h5` | itself, as one name (no `/`) | `dangling`, as HDF5 on Linux would not find it |

An absolute path counts by its last part because HDF5 itself, when the absolute path does not exist, strips the folders and looks for the name beside the linking file (HDF5 reference manual, `H5Lcreate_external`: "If file_name is an absolute pathname, the library will first try to find file_name. If file_name does not exist, file_name is stripped of directory paths to form a new file_name", then `HDF5_EXT_PREFIX`, the link access property's prefix, and the path of the linking file; https://support.hdfgroup.org/documentation/hdf5/latest/group___h5_l.html, read 2026-11-13). `./x.h5` is left as written, not normalised, and counts `elsewhere`, though HDF5 would find it beside the file: nobody has seen one. A name is only ever compared with the folder's names, never joined into a path that is opened (D4). Distinct targets are counted by the name they are matched by: two absolute links whose last parts are the same name one target.

`mapped_metadata` of every HDF5 file with links to other files:

| Key | What it counts |
|---|---|
| `external_links` | external links listed |
| `virtual_sources` | virtual-dataset mappings onto another file |
| `found` | distinct target names that are regular files of the file's folder |
| `dangling` | distinct target names that are not |
| `elsewhere` | distinct targets never looked up (table above) |

A link to the file's own name counts in `external_links` only. The extractor reads the file's folder once with `os.scandir` and compares the target names with its entries in memory, a regular file by the entry's type (`d_type`; an entry of unknown type asked with `lstat`), opening nothing (second review, S2: 441 `lstat` calls would take 7 to 19 s on NFS). An error of the listing (`EIO`) fails the extraction, which the next crawl tries again (decision of `extractor-identity`, D9). So `found` and `dangling` are true whatever the membership: a target linked by two anchors, a target that is no HDF5 file, a folder over the bound all count as `found`, and the record's member list says what belongs to the dataset. A dangling link is normal (321, point 3): no warning.

A count can lag: the extraction is reused while the dataset's members are unchanged, so a target that appears later and does not become a member (no HDF5 file) leaves `dangling` as it was until the next extraction (a new extractor identity, the spot check, or a change of the members).

## D4 Grouping: anchor, members

In the post-order call, for a folder with two to 200 files of the three HDF5 types, at least one of them listed (D1), the format lists the links of the listed files (D5) and computes, once, among the folder's HDF5 files:

- a **target** of a listed file: an HDF5 file of the folder, other than itself, whose name equals the name one of its external links or virtual-dataset sources is matched by (D3);
- a **back-link**: a link from a listed target whose only target is that file (an `.h5` data file that links its master). Links from files that are not listed are not known and count for nothing;
- an **anchor** (A5 of the proposal): a listed file with at least one target, that no other listed file names but through a back-link, and that is not one of two listed files each the other's only target; its **members** are its targets, minus those another anchor names too;
- two listed files each the other's only target (a **cycle**) are anchors of nothing: each stays a dataset of its own, with a remark in its basis naming the other. Without that rule, each link would be the other's back-link and both files would anchor each other;
- a target named by **two anchors** belongs to neither: it stays its own dataset (by `common/hdf5` and the others), and each anchor's basis says so, `shared.h5 also linked by b.h5, not a member` (`Directory.note` on the anchor);
- **chains** (a member that links further) are not followed: a member's own targets are not added. Nobody has seen one.

Only listed files can name or anchor, so the rules hold among `.h5` files: a back-link from an `.h5` data file still counts, a `.nxs` data file's link back to its master is not seen and cannot stop it.

Each anchor with members is a dataset of `common/hdf5links`, basis `external links to <n> HDF5 files of this folder` (or `virtual-dataset sources in`, or both), as the Merlin format writes `4 frame file(s) acq*.mib`. A file the inspection could not list (D5) names nothing this crawl and stays a dataset of its own.

**Security.** Target names come from file content. They are compared with the names of the folder's entries, never joined into a path that is opened; the extractor opens `root + member` for the dataset's members only and lists the anchor's folder (D3). Nothing is ever opened through a link, in recognition or extraction: links are listed with `links.get_val`; objects are opened by hard links only; a target path inside a member is followed one component at a time, each checked with `links.get_info` to be a hard link before it is opened, never through `values()`, `items()` or `group[path]` (first review, SHOULD 6: an absolute external link, dereferenced, makes HDF5's native driver open the other file by its path). Every HDF5 file is opened through a file object of a descriptor that `files.regular` opened (D5), never by path with HDF5's native driver, in recognition and extraction alike. `Directory.read` opens through `files.regular` too (second review, nit).

## D5 Recognition inspects files in worker processes, bounded by counts

The link messages of the real master are written at its end (87.0 to 87.2 MiB of 87.2): a reader of first bytes (`Directory.read(entry, n)`) cannot find them, and the decision rules out names. So recognition opens `.h5` files with h5py. Measured through an unbuffered Python file object, listing every link by descending into hard-linked groups:

| File | Reads | Bytes |
|---|---|---|
| the real master, every link (684 objects, 441 external links) | 967 (the first reviewer: 968) | 482,885 (482,967) |
| the real master, `/entry/data` only | 50 | 40,461 |
| a synthetic data file: `/entry/data/data` `[10, 64, 64] <u4` chunked, two attributes, three groups | 23 | 8,248 |

Telling a group from a dataset needs each object's header, one read each, so a file costs about one read per object.

**Why not in the walk's threads** (first review, MUST 1 and 2). libhdf5 would parse untrusted files in the crawler's own process, with no limit on its time: a file that crashes libhdf5 would end the crawl, one that hangs it would hang it; and h5py's global lock serialises every h5py call of a process, so the walk's 32 threads would list one file at a time (4 threads at 10 ms a read: 2.08 s, against 0.52 s for one).

**One pool for the crawl, one folder at a time** (second review, M1). The extraction's `_run` runs a batch in a pool of spawned processes with a time limit enforced from outside: it kills all workers when a task is late and runs again the tasks that were in flight, one at a time after a crash. A pool per format call would multiply: `run_post` runs in up to 32 walk threads (`walk.py`, `io(run_post, …)`), so up to 256 processes, about 12 GB (the reviewer: spawning one and importing h5py takes 0.39 to 0.56 s and 46 to 51 MB). So the walk makes **one** inspection pool per crawl, of `default_workers()` spawned processes (8 at most), at the first inspection (a crawl with no folder to inspect makes none), and shuts it down after the walk; `_run` takes the pool as an argument instead of making its own; a lock lets one folder inspect at a time, so that killing late workers or rerunning after a crash touches that folder's tasks only. A folder's files spread over the workers. A format call waiting for the lock blocks its walk thread: the other threads go on until they need the pool too. The extraction does not run during the walk (`cli.py`: `walk(...)`, then `extraction.extract(...)`), so the two never compete for processes; the walk's MIME matching processes (`processes=`) do run beside the inspection pool, 8 plus 8 at most.

**Core: `Directory.inspect(entries, fn, budget)`.** A format hands the core a module-level function `fn(f) -> plain data`, entries of its folder and a byte budget per file; the core runs `fn` once per entry in the inspection pool and returns one outcome per entry. In the worker, the core:

1. opens the entry with `files.regular(path)`, a helper shared with `walk.py`'s `_opens`, `Directory.read` and the extractors: `os.open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_NOCTTY)`, then `fstat` and `S_ISREG`; a symlink (`ELOOP`) or anything but a regular file the entry may have become since its listing is not read and gives the outcome *not a regular file*;
2. wraps the descriptor in an unbuffered, read-only file object, readahead off, that counts the bytes read against the file's budget and raises `BudgetExceeded` on every read past it, the first and all later ones, and notes an `OSError` of a read;
3. calls `fn(f)`, which opens h5py on `f` (`h5py.File(f, "r", locking=False)`) in a `with` block, so that h5py's file is closed before `fn` returns; then the core closes the file object and the descriptor, in a `finally`. (The first reviewer: a counting `RawIOBase` left unclosed crashed the interpreter at exit with status 139; closed, it exits with 0.)

**The budget is per file** (second review, S1): each worker enforces its file's budget itself, so nothing is summed across processes after the fact, and one large file cannot make the others' results depend on the order they finished in. `common/hdf5links` gives 4 MiB a file (the real master reads 483 KB). The call's budget of 1 MiB for first bytes (`Directory.read`) is unchanged, and no format needs a budget of its own any more (the first version's `Format.byte_budget` is gone).

**Outcomes**, each for one file, in the format's process:

| Outcome | What it is | What the format does |
|---|---|---|
| the result | `fn` returned | uses it |
| *not a regular file* | step 1 | not listed, no warning (the walk skips such entries too) |
| *over the budget* | a read past the file's budget, even if `fn` caught h5py's error made of it | not listed; a warning |
| *the file system did not answer* | an `OSError` of a read, even if `fn` caught h5py's error made of it | `did_not_answer`: the folder's stored datasets are kept (listing-errors D2) |
| *failed* | `fn` raised (a bug, a `MemoryError` under the workers' 4 GiB) | not listed; a warning; `retry` |
| *timed out* | not done after 60 s; the worker killed | not listed; a warning; `retry` |
| *died* | the worker process ended (a crash in libhdf5) | not listed; a warning; `retry` |

A file not listed names nothing this crawl and stays a dataset of its own, of `common/hdf5`; the warning of a failed, timed out or dead inspection always holds the marker `not inspected` (`formats.NOT_INSPECTED`), by which one grep or query lists them all (340), as `two formats want it` does for 344; `retry` makes the core recognise the folder again next crawl (`Directory.retry`, as for a read error), as the extraction tries every failure again (`extractor-identity`, D9). The first version treated a timeout as the file system not answering, which keeps the stored datasets: a folder crawled for the first time with one file that hangs libhdf5 would then never get records at all (second review, M3; Q13 settled).

The mapping from what happened in the worker to these outcomes is a function of its own, tested apart from the processes; the counting file object is tested in the test's own process, since a monkeypatch does not reach a spawned worker (second review, S3).

**Bounds by counts, not by time** (second review, M2; Q15 for @weber). The grouping must be the same on every crawl of the same files: a cut that falls before `/entry/data` on a slow night and after it on a fast one turns 1 record into 46 and back, and the harvester sees deletions at every turn. So the listing of one file stops at **5,000 objects and links** (the extractor's `MAX_OBJECTS`; the real master has 684 objects and 441 links, 1,125) or at its budget of 4 MiB, both the same on every crawl; past either, the file groups with the targets found so far, and its dataset gets a warning. Time is bounded only from outside, by the kill at 60 s, for files that hang: a master that needs 15 to 42 s on NFS (968 reads at 16 to 43 ms) is listed in full. A timeout still makes that crawl's grouping depend on the load, but only for a file over 60 s, and it is retried and warned.

@weber asked for LiberTEM's deadline ("yes with time limit, please", 321): `_get_datasets` (`src/libertem/io/dataset/hdf5.py`, lines 95 to 118 at commit d6aa0fa8, read 2026-11-13) checks `current_time() - t0 > timeout` in its `visititems` visitor and raises `TimeoutError` (lines 105 to 107; `timeout` from `LIBERTEM_IO_HDF5_TIMEOUT_DEBUG`, default 3 s, lines 98 to 101), and `detect_params` catches `(RuntimeError, TimeoutError, SystemError)` (line 411; `SystemError` for h5py issue 1740, lines 409 to 410) and, at the open, `(OSError, KeyError, ValueError, TypeError, DataSetException)` (line 400). LiberTEM uses the result to pick a dataset for a person to confirm, where a partial answer harms nothing; here it decides which records exist. The time limit @weber asked for stays, as the outside kill; the inner deadline is replaced by the count bounds, pending his answer (Q15). The exception classes are taken as prior art: `fn` catches `OSError`, `KeyError`, `ValueError`, `TypeError` at the open as "not HDF5" (an `OSError` of a read is noted by the file object first, so it stays "did not answer") and `RuntimeError`, `SystemError` in the listing as *failed*. No code is lifted, so no credit comment is needed; if @weber keeps the inner deadline, code from LiberTEM commit 933f89ada86f4b235e4a08410a447c7d69ee5e35 (his own, MIT) may be lifted and credited with that commit's URL and "MIT".

**Bounds of `common/hdf5links`**, each recorded where it cuts: two to 200 HDF5 files per folder, at least one `.h5` (fewer: nothing opened; more than 200: nothing opened, the files stay datasets of their own, and the folder gets a warning); 5,000 objects and links, and 4 MiB, per file; 60 s per file from outside.

**Cost** (333; re-estimated after the second review, Q14). In the October listing, the folders with two to 200 HDF5 files and at least one `.h5` file are 141, holding 2,855 `.h5` files, 25 of them named `*master*`. Assumed: about 1,000 reads for a master (the real one: 967), 23 to 100 for any other `.h5` file (23 measured for a detector's data file; others, simulation outputs and the like, unmeasured, so up to 100). That is 90,000 to 310,000 reads, 0.4 to 3.7 hours of reads at 16 to 43 ms each. With one folder at a time and 8 workers, the 141 folders take 379 rounds of up to 8 files, each as long as its slowest file: 25 rounds with a master (16 to 43 s each, 7 to 18 minutes) and 354 rounds of other files (0.4 to 4.3 s each, 2 to 25 minutes), about 10 to 45 minutes in all, if NFS serves 8 requests in flight as fast as one (the NFS benchmark found the number of requests in flight a main lever; not measured for this pattern). This cost comes once per change of a folder's listing, and for the whole tree once per release of the crawler or of any format distribution, since the rules' fingerprint covers all of them (README, "How it works"). Measured on staging before the merge (task 6.4).

**Alternatives considered.** Grouping after extraction: the recognition result is the stored form and the oracle (decision 2026-10-16), and a regrouping step would be a second recognition in the core. A byte search for the folder's file names in each file: the names are at the file's end here, a search would read whole files (91 MB), and a name in an attribute is not a link. Grouping by name (`*_master.h5` and `*_data_*.h5`): ruled out by 321. The first reviewer found no cheaper trigger that keeps "by content". Listing in the walk's threads: MUST 1 and 2 of the first review. A pool per call, or the extraction's own pool: M1 above.

## D6 The linked data described from the members, bounded

A member belongs to the dataset, so reading it is not reading outside a file (321, point 4). For each run of external links (and each single link), the extractor opens the **first target that is a member**, by its own path through `files.regular` and a file object, never through the link, and finds the object at the target path as written one component at a time by hard links only (D4). Its `shape` and `dtype` go under the first link's dotted name in `original_metadata`, `entry.data.data_000001.shape [N, 2167, 2070]`, `entry.data.data_000001.dtype <u4`, as a reader of the master sees the linked dataset. A target path that crosses a soft or external link inside the member gives nothing. For a virtual dataset, nothing more: its extent comes from its first mapping already (`common-pydata`, "Nothing is read from outside the file"). Reading shapes and dtypes needs no filter plugin: a filter is needed only to read chunks (the Eiger data files are bitshuffle/LZ4, filter 32008 in their pipeline).

The members' own walks (point 4: "each data file's own structure") are not kept for now: a values section `members` would be stored but rendered nowhere (decision 234 renders `original_metadata` only; first review, SHOULD 9). Backlog, with a way to show them.

## D7 The summary line

316's rule as amended (324 to 326), on the anchor's `original_metadata`: a file without a title gets its three largest arrays (`<dotted path> <shape> <dtype>`, most elements first, ties by name), then `*.start_time`, `*.definition` and the root's `file_time`, as found. With D6 the linked data is among the arrays. Two additions:

- **Q5, the detector's description first** (lean). `*.instrument.detector.description` as found, before the arrays of a file without a title. NeXus defines it in `NXdetector`: "description: (optional) NX_CHAR — name/manufacturer/model/etc. information" (NeXus manual, base class NXdetector, https://manual.nexusformat.org/classes/base_classes/NXdetector.html, read 2026-11-13). One more entry on the positive list (decision 2026-11-12), not an exception. The brief's `Eiger 4M` is such a value.
- **The counts last** (331). `external_links`, `virtual_sources`, `dangling` and `elsewhere` from `mapped_metadata`, each `<name> <value>` as `headline` writes any value that is not text, 0 left out, on every HDF5 file's line, with a title or without. `found` is left out: the record's tail gives the number of files.

The real master's line: `<description>, entry.data.data_000001 [N, 2167, 2070] <u4, entry.instrument.detector.detectorSpecific.flatfield [2167, 2070] <f4, entry.instrument.detector.detectorSpecific.pixel_mask [2167, 2070] <u4, external_links 441, dangling 396`, then the core's `HDF5 …, 46 files, <size>, in eiger4m_01/`.

## D8 Order with 311

311 (332): `run_post` never narrows `d.entries`, so a later format still sees what an earlier one claimed; with `common/hdf5links` at 62, `common/nexus` and `common/hdf5` would each yield a dataset for every member, rejected with a warning. The change that fixes it is being built and also brings the spec `recognition` in line with the code since commit 6fdd88be (a slow call's result is logged and kept). This change adds the inspection to `recognition` and modifies "Plain data in, no reach outside the directory"; it no longer touches the byte budget's requirement (D5: the budget of an inspection is per file).

## Questions for @weber (each with the lean)

Answered on 2026-11-13: Q1 (334), Q2 (332), Q6 (331), Q10 (333, cost accepted), Q4 (341: yes), Q14 (339: as estimated, revisited if staging shows it hurts), Q15 (342: count bounds and the outside kill), timeouts (340: a plain HDF5 file for that crawl, tried again, flagged `not inspected`). Settled by the second review: Q13. The rest were built on their leans, by the coordinator's go-ahead of 2026-11-13.

- **Q3** A linking file in a collapsed folder: nothing changes, lean (the collapse wins; nothing inside is recognised). Against: a collapsed folder's HDF5 masters stay invisible, as everything else in it.
- **Q4 (341)** Absolute target paths: matched by their last part in the folder, lean, as HDF5 does when the absolute path does not exist (D3, cited); the second reviewer agrees. The name is only compared, never joined into a path and opened. Against, with a scenario ("A generic name linked by an absolute path"): an `.h5` file linking `/calibration/shared/flatfield.h5`, which exists on the acquisition computer, groups an unrelated `flatfield.h5` beside it.
- **Q5** The detector's `description` first in the summary line of a file without a title, lean yes (NXdetector, cited in D7).
- **Q7** A virtual dataset whose sources are in another folder, or with printf-style `%b` names: listed as written, counted `elsewhere`, no members, lean.
- **Q8** A file linked by two masters: its own dataset, each master's basis saying so, lean. Against: if it is the common data of two views (a summed and a raw master), the user sees three records.
- **Q9** A link to a file of the folder that is not HDF5: not a member, counted `found` (it exists), lean.
- **Q11** Fixtures generated by h5py after the real master's structure (names and shapes), lean; a cut of the real master (structure only, values zeroed, arrays dropped) only with its owner's agreement.
- **Q12** `found` and `dangling` from one `scandir` of the file's folder at extraction, lean: true counts whatever the membership, nothing opened. Against: an extractor then looks at more than its members' content (names only), and the count can lag (D3).
- **Q14** The revised cost (D5): 90,000 to 310,000 reads per full recognition, about 10 to 45 minutes over 8 workers if NFS keeps up, per release of any format distribution or the crawler; to be measured on staging.
- **Q15** Count bounds (5,000 objects and links, 4 MiB per file) instead of an inner deadline, with the outside kill at 60 s as the only time limit, lean (second review, M2): the same files give the same records on every crawl. Against: @weber asked for LiberTEM's deadline; a file that is slow but under 60 s takes its full time every time.
- **Q16** Only `*.h5` files are listed and may anchor, lean (second review, S4: 51 % of the HDF5 files in such folders are `.emd`, none of them seen as a master). Against: an `.emd`, `.nxs` or `.hdf5` master (66 `.hdf5` files in such folders) stays unseen until one is found and the backlog item is done.
