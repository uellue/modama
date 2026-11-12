# Spec Delta

## ADDED Requirements

### Requirement: Image files are datasets of their format
A file of the core's type `image/tiff`, `image/png`, `image/jpeg`, `image/bmp`, `image/gif`, `image/webp` or `image/svg+xml` SHALL be a dataset of one file of the format `common/tiff`, `common/png`, `common/jpeg`, `common/bmp`, `common/gif`, `common/webp` or `common/svg`, with the basis `single file`, whatever its content: recognition reads nothing (proposal, lean 1). An EPS file SHALL keep the core's type `image/x-eps` and no format.

#### Scenario: An SEM image from an FEI instrument
- **WHEN** a folder holds `FEI-Helios-Ebeam-8bits.tif`, written by an FEI Helios NanoLab 660
- **THEN** it is one dataset of the format `common/tiff`, type `image/tiff`, basis `single file`

#### Scenario: An image of each other kind
- **WHEN** a folder holds a PNG, a JPEG, a BMP, a GIF, a WEBP and an SVG file, each named for its type
- **THEN** each is one dataset of its format (`common/png`, `common/jpeg`, `common/bmp`, `common/gif`, `common/webp`, `common/svg`)

#### Scenario: An EPS file
- **WHEN** a folder holds `figure.eps` with an EPS header
- **THEN** its type is `image/x-eps`, it has no format and no extraction

#### Scenario: A text file named like an image
- **WHEN** a text file is named `notes.tif`
- **THEN** it is a dataset of `common/tiff` and its extraction fails with tifffile's error, which the crawl reports as a warning

### Requirement: TIFF metadata is every tag of the first page
The extractor of `common/tiff` SHALL read the file with tifffile, the first page only, and keep as `original_metadata` every tag of the first page under tifffile's name (a tag without a name under its number, `65003`), its value as tifffile reads it: a code tifffile names under its name (`NONE`), a tuple as a list, a dict (a vendor block tifffile parses: `FEI_HELIOS`, `FEI_SFEG`, `CZ_SEM`, `ExifTag`, `IJMetadata`, …) flat under dotted names (`FEI_HELIOS.Beam.HV`), an infinity or NaN as its text. For a file tifffile recognises as ImageJ's, the tags `ImageDescription` and `IJMetadata` SHALL be kept as tifffile's `imagej_metadata` instead, flat under that name. `mapped_metadata` SHALL be the first page's shape as `first_page_shape`, its `dtype` and `axes` as tifffile gives them. Empty values SHALL be kept.

#### Scenario: The FEI metadata of an SEM image
- **WHEN** `FEI-Helios-Ebeam-8bits.tif` is extracted
- **THEN** its values hold `FEI_HELIOS.Beam.HV` 5000, `FEI_HELIOS.System.SystemType` `Helios NanoLab" 660`, `FEI_HELIOS.User.Date` `06/13/2016`, `FEI_HELIOS.EBeam.EmissionCurrent` `""`, `ExifTag.ImageUniqueID`, `Compression` `NONE`, `XResolution` `[64, 1]`, and `mapped_metadata` `first_page_shape` `[471, 512]`, `dtype` `uint8`, `axes` `YX`

#### Scenario: The Zeiss metadata of an SEM image
- **WHEN** `test_tiff_Zeiss_SEM_512pix.tif`, written by a Zeiss ULTRA 55, is extracted
- **THEN** its values hold `CZ_SEM.ap_actualkv` `["EHT", 5.0, "kV"]` and `CZ_SEM.dp_detector_channel` `["Signal A", "InLens"]`

#### Scenario: An image saved by ImageJ
- **WHEN** `test_loading_image_saved_with_imageJ.tif`, saved by ImageJ 1.51a, is extracted
- **THEN** its values hold `imagej_metadata.ImageJ` `1.51a` and `imagej_metadata.unit` `micron`, and no `ImageDescription` or `IJMetadata`

