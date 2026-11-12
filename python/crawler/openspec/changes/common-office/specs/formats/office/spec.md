# Spec Delta

## Purpose

Office documents and PDFs in the tree (October listing: 862 PDFs, about 360 Office Open XML, 30 OpenDocument and 11 legacy OLE2 files, 13 lock files), as single-file datasets of the collection `common`, recognised by content and described by the metadata the file holds: what the file says, without editorializing (TEMPLATE.md, "Lessons from the EM formats").

## ADDED Requirements

### Requirement: Office documents are recognised by content
A file that the core types by its name as an Office Open XML document (`.docx`, `.docm`, `.pptx`, `.xlsx`, `.xlsm`), an OpenDocument file (`.odt`, `.odp`, `.ods`), a PDF or a legacy Word, PowerPoint or Excel file (`.doc`, `.ppt`, `.pps`, `.xls`) SHALL be one dataset of its format (`common/docx` … `common/pdf`) when its first bytes are those of its kind: a ZIP's local header (`PK\3\4`) for Office Open XML and OpenDocument, `%PDF-` within the first 1,024 bytes for a PDF, the OLE2 signature for the legacy files. Otherwise the file SHALL get the type its content gives without the name rule (`Directory.not_of_type`), the reason in its basis. The formats of Office Open XML and OpenDocument run before those of OLE2, and these before the PDF format, so that a misnamed file reaches the format of its content in the cases seen (an encrypted Office Open XML file is an OLE2 file).

#### Scenario: A Word document
- **WHEN** a representative `.docx` written by Word is crawled (`word_docx`)
- **THEN** it is one dataset of format `common/docx` and type `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, basis `ZIP header`

#### Scenario: Macro-enabled variants
- **WHEN** a `.docm` and a `.xlsm` written by Word and Excel are crawled (`word_docm`, `excel_xlsm`)
- **THEN** they are datasets of `common/docm` and `common/xlsm`, of the core's macro-enabled types, described as their `.docx` and `.xlsx` counterparts

#### Scenario: A text file named like an office document
- **WHEN** text files are named `notes.docx`, `notes.pdf` and `testODTnotaZipFile.odt` (`text_docx`, `text_pdf`, `text_odt`), and an RTF file `letter.doc` (`rtf_doc`)
- **THEN** none gets an office type or format: the text files are `text/plain`, the RTF file `application/rtf`, each with the reason in its basis (`common/docx: not application/vnd.openxmlformats-officedocument.wordprocessingml.document, no ZIP header`)

#### Scenario: An empty file named like a presentation
- **WHEN** a file `empty.pptx` has 0 bytes, as one `.docx` and one `.pptx` in the October listing (`empty_pptx`)
- **THEN** it does not get the PowerPoint type, and no extraction runs

#### Scenario: A password-protected Word document
- **WHEN** a `.docx` is encrypted by Word, which writes it as an OLE2 file (`protected_docx`)
- **THEN** it gets the type its content gives, `application/x-ole-storage`, and no office format

### Requirement: Lock files are recognised by name
A file whose name starts with `~$` (Microsoft Office's owner file, written beside a document it has open) SHALL get the type `application/x-ms-owner` (Apache Tika's name for it, PRONOM fmt/473), whatever its extension; a file named `.~lock.<name>#` (LibreOffice's lock file) the type `application/x.libreoffice-lock`. Neither is read nor extracted.

#### Scenario: Lock files beside documents
- **WHEN** a directory holds `~$report.docx`, `~$slides.pdf` and `.~lock.report.odt#` (`lock_files`)
- **THEN** the first two are `application/x-ms-owner`, the third `application/x.libreoffice-lock`, each a single file without format and extraction

### Requirement: Office Open XML metadata from the package's property parts
For a `.docx`, `.docm`, `.pptx`, `.xlsx` or `.xlsm` dataset, the extractor SHALL read the package's relationships (`_rels/.rels`) and the property parts they name, without loading the document's other parts, and keep as `original_metadata` every entry but the skip list: `core.<element>` for each element of the core properties (`docProps/core.xml`), `app.<element>` for each element of the extended properties (`docProps/app.xml`), `custom.<name>` for each custom property (`docProps/custom.xml`); a value as the file writes it (text; a `vt:vector` as the list of its values). As `mapped_metadata`: the slide count of a presentation (`slides`, the slides its `presentation.xml` lists), and a workbook's sheets with their dimension as the sheet writes it (`sheets`, read by openpyxl in read-only mode, which also reads the styles, the shared strings, that is the cells' texts, and each worksheet up to its `<dimension>`), unless a part of cell data is larger than 16 MiB uncompressed (`common.MAX_PART`).

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

#### Scenario: Only the property parts are read
- **WHEN** a presentation of 5 MB, nearly all of it one picture, is extracted
- **THEN** the extractor reads less than 1 MB of it (measured with 20 MB: 68,830 bytes)

