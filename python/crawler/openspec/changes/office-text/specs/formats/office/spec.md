## ADDED Requirements

### Requirement: The text of a Word document, rendered
For a dataset of `common/docx` or `common/docm`, the extractor SHALL render the document's text as Markdown for `values["text"]`: the title (style Title) and headings as `#` headings, paragraphs, lists, bold and italic, tables as pipe tables, links, footnotes and endnotes, names as written (no `\_`, no `\*`). Pictures SHALL be left out without a line, comments SHALL NOT be shown, tracked changes SHALL be shown as accepted. The summary line stays as it is.

#### Scenario: Emphasis in a macro-enabled document
- **WHEN** `testWORD_macros.docm` is extracted
- **THEN** `values["text"]` is `The **quick** *brown* fox.` and its summary line is as before

#### Scenario: Title, headings, a list and a table
- **WHEN** a `.docx` written by python-docx holds the title `Lamella preparation`, the heading `Milling`, a paragraph with `30 kV` in bold, two bullet items and a table of two rows
- **THEN** its text starts with `# Lamella preparation`, holds the lines `# Milling`, `Thinning at **30 kV**`, `* first step`, `* second step`, `| Step | Current |` and `| rough | 1 nA |`

#### Scenario: Names as written
- **WHEN** a paragraph reads `Grid TEM_grid_03, files *.dm4`
- **THEN** the text is `Grid TEM_grid_03, files *.dm4`

#### Scenario: A comment is not shown
- **WHEN** `testComment.docx` is extracted
- **THEN** its text is `Here is some text.`, without the comment `Here is a comment`

#### Scenario: Tracked changes as accepted
- **WHEN** a paragraph holds `Kept `, a tracked insertion `INSERTED` and a tracked deletion `DELETED`
- **THEN** the text holds the line `Kept INSERTED` and nowhere `DELETED`

#### Scenario: A picture is left out
- **WHEN** a `.docx` holds a picture between the paragraphs `Before the picture.` and `After the picture.`
- **THEN** its text is these two paragraphs, a blank line between them, and nothing for the picture

### Requirement: The text of a presentation, rendered
For a dataset of `common/pptx`, the extractor SHALL render the deck's text as Markdown for `values["text"]`: per slide, in the deck's order, its title as a `#` heading (a line `---` for a slide without a title), the paragraphs of its text shapes (in groups too) as lines, its tables as pipe tables, then its speaker notes after a line `### Notes:`. Pictures, media, charts and comments SHALL be left out.

#### Scenario: Title and subtitle
- **WHEN** `testPPT_comment.pptx` is extracted
- **THEN** its text is `# title` and `subtitle` on two lines, without the comment, and its summary line is as before

#### Scenario: Slides with notes and a picture
- **WHEN** a deck written by python-pptx has the slide `Drift correction` with the lines `Cross-correlation per frame` and `Sub-pixel by upsampling` and the note `mention the 2019 data`, then the slide `Results` with only a picture
- **THEN** its text is `# Drift correction`, the two lines, `### Notes:`, `mention the 2019 data`, a blank line, then `# Results`

### Requirement: The author's properties lead the text
The core properties `subject`, `keywords`, `description` and `category` that are not empty SHALL lead the text, in this order, as `core.<name>: <value>` lines, then a blank line, then the rendering; with a text, the record shows no other property line.

#### Scenario: A document with subject, keywords and comments
- **WHEN** `testWORD_custom_props.docx` is extracted
- **THEN** its text is `core.subject: My subject`, `core.keywords: My Keyword`, `core.description: My Comments`, a blank line, `Document content`, and that is the record's second description

### Requirement: Embedded files are never read
The extractor of `common/docx`, `common/docm` and `common/pptx` SHALL read only the parts whose content type (Override before Default, case-insensitive) is `application/xml`, `text/xml` or ends in `+xml` and is not `image/`, `audio/`, `video/` or `model/`, besides the ZIP's directory; a part of unknown type SHALL NOT be read.

#### Scenario: A document with a large picture
- **WHEN** a `.docx` and a `.pptx`, written by python-docx and python-pptx with one 20 MB picture each, are extracted
- **THEN** each extraction reads less than 1 MiB of the file (`bytes_read`), and the texts are those of the same documents with a picture of 20 by 20 pixels

#### Scenario: A large SVG picture
- **WHEN** a `.docx` holds a 3 MB SVG part typed `image/svg+xml`
- **THEN** its extraction reads less than 256 KiB, and its text ends with `Document content`

#### Scenario: Embedded audio
- **WHEN** `testPPT_embeddedMP3.pptx` is extracted
- **THEN** in the copy the converter gets, `ppt/media/media1.mp3` and `ppt/media/image1.png` are empty and `ppt/slides/slide1.xml` is not, and the text is `---` (one slide without a title or text)

#### Scenario: A part of unknown type
- **WHEN** a `.docx` holds a part `word/blob.unknownext` whose extension has no content type
- **THEN** that part is empty in the copy the converter gets

### Requirement: The shown text, as for a text file
The rendering SHALL be shown by the text area's rule (`written.shown`): a line that may hold a credential left out with the marker `… (a line left out: may be a credential)` and counted in `mapped_metadata["credentials_left_out"]`; a rendering over 4,096 characters as its first and last lines with a line `… N bytes left out …` between them, at most 4,096 characters in all.

#### Scenario: A credential is left out
- **WHEN** a `.docx` holds the paragraphs `Login for the microscope PC` and `password: hunter2`
- **THEN** its text holds the first, the marker in place of the second, nowhere `hunter2`, and `credentials_left_out` is 1

