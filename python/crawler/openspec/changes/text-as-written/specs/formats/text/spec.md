## ADDED Requirements

### Requirement: The text as written
For a dataset of `common/text`, `common/log`, `common/readme`, `common/markdown`, `common/rst`, `common/tex` or `common/bibtex` whose bytes are text, the extractor SHALL put the file's text into `values["text"]`: decoded with the encoding the area finds, line ends as line feeds, no byte order mark; whole when it has at most 4,096 characters (`TEXT`), otherwise its head and tail. A file typed by its content gives its text too. The summary line and `original_metadata` stay as they are.

#### Scenario: A note in a session folder
- **WHEN** `info.txt` holds the four lines `run 1: tilt series, 1 degree steps`, `1-10: focus series, 2 nm steps`, `11: reference without specimen`, `note: drift after 11, stage relaxed for 10 min`, each with a line feed
- **THEN** `values["text"]` is these four lines as written, the summary line is still `ascii, lines 4`, and the record's second description is the text

#### Scenario: Windows line ends and a byte order mark
- **WHEN** `notes_utf8_bom.txt` (UTF-8 with a BOM, CRLF line ends, as Windows Notepad writes it) is extracted
- **THEN** its text has no BOM and no carriage return, one line feed per line

#### Scenario: A Western 8-bit text
- **WHEN** a file holds `Änderung: Blende 50 µm, 20 °C` in Windows-1252
- **THEN** its text is `Änderung: Blende 50 µm, 20 °C`

#### Scenario: Markdown with front matter
- **WHEN** `note.md` (`markdown`) is extracted
- **THEN** its text is the whole file, front matter included, and `original_metadata` still has `title` `Lamella preparation`

### Requirement: No text of HTML or of what is not text
`common/html` SHALL NOT give a text: it keeps the head's entries (design D1 of `text-as-written`, Q1). A file whose bytes are not text (no encoding) SHALL have no `text`.

#### Scenario: HTML and binary content
- **WHEN** `tools.html` (`html_docutils`) or `frames.txt` (the bytes 0 to 255 repeated) is extracted
- **THEN** its values hold no `text`

### Requirement: Head and tail of a long text
A text of more than 4,096 characters SHALL be shown as: the complete lines from its start that fit in 2,000 characters (a longer first line: its first 2,000 characters); a line `… N bytes left out …`, N being the file's size minus the bytes of the lines shown, with thousands separators; the lines that start within the file's last 2,000 characters (none: the last 2,000 characters).

#### Scenario: A long note within the head
- **WHEN** a note of 166 lines of 60 characters each, line feed included (9,960 characters), is extracted
- **THEN** its text is its first 33 lines, the line `… 6,000 bytes left out …` and its last 33 lines, and the extractor read the file once, from its start

#### Scenario: One very long line
- **WHEN** a text file holds one line of 100,000 characters
- **THEN** its text is the line's first 2,000 characters, the marker line and the line's last 2,000 characters

### Requirement: The tail of a file larger than the head
When a file typed by its name is larger than the head the extractor reads (requirement "The line count up to a bound"), the extractor SHALL read its last 16 KiB (`TAIL`, 16,384 bytes) too, without readahead, and drop the first, partial line of those bytes; never more.

#### Scenario: A log larger than the bound
- **WHEN** the log `big_log` (1.5 MiB, lines of 52 bytes) is extracted
- **THEN** its text starts with its first lines, then a line `… N bytes left out …` with N its size minus the bytes of the lines shown, then its last lines, at most 4,096 characters in all; and the extractor read at most 1,048,576 + 16,384 bytes of it

### Requirement: A credential is left out of the text
Every line of the text for which the shared check `values.credential("", line)` is true SHALL be replaced by `… (a line left out: may be a credential)`, its leading whitespace kept; a Markdown front matter in which the check flagged a value SHALL be replaced as a whole by `… (front matter left out: it may hold a credential)`. `mapped_metadata.credentials_left_out` SHALL count the lines too.

#### Scenario: A note with a password
- **WHEN** `notes.txt` has the lines `sample: Au on C`, `db password: hunter2` and `  server: postgres://admin:hunter2@db/x`
- **THEN** its text is `sample: Au on C`, `… (a line left out: may be a credential)` and `  … (a line left out: may be a credential)`, `hunter2` is nowhere in the record, and `mapped_metadata` has `credentials_left_out` 2

#### Scenario: A front matter with a credential
- **WHEN** a Markdown file's front matter has `title: Notes` and `api_key: abc123`, followed by the line `# Notes`
- **THEN** its text starts with `… (front matter left out: it may hold a credential)`, then `# Notes`; `abc123` is nowhere in the record

## MODIFIED Requirements

### Requirement: The line count up to a bound
The extractor SHALL read at most the first 1 MiB of a file (`HEAD`, 1,048,576 bytes), and of a file typed by its content at most the first 64 KiB (`SNIFFED_HEAD`, 65,536 bytes), without readahead, the file's size telling whether that is all of it, and the last 16 KiB of a larger file typed by its name for the text's tail only; it SHALL count the line feeds in the head it decoded, as `lines` (plus a last line without one) for a whole file, as `lines at least` for a longer one, in `mapped_metadata` and the summary line.

#### Scenario: A whole file
- **WHEN** a file holds `a\nb\nc` (no line feed at the end)
- **THEN** `mapped_metadata` has `lines` 3

#### Scenario: A log larger than the bound
- **WHEN** a log of 1.5 MiB with lines of 52 bytes is extracted (`big_log`)
- **THEN** its summary line is `ascii, lines at least 20164`, and the extractor read at most 1,048,576 bytes of its head and 16,384 bytes of its end

#### Scenario: A UTF-8 character cut by the bound
- **WHEN** a UTF-8 file longer than 1 MiB has a two-byte character across the 1 MiB boundary
- **THEN** its encoding is `utf-8`
