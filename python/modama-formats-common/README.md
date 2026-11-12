# modama-formats-common

Common file formats for the modama crawler (`python/crawler/`), as the format collection `common`: images, Python data science (notebooks, NumPy, HDF5, Zarr and their derivatives), office documents, plain text and structured data. Install it next to the crawler and the crawler finds it through the entry point group `modama.formats`; its format ids start with `common/`.

| Format | Recognised as | Extracted |
|---|---|---|
| `common/npy`: NumPy `.npy` | `application/x-npy`, by its magic | the header (`numpy.lib.format`): `descr`, `fortran_order`, `shape`, version |
| `common/npz`: NumPy `.npz` | `application/x.npz`, by name, checked for a ZIP | each array's header, by NumPy's key |
| `common/hdf5`: HDF5 (`.h5`, `.hdf5`, `.emd` …) | `application/vnd.hdfgroup.hdf5`, by its signature | h5py, a bounded walk: every attribute, each dataset's shape and dtype, scalar datasets' values; no array, no external link |
| `common/nexus`: NeXus `.nxs` | `application/x.nexus`, by name, checked for HDF5 | as HDF5 (`NX_class` among the attributes) |
| `common/hspy`: HyperSpy `.hspy` | `application/x.hspy`, by name, checked for HDF5 | as HDF5, without HyperSpy's internal state |
| `common/matlab`: MATLAB `.mat` | `application/x-matlab-data`, by its header or name | the header text; variables' shape and class (SciPy), version 7.3 as HDF5 |
| `common/notebook`: Jupyter `.ipynb` | the core's `application/x-ipynb+json`, checked for a JSON object | the notebook's metadata (nbformat), cell counts, the first heading; no outputs |
| `common/python`, `common/python3`: Python scripts | the core's `text/x-python`, `text/x-python3` | `ast`, never run: shebang, docstring, dunder names, imports |
| `common/pickle`: `.pkl`, `.pickle` | `application/x-python-pickle`, by its start | the protocol; never unpickled |

Each area (`image`, `pydata`, `office`, `text`, `structured`) is a subpackage added by its own change, with one import and one entry in `PARTS` in `src/modama_formats_common/__init__.py`, and its rows here.

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
