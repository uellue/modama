# Spec Delta

## ADDED Requirements

### Requirement: Each text document is a dataset of its type
The collection `common` SHALL make one dataset of each file of the types `text/plain` (`common/text`), `text/x-log` (`common/log`), `text/x-readme` (`common/readme`), `text/markdown` (`common/markdown`), `text/x-rst` (`common/rst`), `text/html` (`common/html`), `text/x-tex` (`common/tex`) and `text/x-bibtex` (`common/bibtex`), as the core's MIME database types them, with the basis `single file`, at priority 20. It SHALL NOT read a file to recognise it.

#### Scenario: Text files of each kind
- **WHEN** a folder holds `notes.txt`, `acquisition.log`, `README`, `note.md`, `tools.rst`, `tools.html`, `tools.tex` and `references.bib`
- **THEN** each is one dataset of its own, of the format `common/text`, `common/log`, `common/readme`, `common/markdown`, `common/rst`, `common/html`, `common/tex` and `common/bibtex` in that order, with the type the core gives its name

### Requirement: The encoding as detected
The extractor SHALL put into `mapped_metadata.encoding`, from the bytes it reads: the encoding a byte order mark names (`UTF-32`, `UTF-8-SIG`, `UTF-16`); else `null` (not text) for bytes with a NUL; else `ascii` if they decode as ASCII and `utf-8` if they decode as UTF-8, a sequence cut by the end of what was read allowed; else `Windows-1252` (design D1). The text is decoded with that encoding, an undecodable byte replaced. The encoding SHALL be in the summary line, as its name alone.

#### Scenario: Encodings as written by common tools
- **WHEN** the same two lines of notes are written as ASCII (`notes_ascii.txt`), UTF-8 (`notes_utf8.txt`), UTF-8 with a BOM and CRLF line ends as Windows Notepad writes it (`notes_utf8_bom.txt`), Windows-1252 (`notes_windows.txt`) and UTF-16 with a BOM as Windows PowerShell 5 writes it (`notes_utf16.txt`)
- **THEN** their summary lines are `ascii, lines 2`, `utf-8, lines 2`, `UTF-8-SIG, lines 2`, `Windows-1252, lines 2` and `UTF-16, lines 2`

#### Scenario: A short Western text in an 8-bit encoding
- **WHEN** a file holds the one word `Größe` and a line feed in Latin-1, or `Änderung: Blende 50 µm, 20 °C` in Windows-1252
- **THEN** its encoding is `Windows-1252`, not a Mac, Greek or Korean encoding, and its text decodes as written

#### Scenario: Content that is not text
- **WHEN** a file named `frames.txt` holds the bytes 0 to 255 repeated
- **THEN** its extraction does not fail: `mapped_metadata` has `encoding` `null` and no line count, `original_metadata` is empty, and the summary line is empty

#### Scenario: An empty file
- **WHEN** a file named `empty.txt` is empty
- **THEN** the extractor returns nothing, and the record has the basic description

### Requirement: The line count up to a bound
The extractor SHALL read at most the first 1 MiB of a file (`HEAD`, 1,048,576 bytes, plus one byte to know whether the file is longer), and count the line feeds in what it decoded, plus one for a last line without a line feed. When the file is longer than `HEAD`, it SHALL count the line feeds only and put the count into `mapped_metadata` as `lines at least`, otherwise as `lines`; the summary line has `lines N` or `lines at least N`.

#### Scenario: A whole file
- **WHEN** a file holds `a\nb\nc` (no line feed at the end)
- **THEN** `mapped_metadata` has `lines` 3

#### Scenario: A log larger than the bound
- **WHEN** a log of 1.5 MiB with lines of 52 bytes is extracted (`big_log`)
- **THEN** its summary line is `ascii, lines at least 20164`, and the extractor read at most 1,048,577 bytes of it

#### Scenario: A UTF-8 character cut by the bound
- **WHEN** a UTF-8 file longer than 1 MiB has a two-byte character across the 1 MiB boundary
- **THEN** its encoding is `utf-8`

