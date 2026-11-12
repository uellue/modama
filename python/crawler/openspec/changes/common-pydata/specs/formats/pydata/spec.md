# Spec Delta

## Purpose

Python and data-science files (NumPy arrays and archives, HDF5 with NeXus, HyperSpy and MATLAB 7.3, MATLAB, Jupyter notebooks, Python scripts, pickles) typed as what they are and described by what their headers and metadata say, read with the field's readers and never by reading their arrays.

## ADDED Requirements

### Requirement: NumPy array files are typed by content
A file starting with the NumPy magic `\x93NUMPY` SHALL be typed `application/x-npy`, whatever its name, and be a dataset of the format `common/npy`.

#### Scenario: A NumPy array file
- **WHEN** a directory holds `frames.npy` written by `numpy.save` and the same file named `frames.bin`
- **THEN** both are datasets of type `application/x-npy`

### Requirement: A NumPy array file is described by its header
The extractor of `common/npy` SHALL read the file's header only, through `numpy.lib.format`, and give as `original_metadata` the header's `descr`, `fortran_order` and `shape` and the format `version`, as `mapped_metadata` NumPy's `dtype`, and as the summary line `shape` with the shape, the dtype, and `fortran_order True` when it is true.

#### Scenario: The header only
- **WHEN** an `.npy` file of 8 MB holding a 1000 × 1000 array of `float64` in Fortran order is extracted
- **THEN** the summary is `shape [1000, 1000], float64, fortran_order True`, `original_metadata` is `descr <f8`, `fortran_order true`, `shape [1000, 1000]`, `version 1.0`, and fewer than 4,096 bytes are read

### Requirement: A NumPy archive is described by its arrays' headers
A file named `*.npz` that starts as a ZIP SHALL be a dataset of type `application/x.npz`; one that does not SHALL lose that type. Its extractor SHALL read the ZIP's directory and the header of each `.npy` member, never an array, and give each array's `descr`, `fortran_order` and `shape` under NumPy's key for it (the member's name without `.npy`), as `<key>.shape` and so on; the summary line SHALL give `<key>.shape` with the shape for the first 16 arrays.

#### Scenario: Stored and compressed archives
- **WHEN** an archive written by `numpy.savez` with arrays `image` (512 × 512 `uint16`) and `energy` (2048 `float32`) and one written by `numpy.savez_compressed` with the same arrays are extracted
- **THEN** both give `image.shape [512, 512]`, `image.descr <u2`, `energy.shape [2048]`, and each reads less than a tenth of its file

#### Scenario: A text file named like an archive
- **WHEN** a text file is named `notes.npz`
- **THEN** it is not a dataset of type `application/x.npz`, and its basis says it is no ZIP

### Requirement: HDF5 files are typed by content
A file with the HDF5 signature at offset 0 or 512 (after a user block, as MATLAB 7.3 writes it) SHALL be typed `application/vnd.hdfgroup.hdf5` (a subclass of `application/x-hdf`), whatever its name, and be a dataset of the format `common/hdf5`; a file with the HDF4 signature keeps `application/x-hdf`.

#### Scenario: HDF5 whatever the name
- **WHEN** a directory holds HDF5 files named `scan.h5`, `velox.emd` and `old.hdf`, one with a user block of 512 bytes named `blocked.h5`, and an HDF4 file named `legacy.hdf`
- **THEN** the four HDF5 files are of type `application/vnd.hdfgroup.hdf5` and `legacy.hdf` is of type `application/x-hdf`

### Requirement: NeXus and HyperSpy files are HDF5 files of their name
A file named `*.nxs` SHALL be typed `application/x.nexus` and one named `*.hspy` `application/x.hspy`, both subclasses of HDF5, when it starts with the HDF5 signature; one that does not SHALL lose that type.

#### Scenario: A NeXus file and a HyperSpy file
- **WHEN** a directory holds the NeXus example file renamed `example.nxs` and RosettaSciIO's test file `example2_v3.1.hspy`
- **THEN** they are datasets of type `application/x.nexus` and `application/x.hspy`

#### Scenario: A text file named like a NeXus file
- **WHEN** a text file is named `notes.nxs`
- **THEN** it is not of type `application/x.nexus`, and its basis says it has no HDF5 signature

### Requirement: An HDF5 file is described by a walk of its objects
The extractor of the HDF5 types SHALL walk the file's objects with h5py in name order and give as `original_metadata`, with dotted names: every attribute of the file, its groups and datasets (`group.dataset.name`); each dataset's `shape` and `dtype`; each scalar dataset's value (`entry.title`). Values as found, text bytes decoded as UTF-8, an empty attribute as `""`; left out: what h5py cannot read and what is not suitable for text (`textual`).

