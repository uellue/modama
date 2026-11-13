# Spec Delta

## MODIFIED Requirements

### Requirement: Entries that cannot make a useful record are skipped and logged
The crawl SHALL skip symlinks, special files, files the file system refuses to open (`EACCES`, `EPERM`) and directories the file system refuses to list or says are gone (`EACCES`, `EPERM`, `ENOENT`, `ENOTDIR`), with an info line naming the entry and the reason, and SHALL continue with the rest of the tree; a skipped entry gets no record. Names it cannot store SHALL be reported as warnings. The root itself not being readable SHALL be an error, whatever the error. Other errors of the file system below the crawl's start are covered by the requirements on what the file system did not answer.

#### Scenario: Permission denied
- **WHEN** a subdirectory cannot be listed with `EACCES`, or a file cannot be opened with `EACCES`
- **THEN** it gets no record, an info line names it, and the rest of the tree is recognised

#### Scenario: Access says no, and open says why
- **WHEN** `access(2)` says a file is not readable, and opening it fails with `EACCES`
- **THEN** the file is skipped as not readable

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
When listing a folder below the crawl's start, its own stat after the listing, or a format's read in its pre-order call fails with an error other than `EACCES`, `EPERM`, `ENOENT` and `ENOTDIR` (for example `EIO`, `ESTALE`, `ETIMEDOUT`, or no errno), the crawl SHALL keep the stored datasets of that folder and of every folder below it, with their members, extractions and records unchanged, datestamps included, SHALL NOT enter the folder, and SHALL go on with the rest of the tree.

#### Scenario: A stale file handle
- **WHEN** a tree with the datasets `adhoc/lib/test-data/dm/a.stand` and `…/b.stand` and the dataset `other/c.stand` is crawled, `other/d.stand` is added, and in the next crawl listing `adhoc/lib/test-data/dm` fails with `ESTALE`
- **THEN** the records of `a.stand` and `b.stand` are unchanged, datestamps included, and `other/d.stand` has a record

#### Scenario: An I/O error
- **WHEN** the same tree is crawled, and in the next crawl listing `adhoc/lib/test-data/dm` fails with `EIO`
- **THEN** the records of `a.stand` and `b.stand` are unchanged, datestamps included

#### Scenario: An errno nobody listed
- **WHEN** the same tree is crawled, and in the next crawl listing `adhoc/lib/test-data/dm` fails with `ENOMEM`
- **THEN** the records of `a.stand` and `b.stand` are unchanged

#### Scenario: Folders below the one that did not answer
- **WHEN** a tree with the datasets `adhoc/lib/test-data/notes.stand` and `adhoc/lib/test-data/dm/a.stand` is crawled, and in the next crawl listing `adhoc/lib/test-data` fails with `EIO`
- **THEN** both records are unchanged, and `adhoc/lib/test-data/dm` is not listed

#### Scenario: The folder's own stat does not answer
- **WHEN** the same tree is crawled, and in the next crawl the stat of `adhoc/lib/test-data/dm` after its listing fails with `EIO`
- **THEN** the records of `a.stand` and `b.stand` are unchanged and the crawl finishes

#### Scenario: A collapsed folder that did not answer
- **WHEN** a tree with the Zarr store `adhoc/z.zarr`, stored as one collapsed dataset, is crawled, and in the next crawl listing `adhoc/z.zarr` fails with `EIO`
- **THEN** its record is unchanged and nothing below it is listed

#### Scenario: A pre-order read that did not answer
- **WHEN** the same tree is crawled, and in the next crawl reading the store's marker file `adhoc/z.zarr/.zgroup` fails with `EIO`
- **THEN** the store's collapsed dataset and record are unchanged, and nothing below `adhoc/z.zarr` is listed

#### Scenario: A lower-priority format would collapse the folder
- **WHEN** a folder that a test format collapses after reading a marker is crawled, and in the next crawl that read fails with `EIO` while a test format of lower priority collapses the folder from its listing alone
- **THEN** the folder's stored dataset and record are unchanged

#### Scenario: A folder below the path of a subtree crawl
- **WHEN** a tree with records under `adhoc/lib/test-data/dm` is crawled, and `crawl --path adhoc/lib/test-data` is run while listing `adhoc/lib/test-data/dm` fails with `ESTALE`
- **THEN** the records of `a.stand` and `b.stand` are unchanged, datestamps included

#### Scenario: A changed rule set
- **WHEN** a tree is crawled, the rule set changes while the stand-in format stays enabled, and in the next crawl listing `adhoc/lib/test-data/dm` fails with `EIO`
- **THEN** the records of `a.stand` and `b.stand` are unchanged

### Requirement: A file the file system did not answer keeps its folder's records
When an entry's stat or a file's `access(2)` and the `open(2)` that asks again, the MIME detection of a file, or a format's read of a file fails with an error other than `EACCES`, `EPERM`, `ENOENT` and `ENOTDIR`, also when the format catches the error itself, the crawl SHALL keep the stored datasets of that file's folder and, for an entry, the stored datasets below it, unchanged, SHALL store its other subfolders' results of this crawl, and SHALL store no listing for the folder.