### Requirement: Markdown front matter and first heading
For a Markdown file, the extractor SHALL parse the first 65,536 characters (`PARSE`) of the decoded text with markdown-it-py (CommonMark) and its front matter plugin, and SHALL keep every entry of a YAML front matter block, read with PyYAML's safe loader, in `original_metadata`: flat under its keys joined with dots, a list of mappings or lists numbered (`author[0].name`), a list of values kept as a list, empty values kept, at most 1,000 entries; a date or time as written, not converted. The skip list: values not suitable for text (`textual`). A front matter that is not YAML SHALL leave `original_metadata` empty and put PyYAML's message into `mapped_metadata` as `front matter error`, the rest of the extraction kept. The text of the first heading (ATX or setext), its inline source as written, SHALL go into `mapped_metadata` as `first heading`. The summary line starts with the front matter's `title`, `author` and `date` as found (text bare, a number after its name, a list item by item), then the first heading, a phrase repeated once.

#### Scenario: A note with front matter
- **WHEN** `note.md` has the front matter `title: Lamella preparation`, `author` a list of one mapping with `name` and `affiliation`, `date: 2026-11-12T10:00:00+01:00`, `tags: [FIB, lamella]`, `draft: false`, then the setext heading `Lamella preparation` (`markdown`)
- **THEN** `original_metadata` has `title` `Lamella preparation`, `author[0].name` `A. Example`, `author[0].affiliation` `ER-C`, `date` `2026-11-12T10:00:00+01:00`, `tags` [`FIB`, `lamella`] and `draft` false
- **AND** `mapped_metadata` has `first heading` `Lamella preparation`, and the summary line is `Lamella preparation, 2026-11-12T10:00:00+01:00, ascii, lines 18`

#### Scenario: The time as written in any time zone
- **WHEN** that note is extracted with `TZ=Europe/Berlin` and with `TZ=UTC`
- **THEN** `date` is `2026-11-12T10:00:00+01:00` both times

#### Scenario: A Markdown file without front matter
- **WHEN** `README.md` starts with `# Session 2026-11`
- **THEN** `original_metadata` is empty and the summary line starts with `Session 2026-11`

#### Scenario: A front matter entry nobody has seen before
- **WHEN** a front matter has `made_up_key: 42 zz`, `made_up_empty: ""` and `made_up_group: {made_up_number: 7}`
- **THEN** `original_metadata` has `made_up_key` `42 zz`, `made_up_empty` as empty text and `made_up_group.made_up_number` 7

#### Scenario: A front matter value not suitable for text
- **WHEN** a front matter has a value of 1,001 characters, or a list of 17 numbers
- **THEN** `original_metadata` has no entry for it, and the front matter's other entries

#### Scenario: A front matter that is not YAML
- **WHEN** a front matter holds `title: [unclosed`
- **THEN** the extraction does not fail: `original_metadata` is empty, `mapped_metadata` has `front matter error`, the encoding and the line count

#### Scenario: A front matter with an alias bomb
- **WHEN** a front matter nests nine levels of nine aliases of the level below
- **THEN** the extraction ends within a second with at most 1,000 entries in `original_metadata`

### Requirement: reStructuredText title and docinfo
For a reStructuredText file, the extractor SHALL parse the first 65,536 characters of the decoded text with docutils, without file insertion (`.. include::` is not followed), without raw input and without reading a configuration file, its messages not reported, and SHALL keep in `original_metadata` the document's `title` and `subtitle` and every entry of its docinfo as docutils reads it: a bibliographic field under docutils' name (`author`, `date`, `revision`, `contact`, `copyright`, …), `authors` as a list, any other field under its name as written. The skip list: values not suitable for text. The summary line has the title, subtitle, author or authors and date as found.

#### Scenario: A docutils document
- **WHEN** docutils' own `docs/user/tools.rst` (0.23) is extracted (`rst_docutils`); it starts with `.. include:: ../header.rst`
- **THEN** `original_metadata` has `title` `Docutils Front-End Tools`, `author` `David Goodger`, `contact` `docutils-develop@lists.sourceforge.net`, `revision` `9993`, `date` `2024-12-04` and `copyright` `This document has been placed in the public domain.`
- **AND** its summary line is `Docutils Front-End Tools, David Goodger, 2024-12-04, utf-8, lines 570`, and no file but `tools.rst` was opened

#### Scenario: A docinfo field nobody has seen before
- **WHEN** a document titled `Probe` has the fields `:Made-up field: 42 zz` and `:Authors: A; B`
- **THEN** `original_metadata` has `Made-up field` `42 zz` and `authors` [`A`, `B`]

