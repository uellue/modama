# Spec Delta

## MODIFIED Requirements

### Requirement: Entries that cannot make a useful record are skipped and logged
The crawl SHALL skip symlinks, special files, files it cannot read and directories the file system says it may not list or that are gone (permission denied, `EACCES` or `EPERM`; not found, `ENOENT` or `ENOTDIR`), with an info line naming the entry and the reason, and SHALL continue with the rest of the tree; a skipped entry gets no record. Names it cannot store SHALL be reported as warnings. The root itself not being readable SHALL be an error, whatever the error. Any other error of the file system on a directory or file below the crawl's start is covered by "A folder the file system did not answer keeps its records".

#### Scenario: Permission denied
- **WHEN** a subdirectory cannot be listed with `EACCES`, or a file cannot be read
- **THEN** it gets no record, an info line names it, and the rest of the tree is recognised

#### Scenario: A folder that is gone
- **WHEN** a tree with records under `adhoc/lib/test-data/dm` is crawled, and in the next crawl listing `adhoc/lib/test-data/dm` fails with `ENOENT`
- **THEN** its records are gone, the run is `finished`, and the exit status is 0

#### Scenario: Symlink and FIFO
- **WHEN** a directory contains a symlink to a file and a named pipe
- **THEN** neither gets a record, each is named in an info line, and formats never see them

#### Scenario: The root cannot be read
- **WHEN** the path given to the crawl does not exist or cannot be listed
- **THEN** the crawl fails with an error naming the path

#### Scenario: The root does not answer
- **WHEN** a tree is crawled, and in the next crawl listing the data root fails with `EIO`
- **THEN** the crawl fails with exit status 2 and an error naming the root, its run is `failed`, and every record is still there, datestamps included

#### Scenario: A name that is not valid UTF-8
- **WHEN** an entry's name cannot be decoded as UTF-8
- **THEN** the entry is skipped with a warning naming its directory

## ADDED Requirements

### Requirement: A folder the file system did not answer keeps its records
When listing a folder below the crawl's start, its own stat, the stat of one of its entries, or a format's pre-order call fails with an error other than `EACCES`, `EPERM`, `ENOENT` and `ENOTDIR` (for example `EIO`, `ESTALE`, `ETIMEDOUT`, `ENOTCONN`, or no errno), the crawl SHALL keep the stored datasets of that folder and of every folder below it, with their members, extractions and records unchanged, datestamps included, SHALL NOT enter the folder, and SHALL go on with the rest of the tree.

#### Scenario: A stale file handle
- **WHEN** a tree with the datasets `adhoc/lib/test-data/dm/a.stand` and `…/b.stand` and the file `other/c.txt` is crawled, `other/d.txt` is added, and in the next crawl listing `adhoc/lib/test-data/dm` fails with `ESTALE`
- **THEN** the records of `a.stand` and `b.stand` are unchanged, datestamps included, and `other/d.txt` has a record

#### Scenario: An I/O error
- **WHEN** the same tree is crawled, and in the next crawl listing `adhoc/lib/test-data/dm` fails with `EIO`
- **THEN** the records of `a.stand` and `b.stand` are unchanged, datestamps included

#### Scenario: An errno nobody listed
- **WHEN** the same tree is crawled, and in the next crawl listing `adhoc/lib/test-data/dm` fails with `ENOMEM`
- **THEN** the records of `a.stand` and `b.stand` are unchanged

#### Scenario: Folders below the one that did not answer
- **WHEN** a tree with the datasets `adhoc/lib/a.stand` and `adhoc/lib/test-data/dm/b.stand` is crawled, and in the next crawl listing `adhoc/lib` fails with `EIO`
- **THEN** both records are unchanged, and `adhoc/lib/test-data` and `adhoc/lib/test-data/dm` are not listed

#### Scenario: The stat of an entry does not answer
- **WHEN** a tree with the datasets `adhoc/x/a.stand` and `adhoc/x/b.stand` is crawled, and in the next crawl the stat of `adhoc/x/b.stand` fails with `EIO`
- **THEN** both records are unchanged

#### Scenario: A collapsed folder that did not answer
- **WHEN** a tree with the Zarr store `adhoc/z.zarr`, stored as one collapsed dataset, is crawled, and in the next crawl listing `adhoc/z.zarr` fails with `EIO`
- **THEN** its record is unchanged and nothing below it is listed

