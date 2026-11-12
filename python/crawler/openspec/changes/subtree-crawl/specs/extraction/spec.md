# Spec Delta

## MODIFIED Requirements

### Requirement: Unchanged directories are not recognised or extracted again
A crawl of the whole tree SHALL take over the stored datasets of a directory without reading file contents, recognising or extracting, when the directory's listing (names, types, sizes, mtimes, ctimes) and those of all directories below it are unchanged since the last finished crawl and the enabled formats, their versions and the selection are unchanged. Every directory SHALL still be listed, so that a change at any depth is seen. A directory whose recognition met a read error or a format's time limit SHALL NOT be taken over: the next crawl recognises it again. A directory the crawler cannot list SHALL count as unchanged when it could not be listed by the last crawl either and its entry in its parent's listing is unchanged. A subtree crawl takes nothing over under its path (capability `crawl`, "A subtree crawl recognises and extracts its subtree again").

#### Scenario: A second crawl of an unchanged tree
- **WHEN** a tree with files of a format with an extractor is crawled twice without changes
- **THEN** the second crawl reads no file contents, reports no recognition and no extraction for its directories, and the records are unchanged, datestamps included

#### Scenario: A change deep in the tree
- **WHEN** a file three directories below the root is rewritten in place with a new size between two crawls
- **THEN** the second crawl recognises its directory and the directories above it again, extracts only the changed file's dataset, and leaves the other datasets' records unchanged

### Requirement: Extraction follows the identified extractor
Each dataset SHALL record which extractor and which extractor version produced its metadata. In a crawl of the whole tree, a dataset SHALL be extracted again when it is recognised with a different extractor or extractor version, or when its members' sizes or times changed; otherwise its stored result, including a failure of reading the file, SHALL be reused. A failure that comes from the environment, not from the file (the time limit, a dead worker process, an operating system error, a missing module), SHALL NOT be reused: the next crawl runs the extractor again. A subtree crawl reuses no stored result under its path (capability `crawl`).

#### Scenario: A new extractor version
- **WHEN** the extractor's version changes between two crawls of an unchanged tree
- **THEN** the second crawl extracts again the datasets of that extractor only, and only records whose content changed get a new datestamp

#### Scenario: A file whose reading failed stays failed until something changes
- **WHEN** a broken file's extraction failed because the reader raised on its content, and the tree is crawled again unchanged
- **THEN** the second crawl does not run the extractor on it and still reports it as failed

#### Scenario: A timeout is retried on the next crawl
- **WHEN** an extraction ran over the time limit and the tree is crawled again unchanged
- **THEN** the second crawl runs the extractor on the dataset again