#### Scenario: A long document
- **WHEN** a `.docx` holds 300 paragraphs `Paragraph 1.` to `Paragraph 300.`, each padded to 60 characters
- **THEN** its text starts with `Paragraph 1.`, ends with `Paragraph 300.` and its padding, holds one line `… N bytes left out …` and has at most 4,096 characters

### Requirement: A rendering that fails keeps the metadata
When the conversion raises, takes more than 30 s, or a kept XML part declares a DTD (parsed by defusedxml up to its first start tag), the extractor SHALL give the property parts' metadata as before, no `text`, and `mapped_metadata["text not rendered"]` with the reason; the extraction SHALL NOT fail.

#### Scenario: A DOCTYPE after a comment
- **WHEN** a `.docx` whose `word/document.xml` has a comment of 2 KB, then `<!DOCTYPE w:document [<!ENTITY a "x">]>` before its root is extracted
- **THEN** the extraction succeeds with the metadata, no `text`, `text not rendered` `Unrendered: word/document.xml: a DOCTYPE`, and the record's second description is the tag lines

#### Scenario: A rendering over its deadline
- **WHEN** the rendering of `testWORD_custom_props.docx` does not end within the deadline (in the test 0.2 s, a converter that sleeps 5 s)
- **THEN** the extraction ends after the deadline with the metadata and `text not rendered` `TimeoutError: rendering took more than 0.2 s`

### Requirement: The size of a document's XML in its values
For every rendered document the extractor SHALL put into `mapped_metadata` the bytes read of the file (`bytes read`), the XML parts' size uncompressed (`xml bytes`) and `large document text`, `true` when the bytes read are past 1 MiB, the text rendered all the same.

#### Scenario: A large document
- **WHEN** a `.docx` written by python-docx holds 2.6 MB of text in one paragraph
- **THEN** it has a text, `large document text` is `true`, and `bytes read` and `xml bytes` are over 1 MiB

#### Scenario: An ordinary document
- **WHEN** `testWORD_custom_props.docx` is extracted
- **THEN** `large document text` is `false`, `bytes read` and `xml bytes` are between 0 and 1 MiB

## MODIFIED Requirements

### Requirement: Office Open XML metadata from the package's property parts
For a `.docx`, `.docm`, `.pptx`, `.xlsx` or `.xlsm` dataset, the extractor SHALL read the relationships (`_rels/.rels`) and the property parts they name, and keep as `original_metadata` every entry but the skip list: `core.<element>`, `app.<element>`, `custom.<name>`, each value as the file writes it. As `mapped_metadata`: a presentation's `slides`; a workbook's `sheets` (openpyxl, read-only), unless a part of cell data is over 16 MiB uncompressed (`common.MAX_PART`). Other parts: only as "Embedded files are never read" allows.

#### Scenario: A representative Word document
- **WHEN** `word_docx` is extracted
- **THEN** its description starts with `My Title, EJ04325S, 2011-07-29T16:52:00Z, Microsoft Office Word, Pages 1; `, and its values hold `core.lastModifiedBy` `Etienne Jouvin`, `app.Company` `EDF-DIT`, `app.TitlesOfParts` `["My Title"]` and the custom properties `custom.MyCustomString` `MyStringValue` and `custom.myCustomNumber` `3`

#### Scenario: Dates as the file writes them
- **WHEN** `word_docx` is extracted with `TZ=Europe/Berlin`
- **THEN** `core.created` is `2011-07-29T16:52:00Z` and `custom.MyCustomDate` `2010-12-30T23:00:00Z`, as written, not converted

#### Scenario: Empty values are kept
- **WHEN** `word_docm` has an empty title (`<dc:title></dc:title>`)
- **THEN** its values hold `core.title` `""`, and the summary line leaves it out

#### Scenario: A presentation
- **WHEN** `powerpoint_pptx` is extracted
- **THEN** its description starts with `title, Allison, Timothy B., 2015-09-30T17:58:06Z, Microsoft Office PowerPoint, Slides 1; ` and its `mapped_metadata` holds `slides` `1`

#### Scenario: A workbook
- **WHEN** `excel_xlsx` is extracted
- **THEN** its `mapped_metadata` holds `sheets` `{"Feuil1": "A1:D22", "Feuil2": "A1:A1", "Feuil3": "A1:A1"}`

#### Scenario: A workbook with large cell data
- **WHEN** a workbook's shared strings (`xl/sharedStrings.xml`) or a worksheet are larger than 16 MiB uncompressed (openpyxl's read-only mode reads the shared strings whole, and a worksheet up to its `<dimension>`, to its end without one: review finding 2 measured 20 MB read and 279 MB of memory for one)
- **THEN** openpyxl is not called, `mapped_metadata` holds `sheets not read` with the part and its size, the property parts are kept, and the extractor reads less than 1 MB of it

#### Scenario: Only the XML parts are read
- **WHEN** a presentation of 5 MB, nearly all of it one picture, is extracted
- **THEN** the extractor reads less than 1 MB of it, and its text is that of the presentation without the picture

#### Scenario: A broken package
- **WHEN** a `.docx` starts with a ZIP header but is cut off (`truncated_docx`, Apache Tika's `testWORD_truncated.docx`)
- **THEN** it is a `common/docx` dataset, and its extraction fails with the ZIP reader's error, which the crawl reports as for any failed extraction

#### Scenario: An entry nobody has seen
- **WHEN** a document's extended properties hold an element nobody has seen, `<FooVendorSetting>7</FooVendorSetting>`
- **THEN** its values hold `app.FooVendorSetting` `7`
