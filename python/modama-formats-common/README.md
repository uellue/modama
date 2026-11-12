# modama-formats-common

Common file formats for the modama crawler (`python/crawler/`), as the format collection `common`: images, Python data science (notebooks, NumPy, HDF5, Zarr and their derivatives), office documents, plain text and structured data. Install it next to the crawler and the crawler finds it through the entry point group `modama.formats`; its format ids start with `common/`.

| Format | Recognised as | Extracted |
|---|---|---|
| Plain text, logs, READMEs | each file the core types `text/plain` (`.txt`, `.asc`, text without a name rule), `text/x-log` (`.log`) or `text/x-readme` (`README` and the like) is one dataset (`common/text`, `common/log`, `common/readme`) | from the first 1 MiB: the encoding as the bytes say it (a BOM's, `ascii`, `utf-8`, else `Windows-1252`; none for a NUL byte) and the line count, for example `Windows-1252, lines 2` or `ascii, lines at least 20164` for a larger file, as `mapped_metadata`; never the text itself |
| Markdown | `text/markdown` (`.md`, `.markdown`), one dataset each (`common/markdown`) | every entry of a YAML front matter, flat under its dotted name, dates as written, as `original_metadata`; the first heading, encoding and lines as `mapped_metadata`; for example `Lamella preparation, 2026-11-12T10:00:00+01:00, ascii, lines 18` |
| reStructuredText | `text/x-rst` (`.rst`), one dataset each (`common/rst`) | the title, subtitle and docinfo fields as docutils reads them (includes not followed), for example `Docutils Front-End Tools, David Goodger, 2024-12-04, utf-8, lines 570` |
| HTML | `text/html` (`.html`, `.htm`), one dataset each (`common/html`) | from the head: `title`, `lang`, every `meta.<name>` but `meta.viewport`, for example `Docutils Front-End Tools, David Goodger, Docutils 0.23: https://docutils.sourceforge.io/, utf-8, lines 1283` |
| LaTeX | `text/x-tex` (`.tex`, `.sty`, `.cls`, …), one dataset each (`common/tex`) | `documentclass`, `title`, `author`, `date` as raw LaTeX, for example `Docutils Front-End Tools, article, utf-8, lines 850` |
| BibTeX | `text/x-bibtex` (`.bib`), one dataset each (`common/bibtex`) | the number of entries and their keys, for example `entries 3, ascii, lines 22` |

None yet: each area (`image`, `pydata`, `office`, `text`, `structured`) is a subpackage added by its own change, with one import and one entry in `PARTS` in `src/modama_formats_common/__init__.py`, and its rows here.

## Values and units: what the file says

The principles of `python/modama-formats-em/README.md`, "Values and units: what the driver says", hold here too: an extractor shows what the file or its reader says, without editorializing (no rounding, no unit guessed or converted); what the file says comes first, every entry minus a skip list per format, never a list of wanted entries; values not suitable for text (too large, binary) are left out by the one check every collection shares, `modama_crawler.formats.values.textual`. The checklist for writing a format is `python/crawler/src/modama_crawler/formats/TEMPLATE.md`.

## Setup and tests

```bash
uv pip install --python ~/.venv/bin/python -e python/crawler[test] -e python/modama-formats-common[test]
cd python/modama-formats-common && pytest src
```

Each area is a subpackage of `src/modama_formats_common/` with its MIME rules, fixtures and tests, written as `python/crawler/src/modama_crawler/formats/TEMPLATE.md` describes; the crawler's pytest plugin runs them. Fixtures are public test data with their licence and source in `fixtures.toml`, or generated at test time.

## Licence

MIT (`LICENSE`).
