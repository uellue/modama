# Spec Delta

## ADDED Requirements

### Requirement: A stray file its extractor rejects falls back to another type
An extractor SHALL be able to reject a dataset: its files are not of the format's type. This is distinct from failing on them. When the dataset is a single file whose name alone gave it the format's type, the dataset SHALL take the type that detection gives without that type, and its record SHALL describe it as that type. The crawl SHALL report no warning for it, and the fallback type's extractor SHALL NOT run.

#### Scenario: A text file named like a tag file
- **WHEN** a directory holds `notes.gtg` holding `hello\n` and no K2IS sector files, and the `.gtg` format's extractor rejects it for lack of the DM4 header
- **THEN** its record has `dc:format` `text/plain` and a description that names it a plain text document, 1 file of 6 B, and the crawl reports no warning for it

#### Scenario: An empty file named like a workspace
- **WHEN** a directory holds an empty `empty.dmw` and the `.dmw` format's extractor rejects it
- **THEN** its record has `dc:format` `text/plain`, the type an empty file without a name rule gets, and the crawl reports no warning for it

#### Scenario: A file of the type is not rejected
- **WHEN** a directory holds `IDES_DMS_Config.gtg` starting with the DM4 header
- **THEN** its record has `dc:format` `application/x.dm-gtg`

### Requirement: A rejection is reused like a result
A rejection SHALL be stored with the extractor, its version and the dataset's stamp. A crawl of the same files with the same extractor version SHALL give the same type without running the extractor. A crawl after the files or the extractor version changed SHALL run the extractor again and SHALL give the format's type when it no longer rejects.

#### Scenario: A second crawl of an unchanged tree
- **WHEN** a tree holding the text file `notes.gtg` is crawled twice without changes, and the second time its directory is recognised again because another file in it changed
- **THEN** the second crawl does not run the `.gtg` extractor on `notes.gtg`, its type is still `text/plain`, and its record keeps its datestamp

#### Scenario: The file is replaced by a tag file
- **WHEN** `notes.gtg` is replaced between two crawls by a file starting with the DM4 header
- **THEN** the second crawl runs the extractor on it and its type is `application/x.dm-gtg`

### Requirement: Any other rejected dataset keeps its type and fails
A rejection of any dataset other than a single file typed by its name alone SHALL be an extraction failure: the dataset SHALL keep its type, members and record, and the crawl SHALL report the failure as for an extractor that raises. Such datasets are several files, a directory, a collapsed tree, or a file typed by its content. The crawl SHALL NOT recognise the dataset again.

#### Scenario: A K2IS capture whose tag file is text
- **WHEN** a directory holds `X_.gtg` holding `hello\n` and `X_1.bin` to `X_8.bin`, each starting with a K2IS block header
- **THEN** the result has one K2IS dataset with 9 members anchored at `X_.gtg`, no single-file dataset for any of them, and the crawl's warnings name `X_.gtg` and the K2IS extraction failure

#### Scenario: A file typed by its content
- **WHEN** a file with no matching name rule is typed by its content, and its format's extractor rejects it
- **THEN** its type is unchanged and the crawl reports its extraction failure