#### Scenario: The stat of an entry does not answer
- **WHEN** a tree with the datasets `adhoc/x/a.stand`, `adhoc/x/b.stand` and `adhoc/x/sub/c.stand` is crawled, `adhoc/x/sub/d.stand` is added, and in the next crawl the stat of `adhoc/x/b.stand` fails with `EIO`
- **THEN** the records of `a.stand`, `b.stand` and `c.stand` are unchanged, and `sub/d.stand` has a record

#### Scenario: A subfolder's stat does not answer
- **WHEN** the same tree is crawled, and in the next crawl the stat of `adhoc/x/sub` fails with `EIO`
- **THEN** the records of `a.stand`, `b.stand` and `sub/c.stand` are unchanged

#### Scenario: Access does not answer
- **WHEN** the same tree is crawled, and in the next crawl `access(2)` says `adhoc/x/b.stand` is not readable and opening it fails with `EIO`
- **THEN** the record of `b.stand` is unchanged

#### Scenario: A file whose type cannot be read
- **WHEN** a tree with the dataset `adhoc/x/a.stand`, the single file `adhoc/x/notes` (typed by its content) and `adhoc/x/sub/c.stand` is crawled, `adhoc/x/sub/d.stand` is added, and in the next crawl reading `adhoc/x/notes` for its type fails with `EIO`
- **THEN** the records of `a.stand` and `notes` are unchanged, datestamps included, `sub/d.stand` has a record, and no listing is stored for `/adhoc/x`

#### Scenario: A format that catches the read error itself
- **WHEN** a folder with a header `scan.head` naming its raw file `scan.raw`, one dataset of a test format that reads the header and catches every read error as the EMPAD format does, is crawled, and in the next crawl reading `scan.head` fails with `ESTALE`
- **THEN** that dataset and its record are unchanged, and no single-file records of `scan.head` or `scan.raw` appear

#### Scenario: A file that is gone during detection
- **WHEN** reading a file for its type fails with `ENOENT`
- **THEN** the file gets the type its name gives, or `application/octet-stream`, with a warning `cannot read` naming the error, and its folder is recognised again on the next crawl

#### Scenario: The walk's result is unchanged
- **WHEN** `modama-crawler records --verbose` is run on a folder where reading `notes.tags` for its new type fails with `EIO`
- **THEN** it shows the result that `recognition` requires ("A read error on one file leaves the rest of the result"): `notes.tags` keeps its type, with a warning naming the error

### Requirement: A kept folder is tried again by the next crawl
The crawl SHALL count neither a folder it kept because the file system did not answer nor any folder above it as unchanged, and SHALL store no listing for the kept folder or any folder below it, so that the next crawl lists and recognises them again.

#### Scenario: No listing is stored
- **WHEN** a crawl keeps `adhoc/lib/test-data/dm` because its listing failed with `ESTALE`
- **THEN** no listing is stored for `/adhoc/lib/test-data/dm`, and `/adhoc/lib/test-data`, `/adhoc/lib`, `/adhoc` and `/` are not counted as unchanged

#### Scenario: The next crawl tries again
- **WHEN** a crawl kept `adhoc/lib/test-data/dm` because its listing failed with `ESTALE`, `c.stand` was added there meanwhile, and the next crawl lists it
- **THEN** that crawl recognises the folder again, `c.stand` has a record, the records of `a.stand` and `b.stand` are unchanged, and that crawl finishes without errors

#### Scenario: Two crawls in a row that are not answered
- **WHEN** listing `adhoc/lib/test-data/dm` fails with `ESTALE` in two crawls in a row
- **THEN** after both, the records of `a.stand` and `b.stand` are unchanged, datestamps included

### Requirement: Kept datasets are not extracted again
The crawl SHALL keep the stored extraction of a dataset it kept because the file system did not answer, without running its extractor, also under another extractor identity, after a stored failure, or when its format has no extractor any more, SHALL NOT spot-check it, and SHALL NOT count its stored failure as a failed extraction.

#### Scenario: A kept dataset under a new identity
- **WHEN** a tree with the datasets `adhoc/lib/test-data/dm/a.stand` and `…/b.stand` is crawled, the installation's identity changes, and in the next crawl listing `adhoc/lib/test-data/dm` fails with `ESTALE`
- **THEN** the extractor is not called for `a.stand` or `b.stand`, and their stored extractions and records are unchanged

#### Scenario: A kept dataset whose extraction failed
- **WHEN** `adhoc/lib/test-data/dm/a.stand` holds `raise`, the tree is crawled, and in the next crawl listing `adhoc/lib/test-data/dm` fails with `ESTALE`
- **THEN** the extractor is not called for `a.stand`, and that crawl counts no failed extraction and warns about none

### Requirement: A refused folder that had datasets is named
When listing a folder below the crawl's start fails with `EACCES` or `EPERM` and the index holds datasets at or below it, the crawl SHALL remove them as for any skipped folder, SHALL log a warning naming the folder, the error and the number of datasets removed, and SHALL exit with status 0 when nothing else went wrong.

#### Scenario: A group that the crawler lost
- **WHEN** a tree with the datasets `groups/x/a.stand` and `groups/x/b.stand` is crawled, and in the next crawl listing `groups/x` fails with `EACCES`
- **THEN** their records are gone, stderr has a warning naming `/groups/x`, `EACCES` and 2 datasets removed, and the exit status is 0

#### Scenario: A folder that was refused before
- **WHEN** listing `groups/x` fails with `EACCES` in two crawls in a row
- **THEN** the second crawl logs no warning about it
