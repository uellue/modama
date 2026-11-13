# Proposal

## Why

EPU writes beside each MRC image an XML file and, for an image, a JPEG preview of the same name: `FoilHole_…_Data_….mrc` with `….xml` and `….jpg`, a movie `…_Fractions.mrc` with `…_Fractions.xml`. Today each sidecar is a dataset of its own, apart from the image it describes. Request: @weber, 296 (2026-11-13), on the change `em-mrc`'s lean to group them later: "Is there a 1:1 match? If yes, group please!" Serves R30 (findable by what the data is) and the tree's largest MRC project (920 files in EPU's `Images-Disc1/GridSquare_*/Data/FoilHole_*` layout, the private listing of October).

## Is there a 1:1 match? (EMPIAR-12652, EPU 2.12)

I read "1:1" as: each sidecar belongs to exactly one MRC file by its name, and no MRC file has two candidates. Checked on the public EMPIAR-12652 (EPU 2.12.1, Titan Krios, Falcon; CC0), whose folders are EPU's own layout: the HTTPS listings of all 22 `Images-Disc1/GridSquare_*` folders and their `Data/` and `FoilHoles/` (6 squares have neither), grouped by stem (a throwaway script over the directory index pages, 2026-11-13; `_Fractions` counted as part of the extension):

| Folder | Files of one stem | Stems |
|---|---|---|
| `Data/` | `.mrc .xml .jpg`, `_Fractions.mrc _Fractions.xml` | 1505 |
| `Data/` | `.mrc .xml .jpg`, `_Fractions.xml` | 3324 |
| `Data/` | `.mrc .jpg`, `_Fractions.xml` (no `.xml`) | 1 |
| `Data/` | `_Fractions.mrc _Fractions.xml` (no average) | 3 |
| `Data/` | `_Fractions.xml` alone | 1 |
| `FoilHoles/` | `.mrc .xml .jpg` | 448 |
| the square | `GridSquare_….mrc .xml .jpg` | 21 |

- By name the match is never ambiguous: every `.xml` and `.jpg` has one MRC file of its stem or none, and every `_Fractions.xml` one movie or none; nothing else shares a stem (but `Thumbs.db`).
- Every one of the 1508 movies has its `_Fractions.xml`; every one of the 469 grid square and foil hole images has its `.xml` and `.jpg`; of the 4830 micrographs, 4829 have both, and one has its `.jpg` but no `.xml` (`GridSquare_4530420/Data/FoilHole_4554141_Data_4541935_4541937_20220508_012652`).
- 3326 `_Fractions.xml` have no movie in the deposition (the depositors left most movies out), so they stay files of their own.
- EMPIAR-12018 and 12496 hold movies only, without sidecars: no evidence either way.

So: grouped where the files are there, by stem; a missing sidecar is not an error.

## Assumptions and leans

- **The rule, by name only**: an MRC dataset `<stem>.<ext>` takes `<stem>.xml` and `<stem>.jpg` of its folder as members; the movie `<stem>_Fractions.mrc` takes `<stem>_Fractions.xml` by the same rule. EPU writes these exact, lower-case names. No sidecar's content is read: what names the sidecars is EPU's naming, the same for every EPU version seen (2.12 here, 2.9 and 1.2 in `mrcfile`'s test files are single files). Against: another program that writes `x.mrc` beside an unrelated `x.xml` or `x.jpg` gets them grouped too; a person would likely call them one thing anyway.
- **Missing sidecars**: the dataset holds what is there, without a warning (a movie never has a `.jpg`; one micrograph of 4830 has no `.xml`).
- **A sidecar another format claimed first** (a format above em/mrc's priority 61): it stays with that format, and em/mrc names it in the fixed warning of decision 344 (`Directory.claimed_elsewhere`, ending in `two formats want it`).
- **Sidecars' content**: not read now; the extraction stays the MRC file's. Their text is to be shown as written once text as written lands (main session, 2026-11-13). Against: until then, what the XML holds (the dose on the camera, aperture names) is not in the record at all, where today `common/structured` extracts it as the XML's own dataset.
- **Fixture**: one stem of EMPIAR-12652 with all five files (`epu_data`: the micrograph and its movie cut by `cut-header.sh`, the two XML files whole, the JPEG cut to its first 2048 bytes by `cut-sidecars.sh`; nothing reads it).

## What Changes

- `em/mrc`'s recognition: a dataset of an MRC file takes its EPU sidecars as members (spec formats/mrc, new requirement "EPU's sidecars belong to their MRC file").
- A fixture `epu_data` and its tests; `cut-sidecars.sh`.
- `fixtures.toml`'s `fei1` entry recorded as decided (298).

Behaviour towards the user: a harvester and a searcher see one record per EPU image or movie, with its `.xml` (and `.jpg`) as files of that record, instead of separate records for each sidecar; the record's description is the MRC file's as before. The `.xml` and `.jpg` of an EPU image no longer have records or extractions of their own. The recognition `version` of `em/mrc` goes to 2: directories taken over from the last crawl are recognised again.

Out of scope: TIFF and EER movies (`_Fractions.tiff`, `.eer`) and their `_Fractions.xml` (not MRC); the session's `EpuSession.dm`, `Atlas/` and `Metadata/` files; reading the sidecars; grouping a movie with its average.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `formats/mrc` (change `em-mrc`, not yet archived): a new requirement.

## Impact

- `python/modama-formats-em/src/modama_formats_em/mrc/`: recognition, tests, a fixture.
- No new dependency, no migration. The extractor identity changes with the installation, as with every code change.
