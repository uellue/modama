# Spec Delta

## MODIFIED Requirements

### Requirement: Extraction follows the identified extractor
Each dataset SHALL record which extractor (its format id) and which extractor identity produced its metadata. A dataset SHALL be extracted again when it is recognised with a different extractor, when its stored identity is not equal to the identity of the running crawl, or when its members' sizes or times changed; otherwise its stored result, including a failure of reading the file, SHALL be reused. Identities SHALL be compared for equality only, never ordered. A failure that comes from the environment, not from the file (the time limit, a dead worker process, an operating system error, a missing module), SHALL NOT be reused: the next crawl runs the extractor again.

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

#### Scenario: A file whose reading failed stays failed until something changes
- **WHEN** a broken file's extraction failed because the reader raised on its content, and the tree is crawled again unchanged
- **THEN** the second crawl does not run the extractor on it and still reports it as failed

#### Scenario: A timeout is retried on the next crawl
- **WHEN** an extraction ran over the time limit and the tree is crawled again unchanged
- **THEN** the second crawl runs the extractor on the dataset again

## ADDED Requirements

### Requirement: The extractor identity is derived from the installation
Each crawl SHALL compute one extractor identity at its start, a digest of: the Python implementation and version; the name and version of every installed distribution; and the content of each source file of the distributions that provide formats or were installed from a path, an archive or a repository rather than a package index, apart from their tests. No person sets it. The same installation SHALL give the same identity, wherever it is installed.

#### Scenario: The same installation in two places
- **WHEN** the identity is computed for two installations of the same distributions and the same source, at two different paths
- **THEN** the two identities are equal

#### Scenario: A test file does not count
- **WHEN** a fixture or a test module below a format package's `tests` directory changes
- **THEN** the identity stays the same

#### Scenario: A dependency installed from a repository
- **WHEN** a source file changes in a distribution installed from a local path or a repository, and its version stays the same
- **THEN** the identity changes

### Requirement: The crawl reports re-extraction and its cause
The crawl's report SHALL state, per format, how many datasets were extracted again only because the identity changed, what differs between their stored identity and the current one (a distribution's version, a module's source, the Python version, or that the stored identity's ingredients are unknown), and how many of those datasets' records changed. A finished crawl SHALL store these with its run, and `modama-crawler runs` SHALL show them on the run's line.

#### Scenario: A dependency upgrade that changes output
- **WHEN** a tree with two DM4 files is crawled, RosettaSciIO's installed version changes so that one file's description differs, and the tree is crawled again
- **THEN** the second report has the line `em/dm4: 2 extracted again for a new identity (rosettasciio 0.15.0 -> 0.16.0), 1 record changed`, and `runs` shows the same counts for that run

#### Scenario: A refactoring that changes no output
- **WHEN** only a comment changes in `modama_formats_em/dm/__init__.py` between two crawls of the same tree
- **THEN** the second report has the line `em/dm4: 2 extracted again for a new identity (source of modama_formats_em.dm changed), 0 records changed`

#### Scenario: An identity from before this change
- **WHEN** the stored extractions carry a version label from before this change (`"4"`) and the tree is crawled
- **THEN** the report says `em/dm4: 2 extracted again for a new identity (earlier identity "4", ingredients unknown), 0 records changed` when the output is the same