#### Scenario: Only the head is parsed
- **WHEN** a document of 2 MiB has its title at the start
- **THEN** its title is found, and the extraction takes less than 5 s

### Requirement: The HTML head
For an HTML file, the extractor SHALL parse the decoded head with Python's `html.parser` until the document's head ends (`</head>` or `<body>`) or the head read is used up, and SHALL keep in `original_metadata`: `title`, the text of the first `<title>` with ASCII whitespace stripped and collapsed (as the HTML standard defines a document's title); `lang`, the `lang` attribute of `<html>`; `meta.charset`; and for every `<meta>` with `content`, `meta.<key>` where `<key>` is its `name`, `http-equiv`, `property` or `itemprop`, the first present, a key met twice keeping all values as a list in order. The skip list: `meta.viewport` (a display setting) and values not suitable for text. The summary line has the title, `meta.author` and `meta.generator` as found.

#### Scenario: HTML written by docutils
- **WHEN** docutils 0.23's html5 writer writes `tools.html` from `tools.rst` (`html_docutils`)
- **THEN** `original_metadata` has `title` `Docutils Front-End Tools`, `lang` `en`, `meta.charset` `utf-8`, `meta.generator` `Docutils 0.23: https://docutils.sourceforge.io/`, `meta.author` `David Goodger`, `meta.dcterms.date` `2024-12-04` and `meta.dcterms.rights`, and no `meta.viewport`
- **AND** its summary line starts with `Docutils Front-End Tools, David Goodger, Docutils 0.23: https://docutils.sourceforge.io/, utf-8, lines`

#### Scenario: Meta elements of every kind
- **WHEN** a head has `<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">`, `<meta property="og:title" content="X">`, two `<meta name="citation_author">` and `<meta name="made_up_name" content="42 zz">`
- **THEN** `original_metadata` has `meta.Content-Type` `text/html; charset=iso-8859-1`, `meta.og:title` `X`, `meta.citation_author` as a list of the two values in order, and `meta.made_up_name` `42 zz`

#### Scenario: A title in the body is not the document's
- **WHEN** a document has no `<title>` in its head, and an SVG `<title>` in its body
- **THEN** `original_metadata` has no `title`

#### Scenario: A large report
- **WHEN** an HTML file of 3 MiB is extracted
- **THEN** the extractor reads at most 1,048,577 bytes of it

### Requirement: LaTeX title fields
For a LaTeX file, the extractor SHALL parse the first 65,536 characters of the decoded text with pylatexenc, and SHALL keep in `original_metadata` the mandatory argument of the first `\documentclass`, `\title`, `\author` and `\date` outside comments, each under the macro's name, as raw LaTeX as written (an empty argument as empty text). Nothing else of the file is kept. The summary line has the title, author, date and document class as found.

#### Scenario: LaTeX written by docutils
- **WHEN** docutils 0.23's LaTeX writer writes `tools.tex` from `tools.rst` (`latex_docutils`)
- **THEN** `original_metadata` has `documentclass` `article`, `title` `Docutils Front-End Tools`, `author` and `date` as empty text

#### Scenario: Raw LaTeX as written, comments left out
- **WHEN** a file has `% \title{Old}`, then `\documentclass[a4paper]{revtex4-2}`, `\title[Short]{A \emph{new} result}` and `\author{A. Example \and B. Example}`
- **THEN** `original_metadata` has `documentclass` `revtex4-2`, `title` `A \emph{new} result` and `author` `A. Example \and B. Example`

### Requirement: BibTeX entries
For a BibTeX file, the extractor SHALL parse the decoded head with bibtexparser and put the number of entries and their keys in order into `mapped_metadata` as `entries` and `keys`; when the file is longer than `HEAD`, the head cut before its last line that starts with `@`, as `entries at least`. `original_metadata` is empty. The summary line has `entries N` or `entries at least N`.

#### Scenario: A bibliography
- **WHEN** bibtexparser 2.1.0 writes three entries with the keys `example2024`, `example2025` and `example2026` (`bibtex`)
- **THEN** `mapped_metadata` has `entries` 3 and `keys` [`example2024`, `example2025`, `example2026`], and the summary line starts with `entries 3`

#### Scenario: A bibliography larger than the bound
- **WHEN** a BibTeX file of 2 MiB is extracted
- **THEN** `mapped_metadata` has `entries at least` with the number of complete entries in the first 1 MiB, and the extraction logs no parse error