### Requirement: ImageJ's Info line by line
ImageJ's `Info` entry, one text in tifffile's `imagej_metadata`, SHALL be kept line by line where it has lines of the form `key = value` (the first ` = ` splits): each such line as `imagej_metadata.Info.<key>` with its value as text, as found; the number of its other lines as `imagej_info_lines_left_out` in `mapped_metadata` (only when there are any); `Info` with no such line SHALL be kept as it is (then `textual` decides). This is a small parser of our own: tifffile gives `Info` as one text, and ImageJ writes there whatever the image brought (a DM file's tags, 18,996 characters in the fixture), more than `textual` lets through as one value.

#### Scenario: ImageJ's Info line by line
- **WHEN** `test_loading_image_saved_with_imageJ.tif`, whose `Info` holds a DM file's 274 tags as `root.… = …` lines, is extracted
- **THEN** its values hold 274 entries `imagej_metadata.Info.…`, among them `imagej_metadata.Info.root.ApplicationBounds` `{0,0,701,1276}`, and no `imagej_metadata.Info`

#### Scenario: ImageJ's Info with lines of another form
- **WHEN** an ImageJ TIFF written by tifffile has the `Info` `Exposure = 0.5`, `free text`, `[a section]`, `Gain = 2`
- **THEN** its values hold `imagej_metadata.Info.Exposure` `0.5` and `imagej_metadata.Info.Gain` `2`, and `mapped_metadata` `imagej_info_lines_left_out` 2

#### Scenario: A tag nobody has seen before
- **WHEN** a TIFF written by tifffile has a private tag 65500 holding the text `new value`
- **THEN** its values hold `65500` `new value`

### Requirement: What a TIFF's values leave out
The values of `common/tiff` SHALL leave out one skip list (`tiff.skipped`): where the image data is (`StripOffsets`, `StripByteCounts`, `TileOffsets`, `TileByteCounts`, `IJMetadataByteCounts`); the data bar settings of FEI's user interface (`FEI_HELIOS.PrivateFei.DataBarAvailable`, `.DataBarSelected`, the same under `FEI_SFEG`); a value of more than 1 MiB of a tag tifffile reads on demand, which is not read (`MAX_TAG_BYTES`, proposal lean 3; tifffile reads the tags it loads with the page, such as `ImageDescription`, `Software`, `IJMetadata` and the offsets, whatever their size, and `textual` decides about them); the lines of ImageJ's `Info` that are not `key = value` (counted); and values not suitable for text (`modama_crawler.formats.values.textual`: a colour map of 768 numbers, bytes such as `JEOL_Header`, Zeiss's unnamed list of 37 numbers under `CZ_SEM.`).

#### Scenario: Layout, settings and arrays are left out
- **WHEN** `FEI-Helios-Ebeam-8bits.tif` and `test_tiff_Zeiss_SEM_512pix.tif` are extracted
- **THEN** their values hold no `StripOffsets`, no `StripByteCounts`, no `FEI_HELIOS.PrivateFei.DataBarAvailable`, no `ColorMap`, and `FEI_HELIOS.PrivateFei.DatabarHeight` is kept

#### Scenario: A large tag value is not read
- **WHEN** a TIFF has a private tag of 1 MiB and one byte, which tifffile reads on demand
- **THEN** its values do not hold it, and less than 256 kB of the file is read

### Requirement: Pillow's formats' metadata is what Pillow reads before the image data
The extractors of `common/png`, `common/jpeg`, `common/bmp`, `common/gif` and `common/webp` SHALL open the file with Pillow (`Image.open`, restricted to the format's plugin) and keep as `original_metadata` every entry of its `info` under Pillow's key, a tuple as a list, a dict flat under dotted names; a JPEG's or GIF's `comment`, which Pillow gives as bytes, as text where it is valid UTF-8. The EXIF block (`info["exif"]`) SHALL be kept parsed by Pillow's `Image.Exif` instead of its bytes: the tags of IFD0 under `exif.<name>`, the Exif, GPS and Interop IFDs under `exif.Exif.<name>`, `exif.GPSInfo.<name>`, `exif.Interop.<name>`, names as Pillow's `ExifTags.TAGS` and `GPSTAGS` give them, a tag without a name under its number, a rational as Pillow's number, bytes (EXIF's type UNDEFINED) as text where they are valid UTF-8. `mapped_metadata` SHALL be the image's `width`, `height` and `mode`, and `dpi`, Pillow's conversion of the file's resolution. Pixel data SHALL NOT be decoded, so Pillow's decompression-bomb check, which guards decoding, SHALL be off while the header is read. A compressed text chunk that Pillow refuses as larger than its `MAX_TEXT_CHUNK` SHALL NOT fail the extraction: the header is read again with Pillow's leniency, which keeps that chunk's keyword with an empty text, every empty text is then left out, and Pillow's message is kept as `reader_warnings` and in the summary line as `reader warning: …` (as `formats/blockfile`). A WEBP file of more than 16 MiB SHALL NOT be extracted (proposal, lean 5).

#### Scenario: The EXIF of a camera JPEG
- **WHEN** Pillow's test image `flower.jpg`, taken with a Canon PowerShot S40, is extracted
- **THEN** its values hold `exif.Make` `Canon`, `exif.Model` `Canon PowerShot S40`, `exif.Exif.DateTimeOriginal` `2003:12:14 12:01:44`, `exif.Exif.ExposureTime` 0.002, `exif.Interop.InteropIndex` `R98`, `jfif_version` `[1, 1]`, `jfif_density` `[72, 72]`, and `mapped_metadata` `width` 480, `height` 360, `mode` `RGB`, `dpi` `[72, 72]`

#### Scenario: EXIF fields of type UNDEFINED as text
- **WHEN** `flower.jpg` is extracted
- **THEN** its values hold `exif.Exif.ExifVersion` `0220` and `exif.Exif.FlashPixVersion` `0100`, and no `exif.Exif.ComponentsConfiguration` (the bytes 1, 2, 3, 0)

#### Scenario: The text chunks of a PNG file
- **WHEN** a PNG written by Pillow has the text chunks `Title`, `Software`, an empty `Comment`, a compressed and an international one, and a resolution
- **THEN** its values hold each chunk under its keyword with its text, `Comment` as `""`, and `dpi` only in `mapped_metadata`

#### Scenario: A header of more than Pillow's pixel limit
- **WHEN** a PNG's header says 20,000 × 20,000 pixels (Pillow's decompression-bomb check refuses more than 179 Mpixel)
- **THEN** it is extracted, `width` 20000, and Pillow's limit is as before afterwards

#### Scenario: An oversize compressed text chunk
- **WHEN** a PNG has a `Title`, an empty `Comment` and a compressed chunk `Big` of 2 MiB of text
- **THEN** its values hold `Title`, neither `Big` nor `Comment`, and Pillow's message in `reader_warnings` and at the end of the summary line

#### Scenario: An EXIF tag nobody has seen before
- **WHEN** a JPEG written by Pillow has a COM comment and EXIF with the tag 0xC6FF, which Pillow has no name for, in IFD0 and a GPS IFD
- **THEN** its values hold `exif.50943` with its text, `exif.GPSInfo.GPSLatitude`, and `comment` as text

#### Scenario: The comment of a GIF file
- **WHEN** a GIF written by Pillow with a comment is extracted
- **THEN** its values hold `comment` as text, and `width`, `height` and `mode` `P` are in `mapped_metadata`

### Requirement: What Pillow's formats' values leave out
The values of Pillow's formats SHALL leave out one skip list (`pil.skipped`): the pointers to the EXIF block's sub-IFDs (`exif.ExifOffset`, `exif.GPSInfo` and `exif.Exif.ExifInteroperabilityOffset` as offsets: their IFDs are kept); the thumbnail's IFD1, which is not read; after Pillow refused an oversize compressed text chunk, every empty text; and values not suitable for text (`textual`: `icc_profile`, `MakerNote`, a `UserComment` or `ComponentsConfiguration` with control characters, GIF's `version`). The EXIF block's bytes are kept parsed instead.

