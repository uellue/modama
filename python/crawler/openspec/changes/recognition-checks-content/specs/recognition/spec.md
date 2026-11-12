# Spec Delta

## ADDED Requirements

### Requirement: A format can say a file is not of the type its name gave it
While recognising a directory, a format SHALL be able to say that a file is not of the type the file's name gave it, with a reason. When a single best name rule gave that type, the file SHALL get the type detection gives without it, at once: for the formats that run after it on that directory, and as a single file. The dataset holding the file SHALL carry the format, the dropped type and the reason in its basis, and the crawl SHALL report no warning for it.

#### Scenario: A text file named like the format's files
- **WHEN** a directory holds `notes.tags` holding `hello\n`, and the test format `test/tags`, whose files are named `*.tags` and start with `TAGS`, reads its first 4 bytes and says it is not of its type, with the reason "no TAGS header"
- **THEN** `notes.tags` is a single-file dataset of type `text/plain` with the basis `single file; test/tags: not application/x.test-tags, no TAGS header`, its record describes it as a plain text document, and the crawl reports no warning for it

#### Scenario: An empty file named like the format's files
- **WHEN** a directory holds an empty `empty.tags`, and `test/tags` says it is not of its type
- **THEN** `empty.tags` is a single file of type `text/plain`, the type an empty file without a name rule gets

#### Scenario: A file of the type is kept
- **WHEN** a directory holds `real.tags` starting with `TAGS`
- **THEN** `real.tags` is a single file of type `application/x.test-tags` with the basis `single file`

#### Scenario: A later format claims the new type
- **WHEN** a directory holds `picture.tags` starting with the PNG signature, `test/tags` says it is not of its type, and the test format `test/png`, which claims every file of type `image/png` with the basis "PNG signature", has a lower priority than `test/tags`
- **THEN** `picture.tags` is a dataset of `test/png` of type `image/png` with the basis `PNG signature; test/tags: not application/x.test-tags, no TAGS header`, and the crawl reports no warning

#### Scenario: A second call on the same file reads nothing
- **WHEN** `test/tags` says twice in one call that `notes.tags`, holding `hello\n`, is not of its type
- **THEN** `notes.tags` is a single file of type `text/plain`, the file is read once by the core for its new type, and the crawl warns once that `text/plain` does not come from its name alone and is kept

### Requirement: A broken format order is reported
When a format drops a file's type, and a format that runs earlier on the directory reacts to the file's new type, the crawl SHALL report a warning naming both formats, the file and the new type. The earlier format SHALL NOT be called again.

#### Scenario: A format that ran before does not see the new type
- **WHEN** the directory holding `picture.tags` (starting with the PNG signature) is recognised with `test/png` at a higher priority than `test/tags`
- **THEN** `picture.tags` is a single file of type `image/png`, not claimed by `test/png`, and the crawl warns at `picture.tags` that `test/png` runs before `test/tags` and did not see it as `image/png`

### Requirement: A file typed by its content keeps its type
When a format says a file is not of its type, but the file's type did not come from a single best name rule (it came from the content, from a tie that the content decided, or from an earlier drop), the file SHALL keep its type and basis, and the crawl SHALL report a warning naming the format, the file, the type and the reason.

#### Scenario: A file without an extension that matches a content rule
- **WHEN** a directory holds `blob`, which no name rule matches and which starts with the PNG signature, so that it is typed `image/png` by its content, and the test format `test/contradicts` says it is not of its type, with the reason "not a picture"
- **THEN** `blob` is a single file of type `image/png` with the basis `single file`, and the crawl's warnings name `test/contradicts`, `blob`, `image/png` and "not a picture"

### Requirement: A failed format call leaves every type as it was
A format call on a directory that fails, exceeds its byte budget, or meets a read error while the core finds a file's new type, SHALL leave the types and bases of the directory's files as they were before the call. A read error SHALL be reported as the format's failure on the directory, and the directory SHALL be recognised again on the next crawl.

#### Scenario: A format fails after dropping a type
- **WHEN** a variant of `test/tags` says `notes.tags` is not of its type and then raises an exception in the same call
- **THEN** `notes.tags` is a single file of type `application/x.test-tags` with the basis `single file`, and the crawl warns that the format failed on the directory

#### Scenario: A read error while finding the new type
- **WHEN** `test/tags` says `notes.tags` is not of its type, and reading `notes.tags` for its new type fails with an I/O error
- **THEN** `notes.tags` is a single file of type `application/x.test-tags` with the basis `single file`, the crawl warns that `test/tags` failed on the directory, naming the error, and the directory is marked to be recognised again on the next crawl

### Requirement: A dropped type lasts until the file or the rules change
The new type and basis of a file whose name type a format dropped SHALL be stored with its dataset like any recognition result. A crawl of the unchanged directory under the same rules SHALL give the same type and basis without reading the file. A crawl after the file changed SHALL check it again.

#### Scenario: A second crawl of an unchanged directory
- **WHEN** a tree holding the text file `notes.tags` is crawled twice without changes
- **THEN** the second crawl calls no format on its directory and reads none of its files, `notes.tags` is still `text/plain` with the same basis, and its record keeps its datestamp

#### Scenario: The file is replaced by one of the type
- **WHEN** `notes.tags` is replaced between two crawls by a file starting with `TAGS`
- **THEN** after the second crawl its type is `application/x.test-tags` and its basis is `single file`

## MODIFIED Requirements

### Requirement: Plain data in, no reach outside the directory
A format SHALL receive only the directory's entries, their types, the children's datasets and a bounded reader for the directory's own files, and SHALL NOT receive database connections or access to other directories. The bytes the core reads to find a file's new type, after a format said the file is not of its name's type, SHALL NOT count against that format call's budget (decision 166); the format's own reads do.

#### Scenario: Reading a file within the budget
- **WHEN** a format reads the first bytes of an entry through the reader
- **THEN** it receives at most the configured number of bytes and the read counts against the directory's budget

#### Scenario: The new type's detection does not use the format's budget
- **WHEN** `test/tags` reads the first 4 bytes of `big.tags`, 20,000 bytes of text, and says it is not of its type, with a byte budget of 1,000 bytes
- **THEN** `big.tags` is a single file of type `text/plain`, and no warning about `test/tags`'s budget is given

### Requirement: A byte budget bounds every format call
Each format call on a directory SHALL have a byte budget for reads, enforced while reading; exceeding it SHALL discard that format's result for that directory with a warning naming the format, and SHALL NOT stop the crawl. The core's detection of a file's new type after a drop SHALL NOT count against it (requirement "Plain data in, no reach outside the directory").

#### Scenario: A format reads past its budget
- **WHEN** a format reads more bytes on a directory than its budget allows
- **THEN** its result is discarded, the directory is recognised by the remaining formats, and a warning names the format and the read
