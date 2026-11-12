# Proposal

## Why

@weber, 2026-11-12, as a task for the night: "Let's develop more format libraries to be tested tomorrow. Apply all lessons from EM formats as far as applicable. Use publicly available test data", with Python data-science formats as one of five areas; "go with your leans, upstream prior art and common sense. Just don't do anything that could realistically disrupt the crawl"; "please use the 'industry standard' readers and practices". The October listing (`.claude/survey/listing-2026-10-15.tsv.gz`) holds, as files: `.npy` 73,113 (1.8 TB, the largest 242 GB), `.py` 19,419, `.h5` 7,654 (510 GB), `.npz` 1,639 (231 GB), `.ipynb` 1,525 (607 of them in `.ipynb_checkpoints`, which the core collapses), `.nxs` 1,231, `.mat` 111, `.hdf5` 80, `.hspy` 49 (134 GB), `.pkl`/`.pickle` 32, `.zspy` 1, and 132 `.zarr` and 4 `.zspy` directories. Today the core types `.npy`, `.pkl` and MAT files without a glob as `application/octet-stream` or `text/plain`, `.npz` as `application/zip`, every HDF5 file as `application/x-hdf` (HDF4 and HDF5 alike), and extracts nothing from any of them. Serves R25 (honest types as MIME strings), R30 (findable by what the data is), R21 (formats outside the core).

## What Changes

A part `pydata` of `modama-formats-common` (collection `common`, format ids `common/<name>`), written along `formats/TEMPLATE.md` and its checklist "Lessons from the EM formats":

