## ADDED Requirements

### Requirement: A Hitachi image and its header are one dataset
The format `em/hitachi` (priority 60, reacting to `image/tiff`) SHALL make one dataset of a TIFF and the file of its directory named as the TIFF with its last suffix replaced by `.txt`, when that file's first 14 bytes are `[SemImageFile]`: type `application/x-hitachi-sem`, anchor the TIFF, members the TIFF and the `.txt`, basis `header <name of the .txt>`. It SHALL read those 14 bytes of the `.txt` and nothing of the TIFF to decide.

#### Scenario: A pair
- **WHEN** a directory holds `grid2_x50.0k_HAADF_0007.tif` and `grid2_x50.0k_HAADF_0007.txt`, which starts with `[SemImageFile]` (fixture `pair`)
- **THEN** it has one dataset of format `em/hitachi`, type `application/x-hitachi-sem`, anchored at the TIFF, with both files as members, and no other dataset; recognition read 14 bytes

#### Scenario: Only the last suffix is replaced
- **WHEN** the TIFF is `a_x50.0k_0001.tif` and the directory holds `a_x50.0k_0001.txt` with the header and `a_x50.txt`
- **THEN** the pair is the TIFF and `a_x50.0k_0001.txt`; `a_x50.txt` stays a dataset of its own

#### Scenario: A text of the same name that is not the header
- **WHEN** a TIFF has a `.txt` of its stem that starts with `notes:` (fixture `notes_beside_tif`)
- **THEN** there is no `em/hitachi` dataset: the TIFF is a `common/tiff` dataset and the `.txt` a `common/text` dataset, without a warning

#### Scenario: A TIFF without its header
- **WHEN** a TIFF whose description is Hitachi's has no `.txt` beside it (fixture `lone_tif`)
- **THEN** it is a `common/tiff` dataset, with the values and summary line of spec `formats/image` ("Hitachi's header in a TIFF's description", "Hitachi's tag 65500", "The summary line of a Hitachi TIFF")

#### Scenario: A header without its TIFF
- **WHEN** a `.txt` that starts with `[SemImageFile]` has no TIFF of its stem beside it (fixture `lone_txt`)
- **THEN** it is a `common/text` dataset of type `text/plain`, its text as written (change `text-as-written`)

#### Scenario: The header cannot be read
- **WHEN** reading the `.txt`'s first bytes fails
- **THEN** the TIFF and the `.txt` are datasets of their own formats, the crawl warns at the `.txt` that it cannot be read, and the directory is recognised again next crawl

#### Scenario: The pair's files are not offered to the formats after it
- **WHEN** a pair is recognised with the image and text areas' formats too
- **THEN** it is the directory's only dataset, and the crawl warns of nothing (spec `recognition`, "Formats run in priority order with exclusive claims")

#### Scenario: The header claimed by another format
- **WHEN** a format of higher priority claims the pair's `.txt` (decision 344)
- **THEN** the crawl warns at the TIFF `em/hitachi: <name>.txt is claimed by <format>; two formats want it`, and the TIFF is left to the formats after `em/hitachi`

### Requirement: The pair's values are its TIFF's
The extractor SHALL give the pair the summary line, `original_metadata` and `mapped_metadata` that the image area's TIFF extractor gives its TIFF (spec `formats/image`), and SHALL NOT parse the `.txt` into values.

#### Scenario: The summary line of a pair
- **WHEN** the fixture `pair` is extracted (made-up values: instrument `HF3300`, signal `HAADF`, operation mode `Analysis`, voltage `300000`, magnification `50000`, pixel size `0.5`, sample `Au on C`, 64 × 96 pixels of 8 bits, `2024/01/15`, `09:30:00`)
- **THEN** its summary line is `HF3300, HAADF, Analysis, Accelerating voltage 300000 (unit unknown), Magnification 50000, PixelSize 0.5 (unit unknown), Au on C, ImageWidth 64, ImageLength 96, BitsPerSample 8, 2024/01/15, 09:30:00`

#### Scenario: A value the two files disagree on
- **WHEN** the pair's `.txt` says `Magnification=50000` and its tag 270 `Magnification=60000`
- **THEN** `original_metadata` has `SemImageFile.Magnification` `60000` and the summary line `Magnification 60000`, and the text has the line `Magnification=50000`

### Requirement: The pair's text is its header as written
The extractor SHALL put the `.txt`'s text into `values["text"]` by the rules of change `text-as-written` (spec `formats/text`: the text as written, head and tail of a long text, a credential left out), so that it becomes the record's second description (spec `records`).

#### Scenario: The header as written
- **WHEN** the fixture `pair` is extracted (its `.txt` 41 lines with CRLF line ends)
- **THEN** `values["text"]` is the `.txt`'s 41 lines with line feeds, `InstrumentName` spelled as the `.txt` spells it; `original_metadata` has `SemImageFile.Instrument name` as tag 270 spells it and no `SemImageFile.InstrumentName`; the record's second description is the text

#### Scenario: A line that may hold a credential
- **WHEN** the pair's `.txt` has the line `Image comment=password: hunter2`
- **THEN** `hunter2` is not in the text, and `mapped_metadata` has `credentials_left_out` 1

### Requirement: Only the headers are read
The extractor SHALL read the TIFF as the image area reads one (spec `formats/image`, "Only the header is read") and the `.txt` as the text area reads a text; never the TIFF's image data.

#### Scenario: A large TIFF
- **WHEN** a pair whose TIFF has a strip of 1 GiB (a sparse file) is extracted
- **THEN** the extraction reads less than 256 KiB (`rchar`)