#### Scenario: A broken package
- **WHEN** a `.docx` starts with a ZIP header but is cut off (`truncated_docx`, Apache Tika's `testWORD_truncated.docx`)
- **THEN** it is a `common/docx` dataset, and its extraction fails with the ZIP reader's error, which the crawl reports as for any failed extraction

#### Scenario: An entry nobody has seen
- **WHEN** a document's extended properties hold an element nobody has seen, `<FooVendorSetting>7</FooVendorSetting>`
- **THEN** its values hold `app.FooVendorSetting` `7`

### Requirement: OpenDocument metadata from meta.xml
For an `.odt`, `.odp` or `.ods` dataset, the extractor SHALL read `meta.xml` and keep as `original_metadata` every child of `office:meta` but the skip list, by its local name: its text (`creation-date`), its attributes as `<name>.@<attribute>` (`document-statistic.@page-count`), a user-defined field as `user-defined.<its name>`, an element that repeats as the list of its texts (`keyword`). An encrypted document's `meta.xml` (its manifest gives it encryption data) SHALL NOT be read; `mapped_metadata` says `encrypted` for every OpenDocument dataset.

#### Scenario: A representative text document
- **WHEN** `writer_odt` is extracted
- **THEN** its description starts with `Apache Tika, Bart Hanssens, 2009-10-05T19:04:01, OpenOffice.org/3.1$Unix OpenOffice.org_project/310m19$Build-9420, page-count 2; `, and its values hold `keyword` `["Apache", "Lucene", "Tika"]`, `editing-duration` `PT02H03M24S`, `user-defined.Editor` `Bart Hanssens` and `user-defined.Info 2` `""`

#### Scenario: A spreadsheet and a presentation
- **WHEN** `calc_ods` and `impress_odp` are extracted
- **THEN** their values hold `document-statistic.@cell-count` `4` and `document-statistic.@object-count` `25`

#### Scenario: An encrypted document
- **WHEN** an `.odt` saved with a password is extracted (`encrypted_odt`)
- **THEN** the extraction succeeds with `mapped_metadata` `encrypted` `true` and an empty `original_metadata`

#### Scenario: An attribute nobody has seen
- **WHEN** `meta.xml` holds an element nobody has seen, `<foo:setting foo:level="7">high</foo:setting>`
- **THEN** the values hold `setting` `high` and `setting.@level` `7`

### Requirement: PDF metadata from the Info dictionary and XMP
For a PDF dataset, the extractor SHALL read with pypdf the document information dictionary, each entry as `Info.<key>` (a text string as text, a number as a number, an array as a list), and the catalog's XMP metadata stream, each property as `XMP.<prefix>:<name>` with the prefix the file declares (an `rdf:Alt`, `rdf:Seq` or `rdf:Bag` as the list of its items, a structure as `.<prefix>:<name>` below it, a list of structures as `[i]`). pypdf's `XmpInformation` gives named properties only, so the packet is flattened by our code. A value's own reference SHALL be followed, a reference inside it written as the file writes it (`12 0 R`). As `mapped_metadata`: the header as written where `%PDF-` is found in the first 1,024 bytes (`header` `%PDF-1.4`), the catalog's `/Version` where given, the page count the page tree gives (`pages`, its `/Count`), and `encrypted`. An encrypted PDF SHALL be read with the empty user password, as viewers open it; one that needs a password keeps `header` and `encrypted` only. The extractor SHALL NOT read the pages' content. A file without `%%EOF` in its last 1,024 bytes SHALL NOT be given to pypdf, and pypdf SHALL read at most 32 MiB of a file (`pdf.BUDGET`): its recovery paths read and hold whole files (review finding 1: 50.8 GB read in 7.7 s for a 50 MB file cut by 3 kB); either fails the extraction with its reason.

#### Scenario: A representative PDF
- **WHEN** `pdf_info` (written by Mac OS X's Quartz from Firefox) is extracted
- **THEN** its description starts with `Apache Tika - Apache Tika, Bertrand Delacrétaz, D:20070915110231+02'00', Firefox, Mac OS X 10.4.10 Quartz PDFContext, pages 1; `, its date as written

#### Scenario: Custom entries and XMP structures
- **WHEN** `pdf_custom` (Apache FOP) is extracted
- **THEN** its values hold `Info.Custom Property` `Custom Value`, `Info.Custom Array` `["Array Entry 1", "Array Entry 2"]`, `XMP.xmp:CreateDate` `2010-06-30T14:01:54+02:00`, `XMP.bib:title` as the list of its four language versions, `XMP.bib:representative.bib:rep-name` `name of the representative` and `XMP.bib:priorities[1].rdf:value` `number of priority n`

#### Scenario: An encrypted PDF that opens without a password
- **WHEN** a PDF encrypted with RC4 and an empty user password (`pdf_owner_password`), and one encrypted with AES-256 and an empty user password, written by pypdf (`pdf_aes`), are extracted
- **THEN** both are read: `encrypted` `true`, their page count and, for `pdf_aes`, `Info.Title` `Encrypted with AES-256`

#### Scenario: An encrypted PDF that needs a password
- **WHEN** a PDF needs a user password (`pdf_user_password`)
- **THEN** the extraction succeeds with `mapped_metadata` `{"header": "%PDF-1.4", "encrypted": true}`, an empty `original_metadata` and an empty summary line

#### Scenario: Only the metadata is read
- **WHEN** a PDF of 5 MB, nearly all of it one attached file, is extracted
- **THEN** the extractor reads less than 1 MB of it (measured with 20 MB: 918,554 bytes by `/proc/self/io` rchar; pypdf reads the last 128 KiB backwards once for each of the trailer's last lines, from the page cache after the first time)

#### Scenario: A cut-off PDF
- **WHEN** the PDF of 5 MB is cut off by 3,000 bytes, as an interrupted copy leaves it
- **THEN** the extraction fails with `no %%EOF in the last 1,024 bytes`, having read less than 1 MB

#### Scenario: A PDF whose recovery would read all of it
- **WHEN** the PDF of 5 MB has a wrong `startxref` offset, and the budget is 1 MiB
- **THEN** the extraction fails with `OverBudget`, having read less than 2 MiB

#### Scenario: A header after other bytes
- **WHEN** a PDF has 101 bytes before `%PDF-1.3`
- **THEN** it is a `common/pdf` dataset, and `header` is `%PDF-1.3`, from where the header is

#### Scenario: A reference cycle in the Info dictionary
- **WHEN** an Info entry `/Foo` refers to the catalog, which refers to the page tree
- **THEN** `Info.Foo` holds the catalog with its `/Pages` as `<n> 0 R`, and the extraction succeeds with `Info.Title`

### Requirement: Legacy Word, PowerPoint and Excel metadata from the OLE2 property sets
For a `.doc`, `.ppt` or `.xls` dataset, the extractor SHALL read with olefile the `SummaryInformation` and `DocumentSummaryInformation` property sets (their first section), each property under olefile's name for it (`title`, `author`, `create_time`, `company`; one it has no name for as `<stream>.<id>`), strings decoded with the code page the property set gives (an unsigned 16-bit number, which olefile reads as signed), a time as olefile gives it with `Z` (a FILETIME is UTC by the format's definition). User-defined properties are not read (BACKLOG, olefile).

#### Scenario: A representative Word 97 document
- **WHEN** `word_doc` is extracted
- **THEN** its description starts with `My Title, EJ04325S, 2010-10-05T09:03:00Z, Microsoft Office Word, num_pages 1; ` and its values hold `company` `EDF-DIT` and `heading_pairs` `["Titre", 1]`

#### Scenario: A Mac code page
- **WHEN** `powerpoint_ppt` gives the code page 10000 (Mac Roman)
- **THEN** its strings are decoded with it: `title` `Sample Powerpoint Slide`, and the summary line ends with `slides 1`

#### Scenario: A UTF-8 code page
- **WHEN** `word_doc`'s code page is changed to 65001 (UTF-8), which olefile reads as -535
- **THEN** `codepage` is `65001`, and its strings are decoded as UTF-8 (`title` `My Title`)

#### Scenario: User-defined properties
- **WHEN** `excel_xls` holds user-defined properties (`MyCustomString` in the second section of DocumentSummaryInformation)
- **THEN** they are not in the values, and the extraction succeeds with the properties of the first sections

### Requirement: What is left out
The values of each family SHALL keep every entry but one skip list, defined once per family, in the docstring of its module (`office.ooxml`, `office.odf`, `office.pdf`, `office.ole` with `ole.SKIPPED`) and here: values not suitable for text (`values.textual`, applied by `common.kept`: lists over 16 items, strings over 1,000 characters or with control characters, bytes); for Office Open XML the attributes of the property elements, which are type annotations (`xsi:type="dcterms:W3CDTF"`) and a vector's size and base type; for OpenDocument the value type of a user-defined field (`meta:value-type`); for XMP the RDF syntax (`rdf:about`, `xml:lang`, `rdf:parseType`, the containers `rdf:Alt`, `rdf:Seq`, `rdf:Bag` as such, their items kept); for OLE2 the binary properties `thumbnail`, `dig_sig` and `hlinks`, which would otherwise be decoded as text.

#### Scenario: Binary values
- **WHEN** `powerpoint_ppt` holds a thumbnail (a PICT picture)
- **THEN** `thumbnail` is not in its values, its other properties are

#### Scenario: A value too long for text
- **WHEN** an Office Open XML document's `app.TitlesOfParts` lists 17 titles
- **THEN** it is left out of the values, the other entries stay

### Requirement: The summary line of an office document
The summary line SHALL hold, from a chosen list per family (the only positive list), the entries present and not empty, in the list's order, as the file holds them: a text as it is, a count after its name, not when it is 0. Office Open XML: `core.title`, `core.creator`, `core.created`, `app.Application`, `app.Pages`, `app.Slides`; OpenDocument: `title`, `initial-creator`, `creation-date`, `generator`, `document-statistic.@page-count` (as `page-count`); PDF: `Info.Title`, `Info.Author`, `Info.CreationDate`, `Info.Creator`, `Info.Producer`, the page count (`pages`); OLE2: `title`, `author`, `create_time`, `creating_application`, `num_pages`, `slides`.

#### Scenario: A count of 0
- **WHEN** a document's extended properties say `<Pages>0</Pages>`
- **THEN** the summary line has no `Pages`, and the values keep `app.Pages` `0`