#### Scenario: A pre-order call that did not answer
- **WHEN** a tree with a folder that a test format collapses after reading a marker file is crawled, and in the next crawl reading the marker fails with `EIO`
- **THEN** the folder's collapsed dataset and record are unchanged, and nothing below the folder is listed

#### Scenario: A folder below the path of a subtree crawl
- **WHEN** a tree with records under `adhoc/lib/test-data/dm` is crawled, and `crawl --path adhoc/lib/test-data` is run while listing `adhoc/lib/test-data/dm` fails with `ESTALE`
- **THEN** the records of `a.stand` and `b.stand` are unchanged, datestamps included

#### Scenario: A changed rule set
- **WHEN** a tree is crawled, the rule set changes, and in the next crawl listing `adhoc/lib/test-data/dm` fails with `EIO`
- **THEN** the records of `a.stand` and `b.stand` are unchanged

### Requirement: A kept folder is tried again by the next crawl
The crawl SHALL count neither a folder it kept because the file system did not answer nor any folder above it as unchanged, and SHALL store no listing for the kept folder or any folder below it, so that the next crawl lists and recognises them again.

#### Scenario: No listing is stored
- **WHEN** a crawl keeps `adhoc/lib/test-data/dm` because its listing failed with `ESTALE`
- **THEN** no listing is stored for `/adhoc/lib/test-data/dm` or below it, and `/adhoc/lib/test-data`, `/adhoc/lib`, `/adhoc` and `/` are not counted as unchanged

#### Scenario: The next crawl tries again
- **WHEN** a crawl kept `adhoc/lib/test-data/dm` because its listing failed with `ESTALE`, `c.stand` was added there meanwhile, and the next crawl lists it
- **THEN** that crawl recognises the folder again, `c.stand` has a record, the records of `a.stand` and `b.stand` are unchanged, and that crawl finishes without errors

### Requirement: Kept datasets are not extracted again
The crawl SHALL keep the stored extraction of a dataset it kept because the file system did not answer, without running its extractor, also under another extractor identity or after a stored failure, and SHALL NOT spot-check it.

#### Scenario: A kept dataset under a new identity
- **WHEN** a tree with the datasets `adhoc/lib/test-data/dm/a.stand` and `…/b.stand` is crawled, the installation's identity changes, and in the next crawl listing `adhoc/lib/test-data/dm` fails with `ESTALE`
- **THEN** the extractor is not called for `a.stand` or `b.stand`, and their stored extractions and records are unchanged

### Requirement: A file the file system did not answer keeps its folder's records
When MIME detection, a format's check of a file's content, or a format's post-order call fails on a file with an error other than `EACCES`, `EPERM`, `ENOENT` and `ENOTDIR`, the crawl SHALL keep the stored datasets of that file's folder, with their members, extractions and records unchanged, SHALL keep its subfolders' results of this crawl, and SHALL store no listing for the folder.

#### Scenario: The walk's result is unchanged
- **WHEN** `modama-crawler records --verbose` is run on a folder where reading `notes.tags` for its new type fails with `EIO`
- **THEN** it shows the result that `recognition` requires ("A read error on one file leaves the rest of the result"): `notes.tags` keeps its type, with a warning naming the error

#### Scenario: A file whose type cannot be read
- **WHEN** a tree with the datasets `adhoc/x/a.stand` and the single file `adhoc/x/notes` (typed by its content) and `adhoc/x/sub/c.stand` is crawled, `adhoc/x/sub/d.stand` is added, and in the next crawl reading `adhoc/x/notes` for its type fails with `EIO`
- **THEN** the records of `a.stand` and `notes` are unchanged, datestamps included, `sub/d.stand` has a record, and no listing is stored for `/adhoc/x`

#### Scenario: A format's read that did not answer
- **WHEN** a tree with a folder that a test format makes one dataset of after reading one of its files is crawled, and in the next crawl that read fails with `ESTALE`
- **THEN** the folder's dataset and record are unchanged

#### Scenario: A file that is gone during recognition
- **WHEN** reading a file for its type fails with `ENOENT`
- **THEN** the crawl stores the walk's result for its folder, as before this change
