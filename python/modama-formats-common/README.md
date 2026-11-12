# modama-formats-common

Common file formats for the modama crawler (`python/crawler/`), as the format collection `common`: images, Python data science (notebooks, NumPy, HDF5, Zarr and their derivatives), office documents, plain text and structured data. Install it next to the crawler and the crawler finds it through the entry point group `modama.formats`; its format ids start with `common/`.

| Format | Recognised as | Extracted |
|---|---|---|
| `common/json`, `common/jsonschema` | `application/json` (`*.json`, a JSON value first), `application/schema+json`; JSON Lines in a `.json` too | every value under its dotted path; several documents numbered |
| `common/yaml` | `application/yaml` (`*.yaml`, `*.yml`) | every value under its dotted path; a stream's documents numbered |
| `common/toml` | `application/toml` (`*.toml`) | every value under its dotted path |
| `common/csv` | `text/csv` (`*.csv`) | the dialect, the header's names, columns and rows; no data row |
| `common/xml` | `application/xml` (`*.xml`, `<` first), not its subtypes | every attribute and text, names with the file's prefixes |
| `common/ini`, `common/cfg` | `text/x-ini` (`*.ini`), `text/x-config` (`*.cfg`), a `[section]` first | every `section.key` |

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
