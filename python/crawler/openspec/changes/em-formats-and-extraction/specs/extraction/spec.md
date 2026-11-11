# Spec Delta

## Purpose

Running metadata extractors on recognised datasets, apart from the walk, and turning their results into the record's description and subjects, so that a search finds data by what it is and not only by its path.

## ADDED Requirements

### Requirement: Formats may extract metadata after recognition
A format MAY provide an extractor. After recognition, the crawl SHALL run the extractor of each dataset's format, if it has one, and SHALL put its result into the dataset's record; a dataset whose format has no extractor SHALL get no extracted metadata and no error.

#### Scenario: A format with an extractor
- **WHEN** a test tree holds one file of a format with an extractor and one plain text file
- **THEN** the first file's record carries the extracted values and the text file's record carries none, and the crawl reports one extraction

### Requirement: A failing or slow extractor does not stop the crawl
An extractor that raises, crashes its process, or exceeds its time limit SHALL leave its dataset recognised, with a basic description and a warning that names the dataset and the reason; the crawl SHALL continue and finish.

#### Scenario: An extractor raises on a broken file
- **WHEN** a file of a format with an extractor is truncated so that the reader fails
- **THEN** the crawl finishes, the file's record exists with a basic description, and the crawl's warnings name the file and the error

#### Scenario: An extractor hangs
- **WHEN** an extractor does not return within the time limit
- **THEN** the crawl finishes, the dataset's record has a basic description, and a warning says that the extractor timed out

### Requirement: Unchanged directories are not recognised or extracted again
A crawl SHALL take over the stored datasets of a directory without reading file contents, recognising or extracting, when the directory's listing (names, types, sizes, mtimes, ctimes) and those of all directories below it are unchanged since the last finished crawl and the enabled formats, their versions and the selection are unchanged. Every directory SHALL still be listed, so that a change at any depth is seen.

#### Scenario: A second crawl of an unchanged tree
- **WHEN** a tree with files of a format with an extractor is crawled twice without changes
- **THEN** the second crawl reads no file contents, reports no recognition and no extraction for its directories, and the records are unchanged, datestamps included

#### Scenario: A change deep in the tree
- **WHEN** a file three directories below the root is rewritten in place with a new size between two crawls
- **THEN** the second crawl recognises its directory and the directories above it again, extracts only the changed file's dataset, and leaves the other datasets' records unchanged

### Requirement: Extraction follows the identified extractor
Each dataset SHALL record which extractor and which extractor version produced its metadata. A dataset SHALL be extracted again when it is recognised with a different extractor or extractor version, or when its members' sizes or times changed; otherwise its stored result, including a stored failure, SHALL be reused.

#### Scenario: A new extractor version
- **WHEN** the extractor's version changes between two crawls of an unchanged tree
- **THEN** the second crawl extracts again the datasets of that extractor only, and only records whose content changed get a new datestamp

#### Scenario: A file that failed stays failed until something changes
- **WHEN** a broken file's extraction failed and the tree is crawled again unchanged
- **THEN** the second crawl does not run the extractor on it and still reports it as failed

### Requirement: The crawl reports extraction
The crawl's report SHALL state the number of extractions run, reused from the last crawl and failed, the number of directories taken over unchanged, and the time spent extracting per format.

#### Scenario: Report after a crawl
- **WHEN** a crawl extracts two files and one extraction fails
- **THEN** the report shows 2 run, 0 reused and 1 failed, with the time per format
