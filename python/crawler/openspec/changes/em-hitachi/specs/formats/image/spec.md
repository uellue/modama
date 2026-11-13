## ADDED Requirements

### Requirement: Hitachi's header in a TIFF's description
When a TIFF's `ImageDescription` (tag 270) starts with `[SemImageFile]`, the TIFF extractor SHALL put its lines into `original_metadata` as entries instead of the description as one text: lines split at `\r`, `\n` or `\r\n`; a blank line is skipped; a line `[<section>]` starts a section; any other line is split at its first `=` into a key and a value, both as written, under `<section>.<key>`; a line without `=` is a key with the value `""`; a key met twice keeps its last value.

#### Scenario: Every line of the header
- **WHEN** the TIFF of the fixture `hitachi_tif` is extracted (tag 270 with `\r` line ends, 40 `key=value` lines after `[SemImageFile]`)
- **THEN** `original_metadata` has 40 entries `SemImageFile.<key>`, among them `SemImageFile.Accelerating voltage` `300000` and `SemImageFile.Stage position R`, and no `ImageDescription`

#### Scenario: An entry nobody has seen
- **WHEN** tag 270 has the line `Detector temperature=-25` added
- **THEN** `original_metadata` has `SemImageFile.Detector temperature` `-25`

#### Scenario: Values as written
- **WHEN** tag 270 has the lines `Image comment=  two spaces before` and `Key without value`
- **THEN** `SemImageFile.Image comment` is `  two spaces before` and `SemImageFile.Key without value` is `""`

#### Scenario: Another program's description
- **WHEN** a TIFF's description is `ImageJ=1.54f` or any other text not starting with `[SemImageFile]`
- **THEN** its values are as before this change

### Requirement: Hitachi's tag 65500
When a TIFF's description starts with `[SemImageFile]`, the TIFF extractor SHALL put its tag 65500 into `original_metadata` as entries `65500.@<group>.<key>`, one per item `"@<group>"<key>=<value>` (the value up to the next `"` or line end), a key met twice keeping its last value. A tag 65500 without such an item, or of a TIFF whose description is not Hitachi's, SHALL stay one text, as before.

#### Scenario: Tag 65500's items, one glued to the one before it
- **WHEN** tag 65500 is `"@Fld"FldImgPropModeID=7\r"@Confidential"ScanTimeY=12.5\r"@Confidential"Stage tilt axis=Y"@Confidential"ScanTimeX=0.02\r"@Confidential"Stage tilt axis=Y` (made-up values)
- **THEN** `original_metadata` has `65500.@Fld.FldImgPropModeID` `7`, `65500.@Confidential.ScanTimeY` `12.5`, `65500.@Confidential.ScanTimeX` `0.02`, `65500.@Confidential.Stage tilt axis` `Y`, and no `65500`

#### Scenario: Another program's private tag
- **WHEN** a TIFF whose description is not Hitachi's has a tag 65500 `"@Fld"A=1`
- **THEN** `original_metadata` has `65500` `"@Fld"A=1` as one text

#### Scenario: Tag 65501 is left out
- **WHEN** the TIFF has a tag 65501 of 15,156 hexadecimal characters
- **THEN** `original_metadata` has no `65501` (not suitable for text, "What a TIFF's values leave out")

### Requirement: The summary line of a Hitachi TIFF
The image area's `HEADLINE` SHALL have, after Zeiss's pixel size and before `ImageWidth`, `SemImageFile.Instrument name`, `Signal name`, `Operation mode`, `Accelerating voltage` (followed by `(unit unknown)`), `Magnification`, `PixelSize` (followed by `(unit unknown)`), `SampleName`, and after Zeiss's date and time `SemImageFile.Date` and `Time`.

#### Scenario: The summary line of a lone Hitachi TIFF
- **WHEN** the TIFF of the fixture `hitachi_tif` is extracted
- **THEN** its summary line is `HF3300, HAADF, Analysis, Accelerating voltage 300000 (unit unknown), Magnification 50000, PixelSize 0.5 (unit unknown), Au on C, ImageWidth 64, ImageLength 96, BitsPerSample 8, 2024/01/15, 09:30:00`

### Requirement: A number written as text in a Hitachi summary phrase
A value of a `SemImageFile` entry of the summary line that is a number written as text (digits with an optional sign, decimal point and exponent) SHALL be put after its key, and left out when it is 0; any other text SHALL be shown bare.

#### Scenario: A voltage of 0
- **WHEN** tag 270 has `Accelerating voltage=0`
- **THEN** the summary line has no `Accelerating voltage` phrase, and `original_metadata` keeps `SemImageFile.Accelerating voltage` `0`

#### Scenario: A sample named by a number
- **WHEN** tag 270 has `SampleName=1234`
- **THEN** the summary line has the phrase `SampleName 1234`