#### Scenario: A NeXus file's attributes and datasets
- **WHEN** the NeXus example file `simple_example_basic.nexus.hdf5` is extracted
- **THEN** `original_metadata` has `creator simple_example_basic_write.py`, `entry.NX_class NXentry`, `entry.mr_scan.mr_indices [0]`, `entry.mr_scan.I00.shape [31]`, `entry.mr_scan.I00.dtype int32`, `entry.mr_scan.I00.units counts` and `entry.title` with its value, and the summary starts with that title

#### Scenario: An attribute nobody has seen before
- **WHEN** an HDF5 file has an attribute `never_seen_before` on a group `g` and an empty attribute `blank`
- **THEN** `original_metadata` has `g.never_seen_before` with its value and `blank` as `""`

#### Scenario: Values not suitable for text
- **WHEN** an HDF5 file has an attribute of 100 numbers, an opaque attribute of bytes and a scalar dataset of a string over 1,000 characters
- **THEN** none of them is in `original_metadata`, and the attribute of 100 numbers is not read

### Requirement: The walk of an HDF5 file is bounded
The extractor SHALL open the file without file locking and with readahead off, SHALL never read a dataset of more than one element, nor follow an external link, and SHALL stop the walk at 1,000 entries or after 20 seconds; `mapped_metadata.walk` SHALL then say which limit cut it.

#### Scenario: Arrays are never read
- **WHEN** an HDF5 file of 32 MB holding one array dataset with attributes is extracted
- **THEN** its shape, dtype and attributes are given, and fewer than 256 KiB are read

#### Scenario: The walk stops at 1,000 entries
- **WHEN** an HDF5 file has 1,500 groups with one attribute each
- **THEN** `original_metadata` has 1,000 entries, and `mapped_metadata.walk` says that the entry limit of 1,000 cut it

#### Scenario: The walk stops after its time
- **WHEN** the walk's time is up before the walk ends
- **THEN** the entries found so far are given, and `mapped_metadata.walk` says that the time limit cut it

#### Scenario: External links are not followed
- **WHEN** an HDF5 file links a dataset in another HDF5 file beside it
- **THEN** nothing of the other file is in `original_metadata`, not even the link's name

### Requirement: A HyperSpy file is described as HyperSpy stores it
An HDF5 file whose attribute `file_format` is `HyperSpy` (a `.hspy` file, or an older HyperSpy `.hdf5` file) SHALL be described by the HDF5 walk, with HyperSpy's names as stored (`_list_`, `_sig_`), but a skip list: HyperSpy's internal groups `_HyperSpy` and values that are HyperSpy's placeholder `_None_`. Its summary line SHALL give the first signal's title, signal type and data shape.

#### Scenario: RosettaSciIO's test file
- **WHEN** `example2_v3.1.hspy` is extracted
- **THEN** the summary is `test_diffraction_pattern, shape [16, 16]` (the signal type is empty), `original_metadata` has `file_format HyperSpy` and `Experiments.test_diffraction_pattern.metadata.Acquisition_instrument.TEM.microscope FEI Tecnai`, and no name with `_HyperSpy` and no value `_None_`

#### Scenario: A variance signal in the metadata
- **WHEN** a HyperSpy file holds a 32 MB variance signal under `metadata.Signal.Noise_properties._sig_variance`
- **THEN** its shape, dtype and attributes are given, and fewer than 256 KiB are read

