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
`modama-crawler crawl --path PATH` SHALL walk only the directory PATH and SHALL leave every dataset, stored listing and record outside it unchanged, datestamps included. A directory is under PATH when it is PATH or its path continues PATH after a `/`. Its datasets SHALL get the same anchors and identifiers as in a crawl of the whole tree.

#### Scenario: Records outside the subtree stay as they are
- **WHEN** a tree with files in `adhoc/libertem/libertem-test-data/` and in `other/` is crawled, a file in `other/` is deleted, and `crawl --path adhoc/libertem/libertem-test-data` is run
- **THEN** the deleted file's record is still there, and no record outside `adhoc/libertem/libertem-test-data/` has a new datestamp

#### Scenario: A sibling with the same prefix stays
- **WHEN** a tree holding `adhoc/a/b/x.txt`, `adhoc/a/bc/y.txt`, `adhoc/a/b_/z.txt` and `adhoc/a/b%/w.txt` is crawled, and `crawl --path adhoc/a/b` is run
- **THEN** the records of `y.txt`, `z.txt` and `w.txt` are unchanged, datestamps included, and the next crawl of the whole tree takes their directories over unchanged

#### Scenario: The same identifiers as a full crawl
- **WHEN** `crawl --path /adhoc/libertem/libertem-test-data` is run on a fresh index, and then the whole tree is crawled
- **THEN** the records under the path have the identifiers that the subtree crawl gave them, for example the one of `/adhoc/libertem/libertem-test-data/dm/a.dm4`, and their datestamps did not move

### Requirement: A subtree crawl's path is a canonical path
The path of `crawl --path` SHALL be read as a canonical path, relative to the data root, with or without a leading or a trailing `/`, and normalised. A file SHALL stand for its directory.

#### Scenario: A path in another spelling
- **WHEN** `crawl --path adhoc/other/../libertem/libertem-test-data/` is run
- **THEN** the crawl covers `adhoc/libertem/libertem-test-data`, as `crawl --path adhoc/libertem/libertem-test-data` does, and its run records that path

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
A subtree crawl SHALL end with status 2, an error line naming the directory and the reason, and no run recorded, when its path or a directory above it is a symlink, is excluded by `[crawl] exclude` or cannot be listed, or when a directory above it is collapsed by a format active there after per-path ignores. A path that is itself collapsed SHALL become one dataset, as in a crawl of the whole tree.

#### Scenario: A collapsed directory as path
- **WHEN** `adhoc/project/data.zarr` is a Zarr store and `crawl --path adhoc/project/data.zarr` is run
- **THEN** the crawl ends with status 0, and the index holds one dataset anchored at `/adhoc/project/data.zarr` with the same record as a crawl of the whole tree gives it

#### Scenario: A path inside a collapsed directory
- **WHEN** `crawl --path adhoc/project/.venv/lib` is run and `adhoc/project/.venv` is a Python environment
- **THEN** the exit status is 2, stderr names `/adhoc/project/.venv` as collapsed, and no run is recorded

#### Scenario: An excluded path
- **WHEN** the configuration excludes `/scratch/**` and `crawl --path scratch/tmp` is run
- **THEN** the exit status is 2 and stderr says that the path is excluded

#### Scenario: A symlink on the way
- **WHEN** `adhoc/link` is a symlink to `adhoc/real` and `crawl --path adhoc/link/session1` is run
- **THEN** the exit status is 2, stderr names `/adhoc/link` as a symlink, and no run is recorded

#### Scenario: A directory on the way that cannot be listed
- **WHEN** the crawler cannot list `adhoc/closed` and `crawl --path adhoc/closed/session1` is run
- **THEN** the exit status is 2, stderr names `/adhoc/closed` as not listable, and no run is recorded

### Requirement: A subtree crawl's path lies below the data root
A subtree crawl SHALL end with status 2, an error line naming the path and the reason, and no run recorded, when its path is not valid UTF-8, leaves the data root, is the data root itself (also through a file at the top level), or does not exist below the data root; the error for a path that does not exist SHALL name the data root it is relative to.

#### Scenario: A path outside the data root
- **WHEN** `crawl --path ../etc` or `crawl --path adhoc/nosuch` is run
- **THEN** the exit status is 2 and stderr names the path

#### Scenario: A path typed as the container's path
- **WHEN** the data root is `/data` and `crawl --path /data/adhoc/libertem` is run
- **THEN** the exit status is 2, and stderr names `/data/adhoc/libertem`, the data root `/data` and that the path is relative to it

#### Scenario: The data root as path
- **WHEN** `crawl --path /`, `crawl --path .`, or `crawl --path README.txt` for a file at the top level of the data root is run
- **THEN** the exit status is 2, stderr says that the data root is crawled by `crawl` without `--path`, and no run is recorded

#### Scenario: A path that is not UTF-8
- **WHEN** `crawl --path` is given the bytes `adhoc/caf\xe9` (Latin-1), naming an existing directory
- **THEN** the exit status is 2, stderr names the path with its escape, no traceback is printed, and no run is recorded

### Requirement: A subtree crawl uses the data root of the full crawls
When a crawl of the whole tree has finished on the index, a subtree crawl under another data root SHALL end with status 2, an error line naming both data roots, and no run recorded, so that its datasets cannot get other anchors and identifiers.

#### Scenario: Another data root
- **WHEN** the whole tree was crawled with the data root `/data`, and `crawl --root /data/adhoc --path libertem` is run
- **THEN** the exit status is 2, stderr names both data roots, and no run is recorded

### Requirement: A subtree crawl fails when its path cannot be listed
When its path cannot be listed as the walk reaches it, a subtree crawl SHALL fail as a crawl of the whole tree does when its root cannot be read: exit status 2, an error line naming the path, the run recorded as `failed`, and no dataset, stored listing or record changed.

#### Scenario: The path cannot be listed when the walk reaches it
- **WHEN** a tree with records under `adhoc/libertem/libertem-test-data` is crawled, and `crawl --path adhoc/libertem/libertem-test-data` is run while listing that directory fails after the path checks
- **THEN** the exit status is 2, stderr says that `/adhoc/libertem/libertem-test-data` cannot be read, the run is `failed`, and every record under the path is still there, datestamps included

### Requirement: A subtree crawl shares the crawl lock and stops on SIGTERM
A subtree crawl SHALL take the crawl lock as a crawl of the whole tree does, so that neither starts while the other runs, and on SIGTERM it SHALL end as a crawl of the whole tree does, without a change to the records.

#### Scenario: A subtree crawl while the timer's crawl runs
- **WHEN** `crawl --path adhoc/libertem/libertem-test-data` is started while a crawl of the whole tree runs
- **THEN** it exits with status 1 and `another crawl is running on this database`, and no run is recorded

#### Scenario: A subtree crawl stopped while it extracts
- **WHEN** a subtree crawl gets SIGTERM during its extraction
- **THEN** its run is `failed` with `terminated (SIGTERM)`, the exit status is 143, and no record changed
