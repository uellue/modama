# Spec Delta

## Purpose

Walking a data tree into recognition results and the index, in an order that lets every directory be recognised together with the results of its subdirectories, while never entering trees that are a dataset as a whole.

## ADDED Requirements

### Requirement: Directories are recognised after their subdirectories
The crawl SHALL run a directory's recognition only after the recognition of all its subdirectories is final, and SHALL pass their resulting datasets to it.

#### Scenario: A parent sees its child's result
- **WHEN** a tree contains `outer/` with a file and a subdirectory `outer/inner/` that a format recognises as a dataset
- **THEN** the recognition of `outer/` receives the dataset anchored at `outer/inner` among its children's results

### Requirement: Collapsed directories are not entered
The crawl SHALL ask the enabled formats, from a directory's listing alone, whether the directory is a dataset as a whole, and if so SHALL record it as one dataset and SHALL NOT list, classify or read anything below it.

#### Scenario: A boring tree is skipped
- **WHEN** a directory is recognised as collapsed by a format from its listing and contains subdirectories with many files
- **THEN** the result contains one dataset anchored at that directory, no entries below it, and no file below it was opened

### Requirement: Entries carry both timestamps
The crawl SHALL record for every entry its size, its modification time and its change time separately, with sub-second precision where the file system provides it.

#### Scenario: Copied series keep their original mtime
- **WHEN** a file has an mtime older than its ctime
- **THEN** both values are available to formats and stored unchanged

### Requirement: The result does not depend on listing order
The recognition result of a tree SHALL be identical whatever order the file system returns directory entries in.

#### Scenario: Shuffled listings
- **WHEN** the same tree is crawled twice with directory entries returned in different orders
- **THEN** both results are identical, including anchors, members and the order of members

### Requirement: Unreadable and unstorable entries are reported, not fatal
The crawl SHALL continue past directories it cannot read and names it cannot store, and SHALL report each with its path and reason.

#### Scenario: Permission denied
- **WHEN** a subdirectory cannot be listed
- **THEN** the crawl records a warning naming it and recognises the rest of the tree

#### Scenario: A name that is not valid UTF-8
- **WHEN** an entry's name cannot be decoded as UTF-8
- **THEN** the entry is skipped with a warning naming its directory

### Requirement: Results reach the index
After a crawl, the index SHALL contain one record per dataset of the recognition result, and datasets that disappeared SHALL be removed from it.

#### Scenario: A deleted file leaves the index
- **WHEN** a file that was a dataset is deleted and the tree is crawled again
- **THEN** its record is gone and the remaining records are unchanged
