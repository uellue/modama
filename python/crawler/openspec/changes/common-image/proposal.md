# Proposal

## Why

@weber, 2026-11-12, as a task for the night: "Let's develop more format libraries to be tested tomorrow. Apply all lessons from EM formats as far as applicable. Use publicly available test data", images first among the five areas; "go with your leans, upstream prior art and common sense. Just don't do anything that could realistically disrupt the crawl"; "please use the 'industry standard' readers and practices". Common image files are the largest group in the tree (October listing, `.claude/survey/listing-2026-10-15.tsv.gz`): 128,491 `.tif` (67,600 of them in one folder of diffraction patterns, 10,100 in another), 5,272 `.tiff` (EPU movie fractions of 185 to 369 MB among them), 10,965 `.png`, 6,313 `.jpg` and 24 `.jpeg`, 1,930 `.bmp`, 159 `.svg`, 127 `.gif`, 83 `.eps`, 15 `.webp`. The core types them all by name already (`freedesktop.org.xml`); their records say only "TIFF image, 1 file, 66.4 kB". Many TIFFs come from microscopes (FEI/Thermo and Zeiss SEM and FIB, ImageJ, DM exports) and carry the instrument's metadata in tags that tifffile reads. Serves R30 (findable by what the data is) and R21 (formats outside the core).

## What Changes

- The `image` part of the collection `common` (`python/modama-formats-common/src/modama_formats_common/image/`): formats `common/tiff`, `common/png`, `common/jpeg`, `common/bmp`, `common/gif`, `common/webp` and `common/svg`, each claiming the files of the core's type (`image/tiff`, `image/png`, …) as single-file datasets and extracting their metadata. No new MIME rules: the core's are right for these files.
- **TIFF** through tifffile: every tag of the first page under tifffile's name (a tag tifffile has no name for under its number), the vendor blocks tifffile parses inside them (FEI/Thermo `FEI_HELIOS`/`FEI_SFEG`, Zeiss `CZ_SEM`, EXIF, …) flat under dotted names, an ImageJ file's description as tifffile's `imagej_metadata`, its `Info` line by line; the first page's shape, data type and axes as `mapped_metadata`.
- **PNG, JPEG, BMP, GIF, WEBP** through Pillow: what `Image.open` reads before the image data (`info`: PNG text chunks, JFIF, comments, …), the EXIF block parsed by Pillow with its Exif, GPS and Interop IFDs under Pillow's tag names; width, height, mode and Pillow's `dpi` as `mapped_metadata`.
- **SVG** through defusedxml: the root element's attributes and the elements at the root that are not the drawing (`<title>`, `<desc>`, `<metadata>`, foreign metadata).
- **EPS**: recognition by the core only, no extraction (see the leans).
- A summary line per format from a few chosen entries; the values become the record's second description (change `tags-in-the-record`).
- New dependencies of `modama-formats-common`: tifffile, Pillow, defusedxml (NumPy comes with tifffile).

Behaviour towards the user: the records of about 155,000 image files gain a summary line before the basic description (for example `FEI_HELIOS` files: `Helios NanoLab" 660, ETD, SE, HV 5000 (unit unknown), ImageWidth 512, ImageLength 471, BitsPerSample 8, 06/13/2016, 05:06:40 PM; TIFF image, 1 file, 252.4 kB, in …`) and a second description with their tags. Types, datasets and record counts stay as they are. The first crawl after the merge extracts each of these files once (an open and a header read each, on NFS).

## Assumptions and leans (to be confirmed at the review)

