# Design

## Context

The core's `zarr/zarr` (priority 80) collapses a store pre-order from its listing; a collapsed dataset has no members, and its stamp is the digest of the store folder's listing (`walk.py`: names, kinds, sizes, owners and times of the top-level entries, and the folder's own stat). The extraction module runs any format's extractor on any of its datasets, collapsed or not (`extraction.py`, `wanted`): so a collapse format with an extractor in `common` is enough, the crawler's code does not change. The first collapsed dataset of the pre-order call wins, in priority order (`formats.run_pre`).

What is in the tree (the October listing, `.claude/survey/listing-2026-10-15.tsv.gz`, metadata file names only): 135 `.zarray`, 201 `.zattrs`, 232 `.zgroup`, 2 `zarr.json`, no `.zmetadata`. The four `.zspy` stores have RosettaSciIO's layout of an `.hspy` file as folders: `.zattrs` at the root (63 bytes: `file_format`, `file_format_version`), `Experiments/__unnamed__/` with `metadata/<…>/.zattrs`, `original_metadata/<…>/.zattrs` (one group per key, as h5py groups), `axis-0` … `axis-3/.zattrs`, `learning_results/`, `data/.zarray` (420 bytes) and nested chunk folders (`data/0/0/0/0`, dimension separator `/`), up to 18,862 entries. The v3 store (staging sample `AB-graphene.zarr`, read for layout and key names only): root `zarr.json` of 3,444 bytes with `attributes.metadata0` (abTEM's `ArrayObject.to_zarr`, `abtem/array.py` of abTEM 1.0.11: root attributes `metadata<i>`, arrays `array<i>`; the store's own `metadata0.data_origin` names abTEM), `array0/zarr.json` of 683 bytes, one chunk of 177 MB, and `.ipynb_checkpoints/zarr-checkpoint.json`.

## Decisions

### D1 Python's `json` on the metadata files, not zarr-python

Measured with zarr-python 3.4.2 (current release on PyPI, 2026-10-27, pure Python; it brings numcodecs, msgspec, google-crc32c, donfig) on stores written by it, v2 with nested chunk keys and v3, 4,096 chunks each, walking every group's members and each array's attributes, shape, dtype, chunks and compressors (`strace -e openat`):

| | v2 | v3 |
|---|---|---|
| metadata files opened | 13 (`.zgroup`, `.zattrs`, `.zarray`) | 6 (`zarr.json`) |
| folders listed | 4 groups | 4 groups |
| chunk files or array folders opened | 0 | 0 |

So zarr-python reads what is needed, no more. Three findings rule it out as the reader here:

1. **It reads outside the store.** A group `linked` in the store that is a symlink to a folder elsewhere: `members()` returns it with that folder's attributes (`{'secret': 'from outside the store'}`). The crawler's own walk never follows a symlink, and the pydata area's rule is that nothing is read from outside the file (`common-pydata`, review finding 1, a blocker).
2. **One unknown codec fails the whole group.** A v2 `.zarray` with `"compressor": {"id": "imagecodecs_jpeg2k"}` (numcodecs has no such codec unless imagecodecs registers it): `members()` of its group raises `UnknownCodecError`, so none of the group's other nodes would be described.
3. **One unknown v3 data type fails the whole group** in the same way (`ValueError: No Zarr data type found that matches 'made_up_type'`); v3 makes data types an extension point.

Reading the documents ourselves is what the specifications define them to be: a JSON object per node (Zarr v2 storage specification, "Metadata"; v3 core specification, "Metadata"). The walk opens each folder relative to its parent with `O_DIRECTORY | O_NOFOLLOW` and each metadata file with `O_NOFOLLOW | O_NONBLOCK`, checks with `fstat` that it is a regular file of at most 1 MiB, and reads it unbuffered. zarr-python stays a test dependency: it writes the fixtures, as in the core's `zarr` collection.

### D2 Which folders are nodes

A child folder is a node when it holds `zarr.json`, `.zarray` or `.zgroup` (the core's markers), checked by opening those names (an absent one costs a failed `openat`, no listing). An array is not listed: its chunks are never seen. A group is listed once, names sorted (Zarr has no stored order; zarr-python sorts members too), at most 10,000 names. A folder without a marker is not entered (`.ipynb_checkpoints/` in a store, chunk folders, v3's implicit groups, which the v3 specification removed). A nested store is a node of the outer one, whatever its version.

### D3 Names, as the HDF5 walk

A node's path joined with dots from the store's root: the root's attributes as `file_format`, a group's as `metadata.General.title`, an array's metadata document's entries as `data.shape`, `data.compressor.id`; attribute values that are objects or lists of objects flattened as the structured area does (`modama_formats_common.structured.entries.of_data`: `a.b`, `a[2].b`, a list of plain values as one value). So a `.zspy` store's names are those of the same signal saved as `.hspy`, and the HDF5 walk's summary patterns and HyperSpy's skip list apply unchanged; HyperSpy's skip list moves from `hdf5.py` to `values.py`, as its second user arrives. As in the HDF5 walk (`common-pydata`, A5), an attribute named like an entry of the array's document (`shape`) takes its place.

### D4 Recognition

`common/zarr` subclasses the core's `Zarr` format, with priority 81 and an extractor: same markers, basis and warnings (a `zarr.json` that cannot be parsed still collapses, with the core's warning). `common/zspy` (82) reads the root's attributes (`.zattrs` or `zarr.json`, at most 64 KiB, the core's read limit) of a store named `*.zspy` and yields only when `file_format` is `HyperSpy`; otherwise `common/zarr` takes the store.

## Risks

- A nested metadata file changed in place does not change the stamp (A7): the record stays stale until the top-level listing or the installation changes.
- A store of thousands of groups (one per `original_metadata` key, as RosettaSciIO writes them) costs one `openat` per marker name per folder: the 4,786-entry `.zspy` has about 60 groups, 180 opens; the object limit caps the worst case at 5,000 nodes.