### Requirement: MATLAB files are checked by their start
A file named `*.mat` SHALL be typed `application/x-matlab-data` when it starts with `MATLAB` or has a zero byte in its first 4 bytes (a version 4 file, as SciPy's `matfile_version` decides); one that does not SHALL lose that type.

#### Scenario: A text file named like a MATLAB file
- **WHEN** a text file is named `notes.mat`
- **THEN** it is not of type `application/x-matlab-data`

### Requirement: A MATLAB file is described by its header and its variables
The extractor SHALL give the header text as found (`header`: the first 116 bytes without trailing spaces and NUL bytes, as SciPy strips them; versions 5 and 7.3) and the variables: for versions 4 and 5 each one's `shape` and `class` from SciPy's `whosmat`, for version 7.3 the HDF5 walk without MATLAB's internal groups `#refs#` and `#subsystem#`. The summary line SHALL be the header text.

#### Scenario: A MATLAB 5 file
- **WHEN** SciPy's test file `testmulti_7.4_GLNX86.mat`, written by MATLAB 7.4, is extracted
- **THEN** the summary is its header text, as written (`MATLAB 5.0 MAT-file, Platform: GLNX86, Created on: …`), and `original_metadata` has `theta.shape`, `theta.class` and `a.shape`, `a.class`, also with `TZ=Europe/Berlin`

#### Scenario: A MATLAB 7.3 file
- **WHEN** SciPy's test file `testhdf5_7.4_GLNX86.mat` and a version 7.3 file with a `#refs#` group are extracted
- **THEN** each gives its header text and its variables' `shape`, `dtype` and `MATLAB_class`, and no name starting with `#refs#`

#### Scenario: A MATLAB 4 file
- **WHEN** SciPy's test file `testdouble_4.2c_SOL2.mat` is extracted
- **THEN** `original_metadata` has `testdouble.shape [1, 9]` and `testdouble.class double`, and no header

### Requirement: Notebooks are checked by their start
A file of type `application/x-ipynb+json` whose first character but white space is `{` SHALL be a dataset of the format `common/notebook`; one whose first character is another SHALL lose that type.

#### Scenario: A file named like a notebook that is not JSON
- **WHEN** a text file not starting with `{` is named `notes.ipynb`
- **THEN** it is not of type `application/x-ipynb+json`

### Requirement: A Jupyter notebook is described by its metadata and its cells
The extractor SHALL give as `original_metadata` the notebook's `metadata`, flattened, and `nbformat` and `nbformat_minor`, as found, but a skip list of editor state (`widgets`, `toc`, `varInspector`, `vscode`); as `mapped_metadata` the number of cells per type (`cells.code` …) and the first Markdown heading (`first_heading`) of the notebook converted to version 4 by nbformat; no source or output otherwise. The summary line SHALL be the first heading and the kernel's display name.

#### Scenario: A version 4 notebook
- **WHEN** nbformat's test file `test4.5.ipynb` is extracted
- **THEN** `original_metadata` has its kernelspec and language_info and `nbformat 4`, `mapped_metadata` its cell counts and first heading, and no value holds an output

#### Scenario: A version 3 notebook
- **WHEN** nbformat's test file `test3.ipynb` is extracted
- **THEN** `nbformat` is 3 in `original_metadata`, and `mapped_metadata` has its cells counted after nbformat's conversion, its heading cells as Markdown

#### Scenario: Editor state
- **WHEN** a notebook's metadata has `widgets` and `toc` beside `kernelspec`
- **THEN** `original_metadata` has the kernelspec and nothing under `widgets` or `toc`

### Requirement: A large notebook is read at its end only
A notebook of more than 8 MiB SHALL be read at its end only (64 KiB): its metadata as Jupyter writes it, after the cells, without cell counts; `mapped_metadata.read` says so.

#### Scenario: A large notebook
- **WHEN** a notebook larger than the limit is extracted
- **THEN** its metadata is given, no cell counts, `mapped_metadata.read` says why, and at most 64 KiB are read

### Requirement: A Python script is described by its source, never run
The extractor of `text/x-python` and `text/x-python3` files SHALL parse the source with `ast`, never executing it, and give as `original_metadata` the shebang line (`shebang`), the module docstring (`docstring`), each module-level assignment of a literal to a dunder name (`__version__` …), and the imported module names in the order first found (`imports`, relative ones with their dots). The summary line SHALL be the docstring's first line.

#### Scenario: A script
- **WHEN** a script with a shebang, a docstring, `__version__ = "1.2"`, `__author__`, imports of `os`, `numpy as np` and `from .tools import x`, and code that writes a file when run, is extracted
- **THEN** all of these are in `original_metadata` (`imports ["os", "numpy", ".tools"]`), the summary is the docstring's first line, and the file the code would write does not exist

### Requirement: A script that cannot be parsed gives its shebang and the reason
The extractor SHALL read at most 1 MiB. A larger file, or one that Python cannot parse (Python 2), SHALL give its shebang and, in `mapped_metadata.not_parsed`, the reason.

#### Scenario: A Python 2 script
- **WHEN** a script with `print "hello"` and a shebang is extracted
- **THEN** `original_metadata` has the shebang, and `mapped_metadata.not_parsed` names the syntax error and its line

#### Scenario: A large script
- **WHEN** a script of more than 1 MiB is extracted
- **THEN** only its shebang is given, `mapped_metadata.not_parsed` says it is larger than 1 MiB, and at most 1 MiB and a byte are read

### Requirement: A pickle is recognised, never unpickled
A file named `*.pkl` or `*.pickle`, or starting as a pickle of protocol 2 to 5 does (Apache Tika's magic), SHALL be typed `application/x-python-pickle` when it starts with the PROTO opcode of protocol 2 to 5; one named so that does not SHALL lose that type. The extractor SHALL give the protocol (`protocol`) and the summary `protocol <n>`, from the file's first two bytes, and SHALL never unpickle it.

#### Scenario: A pickle
- **WHEN** a pickle of protocol 4 whose unpickling would write a file is named `state.pkl`
- **THEN** it is of type `application/x-python-pickle`, its summary is `protocol 4`, and the file is not written

#### Scenario: A protocol 0 pickle
- **WHEN** a pickle of protocol 0 (text) is named `old.pkl`
- **THEN** it is not of type `application/x-python-pickle`, and its basis says it has no protocol 2 to 5 start
