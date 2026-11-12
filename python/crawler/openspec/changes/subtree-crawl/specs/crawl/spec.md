# Spec Delta

## MODIFIED Requirements

### Requirement: Results reach the index
After a crawl of the whole tree, the index SHALL contain one record per dataset of the recognition result, and datasets that disappeared SHALL be removed from it. After a subtree crawl the same SHALL hold for the datasets under its path, and the index SHALL be unchanged outside it.

#### Scenario: A deleted file leaves the index
- **WHEN** a file that was a dataset is deleted and the tree is crawled again
- **THEN** its record is gone and the remaining records are unchanged

#### Scenario: A deleted file in a subtree leaves the index
- **WHEN** a tree holding `adhoc/libertem/libertem-test-data/dm/a.dm4`, `adhoc/libertem/libertem-test-data/dm/b.dm4` and `other/c.txt` is crawled, `b.dm4` is deleted, and `crawl --path adhoc/libertem/libertem-test-data` is run
- **THEN** the record of `b.dm4` is gone, and the records of `a.dm4` and `other/c.txt` are unchanged, datestamps included

## ADDED Requirements

### Requirement: A subtree crawl changes only its subtree
`modama-crawler crawl --path PATH` SHALL walk only the directory PATH, a canonical path (relative to the data root, with or without a leading `/`), and SHALL leave every dataset and record outside it unchanged, datestamps included. Its datasets SHALL get the same anchors and identifiers as in a crawl of the whole tree.

#### Scenario: Records outside the subtree stay as they are
- **WHEN** a tree with files in `adhoc/libertem/libertem-test-data/` and in `other/` is crawled, a file in `other/` is deleted, and `crawl --path adhoc/libertem/libertem-test-data` is run
- **THEN** the deleted file's record is still there, and no record outside `adhoc/libertem/libertem-test-data/` has a new datestamp

#### Scenario: The same identifiers as a full crawl
- **WHEN** `crawl --path /adhoc/libertem/libertem-test-data` is run on a fresh index, and then the whole tree is crawled
- **THEN** the records under the path have the identifiers that the subtree crawl gave them, for example the one of `/adhoc/libertem/libertem-test-data/dm/a.dm4`, and their datestamps did not move

#### Scenario: A file stands for its directory
- **WHEN** `crawl --path adhoc/libertem/libertem-test-data/dm/a.dm4` is run
- **THEN** the crawl covers `adhoc/libertem/libertem-test-data/dm/`, and an info line on stderr says so

### Requirement: A subtree crawl recognises and extracts its subtree again
A subtree crawl SHALL recognise every directory under its path and SHALL run the extractor of every dataset there that has one, without taking over stored datasets and without reusing stored extractions. A record SHALL get a new datestamp only if its content changed.

#### Scenario: A changed extractor without a new version
- **WHEN** the tree was crawled, the extractor of `em/dm4` is changed without changing its `extractor_version`, and `crawl --path adhoc/libertem/libertem-test-data` is run
- **THEN** the DM4 files under the path are extracted again, and only their records whose description or subjects changed get a new datestamp

#### Scenario: The same code gives the same records
- **WHEN** `crawl --path adhoc/libertem/libertem-test-data` is run twice without changes to the files or the formats
- **THEN** the second crawl reports the extractions as run, not reused, and 0 records changed

#### Scenario: The next full crawl takes over the extractions
- **WHEN** a subtree crawl is followed by a crawl of the whole tree with nothing changed
- **THEN** the full crawl recognises the directories under the path again, reuses their extractions, and changes no record

### Requirement: A subtree crawl only covers what a full crawl enters
A subtree crawl SHALL end with status 2, an error line naming the path and the reason, and no run recorded, when its path is not a directory (or a file in one) below the data root, when it or a directory above it is a symlink, is excluded by `[crawl] exclude`, cannot be listed, or is a directory that a format collapses.

#### Scenario: A path inside a collapsed directory
- **WHEN** `crawl --path adhoc/project/.venv/lib` is run and `adhoc/project/.venv` is a Python environment
- **THEN** the exit status is 2, stderr names `/adhoc/project/.venv` as collapsed, and no run is recorded

#### Scenario: An excluded path
- **WHEN** the configuration excludes `/scratch/**` and `crawl --path scratch/tmp` is run
- **THEN** the exit status is 2 and stderr says that the path is excluded

#### Scenario: A path outside the data root
- **WHEN** `crawl --path ../etc` or `crawl --path adhoc/nosuch` is run
- **THEN** the exit status is 2 and stderr names the path

### Requirement: A subtree crawl shares the crawl lock and stops on SIGTERM
A subtree crawl SHALL take the crawl lock as a crawl of the whole tree does, so that neither starts while the other runs, and on SIGTERM it SHALL end as a crawl of the whole tree does, without a change to the records.

#### Scenario: A subtree crawl while the timer's crawl runs
- **WHEN** `crawl --path adhoc/libertem/libertem-test-data` is started while a crawl of the whole tree runs
- **THEN** it exits with status 1 and `another crawl is running on this database`, and no run is recorded

#### Scenario: A subtree crawl stopped while it extracts
- **WHEN** a subtree crawl gets SIGTERM during its extraction
- **THEN** its run is `failed` with `terminated (SIGTERM)`, the exit status is 143, and no record changed
