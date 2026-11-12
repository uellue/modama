# modama-formats-em

Electron microscopy formats for the modama crawler (`python/crawler/`), as the format collection `em`. Install it next to the crawler and the crawler finds it through the entry point group `modama.formats`; its format ids start with `em/`.

| Format | Recognised as | Extracted |
|---|---|---|
| EMPAD | the XML header with the raw file it names, one dataset (`em/empad`) | scan size or frame count, frame size, exposure, time; from the header |
| Gatan Digital Micrograph | DM3 and DM4 files by their header, whatever their name (`em/dm3`, `em/dm4`), except `.dmw` and `.gtg` files: types of their own by name, not images | voltage, magnification, camera length, pixel size, dimensions, device, microscope, time; from the tags |
| Gatan Digital Micrograph workspace | a `.dmw` file with the DM3 or DM4 header, one dataset (`em/dmw`); a DM3 one is marked as a file of interest in its basis; a `.dmw` without the header gets the type it has without the name (a text file: `text/plain`) | every tag under its path, in the reader's order, nothing left out (for now) |
| K2IS | a `.gtg` tag file with its 8 sector files `<stem>*.bin`, one dataset (`em/k2is`), whatever the `.gtg` holds (a broken one fails at extraction); sector files by their block header, whatever their name; sector files without their `.gtg`, or a `.gtg` with other than 8, stay single files with a warning; a `.gtg` without sector files and without the DM4 header gets the type it has without the name | every tag of the `.gtg` under its path, `SI Dimensions` (the scan shape) and `Microscope Info` first, except Gatan Microscopy Suite's user-interface settings (the image viewer's, the Session Info form) |
| Merlin | the `.hdr` text header by its content with its `.mib` frame files, one dataset (`em/merlin`); `.mib` files without a header stay single files with a warning | frame count, frame size, counter depth, readout system, time; from the header and the first frame's header |

Metadata extraction uses [RosettaSciIO](https://github.com/hyperspy/rosettasciio) (GPL-3.0-or-later), a dependency of this package only, for DM, `.dmw` and `.gtg` (its reader classes on a file we open with a 64 KiB buffer and readahead off: the tags are parsed, the image data skipped; Python's default buffer on NFS is 1 MiB, refilled at every seek) and Merlin (its header parsers). Merlin frames belong to the header whose name they start with, as LiberTEM groups them (`acq.hdr`: `acq*.mib`). The extraction tests print each fixture's description, subjects and the bytes read (`pytest -s src`).

## Values and units: what the driver says

An extractor shows what the file or its reader (the format driver, for example RosettaSciIO) says, without editorializing: no number rounded (the DM reader's `18.325349807739258`, not `18.3`), no unit guessed from a value's size, no unit converted, no number from one tag joined with a unit from another. Where the driver gives no unit, the description says so ("unit unknown"). Consistent units and metadata blocks (with pint or similar) come later, in the drivers upstream where possible (@weber, 2026-11-11).

## Setup and tests

```bash
uv pip install --python ~/.venv/bin/python -e python/crawler[test] -e python/modama-formats-em
cd python/modama-formats-em && pytest src
```

Each format is a subpackage of `src/modama_formats_em/` with its MIME rules, fixtures and tests, written as `python/crawler/src/modama_crawler/formats/TEMPLATE.md` describes; the crawler's pytest plugin runs them. Real files as fixtures are added only with agreement on each file.

## Licence

MIT (`LICENSE`).
