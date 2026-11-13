# Direct Electron acquisitions: which files belong together

Research of 2026-11-13 (@weber, from a browse snapshot: "`20200821_92978_info.txt`, `_movie.mrc`, `_processing.log` seem to belong together. Can you research if that is a common pattern … In that case the three become one dataset"). Sources fetched on that day; what could not be verified is marked.

## For @weber

- **Answer:** yes, this is an established convention. Direct Electron's DE-Server (the camera server software for DE-16, DE-64, Apollo, Celeritas and others) gives every acquisition a **Dataset Name** of the form `YYYYMMDD_NNNNN` and puts it at the start of every autosaved file: `_movie.mrc|.de5|.tif|.hspy` (the frame stack), `_info.txt` (all server properties as `key = value`), `_final.mrc` (the summed image), `_ext<n>_<name>.mrc`, `_<n>_<name>_<calc>.mrc` (virtual STEM images) and `_scan_coordinates.csv`.
- **Rule:** in one folder, the files `^(\d{8})_(\d+)(_suffix)?_…` that share `date_number` are one acquisition. The anchor is `*_movie.<ext>`, and the `_info.txt` holds the metadata. Both RosettaSciIO's reader (`find_related_de_files`) and DE's own tests group files exactly this way.
- **Example:** `20241021_00405_movie.mrc`, `_info.txt`, `_final.mrc`, `_ext1_Ext 1.mrc`, `_0_Virt 0_sum.mrc` and `_1_Virt 1_sum.mrc` in RosettaSciIO's test data. That `_info.txt` contains `Dataset Name = 20241021_00405` and `Autosave Movie Frames File Path = …\20241021_00405_movie.mrc`.
- **The number:** it is the server's acquisition counter, zero-padded. In the example `Acquisition Counter = 406` and the dataset is `00405`. That is my inference from one file, not documented.
- **Not verified: `_processing.log`.** I found no public source for it. It is not among the autosave paths of DE-Server 2.7.x, where the server log goes to a separate `File Path - Log` folder. It is probably an older (2020) DE-Server per-dataset log. Adding it to the group by its prefix is safe, but no document names it.
- **Readers:** LiberTEM's MRC reader ignores `_info.txt` (open issue #1675, which is why it gets the scan shape wrong). RosettaSciIO/HyperSpy reads it automatically together with the movie. So reading the info.txt with the movie is established practice, and the triple is one dataset by an established convention.

## Details with sources

