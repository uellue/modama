# Spec Delta

## Purpose

Running metadata extractors on recognised datasets, apart from the walk, and turning their results into the record's description and subjects, so that a search finds data by what it is and not only by its path.

## ADDED Requirements

### Requirement: Formats may extract metadata after recognition
A format MAY provide an extractor. After recognition, the crawl SHALL run the extractor of each dataset's format, if it has one, and SHALL put its result into the dataset's record; a dataset whose format has no extractor SHALL get no extracted metadata and no error. In the result, NUL characters and lone surrogates SHALL be replaced by U+FFFD, strings SHALL be cut to 4096 characters and lists and mappings to 1000 entries; a result that still cannot be stored (NaN, an infinity, a value that is not JSON) SHALL become the dataset's extraction error, never a failure of the crawl.

#### Scenario: A format with an extractor
- **WHEN** a test tree holds one file of a format with an extractor and one plain text file
- **THEN** the first file's record carries the extracted values and the text file's record carries none, and the crawl reports one extraction

### Requirement: A failing or slow extractor does not stop the crawl
An extractor that raises, crashes its process, exceeds its memory budget (an address space per worker process, configurable) or exceeds its time limit SHALL leave its dataset recognised, with a basic description and a warning that names the dataset and the reason; the crawl SHALL continue and finish.

#### Scenario: An extractor raises on a broken file
- **WHEN** a file of a format with an extractor is truncated so that the reader fails
- **THEN** the crawl finishes, the file's record exists with a basic description, and the crawl's warnings name the file and the error

#### Scenario: An extractor hangs
- **WHEN** an extractor does not return within the time limit
- **THEN** the crawl finishes, the dataset's record has a basic description, and a warning says that the extractor timed out

### Requirement: Unchanged directories are not recognised or extracted again
A crawl SHALL take over the stored datasets of a directory without reading file contents, recognising or extracting, when the directory's listing (names, types, sizes, mtimes, ctimes) and those of all directories below it are unchanged since the last finished crawl and the enabled formats, their versions and the selection are unchanged. Every directory SHALL still be listed, so that a change at any depth is seen. A directory whose recognition met a read error or a format's time limit SHALL NOT be taken over: the next crawl recognises it again. A directory the crawler cannot list SHALL count as unchanged when it could not be listed by the last crawl either and its entry in its parent's listing is unchanged.

#### Scenario: A second crawl of an unchanged tree
- **WHEN** a tree with files of a format with an extractor is crawled twice without changes
- **THEN** the second crawl reads no file contents, reports no recognition and no extraction for its directories, and the records are unchanged, datestamps included

#### Scenario: A change deep in the tree
- **WHEN** a file three directories below the root is rewritten in place with a new size between two crawls
- **THEN** the second crawl recognises its directory and the directories above it again, extracts only the changed file's dataset, and leaves the other datasets' records unchanged

### Requirement: Extraction follows the identified extractor
Each dataset SHALL record which extractor and which extractor version produced its metadata. A dataset SHALL be extracted again when it is recognised with a different extractor or extractor version, or when its members' sizes or times changed; otherwise its stored result, including a failure of reading the file, SHALL be reused. A failure that comes from the environment, not from the file (the time limit, a dead worker process, an operating system error, a missing module), SHALL NOT be reused: the next crawl runs the extractor again.

#### Scenario: A new extractor version
- **WHEN** the extractor's version changes between two crawls of an unchanged tree
- **THEN** the second crawl extracts again the datasets of that extractor only, and only records whose content changed get a new datestamp

#### Scenario: A file whose reading failed stays failed until something changes
- **WHEN** a broken file's extraction failed because the reader raised on its content, and the tree is crawled again unchanged
- **THEN** the second crawl does not run the extractor on it and still reports it as failed

#### Scenario: A timeout is retried on the next crawl
- **WHEN** an extraction ran over the time limit and the tree is crawled again unchanged
- **THEN** the second crawl runs the extractor on the dataset again

### Requirement: The crawl reports extraction
The crawl's report SHALL state the number of extractions run, reused from the last crawl and failed, the number of directories taken over unchanged, and the time spent extracting per format. A finished crawl SHALL store these counts, without the times, with its run, and `modama-crawler runs` SHALL show them on the run's line (@weber, 2026-11-11).

#### Scenario: Report after a crawl
- **WHEN** a crawl extracts two files and one extraction fails
- **THEN** the report shows 2 run, 0 reused and 1 failed, with the time per format

#### Scenario: The counts stay with the run
- **WHEN** a tree is crawled a second time without changes and `modama-crawler runs` is run
- **THEN** the second run's line shows `extraction: 0 run, 0 reused, 0 failed; 2 directories unchanged` for a tree of two directories without extractable files