1. **No content check at recognition.** The checklist asks for recognition by content where names lie; here the cost is one open and read per file during recognition, on top of the extraction's, in folders of up to 67,600 TIFFs (recognition has a byte budget of 1 MiB and a slow-call warning at 5 s per format and folder). No image file named for a type it is not has been seen. A file that is not what its name says fails at extraction with the reader's error, as a warning; its type stays the name's. Revisit when such a file turns up.
2. **The first page only, no page count or series for TIFF.** tifffile's `series`, `len(pages)` and the file-level `flags` walk every page's IFD (one read each, anywhere in the file); the multi-page files in the tree are movie fractions of hundreds of MB. What the first page says is complete for single-page files (most of the tree); the shape tifffile writes into a description (`{"shape": …}`) and ImageJ's `images=` are in the values as the file states them. `TiffFile` is opened with `is_lsm`, `is_scanimage` and `is_ndpi` off, which otherwise load all pages on open.
3. **A tag value of more than 1 MiB is not read** (`MAX_TAG_BYTES`), of the tags tifffile reads on demand: such a value cannot pass `textual` anyway; it bounds what one file can make the extractor read. The tags tifffile loads with the page (`ImageDescription`, `Software`, `IJMetadata`, the strip and tile offsets: `TIFF.TAG_LOAD`) it reads when it opens the page, whatever their size; `textual` decides about them afterwards.
4. **EPS: recognition only.** Pillow's EPS reader reads the whole file one byte at a time to its end (`%%EOF`) to find the trailer; not light. The core types `.eps` files already.
5. **WEBP: Pillow reads the whole file** (libwebp's demuxer takes it in memory); files above 16 MiB (`WEBP_LIMIT`) are not extracted. The tree's 15 WEBP files are at most 0.3 MB.
6. **PNG: the chunks before the image data.** Pillow's `open` stops at the first `IDAT`; text chunks after the image data are not read (that would take a pass over all `IDAT` chunks). Pillow's `PngImageFile.getexif()` decodes the whole image when the file has no `eXIf` chunk before the image data; the EXIF block is parsed from `info["exif"]` with `Image.Exif.load` instead.
7. **Names and values as the reader gives them**: tifffile's tag names and its enum names (`NONE`, `MINISBLACK`) for the codes it names, rationals as `[numerator, denominator]` as tifffile reads them; Pillow's `ExifTags.TAGS` and `GPSTAGS` names, its rationals as numbers (Pillow's `IFDRational`), a tag without a name under its number; JPEG and GIF comments, which Pillow gives as bytes, as text where they are valid UTF-8 (the formats define them as text). Other bytes are left out (`textual`).
8. **The skip lists** (one per reader, in the spec): where the image data is (strip and tile offsets and byte counts, IJMetadata's byte counts, the EXIF sub-IFD pointers), FEI's data bar settings of the user interface, the EXIF thumbnail (IFD1), and values not suitable for text.
9. **"(unit unknown)"** after a physical quantity whose file states no unit (FEI's `HV`); not after counts (pixels, bits), which have no unit.
10. **Fixtures**: RosettaSciIO's FEI Helios and Zeiss SEM TIFFs and its ImageJ TIFF (GPL-3.0-or-later, as the DM fixtures), Pillow's camera JPEG `flower.jpg` (Pillow's MIT-CMU licence; the repository names no separate licence for its test images, Debian's `debian/copyright` puts them under `Files: *`, HPND, after its review in Pillow issue #4591), Matplotlib's SVG `multi_font_astext.svg` (Matplotlib licence), the rest written at test time by Pillow and tifffile.
11. **SVG with entity declarations** (Adobe Illustrator writes some) are refused by defusedxml's defaults; extraction fails with its error, a warning. Kept: the safe defaults for files from anyone.

### From the review (2026-11-12, decisions of main; the leans above agreed)

12. **SVG: at most the first MiB, also within one element.** One large element (Matplotlib's base64 `<image>`) made the parser read to its end; the file is read through a reader that ends at `SVG_LIMIT`, the parse error of that cut is caught, what was found is kept (the tree has 10 SVGs over 1 MiB, the largest 22.6 MB).
13. **Pillow's decompression-bomb check is off while a header is read**: it guards decoding, which never happens here, and failed the extraction of headers over 179 Mpixel. A compressed text chunk over Pillow's `MAX_TEXT_CHUNK` no longer fails the extraction: the header is read again with Pillow's leniency (`ImageFile.LOAD_TRUNCATED_IMAGES`, set only for that open), which keeps that chunk's keyword with an empty text; every empty text is then left out (they cannot be told apart), and Pillow's message goes into `reader_warnings` and the summary line as `formats/blockfile` does. Both settings are global in Pillow and restored after the open.
14. **ImageJ's `Info` line by line**: lines `key = value` as `imagej_metadata.Info.<key>`, other lines counted (`imagej_info_lines_left_out`). A small parser of our own: tifffile gives `Info` as one text, which `textual` drops whole when it is long (18,996 characters in the fixture, a DM file's tags).
15. **EXIF bytes as text where they are UTF-8** (`ExifVersion` `0220`), binary ones still left out by `textual`; Pillow's `dpi` (its conversion of pHYs, a BMP header or JFIF) in `mapped_metadata`; `pil.skipped` and `svg.skipped` named as `tiff.skipped`; the SVG rule phrased as a skip list (the drawing, Inkscape's `sodipodi:namedview`), so foreign metadata at the root is kept; `mapped_metadata.shape` renamed `first_page_shape`.
16. **Zeiss and FEI values in tifffile's form** (`CZ_SEM.ap_actualkv: ["EHT", 5.0, "kV"]`) kept; to be confirmed with @weber.

Out of scope: pixel data of any kind (statistics, thumbnails); page counts and series of multi-page TIFFs (lean 2); XMP packets (bytes in Pillow; Pillow's `getxmp` would parse them); OME-XML beyond the tag's text (no `.ome.tif` in the listing); grouping image series (for example the 67,600 diffraction patterns) into one dataset; new MIME types.

## Capabilities

### New Capabilities
- `formats/image`: common image files (TIFF, PNG, JPEG, BMP, GIF, WEBP, SVG) as single-file datasets with their metadata from the established readers; EPS by the core's type only.

### Modified Capabilities
None.

## Impact

- `python/modama-formats-common/`: the `image/` part (formats, fixtures, tests), its entry in `PARTS`, the README's table, dependencies `tifffile`, `pillow`, `defusedxml` pinned in `pyproject.toml`.
- The crawl: one extraction per image file after the merge (any code change does that, `identity.py`); each reads the header (a 64 KiB buffer, readahead off), the first IFD and its tag values for TIFF; the search stack's image needs a rebuild for the new dependencies.
