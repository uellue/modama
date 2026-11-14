## ADDED Requirements

### Requirement: The text of a Word document, rendered
For a dataset of `common/docx` or `common/docm`, the extractor SHALL put the document's text, rendered as Markdown, into `values["text"]`: the title (style Title) and headings as `#` headings, paragraphs, lists, bold and italic, tables as pipe tables, links, footnotes and endnotes. Pictures SHALL be left out without a line, comments SHALL NOT be shown, tracked changes SHALL be shown as accepted. The summary line and `original_metadata` stay as they are.

#### Scenario: Emphasis in a macro-enabled document
- **WHEN** `testWORD_macros.docm` is extracted
- **THEN** `values["text"]` is `The **quick** *brown* fox.` and its summary line is as before

#### Scenario: Title, headings, a list and a table
- **WHEN** a `.docx` written by python-docx holds the title `Lamella preparation`, the heading `Milling`, a paragraph with `30 kV` in bold, two bullet items and a table of two rows
- **THEN** its text starts with `# Lamella preparation`, holds `# Milling`, `**30 kV**`, the two items each on a line starting with `* `, and a pipe table with the rows `Step | Current` and `rough | 1 nA`

#### Scenario: A comment is not shown
- **WHEN** `testComment.docx` is extracted
- **THEN** its text holds the commented paragraph and not the comment's text

#### Scenario: Tracked changes as accepted
- **WHEN** a paragraph holds `Kept `, a tracked insertion `INSERTED` and a tracked deletion `DELETED`
- **THEN** the text holds `Kept INSERTED` and nowhere `DELETED`

#### Scenario: A picture is left out
- **WHEN** a `.docx` holds a picture between two paragraphs
- **THEN** the text holds the two paragraphs and no line for the picture (no `![`, no `data:`)

### Requirement: The text of a presentation, rendered
For a dataset of `common/pptx`, the extractor SHALL put the deck's text, rendered as Markdown, into `values["text"]`: per slide, in the deck's order, its title as a `#` heading, the paragraphs of its text shapes (in groups too) as lines, its tables as pipe tables, then its speaker notes after a line `### Notes:`. Pictures, media, charts and comments SHALL be left out.

#### Scenario: Title and subtitle
- **WHEN** `testPPT_comment.pptx` is extracted
- **THEN** its text is `# title` and `subtitle` on two lines, without the comment, and its summary line is as before

#### Scenario: Slides with notes and a picture
- **WHEN** a deck written by python-pptx has the slide `Drift correction` with the lines `Cross-correlation per frame` and `Sub-pixel by upsampling` and the note `mention the 2019 data`, then the slide `Results` with only a picture
- **THEN** its text is `# Drift correction`, the two lines, `### Notes:`, `mention the 2019 data`, then `# Results`, and no line for the picture

### Requirement: Embedded files are never read
The extractor of `common/docx`, `common/docm` and `common/pptx` SHALL read only the parts of the package whose content type ends in `xml`, besides the ZIP's directory; pictures, video, audio, embedded documents, macros and fonts SHALL NOT be read.

#### Scenario: A document with a large picture
- **WHEN** a `.docx` and a `.pptx`, each written by python-docx or python-pptx with one 20 MB picture, are extracted
- **THEN** each extraction reads less than 1 MiB of the file (`bytes_read`), and the text is the same as without the picture

#### Scenario: Embedded audio
- **WHEN** `testPPT_embeddedMP3.pptx` is extracted
- **THEN** the bytes read are fewer than the file's size less the MP3 part's size, and the text holds the slides' text

### Requirement: A long rendering is shortened
A rendering longer than 4,096 characters SHALL be stored as its first and last lines, about 2,000 characters each, with a line `… N characters left out …` between them (`written.shown_text`), at most 4,096 characters in all.

#### Scenario: A long document
- **WHEN** a `.docx` holds 300 paragraphs `Paragraph 1.` to `Paragraph 300.` of 60 characters each
- **THEN** its text starts with `Paragraph 1.`, ends with `Paragraph 300.`, holds one line `… N characters left out …` with N the characters not shown, and has at most 4,096 characters

### Requirement: A rendering that fails keeps the metadata
When the conversion raises, or a kept XML part declares a `<!DOCTYPE`, the extractor SHALL give the property parts' metadata as before, no `text`, and `mapped_metadata["text not rendered"]` with the reason; the extraction SHALL NOT fail. A file that is not a ZIP fails as before.

#### Scenario: A part with a DOCTYPE
- **WHEN** a `.docx` whose `word/document.xml` starts with `<!DOCTYPE w:document [<!ENTITY a "x">]>` is extracted
- **THEN** the extraction succeeds with the metadata, no `text`, `text not rendered` naming `word/document.xml`, and the record keeps its tag lines

#### Scenario: A cut-off document
- **WHEN** `testWORD_truncated.docx` is extracted
- **THEN** the extraction fails as before

### Requirement: A document with much XML is flagged
When the XML parts the extractor reads take more than 1 MiB of the file, it SHALL render the text all the same and SHALL add to `values["warnings"]` the line `<format id> read <bytes> bytes of XML to render its text; large document text`.

#### Scenario: A large document
- **WHEN** a `.docx` whose `word/document.xml` takes 1.5 MiB in the ZIP is extracted
- **THEN** it has a text, and `values["warnings"]` holds one line ending in `; large document text` with the bytes read

#### Scenario: An ordinary document
- **WHEN** `testWORD_custom_props.docx` is extracted
- **THEN** its values hold no `warnings`
