# Proposal: Hitachi electron microscope images with their `.txt` header (`em-hitachi`)

## In short

A Hitachi electron microscope saves each image as a TIFF and a `.txt` file of the same name. The `.txt` is an INI-like header: a line `[SemImageFile]`, then `key=value` lines (instrument, date, time, sample name, magnification, operation mode, signal, accelerating voltage, pixel size, stage position, apertures, …; 40 in the sample). The TIFF carries the same block in its `ImageDescription` tag, and in a private tag 65500 a few more properties. Today the two are separate datasets: the `.txt` a plain text with nothing extracted, the TIFF an image whose summary line is `ImageWidth 1024, ImageLength 1056, BitsPerSample 8`.

With this change the pair is **one dataset** (`em/hitachi`), anchored at the TIFF, the `.txt` a member. Its summary line comes from the header the TIFF carries, for example (made-up values):

`HF3300, HAADF, Analysis, Accelerating voltage 300000 (unit unknown), Magnification 50000, PixelSize 0.5 (unit unknown), Au on C, ImageWidth 1024, ImageLength 1056, BitsPerSample 8, 2024/01/15, 09:30:00`

and its record's second description is the `.txt` as written (the rule of change `text-as-written`). A TIFF with this header but without its `.txt` gets the same values and summary line through the image area; a `.txt` without its TIFF stays a text file, shown as written.

## Why

@weber, 2026-11-13, in `modama-chain browse` (snapshot of 08:31:59 UTC in `/.claude/field-tests/browse/`, a `.txt` of 876 bytes in a `raw/` folder; today `text/plain`, 1 file, nothing extracted; the TIFF its own dataset): "This is a sidecar file for the TIFF, apparently a vendor specific format? I think this should become one dataset with the corresponding tif file, and we reproduce the txt part verbatim and see if there's anything else interesting in the tiff headers? I guess the main file here is the tiff, and the txt a member file."

I read the one pair as an example of a rule, "a Hitachi image and its header are one dataset, anchored at the image; the header is shown as written; the TIFF's own tags are looked at for what else they hold", not as the whole ask. The October listing has 411 such pairs (`.txt` next to a `.tif` of the same stem), in 7 folders; every one of these `.txt` is 829 to 877 bytes, every TIFF 1.1 to 4.3 MB (design D1). It is the BACKLOG's "Hitachi SEM `.txt` sidecars (`[SemImageFile]`)" of the text area's open points (open question 244d).

