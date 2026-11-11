# modama-formats-em

Electron microscopy formats for the modama crawler (`python/crawler/`), as the format collection `em`. Install it next to the crawler and the crawler finds it through the entry point group `modama.formats`; its format ids start with `em/`.

| Format | Recognised as | Extracted |
|---|---|---|
| EMPAD | the XML header with the raw file it names, one dataset (`em/empad`) | scan size or frame count, frame size, exposure, time; from the header |
| Gatan Digital Micrograph | DM3 and DM4 files by their header, whatever their name (`em/dm3`, `em/dm4`) | voltage, magnification, camera length, pixel size, dimensions, device, microscope, time; from the tags |
| Merlin | the `.hdr` text header by its content with its `.mib` frame files, one dataset (`em/merlin`); `.mib` files without a header stay single files with a warning | frame count, frame size, counter depth, readout system, time; from the header and the first frame's header |

Metadata extraction uses [RosettaSciIO](https://github.com/hyperspy/rosettasciio) (GPL-3.0-or-later), a dependency of this package only, for DM (its reader, lazily: the tags are parsed, the image data skipped) and Merlin (its header parsers). Merlin frames belong to the header whose name they start with, as LiberTEM groups them (`acq.hdr`: `acq*.mib`). The extraction tests print each fixture's description, subjects and the bytes read (`pytest -s src`).

## Setup and tests

```bash
uv pip install --python ~/.venv/bin/python -e python/crawler[test] -e python/modama-formats-em
cd python/modama-formats-em && pytest src
```

Each format is a subpackage of `src/modama_formats_em/` with its MIME rules, fixtures and tests, written as `python/crawler/src/modama_crawler/formats/TEMPLATE.md` describes; the crawler's pytest plugin runs them. Real files as fixtures are added only with agreement on each file.

## Licence

MIT (`LICENSE`).
