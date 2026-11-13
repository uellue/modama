# Design

Looked at on 2026-11-13 in the VM, with throwaway scripts outside the repository. The real pair @weber copied to `/.claude/field-tests/samples/` (the `.txt`, 876 bytes, and the TIFF's first 64 KiB) is private data: only its shape, sizes and key names are written down here, no value. Every value in this change's examples is made up.

## D1 The real pair

**The `.txt`** (876 bytes, ASCII, CRLF line ends, ending with CRLF): the line `[SemImageFile]`, then 40 lines `key=value` (41 lines in all), no blank line, no other section. Keys, in the file's order:

`InstrumentName`, `Date` (`yyyy/mm/dd`), `Time` (`hh:mm:ss`), `Image comment`, `Keyword1` (a voltage with its unit, as text), `Keyword2`, `SampleName`, `Magnification`, `Operation mode`, `Sub mode`, `Signal name`, `STEM camera length`, `Accelerating voltage`, `Emission`, `File name` (the TIFF's name), `Image number`, `Data size` (`<w>x<h>`), `Screen mode`, `Data display combine`, `Add embed of property`, `Scan speed`, `Capture speed`, `StagePositionX`, `StagePositionY`, `StagePositionZ`, `StagePositionT`, `StagePositionA`, `Stage position R`, `Stage type`, `Raster rotation angle`, `Calibration`, `Calibration factor X`, `Calibration factor Y`, `PixelSize`, `Brightness`, `Contrast`, `TEM condenser aperture`, `STEM condenser aperture`, `OBJ aperture`, `SA aperture`.

Keys are written in two styles (`StagePositionX` beside `Stage position R`, `PixelSize` beside `Data size`), many with spaces. No key names a unit; `Keyword1` is the only value with one. The instrument is a Hitachi S/TEM (its instrument name and comment say so, as do folder names in the listing), yet the section is `[SemImageFile]`.

**The TIFF** (tifffile 2026.11.8, as the image area reads it: the first page's tags):

| Tag | Shape in the sample | Today's values (`common/tiff`) |
|---|---|---|
| 254 `NewSubfileType`, 256 `ImageWidth` (1024), 257 `ImageLength` (1056), 258 `BitsPerSample` (8), 259 `Compression` (none), 262 `PhotometricInterpretation` (min-is-black), 277 `SamplesPerPixel` (1), 278 `RowsPerStrip`, 282/283 `XResolution`/`YResolution`, 296 `ResolutionUnit` | baseline tags; one strip | kept as they are; `StripOffsets`, `StripByteCounts` skipped (layout) |
| 270 `ImageDescription` | 837 bytes: the `.txt`'s block with `\r` line ends, 41 lines (40 keys) | one string of 835 characters with `\r` in it (it passes `values.textual`, which allows line ends; a longer one, over 1,000 characters, would be left out whole) |
| 65500 (private, ASCII) | 320 bytes: items `"@<group>"<key>=<value>` separated by `\r`: `"@Fld"FldImgPropReserveDbl1`, `…ReserveDbl2`, `…ModeID`, `…SubmodeID`, `"@Confidential"ScanTimeX`, `…ScanTimeY`, `…Stage tilt axis`; the last three repeated once, the first repeat glued to the item before it without `\r` (`…Stage tilt axis=<v>"@Confidential"ScanTimeX=<v>`) | one string, key `65500` |
| 65501 (private, ASCII) | 15,157 bytes: 15,156 characters `0-9A-F` and the terminating NUL | left out: over 1,000 characters (`values.textual`) |

tifffile sets none of its vendor flags (`is_fei`, `is_sem`, …) for this file: it has no Hitachi reader. The strip starts at byte 16,536, right after tag 65501's value; the IFD is at byte 8. So the file's first 16,536 bytes hold every tag and no pixel.

**Tag 270 against the `.txt`**: 39 of the 40 keys are the same, with the same values; one is spelled differently (`.txt` `InstrumentName`, tag 270 `Instrument name`, same value). The `.txt` has CRLF and a final line end, tag 270 `\r` between lines and none at the end. Tag 65500's seven properties are in neither.

**Tag 65500 and the `.txt`**: tag 65500's keys are not in the `.txt`. What its keys mean is not documented anywhere I found.

**What helps a search**, as the person would ask: the instrument (`Instrument name`), the signal (`Signal name`: BF, HAADF, SE …), the operation mode, the accelerating voltage, the magnification, the pixel size, the sample (`SampleName`), the date and time. No operator key. These are the summary line's entries (D6).

**The listing** (October, `.claude/survey/listing-2026-10-15.tsv.gz`, about a quarter of the tree): 424 `.txt` files next to an image of the same stem, 411 of them next to a `.tif` (7 folders; the `.txt` 829 to 877 bytes, the TIFF 1,097,643 to 4,341,885 bytes; one more `.tif` in those folders without a `.txt`), 13 next to a `.png` (not looked at). A UTF-16 `.txt` would be about twice as large, so none of the 411 is one.

## D2 Sources

| Source | What it says | Checked |
|---|---|---|
| Gwyddion, `modules/file/hitachi-sem.c` (David Nečas, 2011, GPL-2.0-or-later; [SourceForge](https://sourceforge.net/p/gwyddion/code/HEAD/tree/trunk/gwyddion/modules/file/hitachi-sem.c)) | declares `application/x-hitachi-sem`, comment "Hitachi SEM data", magic `[SemImageFile]` at offset 0, priority 80; its file(1) rule also looks for `\r\nSerialNumber=` within 160 bytes; user guide: "Hitachi S-3700 and S-4800 SEM data", ".txt + image", read only. Detection: the `.txt` by its first line, the image by the header's `ImageName` (as written, upper, lower case); requires `ImageName`, `DataSize`, `PixelSize` (in nm); every key goes into its metadata | source read, 2026-11-13 |
| Debian, [MimeTypesSupport/PackageList](https://wiki.debian.org/MimeTypesSupport/PackageList) | `application/x-hitachi-sem` and `application/x-hitachi-spm`, both declared by the package gwyddion | 2026-11-13 |
| Bio-Formats, `HitachiReader.java` ([GitHub](https://github.com/ome/bioformats/blob/develop/components/formats-gpl/src/loci/formats/in/HitachiReader.java), GPL-2.0-or-later), and its [format page](https://bio-formats.readthedocs.io/en/v8.4.0/formats/hitachi-s-4800.html) | "the file format reader for S-4800 files", extensions `.txt`, `.tif`, `.bmp`, `.jpg`; magic `[SemImageFile]`, tried as UTF-16 too; the image by `ImageName`, else the same stem with `.tif`, `.jpg`, `.bmp`; all keys of the `[SemImageFile]` section as metadata; maps `SampleName`, `Date`+`Time` (`MM/dd/yyyy HH:mm:ss`), `InstructName`, `SerialNumber`, `PixelSize`, `WorkingDistance`, `StagePositionX/Y/Z` | source read through a summary of the page, 2026-11-13 |
| Bio-Formats [PR 3809](https://github.com/ome/bioformats/pull/3809), merged 2022-05-27 | "Hitachi datasets, which consist of one text file and one pixels file (e.g. TIFF)"; a UTF-16 text file ("by resaving in Notepad"); pixel size in nanometres, checked "against the burned-in scale bar"; the reader chosen from the TIFF too; renamed pixel files | 2026-11-13 |
| image.sc, "Hitachi TEM image compatibility" ([thread](https://forum.image.sc/t/hitachi-tem-image-compatibility/54918)) | reported by a web search's summary: Bio-Formats supports Hitachi SEM only, a TEM variant has a `[TemImageFile]` header | **not verified**: the forum refused the fetch (403) |
| RosettaSciIO, HyperSpy | no Hitachi reader; no issue mentions Hitachi (GitHub search of `hyperspy/rosettasciio`, 0 results) | 2026-11-13 |
| tifffile 2026.11.8 | no Hitachi parser; tag 65500 and 65501 come under their numbers | the sample, 2026-11-13 |
| Python's `configparser` | measured on a made-up header: keys with spaces kept with `optionxform = str`, but values stripped of surrounding spaces, an indented line taken as a continuation (`MultilineContinuationError` for the whole header), `\r`-only line ends not split by `read_string` | 2026-11-13 |

Not found: Hitachi's own description of the format; a public Hitachi pair with a licence (OME's public `downloads.openmicroscopy.org/images/` has none; Bio-Formats' `curated/hitachi` is its private test data); a Python reader.

**This S/TEM's header differs from the S-4800's** as Gwyddion and Bio-Formats read it: no `ImageName` (it has `File name`), no `DataSize` (`Data size`), no `SerialNumber`, `InstrumentName` or `Instrument name` instead of `InstructName`, `Date` as `yyyy/mm/dd` instead of `MM/dd/yyyy`. Gwyddion would refuse this file (its required keys are missing). So the rule here is the first line only, every key kept as written (no list of wanted keys), and the summary line names the keys of the header seen; an S-4800 header's other spellings would add entries to `HEADLINE` once one is seen.

**MIME type (R25)**: `application/x-hitachi-sem` is established in the wild (Gwyddion, Debian's list) for exactly this header; the S/TEM's header is the same `[SemImageFile]` section, so the name fits although the instrument is an S/TEM. Lean (L2, Q2): this type for the dataset.

## D3 What else is in the TIFF

- **The image is taller than the header's `Data size`**: 1056 rows against 1024. The header's `Data display combine` and `Add embed of property` suggest it, and Bio-Formats' PR speaks of a "burned-in scale bar". So the last 32 rows are probably the data bar. Not checked: the sample holds the first 47 rows only. Nothing in this change depends on it; the values say both, as found.
- **Resolution**: per inch, a screen's default, kept as found (as for every TIFF).
- **Tag 65500**: properties the `.txt` lacks (mode and submode ids, scan times, the stage's tilt axis). Kept, parsed (D5). Its group `@Confidential` is the vendor's word (Q4).
- **Tag 65501**: a long hexadecimal text; an encrypted or encoded block, a checksum or a signature, nothing says which. Left out by the shared check as too long; no rule of ours (Q5).

## D4 Recognition

`em/hitachi`, priority 60, reacts to `image/tiff`. For each TIFF of the directory, the entry named as the TIFF with its last suffix replaced by `.txt` (`a_x50.0k_0007.tif` → `a_x50.0k_0007.txt`: only the last suffix, as names hold dots); if it exists and its first 14 bytes (`d.read`, counted against the directory's budget) are `[SemImageFile]`, one dataset: anchor the TIFF, members the TIFF and the `.txt`, basis `header <name>.txt`. A read error of the `.txt` is `d.cannot_read` and leaves the TIFF alone (the directory is recognised again next crawl). Nothing else is read: the TIFF's tags are read at extraction.

- Why the `.txt` and not the TIFF: the signature is at the `.txt`'s offset 0, 14 bytes; the TIFF's description is behind its IFD (offset 206 in the sample), a parse at recognition.
- Why not a MIME rule for the `.txt`: its name gives `text/plain` without a read (shared-mime-info's order); a glob `*.txt` of ours would tie and make every `.txt` in the tree be read at recognition, to find 411. The 14-byte read here happens only for a `.txt` next to a TIFF of its stem.
- `.TXT`, `.bmp`, `.jpg` partners and the `File name` key: not used (out of scope; none in the listing).

## D5 Values

The dataset's values are what the image area's TIFF extractor gives for the anchor, plus `text` (D7). The image area learns Hitachi's blocks, so a lone TIFF gets them too (L7):

- **Tag 270**: when `ImageDescription` starts with `[SemImageFile]`, it is split into lines (`str.splitlines`: `\r`, `\n`, `\r\n`), a line `[<section>]` starts a section, every other line is split at its first `=` into key and value, both as written (no strip), into `<section>.<key>`; a line without `=` is a key with the value `""`; a key met twice keeps its last value. The description as one text leaves the values, as ImageJ's does. Our own few lines, as Merlin's `read_header`, not `configparser`, which strips values and refuses a whole header for one indented line (D2).
- **Tag 65500**: when tag 270 is Hitachi's, every item `"@<group>"<key>=<value>` (the value up to the next `"` or line end) goes into `65500.@<group>.<key>`, a key met twice keeping its last value; what does not match an item is left out, and if nothing matches the tag stays one text as today. The glued repeat in the sample then reads right: `ScanTimeX` and `Stage tilt axis` both get their values (checked on the sample's shape with a made-up tag).
- **Tag 65501**: left out by `values.textual` as too long (the image area's skip list, part 5). Nothing new.
- Names: `SemImageFile.Accelerating voltage`, `SemImageFile.PixelSize`, `65500.@Confidential.ScanTimeX`; in the record's tag lines, if it shows them, `SemImageFile.Accelerating voltage: 300000`.
- No merge with the `.txt` (L3): the TIFF is the anchor and its tags are what the image area shows for every TIFF; the `.txt` is shown as written. Alternatives: (a) parse the `.txt` too, as `SemImageFile.*` from the `.txt` and the tag's under `ImageDescription.*`: 40 entries twice; (b) one merged `SemImageFile.*`, the `.txt`'s keys added where the tag lacks them (`InstrumentName`): a rule of ours deciding which file wins, and an entry whose source the reader cannot tell. Strongest argument against the lean: a pair whose TIFF has no `[SemImageFile]` description (an older SEM, a TIFF saved again by another program) has no header values, only the text; none seen, a fallback to parsing the `.txt` is a next step when one turns up.

## D6 The summary line

Added to the image area's `HEADLINE` (spec `formats/image`, "The summary line of an image file"), after Zeiss's entries and before `ImageWidth`: `SemImageFile.Instrument name`, `SemImageFile.Signal name`, `SemImageFile.Operation mode` (text, bare), `SemImageFile.Accelerating voltage` (`Accelerating voltage <v> (unit unknown)`), `SemImageFile.Magnification` (`Magnification <v>`), `SemImageFile.PixelSize` (`PixelSize <v> (unit unknown)`), `SemImageFile.SampleName` (bare); after Zeiss's date and time: `SemImageFile.Date`, `SemImageFile.Time` (bare). The values are texts in the header; a number is recognised as one by its text (an `int` or `float` literal) and then put after its key, a 0 left out (not seen; a magnification or voltage of 0 says nothing).

Example, made up: `HF3300, HAADF, Analysis, Accelerating voltage 300000 (unit unknown), Magnification 50000, PixelSize 0.5 (unit unknown), Au on C, ImageWidth 1024, ImageLength 1056, BitsPerSample 8, 2024/01/15, 09:30:00`.

"(unit unknown)" after the voltage and the pixel size: the header names no unit; Gwyddion and Bio-Formats read the pixel size as nm, Bio-Formats after comparing with the scale bar; that is their interpretation, not the file's (README of `modama-formats-em`, "Values and units"). Left out on purpose: `STEM camera length` (in TEM modes probably meaningless; in the values), `Keyword1` (repeats the voltage with a unit), `Data size` (the image's size is there), stage and aperture entries.

## D7 The text

`values["text"]` is the `.txt` by the rule of change `text-as-written` (its spec `formats/text`, "The text as written", "Head and tail of a long text", "A credential is left out of the text"), through its shared module: decoded as the text area decides (ASCII here), line ends as line feeds, whole up to 4,096 characters, else head and tail. The record then carries it as its second description, in place of the tag lines (`text-as-written`, `records`). So the record of a pair shows the header in the instrument's words; the TIFF's other tags (tag 65500, the baseline tags) are in the values (`modama-chain browse`, `records --verbose`), not in the record. Strongest argument against: tag 65500's properties are searchable only if they reach the record; the alternative, the tag lines and the text both, is the one `text-as-written` D2 argues against (the same content twice, the embedding's 512 tokens).

## D8 Claimed files: the runner

Today (`formats/__init__.py`, `run_post`): formats run in descending priority; a format's dataset whose members a format that ran earlier claimed is dropped with the warning `<format>: <file> already claimed by <format>`. `Directory.of_type` returns every entry of the type, claimed or not. So after `em/hitachi` (60) claims a pair, `common/tiff` (50) yields the TIFF and `common/text` (20) the `.txt`, and each is dropped with a warning: two per pair, at every recognition of the folder. The same holds for `em/de` against `em/mrc` (BACKLOG, item 302), where `em/mrc` would also read 211 bytes of each claimed file.

| Option | What changes | Against |
|---|---|---|
| A. `of_type` returns only unclaimed entries (lean) | the runner tells the `Directory` what is claimed after each format; `of_type` filters; `entry(name)` and `entries` stay as they are, so a format that finds a file by name and claims it is still warned about | a later format can no longer see that a file of its type exists in the directory (none uses that today); a real conflict between two formats that both use `of_type` goes unseen, the higher priority winning silently |
| B. Each lower format skips claimed entries itself (`d.claimed(e)`) | every single-file format (image, text, structured, mrc …) changes | every format must remember it; one that forgets warns again |
| C. A list of warnings to keep quiet | none | hides the symptom; the formats still run and read |
| D. No change | 822 warnings per crawl of the listing's quarter | noise that hides real warnings |

The recognition spec already says "an entry or child dataset claimed by a dataset SHALL NOT be available to formats that run later"; A makes `of_type` do what it says. The warning stays for a claim that reaches the runner anyway. Lean: A, in this change, as the first format that needs it (Q9).

**Settled elsewhere before the build** (2026-11-13): bug 311 made the runner leave every claimed file out of the entries it offers the formats after the one that claimed it (by type and by name), and decision 344 added `Directory.claimed` (who claimed a file the format is not offered) and `Directory.claimed_elsewhere` (a warning ending in "two formats want it", collected for review). This change therefore has no runner part and no `recognition` delta. `em/hitachi` asks `d.claimed` for the `.txt` of each TIFF's stem: when another format took it, the TIFF gets the warning and is left to the formats after `em/hitachi` (spec `formats/hitachi`, "The header claimed by another format"). The header itself cannot be checked then (it is not offered), so the warning may flag a `.txt` that is not Hitachi's; no format above 60 claims `.txt` files today.

## D9 Bytes read

- Recognition: 14 bytes of each `.txt` next to a TIFF of its stem.
- Extraction: the TIFF's tags as the image area reads them (a 64 KiB buffer, readahead off; the sample's IFD at byte 8 and its tags' values up to byte 16,536, so one buffer), and the `.txt` as the text area reads a text (whole up to its 1 MiB head; 829 to 877 bytes in the listing). Test: a generated pair whose TIFF has a 1 GiB sparse strip: `rchar` of the extraction under 256 KiB.

## D10 Fixtures

No public Hitachi pair with a licence was found (D2). Lean (Q11): generated at test time with tifffile (`generate.py`): a TIFF of 64 × 96 pixels (a `Data size` of 64x64 and 32 rows more), its tag 270 the made-up header with `\r` line ends and the real file's 40 keys in their order, tag 65500 with the real file's item syntax (seven items, the glued repeat), tag 65501 with 15,156 hexadecimal characters; the `.txt` the same block with CRLF and the `InstrumentName` spelling. `validity = "parser-only"`, as nothing that writes the format wrote it. Plus reproducers: a TIFF and a `.txt` of its stem with notes (no pair); a lone TIFF; a lone `.txt`; a header with a key nobody has seen. A cut of the real pair (its first 16,536 bytes and the `.txt`, unchanged; `validity = "vendor-written"`, cut) would be the representative fixture the TEMPLATE asks for, only if @weber agrees to publish its values under a licence.

## Questions to @weber, with leans

Answered on 2026-11-13: all leans accepted (313); Q4: the `@Confidential` items kept as the file says them; Q11: fixtures generated from the sample's layout, values made up (314). Q9 became moot (D8). Q1's second part (which instruments the other folders hold) and Q5 (what tag 65501 is) stay open.

- **Q1** The pair: the `.txt` of the TIFF's stem, by its first line `[SemImageFile]` (lean); or also by the header's `File name` naming the TIFF. Are all 411 in the listing from the S/TEM of the sample, or do the other folders hold SEM (SU-series, S-4800) or HF3300 pairs whose header may be spelled otherwise?
- **Q2** Type `application/x-hitachi-sem`, Gwyddion's (lean), though the sample's instrument is an S/TEM; or `image/tiff` for the dataset (a search by format finds it among TIFFs); or `application/x.hitachi-em` of our own.
- **Q3** Values from the TIFF only, the `.txt` as text (lean); or the `.txt` parsed as well (a or b in D5).
- **Q4** Tag 65500's `@Confidential` items (scan times, the stage's tilt axis): kept (lean: every entry minus a skip list; nothing personal); or left out because the vendor calls them confidential and a record reaches more people than the file.
- **Q5** Tag 65501 (15,156 hexadecimal characters): left out as not suitable for text (lean). Does anyone at ER-C know what it is?
- **Q6** The record's second description is the `.txt` as written (lean, `text-as-written`'s rule); or the TIFF's tag lines, which hold tag 65500 too.
- **Q7** The summary line's entries and "(unit unknown)" after voltage and pixel size (lean); or more entries (camera length, stage position) or fewer.
- **Q8** A lone `.txt` with the header stays a text file (`text/plain`, its text in the record; lean); or `em/hitachi` reads every `.txt`'s first bytes to type it `application/x-hitachi-sem`.
- **Q9** The runner's change (D8, option A) in this change (lean); or a change of its own before this one and `em/de`.
- **Q10** `em/hitachi` in `modama-formats-em`, which then depends on `modama-formats-common` (lean); or the pair in the image area of `modama-formats-common` (as `common/hitachi`, beside FEI's and Zeiss's TIFFs; no dependency between the packages).
- **Q11** Fixtures generated from the layout, values made up (lean); and a cut of the real pair (first 16,536 bytes, every tag and no pixel, the `.txt` whole) as the representative one, if you agree to publish it.
