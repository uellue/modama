# Design: Direct Electron acquisitions (`em/de`)

## D1 What each file holds, and what RosettaSciIO makes of it (decision 302)

Files read on 2026-11-13, nothing copied into the repository:

- RosettaSciIO's test data at tag `v0.15.0` (`rsciio/tests/data/mrc/`, repository licence GPL-3.0, `COPYING.txt`): `20241021_00405_*` (DE-Server 2.7.4.10190 Debug Build, simulated camera DESim: `_info.txt` of 552 entries, `_movie.mrc`, `_final.mrc`, `_ext1_Ext 1.mrc`, `_0_Virt 0_sum.mrc`, `_1_Virt 1_sum.mrc`), `info.txt` (2.7.2.9048, CeleritasXS, 252 entries, CRLF line ends, its movie a `.de5` not in the data), `Custom_*` and `ROI_Random_Scan_*` (2.7.5.10756, DESim, 326 entries, scans of type `XY File` and `Random` with `_scan_coordinates.csv`). RosettaSciIO renamed some of them: the `_info.txt` of `20241021_00405` names `…_ext1_Ext #1.mrc` and `…_0_Virt #0_total_sum.mrc`, and `Custom_info.txt` names `20250429_06699_0_movie.mrc`.
- Read with RosettaSciIO 0.15.0 (the em package's pin): `rsciio.mrc.file_reader(movie, lazy=True)` and `rsciio.mrc._api.read_de_metadata_file(info)`; the MRC headers with a plain `struct` parse of the first 1024 bytes.
- The tree's own acquisition, `20200821_92978` (LiberTEM's test data: `_info.txt` 2,778 bytes, `_movie.mrc` 18,874,368 bytes, `_processing.log` 6,720 bytes, sizes from the private listing): pending @weber's copy (Q2, Q4). Its movie's size is 18 MiB, 2 MiB more than LiberTEM's shape (4, 1024, 1024) needs in 32 bits: whether that is an extended header or another data type, its header will say.

