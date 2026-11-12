# Spec Delta

## ADDED Requirements

### Requirement: A format can say a file is not of the type its name gave it
While recognising a directory, a format SHALL be able to say that a file is not of the type the file's name gave it, with a reason. When a single best name rule gave that type, the file SHALL get the type detection gives without it, at once: for the formats that run after it on that directory, and as a single file. The dataset holding the file SHALL carry the format and the reason in its basis, and the crawl SHALL report no warning for it.

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
- **WHEN** a directory holds `picture.tags` starting with the PNG signature, `test/tags` says it is not of its type, and `test/png` has a lower priority than `test/tags`
- **THEN** `picture.tags` is a dataset of `test/png` of type `image/png`, and its basis ends with `test/tags: not application/x.test-tags, no TAGS header`

#### Scenario: A format that ran before does not see the new type
- **WHEN** the same directory is recognised with `test/png` at a higher priority than `test/tags`
- **THEN** `picture.tags` is a single file of type `image/png`, not claimed by `test/png`

### Requirement: A file typed by its content keeps its type
When a format says a file is not of its type, but the file's type did not come from a single best name rule (it came from the content, from a tie that the content decided, or from an earlier drop), the file SHALL keep its type, and the crawl SHALL report a warning naming the format, the file, the type and the reason.

#### Scenario: A file without an extension that matches a content rule
- **WHEN** a file `blob`, which no name rule matches, starts with the PNG signature and is typed `image/png` by its content, and a format says it is not of type `image/png`
- **THEN** `blob` keeps the type `image/png`, and the crawl's warnings name the format, `blob`, `image/png` and the format's reason

### Requirement: A failed format call leaves every type as it was
A format call on a directory that fails, or exceeds its byte budget, SHALL leave the types of the directory's files as they were before the call. The bytes the core reads to find a file's new type SHALL count against the budget of the format call that dropped the type.

#### Scenario: A format fails after dropping a type
- **WHEN** `test/tags` says `notes.tags` is not of its type and then raises an exception in the same call
- **THEN** `notes.tags` is a single file of type `application/x.test-tags`, and the crawl warns that `test/tags` failed on the directory

#### Scenario: The new type's detection exceeds the budget
- **WHEN** `test/tags` says that `big.tags`, 20,000 bytes of text, is not of its type, with a byte budget of 1,000 bytes
- **THEN** `big.tags` is a single file of type `application/x.test-tags`, and the crawl warns that `test/tags` was skipped on the directory for exceeding its budget

### Requirement: A dropped type lasts until the file or the rules change
The new type and basis of a file whose name type a format dropped SHALL be stored with its dataset like any recognition result. A crawl of the unchanged directory under the same rules SHALL give the same type and basis without reading the file. A crawl after the file changed SHALL check it again.

#### Scenario: A second crawl of an unchanged directory
- **WHEN** a tree holding the text file `notes.tags` is crawled twice without changes
- **THEN** the second crawl calls no format on its directory and reads none of its files, `notes.tags` is still `text/plain` with the same basis, and its record keeps its datestamp

#### Scenario: The file is replaced by one of the type
- **WHEN** `notes.tags` is replaced between two crawls by a file starting with `TAGS`
- **THEN** after the second crawl its type is `application/x.test-tags` and its basis is `single file`