#### Scenario: Binary EXIF fields are left out
- **WHEN** `flower.jpg` is extracted
- **THEN** its values hold no `exif.Exif.MakerNote`, no `exif.Exif.UserComment`, no `exif.ExifOffset` and no `exif.Exif.ExifInteroperabilityOffset`, and no tag of IFD1

### Requirement: SVG metadata is the root's attributes and what is not the drawing
The extractor of `common/svg` SHALL parse the file with defusedxml (its defaults: no entity declarations, no external references) and keep as `original_metadata` the root element's attributes as `@<name>` and the elements at the root with their content, flat under dotted paths as in `formats/empad` (`metadata.rdf:RDF.cc:Work.dc:date`, an attribute `….@rdf:resource`, a repeated element numbered `[2]`), names with the prefix the file declares for their namespace; but one skip list (`svg.skipped`): the drawing (every element of the SVG namespace, or of none, but `title`, `desc` and `metadata`: `g`, `defs`, `path`, `image`, `style`, …), Inkscape's user-interface settings (`sodipodi:namedview`), and values not suitable for text. An element of another namespace (foreign metadata) is kept. It SHALL read at most the first MiB of the file (`SVG_LIMIT`), also when one element is larger; what was found by then is kept, and a parse error within a file that ends before the limit fails the extraction.

