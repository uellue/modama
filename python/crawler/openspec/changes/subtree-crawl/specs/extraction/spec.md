# Spec Delta

## MODIFIED Requirements

### Requirement: Unchanged directories are not recognised or extracted again
A crawl of the whole tree SHALL take over the stored datasets of a directory without reading file contents for recognition and without recognising, when the directory's listing (names, types, sizes, mtimes, ctimes) and those of all directories below it are unchanged since the last finished crawl and the enabled formats, their versions and the selection are unchanged. The stored extractions of the datasets taken over SHALL be checked like any other (requirement "Extraction follows the identified extractor"): a failed one, or one under another identity, is extracted again, and a sample is spot-checked (requirement "Each crawl spot-checks a sample of what it reuses"). Every directory SHALL still be listed, so that a change at any depth is seen. A directory whose recognition met a read error or a format's time limit SHALL NOT be taken over: the next crawl recognises it again. A directory the crawler cannot list SHALL count as unchanged when it could not be listed by the last crawl either and its entry in its parent's listing is unchanged. A subtree crawl takes nothing over under its path (capability `crawl`, "A subtree crawl recognises and extracts its subtree again").

#### Scenario: A second crawl of an unchanged tree
- **WHEN** a tree with files of a format with an extractor, all extracted successfully, is crawled twice without changes and with the same installation
- **THEN** the second crawl reads no file contents apart from the spot check's sample, reports no recognition and no extraction for its directories, and the records are unchanged, datestamps included

#### Scenario: A change deep in the tree
- **WHEN** a file three directories below the root is rewritten in place with a new size between two crawls
- **THEN** the second crawl recognises its directory and the directories above it again, extracts only the changed file's dataset apart from the spot check's sample, and leaves the other datasets' records unchanged

#### Scenario: A failed file in an unchanged directory
- **WHEN** a directory holds a file whose extraction failed, and the tree is crawled again without changes
- **THEN** the directory is taken over without recognising, and the failed file is extracted again

### Requirement: Extraction follows the identified extractor
Each dataset SHALL record which extractor (its format id) and which extractor identity produced its metadata. In a crawl of the whole tree, a stored successful extraction SHALL be reused while the dataset is recognised with the same extractor, its stored identity equals the identity of the running crawl, and its members' sizes and times are unchanged; otherwise the dataset SHALL be extracted again. Identities SHALL be compared for equality only, never ordered. A stored failure SHALL NOT be reused, whatever its cause (the file's content, the memory or time limit, a dead worker process, an operating system error, a missing module): every crawl runs the extractor on it again. A subtree crawl reuses no stored result under its path (capability `crawl`).

#### Scenario: A changed source file of a format package
- **WHEN** a source file of an installed format package changes between two crawls of an unchanged tree
- **THEN** the second crawl extracts again every dataset of every format with an extractor, and only records whose content changed get a new datestamp

#### Scenario: A change that alters no output
- **WHEN** a comment is added to a format package's source between two crawls of an unchanged tree
- **THEN** the second crawl extracts every dataset again, and no record gets a new datestamp

#### Scenario: An upgraded dependency
- **WHEN** the installed version of a distribution that no format package provides changes between two crawls of an unchanged tree (RosettaSciIO 0.15.0 to 0.16.0)
- **THEN** the second crawl extracts every dataset of every format with an extractor again

#### Scenario: Back to an earlier installation
- **WHEN** an unchanged tree is crawled under installation A, then under installation B whose extractor gives other output, then under A again (a rollback, or a reverted experiment)
- **THEN** the third crawl extracts every dataset again, and its records' metadata equals that after the first crawl

#### Scenario: A file whose reading failed is tried again on every crawl
- **WHEN** a broken file's extraction failed because the reader raised on its content, and the tree is crawled again unchanged
- **THEN** the second crawl runs the extractor on it again and reports it as failed again

#### Scenario: A timeout is retried on the next crawl
- **WHEN** an extraction ran over the time limit and the tree is crawled again unchanged
- **THEN** the second crawl runs the extractor on the dataset again

#### Scenario: A failure under a lowered memory limit
- **WHEN** a DM4 file's extraction failed with a `MemoryError` under a lowered memory limit, the limit is raised again, and the unchanged tree is crawled again
- **THEN** the second crawl extracts that file again and it succeeds, and the other datasets are reused