- **Types** (`pydata/pydata.xml`), each named after one in use where one exists:
  - NumPy `.npy`: `application/x-npy` (PRONOM fmt/2112), alias `application/x-numpy-data` (file(1)'s name), by the magic `\x93NUMPY` and `*.npy`.
  - NumPy `.npz`: `application/x.npz`, a subclass of `application/zip`, by name; no type in use was found.
  - HDF5: `application/vnd.hdfgroup.hdf5` (registered with IANA on 2026-03-17; `application/x-hdf5` its deprecated alias), a subclass of the core's `application/x-hdf`, by the HDF5 signature at 0 or at 512 (after a user block, as MATLAB 7.3 writes it; HDF5 allows further powers of two, none seen) and `*.h5`, `*.hdf5`, `*.hdf`, so that the content decides between HDF4 and HDF5. Every HDF5 file gets it whatever its name (`.emd` too: 4,411 files, 500 GB).
  - NeXus `.nxs` (`application/x.nexus`) and HyperSpy `.hspy` (`application/x.hspy`): subclasses of HDF5 by name; recognition checks the HDF5 signature (and for `.hspy` `HyperSpy` in the first 4 KiB) and drops the type of a file without it.
  - MATLAB `.mat`: `application/x-matlab-data` (Apache Tika's name), by the text `MATLAB` at 0 and `*.mat`; recognition keeps a file with that text or with a zero byte in its first 4 bytes (a version 4 file, as SciPy's `matfile_version` decides), and drops the type of others.
  - Python pickles `.pkl`, `.pickle`: `application/x-python-pickle` (Tika's name), by Tika's magic for protocols 2 to 5 and the names; recognition drops the type of a file without that start (protocols 0 and 1 are text without a mark).
  - Jupyter notebooks (`application/x-ipynb+json`) and Python scripts (`text/x-python`, `text/x-python3`) keep the core's types; a notebook whose first character is not `{` loses its name's type.
- **Extraction**, each with the field's reader, reading headers and metadata only:
  - `.npy`: the header (`numpy.lib.format`): `descr`, `fortran_order`, `shape` and the format version as the file says them; NumPy's `dtype` as the mapped value. Never the array.
  - `.npz`: each `.npy` member's header through `zipfile`, under NumPy's key (the member's name without `.npy`).
  - HDF5, NeXus, HyperSpy, MATLAB 7.3: h5py, a walk of the file's objects in name order: every attribute of the file, its groups and datasets, each dataset's shape and dtype, and the value of each scalar (shape `()`) dataset, as flat dotted paths; values through the shared check `textual`; links to other files not followed, nothing read from outside the file (virtual datasets, external storage); opened without file locking and with readahead off; the walk stops at 1,000 entries (the storage's limit per dict), 5,000 objects or after 20 seconds and says so in the mapped values. NeXus's `NX_class` attributes are values like any other.
  - MATLAB 5 and 4: SciPy (`matfile_version`, `whosmat`): the header text and each variable's shape and class; MATLAB 7.3 the header text and the HDF5 walk, without MATLAB's internal groups `#refs#` and `#subsystem#`.
  - Notebooks: nbformat: the notebook's metadata (kernelspec, language_info, …) and its nbformat version as found, but a skip list of editor state (`widgets`, `toc`, `varInspector`, `vscode`); cell counts by type and the first Markdown heading as mapped values; no outputs. A notebook over 8 MiB is not read whole: its metadata comes from its last 64 KiB (Jupyter writes the keys sorted, the notebook's metadata after the cells), without cell counts.
  - Python scripts: `ast`, never executed: the shebang, the module docstring, the module-level dunder assignments of literals (`__version__`, `__author__`, …; PEP 8, "Module Level Dunder Names"), the imported module names as written; a file over 1 MiB, or one Python 3.14 cannot parse (Python 2), gives its shebang and the reason.
  - Pickles: the protocol number from the PROTO opcode; never unpickled.
- **Summary lines**: a few chosen entries as found (checklist): `.npy` its shape and dtype; HDF5 a NeXus entry's `title`, `start_time` and `definition`, a HyperSpy signal's title, signal type and data shape; MATLAB the header text; notebooks the first heading and the kernel's display name; scripts the docstring's first line; pickles the protocol.

## Assumptions and leans (the person was not asked; @weber reviews tomorrow)

- **A1** RosettaSciIO is not used for `.hspy`. Evidence: its `hspy.file_reader(lazy=True)` (0.15.0) reads a signal in the metadata (`_sig_variance`, HyperSpy's noise variance) whole: 32,072,162 bytes of a 64 MB file whose variance is 32 MB (`scratchpad/pyd/hspy_lazy.py`). The h5py walk gives HyperSpy's attributes as the file stores them, HyperSpy's own encodings (`_list_`, `_sig_`) included, without the HyperSpy-internal `_HyperSpy` groups and the placeholder `_None_` (skip list). Recorded in BACKLOG, "Sync with upstream".
- **A2** Scalar datasets are read (deviation from the brief's "never reading dataset values"): NeXus keeps its descriptive metadata (`title`, `start_time`, `definition`) in scalar datasets, a few bytes each; arrays are never read.
- **A3** Zarr stores get no extraction from this part: the core's `zarr/zarr` produces the store's dataset, the extractor belongs to the format that produced it, and the collapsed dataset has no members, so its stamp would not see a change of `.zattrs` (`formats/__init__.py`: `Extraction.extractor` is the format id; `_fill`). `.zspy` directories are Zarr stores and stay with the core; the one `.zspy` file stays as the core types it. Raised as an open question rather than changing the core.
- **A4** No `zarr`, no RosettaSciIO dependency here (A1, A3). New dependencies: `numpy`, `h5py`, `scipy`, `nbformat`, pinned exactly.
- **A5** HDF5 attribute names and dataset paths as dotted paths (`entry.data.data.shape`): the brief's and checklist's form; an attribute of a dataset named `shape` or `dtype` would take the place of the computed one (none seen).

## Review (independent, of 60a5f619..8b5d7476)

Applied: (1, blocker, security) a scalar dataset with external raw storage and a virtual dataset put data of other files into the record, and the shape of an unlimited virtual dataset opened its sources: the creation property list now decides first (requirement "Nothing is read from outside the file"); (2) attributes are listed only as far as entries can still be kept; (3) a walk of its own instead of `visititems`: at most 5,000 objects, each once by address, hard links only, skipped groups not entered; (4) a scalar or attribute is read only when one element takes at most 4,000 bytes and is not of an array type; (5) `.npy` headers up to 1 MiB; (6) "notebook metadata not found in the tail"; (7) the time limit as a third of the extractor's; (8) dtypes as NumPy's descr; (9) imports in source order, the 16-item limit stated; (10) `.hspy` checked for HyperSpy in its first 4 KiB, known limits in the spec's purpose; (11) the reproduction in the BACKLOG. With the merge of `crawler` (common-structured): every value through the shared `credential` check too (requirement "Credentials are left out").

## Out of scope

Reading arrays or chunks; following HDF5 external or soft links; Zarr attributes (A3); interpreting NeXus application definitions; EMD (Velox, Berkeley) as formats of their own (they get the generic HDF5 walk); `.pyc`; unpickling.

Behaviour towards the user: files of these types are typed as what they are (`dc:format`, the subject) instead of `application/octet-stream`, `text/plain`, `application/zip` or `application/x-hdf`, and their records gain a summary line and the `name: value` lines of their metadata. HDF5 files other than `.h5`/`.hdf5`/`.hdf` (`.emd`, …) are typed HDF5 by content. Each of these files is opened once per crawl in which it changed (and once after this change, the new extractor identity), reading its header or metadata only.

## Capabilities

### New Capabilities
- `formats/pydata`: recognition and metadata extraction of NumPy, HDF5 (with NeXus, HyperSpy, MATLAB 7.3), MATLAB, Jupyter notebook, Python script and pickle files.

## Impact

`python/modama-formats-common/`: `src/modama_formats_common/pydata/` (rules, formats, fixtures, tests), one import and one `PARTS` entry, README rows, four dependencies. `python/crawler/BACKLOG.md`: one item under "Sync with upstream" (A1), one open point (A3). `/ruff.toml`: `**/tests/fixtures` excluded, so that ruff neither lints nor reformats wild test files (nbformat's version 3 notebook, scripts with a shebang).

Fixture licences: the package is MIT; its fixtures include RosettaSciIO's (GPL-3.0-or-later, as in `modama-formats-em`), the NeXus manual's (LGPL-3.0 by the README of `nexusformat/definitions`, whose licence GitHub does not detect), SciPy's, h5py's and nbformat's (BSD-3-Clause); texts in `pydata/tests/licences/`.
