# Spec Delta

## MODIFIED Requirements

### Requirement: Unchanged directories are not recognised or extracted again
A crawl SHALL take over the stored datasets of a directory without reading file contents for recognition and without recognising, when the directory's listing (names, types, sizes, mtimes, ctimes) and those of all directories below it are unchanged since the last finished crawl and the enabled formats, their versions and the selection are unchanged. The stored extractions of the datasets taken over SHALL be checked like any other (requirement "Extraction follows the identified extractor"): a failed one, or one under another identity, is extracted again, and a sample is spot-checked (requirement "Each crawl spot-checks a sample of what it reuses"). Every directory SHALL still be listed, so that a change at any depth is seen. A directory whose recognition met a read error or a format's time limit SHALL NOT be taken over: the next crawl recognises it again. A directory the crawler cannot list SHALL count as unchanged when it could not be listed by the last crawl either and its entry in its parent's listing is unchanged.

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
Each dataset SHALL record which extractor (its format id) and which extractor identity produced its metadata. A stored successful extraction SHALL be reused while the dataset is recognised with the same extractor, its stored identity equals the identity of the running crawl, and its members' sizes and times are unchanged; otherwise the dataset SHALL be extracted again. Identities SHALL be compared for equality only, never ordered. A stored failure SHALL NOT be reused, whatever its cause (the file's content, the memory or time limit, a dead worker process, an operating system error, a missing module): every crawl runs the extractor on it again.

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

## ADDED Requirements

### Requirement: The extractor identity is derived from the installation
Each crawl SHALL compute one extractor identity at its start, a digest of the Python version, the name and version of every installed distribution, and the source files, apart from tests, of: the distributions that provide formats; those installed from a path or a repository; and every top-level package imported from outside site-packages and the standard library. No person sets it. The same installation SHALL give the same identity, wherever it is installed.

#### Scenario: The same installation in two places
- **WHEN** the identity is computed for two installations of the same distributions and the same source, at two different paths
- **THEN** the two identities are equal

#### Scenario: A test file does not count
- **WHEN** a fixture or a test module below a format package's `tests` directory changes
- **THEN** the identity stays the same

#### Scenario: A dependency installed from a repository
- **WHEN** a source file changes in a distribution installed from a local path or a repository, and its version stays the same
- **THEN** the identity changes

#### Scenario: A package on PYTHONPATH shadows an installed one
- **WHEN** a directory on `PYTHONPATH` holds a package with the import name of an installed distribution, and a file of that package changes
- **THEN** the identity changes, although the installed distribution's version is the same

#### Scenario: A stale egg-info ahead of the real metadata
- **WHEN** the working directory holds a stale `*.egg-info` of a distribution installed from a path, found before its real metadata, and a source file of that distribution changes
- **THEN** the identity changes

### Requirement: Settings and numerical noise are not part of the identity
Settings that decide only whether an extraction fails or how fast it runs (the memory and time limits, the number of extraction processes, thread counts) SHALL NOT be ingredients of the extractor identity, and neither SHALL any influence whose only effect is insignificant numerical noise in the last digits of a number.

#### Scenario: A changed limit does not count
- **WHEN** the memory limit or the number of extraction processes changes between two crawls
- **THEN** the identity stays the same

### Requirement: A path install without source is named
When a distribution is installed from a path, an archive or a repository and none of its source files is found for the identity, the crawl's report and log SHALL carry a warning naming the distribution.

#### Scenario: A distribution installed from a path without source found
- **WHEN** a distribution's `direct_url.json` names a local path and none of its import packages is found
- **THEN** the crawl's report and log carry a warning naming the distribution

### Requirement: The crawl reports re-extraction and its cause
The crawl's report SHALL state, per format, how many datasets were extracted again only because the identity changed, what differs between their stored identity and the current one (a distribution's version, a module's source, the Python version, or that the stored identity's ingredients are unknown), and how many of their extraction results differ from the stored ones. A finished crawl SHALL store these counts with its run, and `modama-crawler runs` SHALL show them on the run's line.