#### Scenario: An SVG file written by Matplotlib
- **WHEN** Matplotlib's test image `multi_font_astext.svg` is extracted
- **THEN** its values hold `@width` `576pt`, `@height` `432pt`, `@viewBox` `0 0 576 432`, `metadata.rdf:RDF.cc:Work.dc:format` `image/svg+xml`, `metadata.rdf:RDF.cc:Work.dc:type.@rdf:resource`, and no text of the drawing

#### Scenario: An SVG file's title, description and an attribute nobody has seen
- **WHEN** an SVG has `<title>`, `<desc>`, a root attribute `inkscape:version` and a root attribute `data-new`
- **THEN** its values hold `title`, `desc`, `@inkscape:version` and `@data-new` with their text

#### Scenario: What an SVG file's values leave out
- **WHEN** an SVG has at its root a `sodipodi:namedview`, an element `lab:sample` of another namespace and a `rect` with a `title`
- **THEN** its values hold `lab:sample` with its text, nothing of `sodipodi:namedview` and nothing of the `rect`

### Requirement: The summary line of an image file
An image file's summary line SHALL be the values of a few chosen entries as found, in this order, the first present of each group (`HEADLINE` per reader), a text as it is and a number after its name, a number that is 0 left out, a value repeated once: for TIFF `Make`, `Model`, FEI's `System.SystemType`, `Detectors.Name`, `Detectors.Mode`, `Beam.HV` (followed by `(unit unknown)`: the file states no unit), Zeiss's serial number, detector, `EHT`, magnification and pixel size (a Zeiss entry `[label, value, unit]` as `label value unit` when its value is a number, else its value), `ImageWidth`, `ImageLength`, `BitsPerSample`, `Software`, `DateTime`, FEI's `User.Date` and `User.Time`, Zeiss's date and time; for Pillow's formats `exif.Make`, `exif.Model`, `Title`, `width`, `height`, `Software` or `exif.Software`, `exif.Exif.DateTimeOriginal` or `exif.DateTime` or `Creation Time`; for SVG `title`, `width` and `height` after their names (lengths written as text). No words or units of ours but "(unit unknown)".

#### Scenario: The summary line of an FEI SEM image
- **WHEN** `FEI-Helios-Ebeam-8bits.tif` is extracted
- **THEN** its summary line is `Helios NanoLab" 660, ETD, SE, HV 5000 (unit unknown), ImageWidth 512, ImageLength 471, BitsPerSample 8, 06/13/2016, 05:06:40 PM`

#### Scenario: The summary line of a Zeiss SEM image
- **WHEN** `test_tiff_Zeiss_SEM_512pix.tif` is extracted
- **THEN** its summary line starts with `ULTRA 55-36-06, InLens, EHT 5.0 kV, 50.00 K X, Pixel Size 5.825 nm, ImageWidth 512, ImageLength 384`

#### Scenario: The summary line of a camera JPEG
- **WHEN** `flower.jpg` is extracted
- **THEN** its summary line is `Canon, Canon PowerShot S40, width 480, height 360, 2003:12:14 12:01:44`

### Requirement: Only the header is read
Each extractor SHALL read the file's header and metadata only, through a 64 KiB buffer with readahead off (Pillow, tifffile) or unbuffered (SVG), never its image data, and its output SHALL not depend on the local time zone (dates as the file writes them).

#### Scenario: A large image file
- **WHEN** a TIFF (classic, BigTIFF and an ImageJ hyperstack, several pages each), a PNG, a JPEG, a BMP and a GIF of several MB each, written by tifffile and Pillow, are extracted
- **THEN** each extraction reads less than 256 kB of the file

#### Scenario: A large SVG file
- **WHEN** an SVG of 4 MB is extracted
- **THEN** less than 1.1 MB of it is read, and its root attributes are in the values

#### Scenario: An SVG file with one large element
- **WHEN** an SVG of 8 MB, most of it one `<image>` with a data URI as Matplotlib embeds a raster, is extracted
- **THEN** less than 1.1 MB of it is read, and its title is in the values

#### Scenario: A broken small SVG file
- **WHEN** an SVG of a few bytes ends before its root element is closed
- **THEN** its extraction fails with the parser's error

#### Scenario: A large WEBP file
- **WHEN** a WEBP file is larger than 16 MiB
- **THEN** it is not extracted, and nothing of it is read

#### Scenario: Dates in another time zone
- **WHEN** `flower.jpg` is extracted under `TZ=Europe/Berlin` and under `TZ=UTC`
- **THEN** the values are the same, `exif.DateTime` `2003:12:14 12:01:44`