| What | `_info.txt` key (2.7.2 / 2.7.4 / 2.7.5) | RosettaSciIO `original_metadata` | RosettaSciIO mapped | `_movie.mrc` header | Search |
|---|---|---|---|---|---|
| Software version | `Server Software Version` (`2.7.2.9048` / `2.7.4.10190 (Debug Build)` / `2.7.5.10756`), the first line of every file | kept | not mapped | — | yes |
| Camera | `Camera Model`, `Camera Name`, `Camera SN` (`CeleritasXS`, SN `812` / `DESim` / `DESim`) | kept | `TEM.detector` = `Camera Model` | — | yes |
| Date and time | `Timestamp (seconds since Epoch)` in all; `Local time` (`Mon Oct 21 14:36:50 2024`) in 2.7.4 only | kept | `General.timestamp` = the epoch seconds as a string, not a date | — | yes |
| Acquisition | `Dataset Name` (`20230925_01497`, `20241021_00405`, `20250429_06699`), the file name's prefix; `Acquisition Counter` (not in 2.7.2) | kept | not mapped | — | grouping |
| Processing mode | `Image Processing - Mode` (`Integrating` in every file seen; the presets name `Counting` too), `Image Processing - …` (gain, bad pixels, motion correction), `Event Counting - …` | kept | not mapped | `mode` 6 (16-bit) for the movie, 2 (float) for sums: the pixel format, not the mode | yes |
| Voltage | `Instrument Accelerating Voltage (V)` (`300000`; missing in 2.7.2) | kept | not mapped | — | yes |
| Magnification, camera length | `Instrument Project Magnification` (`1000`, `-1`), `Instrument Project Camera Length (centimeters)` (`0.1`, `-1`): `-1` where the microscope did not say | kept | `TEM.magnification` as a string, `-1` included; the camera length only to decide "diffracting" | — | some |
| Exposure | `Exposure Time (seconds)` (`0.3325952` / `0.045712` / `30`), `Frame Exposure Time (nanoseconds)` (2.7.4) | kept | not mapped | — | yes |
| Dose | `Exposure Rate (e-/pix/s)` (`-49261.08203125` / `212.755735` / `22.994363`), `Faraday Plate - …` (dose and beam intensity: values in 2.7.2, 0 or 1 in 2.7.4 and 2.7.5) | kept | not mapped | — | yes |
| Frame rate | `Frames Per Second` (`40000` / `700` / `1`) | kept | `TEM.frames_per_second` as a string | — | yes |
| Frames | `Frame Count`, `Autosave Movie Frames Written` (`16384` / `32` / `30`) | kept | not mapped (the time axis from the MRC header) | `nz` (32, 30) | yes |
| Frame size | `Image Size X (pixels)`, `… Y` (`128` / `8`×`4` / `16`), `Sensor Size …`, `Binning …`, `Crop …` | kept | sizes of the signal axes | `nx`, `ny` | yes |
| Pixel size | `Specimen Pixel Size X (nanometers)`, `… Y` (`10` / `0.1`, `0.2` / `-1`); `Diffraction Pixel Size X`, `… Y` without a unit in the key (`-1` / `0.1` / missing) | kept | every axis scale set to 1 (`axes_scales[axes_scales != -1] = 1`), so the pixel sizes are lost; units `nm` and `nm^-1` assigned, the latter not in the file | cell `-80` × `-40` Å for 8 × 4 pixels (−10 × the size: not calibrated) | yes |
| Scan | `Scan - Enable`, `Scan - Type` (`Raster` / `Raster` / `XY File`, `Random`), `Scan - Size X`, `… Y` (8×32 / 8×4 / 5×5), `Scan - ROI …`, `Scan - Dwell Time (microseconds)`, `Scan - Points`, `Scan - Repeats` | kept | navigation axes with the sizes, the ROI honoured; for `XY File` and `Random` a `ValueError` unless handed the scan coordinate file, which it reads whole (`np.loadtxt`); sizes then as strings | — | yes |
| Electron gain | `ADUs Per Electron Bin1x` (`300`, 2.7.2) or `ADUs Per Electron` (`51`, 2.7.4) | kept | `gain_factor` = 1 / `ADUs Per Electron Bin1x`: 1.0 for 2.7.4, whose key has another name | — | little |
| Output files | `Autosave … File Path` (paths on the camera PC), `Autosave Movie File Format` (`DE5` / `MRC`), `Autosave Filename Suffix` (empty in all) | kept | not used: the files are found by globs (`find_related_de_files`) | — | no |
| Virtual detectors | `Scan - Virtual Detector n …` (shape, size, calculation) | kept | the virtual and external images read whole as navigators, their names crosswise (`_sig_Virt 1` holds `…_0_Virt 0_sum.mrc`: names in glob order, files sorted) | — | little |
| Computer and server | `Computer Name`, `Server IP Addresss`, `File Path - …`, `Computer GPU Info`, `Server Process ID` | kept | not mapped | — | no |
| Option lists | `… Allowed Values` (`300000,200000,120000,80000,0`), `Preset - List`, `Scan - Preset List`, `Scan - Virtual Detector Preset List` | kept | not mapped | — | no: user interface |
| MRC header only | — | `std_header` (`EXTRA` as hex, hiding `nversion` 20140) | — | no labels, no extended header (`next` 0, `exttyp` empty), `dmin` 2 > `dmax` 1 and `rms` −1 (statistics not computed), `ispg` 1, machine stamp `44 44` | no |
| `_processing.log` | pending (Q4) | not read | — | — | ? |

What follows:

