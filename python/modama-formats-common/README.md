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
| TIFF (`image`) | a file of the core's type `image/tiff` (`*.tif`, `*.tiff`, or its header), one dataset (`common/tiff`); the name decides, nothing is read at recognition | through tifffile, the first page only: every tag under tifffile's name (a tag without one under its number), its value as tifffile reads it, the vendor blocks tifffile parses in tags flat under dotted names (`FEI_HELIOS.Beam.HV`, `CZ_SEM.ap_actualkv`, `ExifTag.…`), an ImageJ file's description and IJMetadata as `imagej_metadata.…`, its `Info` line by line (`imagej_metadata.Info.root.ApplicationBounds`, from `key = value` lines), as `original_metadata`; but one skip list (`tiff.skipped`: strip and tile offsets and byte counts, FEI's data bar settings, a value of more than 1 MiB of a tag tifffile reads on demand (it reads `ImageDescription`, `IJMetadata` and the offsets with the page, whatever their size), values not suitable for text); the first page's `first_page_shape`, `dtype`, `axes` as `mapped_metadata`. Summary line, for example `Helios NanoLab" 660, ETD, SE, HV 5000 (unit unknown), ImageWidth 512, ImageLength 471, BitsPerSample 8, 06/13/2016, 05:06:40 PM`. No page count: that walks every page |
| PNG, JPEG, BMP, GIF, WEBP (`image`) | a file of the core's type (`image/png`, `image/jpeg`, `image/bmp`, `image/gif`, `image/webp`), one dataset (`common/png`, …) | through Pillow, what `Image.open` reads before the image data: its `info` (PNG text chunks before the image data, JFIF, a comment as text), the EXIF block parsed by Pillow (`exif.Make`, `exif.Exif.ExposureTime`, `exif.Exif.ExifVersion`, `exif.GPSInfo.…`, `exif.Interop.…`; bytes as text where they are UTF-8; not the thumbnail's IFD1, not binary fields such as `MakerNote`: `pil.skipped`); `width`, `height`, `mode` and Pillow's `dpi` as `mapped_metadata`; for example `Canon, Canon PowerShot S40, width 480, height 360, 2003:12:14 12:01:44`. Pillow's decompression-bomb check is off (nothing is decoded); a compressed text chunk Pillow refuses as too large is left out with a `reader warning`. A WEBP of more than 16 MiB is not extracted (Pillow reads the whole file) |
| SVG (`image`) | a file of the core's type `image/svg+xml`, one dataset (`common/svg`) | through defusedxml, at most the first MiB, also within one large element: the root's attributes (`@width`, `@viewBox`, `@inkscape:version`) and the elements at the root that are not the drawing (`title`, `desc`, `metadata`, foreign metadata; `svg.skipped`: the SVG namespace's drawing elements and Inkscape's `sodipodi:namedview`) under dotted paths with the file's namespace prefixes (`metadata.rdf:RDF.cc:Work.dc:date`); for example `width 576pt, height 432pt` |
| EPS (`image`) | the core's type `image/x-eps`, no format | nothing: Pillow's reader reads the whole file to its end |

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
