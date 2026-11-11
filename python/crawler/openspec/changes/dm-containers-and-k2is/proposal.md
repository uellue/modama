# Proposal

## Why

In staging run 3 (2026-11-11), 2,036 `.dmw` and 33 `.gtg` files carried the Digital Micrograph 4 header, so the crawler typed them `application/x.dm4`, named them "Gatan Digital Micrograph (DM4)" in their records, and their extraction failed: they hold tags but no image (no `ImageList` tag; RosettaSciIO's `get_image_dictionaries` returns `None`). That is 72 % of run 3's extraction failures (finding F15), and the records tell a searcher something false. @weber decided on 2026-11-11 (71): "give them their own types". @weber also asked whether `.gtg` files belong to K2IS datasets: LiberTEM's K2IS reader (`libertem/io/dataset/k2is.py`, master of 2026-10-15) says "Read raw K2IS data sets. They consist of 8 .bin files and one .gtg file"; on staging, 32 of the 33 `.gtg` files are named `<stem>_.gtg` as K2IS captures are (two of them in `libertem-test-data`), so each is one acquisition with 8 sector files that the crawler today indexes as nine unrelated records. Serves R25 (types named by MIME strings, honest ones), R30 (findable by what the data is), R31/R22 (an acquisition's files as one dataset rather than stray files), R27 (issues from real data become reproducers), R21 (domain formats outside the core).

## What Changes

- **New types** in `modama-formats-em`, decided by name (no core type has these globs; the shared-mime-info order lets a name match that is a subclass of the sniffed type win):
  - `.dmw` files: a type of their own, a subclass of `application/x.dm4`; a dataset of one file with the basic description, no extraction. What a `.dmw` is (Gatan's term) is to be confirmed (open question); the type's name says only what is verified.
  - `.gtg` files: a type of their own, a subclass of `application/x.dm4`; on their own (for example `IDES_DMS_Config.gtg`) a dataset of one file with the basic description.
- **K2IS acquisitions as one dataset**: a `.gtg` with exactly 8 sector files `<stem>*.bin` next to it (LiberTEM's grouping: `X.gtg` takes `X*.bin`), anchored at the `.gtg`, as Merlin acquisitions are anchored at their header. Sector files are typed by content (a new type: big-endian `0xFFFF0055` at offset 0, width 256 at offset 20 and height 1860 at offset 22, LiberTEM's `DataBlock.is_valid`), not by the generic name `*.bin`. Sector files without their `.gtg`, or a `.gtg` with other than 8, stay single files with a warning, as `.mib` files without a header do.
- **K2IS extraction** from the `.gtg` tags through RosettaSciIO's DM reader classes on our own file handle (as branch `dm-handle` does for DM files, F14), values as the reader gives them under its names (README, "Values and units"): the tags LiberTEM reads for the scan shape (`SI Dimensions` Size X/Y) and the microscope tags where present (the number of files and their size are in the basic description). No frame count (LiberTEM derives it by synchronising the sectors' blocks; out of scope).
- The `formats/dm` behaviour "recognised by content, whatever the name" gains one exception: these two names decide.

Behaviour towards the user: a searcher sees `.dmw` and `.gtg` files typed and described as what they are instead of "Gatan Digital Micrograph (DM4)"; a K2IS capture becomes one record (with its 8 sector files as members) instead of nine; extraction failures from these files disappear from the crawl's warnings. Identifiers of the 8 sector files' former records disappear from the OAI-PMH endpoint (deleted records).

Out of scope: reading K2IS frames or their count (LiberTEM's sector synchronisation); LiberTEM as a dependency; metadata from `.dmw` files; other Gatan formats (`.dm3`/`.dm4` images stay as they are); Merlin's buffer issue (F14, upstream).

## Capabilities

### New Capabilities
- `formats/k2is`: K2IS acquisitions (`.gtg` with 8 sector files) recognised as one dataset, with their metadata from the `.gtg` tags.

### Modified Capabilities
- `formats/dm`: `.dmw` and `.gtg` files are not typed as DM4 images (added requirement; `formats/dm` is introduced by `em-formats-and-extraction`, so that change is archived first).

## Impact

- `python/modama-formats-em/`: a new `k2is/` part (MIME rules, recognizer, extractor, fixtures, tests); `dm/dm.xml` (two types) and its tests; the collection's `PARTS`; README's table.
- Depends on branch `dm-handle` (the DM reader on our own handle) and on `em-formats-and-extraction` being archived.
- Fixtures (R29): representative files from the wild need @weber's agreement per file (README); a K2IS capture's sector files are large, so its fixture is a reproducer cut from a real capture (the `.gtg` and the first blocks of each `.bin`), also with agreement. No new dependency.
