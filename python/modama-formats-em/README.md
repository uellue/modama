# modama-formats-em

Electron microscopy formats for the modama crawler (`python/crawler/`), as the format collection `em`. Install it next to the crawler and the crawler finds it through the entry point group `modama.formats`; its format ids start with `em/`.

| Format | Recognised as | Status |
|---|---|---|
| EMPAD | the XML header with the raw file it names, one dataset (`em/empad`) | recognition |
| Gatan Digital Micrograph | DM3 and DM4 files by their header, whatever their name (`application/x.dm3`, `application/x.dm4`) | recognition by content; no representative file yet |
| Merlin | the acquisition's `.hdr` text header by its content (`application/x.merlin-header`) | header only; the frames follow; no representative file yet |

Metadata extraction uses [RosettaSciIO](https://github.com/hyperspy/rosettasciio) (GPL-3.0-or-later), a dependency of this package only.

## Setup and tests

```bash
uv pip install --python ~/.venv/bin/python -e python/crawler[test] -e python/modama-formats-em
cd python/modama-formats-em && pytest src
```

Each format is a subpackage of `src/modama_formats_em/` with its MIME rules, fixtures and tests, written as `python/crawler/src/modama_crawler/formats/TEMPLATE.md` describes; the crawler's pytest plugin runs them. Real files as fixtures are added only with agreement on each file.

## Licence

MIT (`LICENSE`).