- **RosettaSciIO keeps every entry**: its `de_metadata` equals a plain parse (split at the first `=`, strip both sides) on all five public files (252 to 552 entries, CRLF or LF). It would drop a line with two `=` (none seen) and decodes in the locale's encoding (all files seen are ASCII).
- **Its mapping adds little and gets some of it wrong**: the list above (strings, scales 1, units not in the file, the gain's key, the non-raster `ValueError`); also `Scan - Time (seconds)` and `Scan - Repeat Delay (seconds)` are joined as strings before `float` (masked by the scale bug). For the `BACKLOG.md` list "Sync with upstream", as *found*.
- **Reading the movie through RosettaSciIO** reads the other members whole (virtual and external images, the scan coordinates) and groups only `*_movie.mrc` (not `.de5`, `.tif`, `.hspy`; `"movie" in filename` decides whether it looks at all). So the movie is not handed to it.
- **The movie's header** says the frame size, the frame count and the pixel format, all in the `_info.txt` (`Image Size …`, `Autosave Movie Frames Written`, `Autosave … Pixel Format`); its cell and statistics are not set. Nothing in it helps a search (Q5).
- **Version differences** are large (244 keys common to 2.7.2, 2.7.4 and 2.7.5; 2.7.2 lacks the voltage; 2.7.4 has 308 keys that 2.7.2 lacks, and lacks 8 of 2.7.2's), so the values are every entry as found, and the summary line leaves out what a file lacks.

## D2 The runner offers only unclaimed entries

The `recognition` spec says a claimed entry "SHALL NOT be available to formats that run later", but `Directory.of_type` returns claimed entries too, and the runner then rejects the later claim with "already claimed by …" (`run_post`). Found by the `em/mrc` agent; `BACKLOG.md`, the `em/de` item. With `em/de` the first format to claim files of generic types, each DE acquisition would bring one such warning per MRC member (`em/mrc`), for the log (`common/text`'s `text/x-log`), for the CSV (`common/structured`), for a `.de5`, `.hspy` or `.tif` movie (`common/pydata`, `common/image`), at every crawl, and `em/mrc` would read 213 bytes of each MRC member to check its map word.

Options:

| | Runner hides claimed entries | Each later format skips claimed entries |
|---|---|---|
| What changes | `of_type` leaves out entries claimed so far; a format whose reacted-to types are present only in claimed entries is not called | `em/mrc`, `common/text`, `common/structured`, `common/pydata`, `common/image` each check a new `Directory.claimed` |
| Matches the spec | yes, as written | no: the spec says "not available" |
| Real conflicts | a format that names a claimed entry (`d.entry`, a header's member list) still gets the warning; a format offered entries by type no longer learns that a higher one took a file | unchanged |
| Work | one place, one test per scenario; reads saved for every format | five formats in two packages, and every future one |

Lean: the runner hides. A format that is offered entries by type has no claim of its own on a particular file; the higher priority decided, as the spec intends. A conflict that matters (two formats that both mean a particular file) shows as before when the later one asks for it by name. `d.entries` and `d.entry(name)` stay unfiltered (a format needs to see its whole directory to name members); child datasets stay as they are (no case of a claimed child offered again). No recognition `version` to raise: no dataset changes, only warnings.

## D3 Recognition and grouping

- **The name**: `de.xml` types `[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_*_info.txt` (shared-mime-info's globs are `fnmatch` patterns; the crawler's index compiles them with `fnmatch.translate`) as `application/x.de-info`, a subclass of `text/plain`. The pattern is longer than `*.txt`, so it wins. A narrower name than `*_info.txt`: a `run_info.txt` elsewhere is never read by `em/de`. Upper case is matched as every glob is (shared-mime-info is case-insensitive unless a glob says otherwise).
- **The content** (Q1): `d.read(e, 64)` must start with `Server Software Version` (the first key of every public file, 2.7.2 to 2.7.5); otherwise `d.not_of_type(e, "no DE-Server first line")`, and the file is `text/plain` for `common/text`. 64 bytes per candidate; the directory's budget of 1 MiB holds 16,384 of them. The alternative, the `Dataset Name = …` line, lies 3,667, 6,303 and 4,251 bytes into the 2.7.2, 2.7.4 and 2.7.5 files; with 8 KiB per candidate, 128 acquisitions fit, and a folder of more skips `em/de` for the whole folder ("em/de skipped: … exceeds the budget"). The 2020 file decides whether the first line holds for older versions (Q2).
- **The stem**: the `_info.txt`'s name without `info.txt` (`20241021_00405_`, with a suffix `20241021_00405_sampleA_`). Members: every regular file of the directory whose name starts with the stem, case-sensitive (DE-Server writes one form; the stem is taken from the file). The longest stem first, and a file belongs to one stem (Merlin's rule), so that `20241021_00405_x_info.txt` keeps `20241021_00405_x_movie.mrc` from `20241021_00405_info.txt`.
- **The anchor** is the `_info.txt`; the dataset's type `application/x.de-acquisition`. `basis`: `"DE-Server info, <n> file(s) <stem>*"`.
- **No warnings** for files with a date prefix and no `_info.txt` (D1 of the proposal: other programs use the same prefix).

## D4 Values and the summary line

- **Reading**: the `_info.txt` whole, after a size check (at most 1 MiB; the public files are 19 to 40 kB, the tree's 2.8 kB; larger is an error of the extraction). Decoded as ASCII, else UTF-8, else Windows-1252 (the rule of `common/text`, `head.encoding`, without a BOM or NUL case: none seen). Lines split at the first `=`, key and value stripped of the padding; a blank line skipped; a line without `=` kept as a key with an empty value (as Merlin's header lines without a tab).
- **`original_metadata`**: every entry, key as written, value as text, in the file's order, minus `de.skipped`: keys ending in ` Allowed Values`, the keys `Preset - List`, and keys ending in ` Preset List` (option lists of the user interface, Q6); then the shared checks, `textual` (none of the public values is over 1,000 characters; the longest 344) and `credential`. Empty values kept (decision 161).
- **The Dataset Name**: a value that does not start the file's name (`20241021_00405` for `20241021_00405_info.txt`) gives a warning of the extraction, "Dataset Name … differs from the file name"; the values are kept.
- **`mapped_metadata`** (Q3): RosettaSciIO's `read_de_metadata_file(path)` with no scan file: its `metadata` and `axes`, flat under dotted names as in `dm` (`Acquisition_instrument.TEM.detector`, `axes[0].size`). It opens the file itself (a text file under 1 MiB, after our size check). A `ValueError` for a scan that is not a raster leaves the mapped part out, with the reader's message as a warning of the extraction. The scan coordinate file is never handed to it.
- **The summary line** (`de.HEADLINE`, the only positive list): `Camera Model`, `Image Processing - Mode`, `Instrument Accelerating Voltage (V)`, `Exposure Time (seconds)`, `Frames Per Second`; when `Scan - Enable` is `Enable`: `Scan - Type`, `Scan - Size X`, `Scan - Size Y`; then `Local time` (Q7). A text bare, a number after its key, as written (`Frames Per Second 700`), a missing or empty entry left out; no 0 or `-1` rule, since none of these entries uses one as "no value" in the files seen.
- **Subjects**: `Camera Model`; the format's display name "Direct Electron acquisition" comes with every dataset.

Examples (RosettaSciIO's files):

- 2.7.4, `20241021_00405`: `DESim, Integrating, Instrument Accelerating Voltage (V) 300000, Exposure Time (seconds) 0.045712, Frames Per Second 700, Raster, Scan - Size X 8, Scan - Size Y 4, Mon Oct 21 14:36:50 2024`
- 2.7.2, `20230925_01497`: `CeleritasXS, Integrating, Exposure Time (seconds) 0.3325952, Frames Per Second 40000, Raster, Scan - Size X 8, Scan - Size Y 32`
- 2.7.5, `20250429_06699`: `DESim, Integrating, Instrument Accelerating Voltage (V) 300000, Exposure Time (seconds) 30, Frames Per Second 1, XY File, Scan - Size X 5, Scan - Size Y 5`

## D5 Priority

62. It must run before `em/mrc` (60) and before every format that claims a member's type on its own: `common/pydata`'s `Npz`, `Nexus` and `Hspy` run at 61 and sort before `em/de` by id (`common/…` < `em/…`), so a `_movie.hspy` would be claimed by `common/hspy` at 61. `em/k2is` is at 61 and shares no type.

## D6 MIME types (R25)

Looked up on 2026-11-13: Debian's `media-types` (`/etc/mime.types`) gives `mrc` to `application/marc` (library records) and has nothing for DE; the list of types Debian's desktop applications declare (https://wiki.debian.org/MimeTypesSupport/PackageList) has none for DE, MRC or a DE-Server info file (its EM-related entries are Gwyddion's SPM types); the vendored shared-mime-info has none either. So the unofficial `application/x.de-acquisition` (comment "Direct Electron acquisition"; no glob, no magic, as `application/x.k2is`) and `application/x.de-info` (comment "Direct Electron DE-Server acquisition info"; the glob of D3; `sub-class-of` `text/plain`). The members keep their own types (`application/x.mrc` from `em-mrc`, `text/x-log`, `text/csv`).

## D7 Bytes read

- Recognition: 64 bytes of each file named like a DE `_info.txt`; nothing of the other members.
- Extraction: the `_info.txt` twice (ours, then RosettaSciIO's), 2.8 to 40 kB each in the files seen, bounded by the 1 MiB size check; no other member. Test: a movie member of 1 GiB, sparse, and `rchar` (`modama_formats_em.testing.rchar`) under 2 × the `_info.txt`'s size plus 64 KiB.

## D8 Fixtures (R29)

- `acquisition_274`: RosettaSciIO's `20241021_00405_*`, all six files as they are (representative, vendor-written, renamed by RosettaSciIO as D1 says; GPL-3.0, `de/tests/LICENSE.fixtures`).
- `lone_info_272`: RosettaSciIO's `info.txt`, renamed `20230925_01497_info.txt` after its Dataset Name (representative: a lone `_info.txt` of an older version, CRLF).
- `xy_scan_275`: RosettaSciIO's `Custom_info.txt`, `Custom_movie.mrc`, `Custom_scan_coordinates.csv`, renamed `20250429_06699_info.txt`, `20250429_06699_0_movie.mrc`, `20250429_06699_scan_coordinates.csv` (representative: a numbered movie, a scan that is not a raster).
- Generated at test time (reproducers): the 2.7.4 `_info.txt` with a made-up entry; with a suffix (`20241021_00405_sampleA_*`); nested stems; a `20240619_1736_info.txt` without DE's first line next to `20240619_1736_HAADF.mrc`; a lone `_movie.mrc`; a 1 GiB sparse movie for D7.
- The 2020 acquisition from LiberTEM's test data: only as a cut, only with @weber's OK (Q9).

## Risks

- A DE-Server version whose first line is another key is not recognised: its `_info.txt` stays `text/plain` with the reason in its basis, its files single. Visible in the record; the fix is one more first key and a fixture.
- A file a user names with the stem of an acquisition (`20241021_00405_notes.txt`) becomes a member. Accepted: it is about that acquisition.
- RosettaSciIO's mapping can change in any release (private module `rsciio.mrc._api`); the pin's comment names it.