#### Scenario: A dependency upgrade that changes output
- **WHEN** a tree with two DM4 files is crawled, RosettaSciIO's installed version changes so that one file's result differs, and the tree is crawled again
- **THEN** the second report has the line `em/dm4: 2 extracted again for a new identity (rosettasciio 0.15.0 -> 0.16.0), 1 result changed`, and `runs` shows the same counts for that run

#### Scenario: A refactoring that changes no output
- **WHEN** only a comment changes in `modama_formats_em/dm/__init__.py` between two crawls of the same tree
- **THEN** the second report has the line `em/dm4: 2 extracted again for a new identity (source of modama_formats_em.dm changed), 0 results changed`

#### Scenario: A change in building records only
- **WHEN** only the description template in `modama_crawler/records.py` changes between two crawls of the same tree
- **THEN** the second report has the line `em/dm4: 2 extracted again for a new identity (source of modama_crawler.records changed), 0 results changed`, although both records get a new datestamp

#### Scenario: An identity from before this change
- **WHEN** the stored extractions carry a version label from before this change (`"4"`) and the tree is crawled
- **THEN** the report says `em/dm4: 2 extracted again for a new identity (earlier identity "4", ingredients unknown), 0 results changed` when the output is the same

### Requirement: The crawl reports failures tried again
The crawl's report SHALL state, per format, how many datasets whose stored extraction had failed were extracted again, and how many of those now succeed.

#### Scenario: Failures tried again
- **WHEN** one of two DM4 files failed under a memory limit that has since been raised, and the tree is crawled again
- **THEN** the report has the line `em/dm4: 1 tried again after a failure, 1 now succeeds`

### Requirement: Each crawl spot-checks a sample of what it reuses
Each crawl SHALL extract again a random sample of the datasets whose stored successful extraction it reuses, 20 per format with an extractor or all when there are fewer, and compare each new result with the stored one. The sample SHALL be drawn anew in every crawl from a seed that the report, the log and the run name; the same seed over the same stored datasets SHALL give the same sample. The spot check's extractions SHALL NOT be counted as run or reused.

#### Scenario: Everything as stored
- **WHEN** a tree with two DM4 files is crawled twice without changes and with the same installation
- **THEN** the second report has the line `spot check (seed <16 hexadecimal digits>): em/dm4 2 of 2 as stored`, and no record gets a new datestamp

#### Scenario: The same seed gives the same sample
- **WHEN** the sample is drawn twice with the same seed over the same 30 stored DM4 datasets
- **THEN** both draws pick the same 20 datasets

#### Scenario: Nothing reused
- **WHEN** a crawl extracts every dataset again because the identity changed
- **THEN** the report says `spot check: nothing reused`

### Requirement: A spot-check difference is reported, not spread
The report SHALL state per format how many datasets the spot check compared and how many are as stored, and name each that differs with the fields that differ; the log SHALL give the stored and new value. A difference SHALL NOT cause any other dataset to be extracted again. A new success SHALL replace the stored result; a new failure SHALL NOT, and SHALL count as a difference. The run SHALL keep the outcome; `runs` SHALL show the number of differences, if any.

#### Scenario: A difference the identity missed
- **WHEN** a tree holds 30 DM4 files, the stored result of each is altered in the database between two crawls (standing in for an influence outside the identity), and the tree is crawled again
- **THEN** the report says `em/dm4 0 of 20 as stored`, names five of the files with the field that differs and `and 15 more`, those 20 records carry the new results, the other 10 datasets are not extracted, and `runs` shows `spot check: 20 differ` for that run

#### Scenario: A new failure does not replace a stored success
- **WHEN** a sampled dataset's extraction now fails
- **THEN** the report names it as differing (`now fails`), and its stored result and record stay as they were