### 1. Who writes it and what the files hold
- **Software:** Direct Electron's DE-Server. The `_info.txt` files start with `Server Software Version = 2.7.4.10190` and `2.7.2.9048` (RosettaSciIO test data, see below). DE's Python client `deapi` ("API for DE Server", https://pypi.org/project/deapi/, https://github.com/directelectron/deapi) sets `Autosave Movie`, `Autosave Directory` and `Autosave 4D File Format` (MRC/DE5/HSPY), then globs `*movie.<fmt>`: `deapi/tests/test_file_saving/test_file_loading_libertem.py` and `test_file_loading_rsciio.py` (commit e16b2ff). A test in that repo (`deapi/tests/test_insitu/test_start_stop.py`) globs `*movie.mrc`.
- **Real info.txt (DE-Server 2.7.4, simulated camera "DESim"):** https://raw.githubusercontent.com/hyperspy/rosettasciio/main/rsciio/tests/data/mrc/20241021_00405_info.txt (552 lines, `key = value`, padded with spaces). Fields relevant here:
  - Camera and time: `Camera Model`, `Timestamp (seconds since Epoch)` (1729539410 = 2024-10-21T19:36:50Z, which matches the date prefix).
  - Dose and exposure: `Exposure Time (seconds)`, `Exposure Rate (e-/pix/s)`, `Frames Per Second`, `Frame Exposure Time (nanoseconds)`, `ADUs Per Electron`.
  - Microscope: `Instrument Accelerating Voltage (V)`.
  - Pixel sizes and image size: `Specimen Pixel Size X/Y (nanometers)`, `Diffraction Pixel Size X/Y`, `Image Size X/Y (pixels)`.
  - Scan: `Scan - Enable/Type/Size X/Size Y`.
  - Processing: `Image Processing - *` (gain applied, bad-pixel correction, motion correction, mode Integrating/Counting).
  - Frame counts: `Number of Frames Grabbed/Processed`, `Autosave Movie Sum Count`, `Autosave Final Image Sum Count`.
  - Grouping: `Dataset Name`, `Acquisition Counter`, and one `Autosave … File Path` per output file.
- **Older file (2.7.2, CeleritasXS):** https://raw.githubusercontent.com/hyperspy/rosettasciio/main/rsciio/tests/data/mrc/info.txt has `Dataset Name = 20230925_01497` and `Autosave Movie Frames File Path = D:\DEOutput\CeleritasXS\20230925_01497_movie.de5`.
- **Your file:** `20200821_92978_info.txt` has 82 lines and 2.8 kB, against 250 to 550 lines for 2023/2024. That fits an older DE-Server version. Its own `Server Software Version` line would settle it, but I could not read the file (it is not on this machine).
- **`_processing.log`:** not verified (several searches, DE repos grepped, no hit). Its content is unknown. Reading the file itself is the next step.

### 2. Other suffixes, date and number
- **Suffixes, from the 2.7.4 info.txt autosave paths:** `_movie.<fmt>`, `_final.mrc`, `_ext<n>_<Name>.mrc`, `_<n>_<VirtName>_<calc>.mrc`, plus empty slots `Autosave Final Motion Corrected Image File Path` and `Autosave Crude Frames File Path`. The scan positions file `_scan_coordinates.csv` comes from RosettaSciIO's regex and test files `Custom_scan_coordinates.csv` and `ROI_Random_Scan_scan_coordinates.csv`, listed at https://api.github.com/repos/hyperspy/rosettasciio/contents/rsciio/tests/data/mrc.
- **Not DE autosave names:** `_sum.mrc`, `_gain.mrc` and `_dark.mrc` do not appear in any DE source I found. DE's sum is `_final`. Gain and dark references live in the server's reference store, not next to the dataset (not verified further).
- **Formats:** MRC, DE5 (HDF5), HSPY in current versions (deapi tests). TIFF and HDF in the older SerialEM DE panel: https://bio3d.colorado.edu/SerialEM/betaHlp/html/hidd_detoolpanel.htm.
- **`Autosave Filename Suffix`:** a user-set string inserted after the number (`date_num_suffix_movie.mrc`). See https://hyperspy.org/rosettasciio/supported_formats/mrc.html ("uniqueid_suffix_movie.mrc") and SerialEM's DE property list http://bio3d.colorado.edu/SerialEM/SerialEM/Docs/DEserverProperties.txt (`Autosave Filename Suffix`, `Autosave Previous Dataset Name (2.3 on): 2.5 -> Dataset Name`).
- **Date:** local acquisition date YYYYMMDD. It matches the Timestamp in both files.
- **Number:** 5-digit zero-padded acquisition counter (00405 next to `Acquisition Counter = 406`). This is an inference, not documented.

### 3. Downstream tools
- **RosettaSciIO/HyperSpy:** `rsciio/mrc/_api.py`, https://raw.githubusercontent.com/hyperspy/rosettasciio/main/rsciio/mrc/_api.py.
  - `MOVIE_RE = ^(\d{8})_(\d+)(?:_(.+?))?(?:_(\d+))?_movie\.mrc$`.
  - `find_related_de_files` globs `{date}_{acq}_*` for info.txt, virtual images, external images and the scan CSV.
  - `read_de_metadata_file` parses `key = value` and takes the navigation shape, pixel sizes, fps and gain from it.
  - Added in PR #162 (CSSFrancis, merged 2023-11-29): https://github.com/hyperspy/rosettasciio/pull/162.
- **LiberTEM:** the MRC reader was added in PR #873 (sk1p, merged 2020-09-21, https://github.com/LiberTEM/LiberTEM/pull/873). A tester there describes using a camera's movie mode for 4D STEM, without naming the vendor. Issue #152 (https://github.com/LiberTEM/LiberTEM/issues/152) was requested by, among others, a Direct Electron person.
  - `tests/io/datasets/test_mrc.py` uses `mrc/20200821_92978_movie.mrc`, expects shape (4, 1024, 1024) and reads no sidecar.
  - Issue #1675 (open, https://github.com/LiberTEM/LiberTEM/issues/1675): LiberTEM ignores `_info.txt`. sk1p proposed reading it, and it is not implemented. DE's own test skips MRC with "MRC file loading in LiberTEM is broken!". DE5 support came in LiberTEM PR #704 (changelog).
- **Test data:** a public listing of LiberTEM's test data or a README for it was not found. Tests take it from `TESTDATA_BASE_PATH`.
- **Cryo-EM SPA tools:** no RELION or cryoSPARC docs mentioning DE `_info.txt` were found. Not verified.

### 4. Other sidecar patterns
- **EPU (Thermo Fisher).** No official spec found, so these are facility and processing-software docs.
  - SLAC S2C2 (https://s2c2.slac.stanford.edu/user-access-information-and-process/user-information/data-access-and-transfer): "Each image acquisition in EPU results in six files". They are an unaligned sum (.mrc/.tiff) with a .jpg, the raw stack with "Fractions" appended, two XMLs (stack and sum) and a .dm5 checksum. Pattern: `FoilHole_[Hole ID]_Data_[Acquisition Area ID]_[date]_[time].mrc`, example `FoilHole_31545690_Data_31547881_31547882_20190601_081945.mrc`.
  - cryoSPARC (https://guide.cryosparc.com/processing-data/tutorials-and-case-studies/tutorial-epu-afis-beam-shift-import): "Each EER movie has a corresponding xml file". It is matched by trimming `_EER.eer` and `.xml`, both in `.../Data/`.
  - A cryoSPARC forum thread reports that newer EPU versions add an AFIS group to the name (https://discuss.cryosparc.com/t/error-importing-afis-beamtilt-groups/16682).
  - Session-level files `EpuSession.dm` and `Metadata/GridSquare_*.dm`: Diamond's smartem-decisions docs (https://diamondlightsource.github.io/smartem-decisions/main/explanations/epu-data-structures.html, seen in search results but 404 when fetched, so not verified by me).
- **SerialEM:** the .mdoc "has the same name as the image file, with the additional extension '.mdoc'" (`x.mrc.mdoc`). `SubFramePath` points to the frames file. See https://bio3d.colorado.edu/SerialEM/hlp/html/about_formats.htm, which also covers `.idoc` for TIFF series.
- **IMOD:** raw stacks use ".st or an extension indicating the format". Dual-axis stacks "have a common, root name that ends in a and b" (`BBa.st`, `BBb.st`), and derived files reuse the root (`BBa.prexf`). See https://bio3d.colorado.edu/imod/doc/etomoTutorial.html. copytomocoms `-name` is the "Root name of data set" and can take angles from a `.rawtlt` file (https://bio3d.colorado.edu/imod/doc/man/copytomocoms.html). The man page does not spell out `root.rawtlt`, so I did not verify it.

### Not verified
- Content and origin of `_processing.log`, and the DE-Server version that wrote the 2020 triple.
- Official DE or Thermo manuals: not public, or not found.
- That the number is the acquisition counter: inferred from one file.

Downloaded for reading only (nothing written to the repo): `/tmp/claude-20335/-workspaces-data-management-system/f4ef3cf6-7a17-407c-bf3a-0de6b20fd28c/scratchpad/dl/de_info.txt` and `/tmp/claude-20335/-workspaces-data-management-system/f4ef3cf6-7a17-407c-bf3a-0de6b20fd28c/scratchpad/dl/info_old.txt`. The cloned repos are under `/tmp/claude-20335/-workspaces-data-management-system/f4ef3cf6-7a17-407c-bf3a-0de6b20fd28c/scratchpad/src/`.