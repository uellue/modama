# modama-formats-em

Electron microscopy formats for the modama crawler (`python/crawler/`), as the format collection `em`. Install it next to the crawler and the crawler finds it through the entry point group `modama.formats`; its format ids start with `em/`.

| Format | Recognised as | Extracted |
|---|---|---|
| EMPAD | the XML header with the raw file it names, one dataset (`em/empad`) | scan size or frame count, frame size, exposure, time; from the header |
| Gatan Digital Micrograph | DM3 and DM4 files by their header, whatever their name (`em/dm3`, `em/dm4`), except `.dmw` and `.gtg` files: types of their own by name, not images | voltage, magnification, camera length, pixel size, dimensions, device, microscope, time; from the tags |
| Gatan Digital Micrograph workspace | a `.dmw` file with the DM3 or DM4 header, one dataset (`em/dmw`); a DM3 one is marked as a file of interest in its basis; a `.dmw` without the header gets the type it has without the name (a text file: `text/plain`). As GMS writes it, a workspace holds root tags only: the file count, each image's name (a Windows path relative to it), frame and window, and the workspace's name; the images it names are separate datasets | every tag under its path, in the reader's order, no tag left out (for now), for example `File name 0 .\exemplary_workspace\h1.dm4`; stored as every extraction, each phrase cut to 4,096 characters, at most 1,000 |
| Gatan Digital Micrograph workspace (compressed) | a `.dmwx` file, a ZIP whose first member is the workspace `<name>/<name>.dmw`, followed by `<name>/files/` with its images, one dataset (`em/dmwx`); one that is not a ZIP, or has no `.dmw` first, gets the type it has without the name | the inner workspace's tags, then each member's name and size; only the central directory and the workspace are read, no image |
| K2IS | a `.gtg` tag file with its 8 sector files `<stem>*.bin`, one dataset (`em/k2is`), whatever the `.gtg` holds (a broken one fails at extraction); sector files by their block header, whatever their name; sector files without their `.gtg`, or a `.gtg` with 1 to 7 or more than 8, stay single files with a warning; a `.gtg` without sector files stays a single file without a warning if it has the DM4 header, or the DM3 header (then marked as a file of interest in its basis), and otherwise gets the type it has without the name | every tag of the `.gtg` under its path, `SI Dimensions` (the scan shape) and `Microscope Info` first, except Gatan Microscopy Suite's user-interface settings (the image viewer's, the Session Info form) |
| Merlin | the `.hdr` text header by its content with its `.mib` frame files, one dataset (`em/merlin`); `.mib` files without a header stay single files with a warning | frame count, frame size, counter depth, readout system, time; from the header and the first frame's header |
| NanoMegas ASTAR block file | a file that starts with `IMGBLO`, whatever its name, one dataset (`em/blockfile`); a `.blo` file without it gets the type its content gives (a text file: `text/plain`) | the header's fields as RosettaSciIO's reader gives them, the mapped metadata second; in the description `NX`, `NY`, `SX`, `SY`, `DP_SZ`, `Beam_energy`, `Camera_length`, `Scan_rotation` (unless 0), the acquisition time |

Metadata extraction uses [RosettaSciIO](https://github.com/hyperspy/rosettasciio) (GPL-3.0-or-later), a dependency of this package only, for DM, `.dmw` and `.gtg` (its reader classes on a file we open with a 64 KiB buffer and readahead off: the tags are parsed, the image data skipped; Python's default buffer on NFS is 1 MiB, refilled at every seek), Merlin (its parser of the first frame's header; the `.hdr` header we read ourselves in Latin-1, as the Merlin software writes "µ" as the byte 0xB5) and block files (its `file_reader`, lazily: the header plus one read buffer of the file it opens, about 132 KiB locally, about 1 MiB and 8 KiB on NFS; patterns are read into the buffer, never decoded; its module imports scikit-image, which comes with RosettaSciIO's extra `blockfile`). A block file's description gives the header's fields under their names, as found (`Beam_energy 200000`, no unit), and its date and time from the header's serial date as written: RosettaSciIO converts them to the local time zone, and the file states none. The reader's warnings (an unknown MAGIC) go into the description. Merlin frames belong to the header whose name they start with, as LiberTEM groups them (`acq.hdr`: `acq*.mib`). The extraction tests print each fixture's description, subjects and the bytes read (`pytest -s src`).

## Values and units: what the driver says

An extractor shows what the file or its reader (the format driver, for example RosettaSciIO) says, without editorializing: no number rounded (the DM reader's `18.325349807739258`, not `18.3`), no unit guessed from a value's size, no unit converted, no number from one tag joined with a unit from another. Where the driver gives no unit, the description says so ("unit unknown"). Consistent units and metadata blocks (with pint or similar) come later, in the drivers upstream where possible (@weber, 2026-11-11).

**What the file says comes first** (@weber, 2026-11-12, decision 230). For every format read through RosettaSciIO, the values are its `original_metadata` first: complete, as the instrument wrote it, minus GUI settings (window, page and display settings) and large arrays. The mapped metadata (HyperSpy's standard names) is kept as a second, labelled section, for comparing across formats; its conversions are RosettaSciIO's, shown as such, and where it disagrees with the original, the original wins and the difference goes to the RosettaSciIO list in `python/crawler/BACKLOG.md`. Getting the meaning of metadata right across vendors, reliably, is a big project of its own and out of scope here: the record represents to the user what is in the file, without editorializing, and the user makes their own sense of it. Open (decision 231): whether the summary line, today a few chosen tags, stays, or the record shows the tags as `name: value` just as they are found in the file.

## Setup and tests

```bash
uv pip install --python ~/.venv/bin/python -e python/crawler[test] -e python/modama-formats-em
cd python/modama-formats-em && pytest src
```

Each format is a subpackage of `src/modama_formats_em/` with its MIME rules, fixtures and tests, written as `python/crawler/src/modama_crawler/formats/TEMPLATE.md` describes; the crawler's pytest plugin runs them. Real files as fixtures are added only with agreement on each file.

## Licence

MIT (`LICENSE`).