Serves R30 (findable by what the data is: instrument, signal, voltage, magnification, sample), R15 (extract from content), R14 (the person's knowledge of the files as rules), decision 230 (what the file says, without editorializing), the skip-list rule of 2026-11-12.

## Assumptions and leans (questions Q1 to Q11 in design.md)

Accepted by @weber on 2026-11-13: "Accept!" (313), all eleven leans, tag 65500's `@Confidential` items kept as the file says them; fixtures: "Yes, please generate based on what you have as a sample." (314), so they are generated in the layout of the private sample pair, values made up, nothing of the real files in the repository. L8 changed before the build: the runner part was done meanwhile by bug 311 and decision 344 (see L8).

- **L1 The pair** (Q1): a TIFF (`image/tiff`) and the `.txt` named as the TIFF with its last suffix replaced by `.txt`, whose first 14 bytes are `[SemImageFile]` (Gwyddion's and Bio-Formats' signature), are one dataset `em/hitachi`, anchored at the TIFF. Recognition reads those 14 bytes of the `.txt`, nothing of the TIFF. A `.txt` of that name that does not start so is not part of it.
- **L2 Type** (Q2): `application/x-hitachi-sem`, the type Gwyddion declares for the header (Debian's list of types desktop applications declare), declared in `em`'s MIME file with a comment only, as `application/x.k2is` is: the format gives it to the dataset. No glob and no magic of ours: a `.txt` is typed by its name without being read, and a tie with `text/plain` would make every `.txt` in the tree be read at recognition.
- **L3 Values from the TIFF** (Q3): the dataset's values are what the image area makes of the TIFF, and that area learns Hitachi's header: a TIFF whose `ImageDescription` starts with `[SemImageFile]` has it parsed into entries `SemImageFile.<key>` (each line split at its first `=`, keys and values as written; `configparser` strips values and refuses a whole header for one indented line, design D2), in place of the description as one text; its tag 65500 parsed into `65500.<group>.<key>` (`65500.@Fld.FldImgPropModeID`). The `.txt` is not parsed: it is shown as written (L5). So nothing is merged and no source has to win: where the `.txt` and the TIFF differ (the sample's `InstrumentName` against `Instrument name`), the values say what the TIFF says and the text what the `.txt` says.
- **L4 Skip list** (Q4, Q5): the image area's for TIFF, unchanged; tag 65501 (in the sample 15,156 hexadecimal characters) is left out by the shared check `values.textual` as too long. Tag 65500's `@Confidential` group is kept (Q4).
- **L5 The text as written** (Q6): the `.txt`'s text goes into `values["text"]` by the rule and module of change `text-as-written` (decoded as the text area decides, line ends as line feeds, whole up to 4,096 characters, a line that may hold a credential left out); so it becomes the record's second description, in place of the tag lines. All 411 `.txt` in the listing fit whole.
- **L6 The summary line** (Q7): from the TIFF's parsed header, in the image area's `HEADLINE`: `Instrument name`, `Signal name`, `Operation mode`, `Accelerating voltage` and `PixelSize` followed by `(unit unknown)` (the header states no unit), `Magnification` (a ratio, no unit), `SampleName`, then the image area's `ImageWidth`, `ImageLength`, `BitsPerSample`, then `Date` and `Time`. A text bare, a number after its key.
- **L7 Lone files**: a TIFF with the header but no `.txt` stays `common/tiff`, with the values and summary line of L3 and L6; a `.txt` without its TIFF stays `common/text`, its text in the record (`text-as-written`), not typed `application/x-hitachi-sem` (Q8).
- **L8 Priority and claimed files** (Q9): `em/hitachi` at 60, above the image area (50) and the text area (20). When proposed, a format that ran later still saw the files an earlier one claimed, so `common/tiff` and `common/text` would have warned "already claimed" twice per pair; the lean was a runner change in this change. Before the build, bug 311 made the runner offer no claimed file to the formats after the one that claimed it, and decision 344 let a format ask who claimed a file it is not offered (`Directory.claimed`) and flag it (`Directory.claimed_elsewhere`, "two formats want it"). So this change has no runner part: `em/hitachi` uses `claimed_elsewhere` when another format took the `.txt` of a TIFF's stem.
- **L9 Where the code goes** (Q10): `em/hitachi` in `modama-formats-em`, which then depends on `modama-formats-common` for the TIFF reading (`image.tiff.extract`) and the text module of `text-as-written`; Hitachi's header in a TIFF in the image area of `modama-formats-common`, beside FEI's and Zeiss's blocks.
- **L10 Fixtures** (Q11): generated at test time with tifffile from the layout of the real pair (key names and order, the `\r` line ends of tag 270, CRLF of the `.txt`, tag 65500's item syntax, a long hexadecimal tag 65501), values made up; `validity = "parser-only"`. A cut of a real pair (every tag, no pixel data: its first 16,536 bytes) only if @weber agrees to publish it.

## What Changes

- `modama-formats-em`: area `hitachi` (format `em/hitachi`, `hitachi.xml` with the type's declaration, fixtures, tests), a README row, a dependency on `modama-formats-common`.
- `modama-formats-common`, image area (`image/tiff.py`): a TIFF whose `ImageDescription` starts with `[SemImageFile]` gets it and tag 65500 parsed into entries, and the summary line's Hitachi entries; the README row for TIFF.
- The search stack's `crawler.Dockerfile` installs `modama-formats-common` before `modama-formats-em`, which now needs it.
- No new third-party dependency (tifffile is the image area's already); a new dependency between two of our packages (L9).

Behaviour towards the user: the 411 Hitachi pairs of the listing (and the tree's others) become one record each instead of two: the TIFF's record, typed `application/x-hitachi-sem` ("Hitachi electron microscope image with its header"), with 2 files, a summary line from the header and the `.txt` as its second description; the 411 records of the `.txt` files leave the crawler's records (the warehouse keeps its copies until deletions are harvested: no `deletedRecord` yet, BACKLOG "End-to-end test"). A TIFF with Hitachi's header and no `.txt` gains the header's entries and summary line. Every TIFF whose description is not Hitachi's is unchanged. The first crawl after the merge recognises the folders again and extracts the pairs once (the TIFF's header, the `.txt` whole).

## Out of scope

- A `.txt` sidecar next to a `.bmp` or `.jpg` (Gwyddion and Bio-Formats read those too; none in the listing: its 13 other `.txt` pairs are next to `.png` files, not looked at); a UTF-16 `.txt` (Bio-Formats reads one, "by resaving in Notepad"; the listing's sizes rule it out for its 411); Hitachi's `[TemImageFile]` header that an image.sc thread is reported to mention (not verified, design D2).
- Parsing the `.txt` into values; using its `File name` key to find the image (Gwyddion and Bio-Formats use `ImageName` for that, which the sample's header does not have).
- Interpreting values across vendors (pixel size in nm, as Bio-Formats assumes since 2022), the data bar's rows (design D3), what tag 65501 holds.
- EDX data of Hitachi instruments, other Hitachi formats (Gwyddion's `application/x-hitachi-spm` is an AFM format).

## Capabilities

### New Capabilities
- `formats/hitachi`: the pair as one dataset, its values, text and bytes read.

### Modified Capabilities
- `formats/image`: Hitachi's header in a TIFF's `ImageDescription` and tag 65500 (from the unarchived change `common-image`).

## Impact

- `python/modama-formats-em/src/modama_formats_em/hitachi/` (new), `python/modama-formats-em/pyproject.toml`, `README.md`, `__init__.py` (`PARTS`); `python/modama-formats-common/src/modama_formats_common/image/tiff.py` and its tests, the package's README; `BACKLOG.md`; `prototypes/search-stack/crawler.Dockerfile` and the image build (the new dependency between the two packages).
- Order: after `text-as-written` (its text module and the record's rule), whose deltas it relies on; `common-image` and `common-text` archived first or with it.
- Cost: recognition reads 14 bytes of each `.txt` next to a TIFF of the same stem (411 in the listing, about a quarter of the tree); extraction reads the TIFF's tags (one 64 KiB buffer: the sample's tags end at byte 16,536) and the `.txt` (under 1 kB).
