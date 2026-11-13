# Spec Delta

## ADDED Requirements

### Requirement: The run records the folders the file system did not answer
When the crawl kept folders because the file system did not answer (spec `crawl`), it SHALL record its run as `finished` with the number of such folders and of datasets kept, their number per errno, and the first 100 folders in path order, each with the path that failed, the errno, the datasets kept, whether its subtree was kept, and since when and for how many crawls covering it it (or a folder above it, whole) was kept. A run without such folders SHALL record none.

#### Scenario: The run records the folder
- **WHEN** a tree with the datasets `adhoc/lib/test-data/dm/a.stand` and `…/b.stand` is crawled, and the next crawl ends after listing `adhoc/lib/test-data/dm` failed with `ESTALE`
- **THEN** its run has outcome `finished` and records 1 folder, 2 datasets kept, `ESTALE` 1, and the folder `/adhoc/lib/test-data/dm` with the path `/adhoc/lib/test-data/dm`, `ESTALE`, 2 datasets kept, its own start time and 1 crawl

#### Scenario: Kept for two crawls
- **WHEN** listing `adhoc/lib/test-data/dm` fails with `ESTALE` in two crawls in a row
- **THEN** the second run records the folder with the start time of the first and 2 crawls

#### Scenario: Kept below a folder kept before
- **WHEN** a crawl kept `adhoc/lib/test-data` whole, two subtree crawls of `other` follow, and the next crawl keeps `adhoc/lib/test-data/dm`
- **THEN** that run records `/adhoc/lib/test-data/dm` with the start time of the first crawl and 2 crawls

#### Scenario: A file in recognition
- **WHEN** a crawl kept `adhoc/x` because reading `adhoc/x/notes` for its type failed with `EIO`
- **THEN** its run records the folder `/adhoc/x` with the path `/adhoc/x/notes` and `EIO`

#### Scenario: The same record whatever the threads
- **WHEN** a tree in which listing 150 sibling folders fails with `EIO` is crawled once with 1 walk thread and once with 16
- **THEN** both runs record the same totals and the same first 100 folders

#### Scenario: Not visible is no error
- **WHEN** a crawl skips a folder whose listing fails with `EACCES`, which had no datasets
- **THEN** its run records no folders that did not answer, no refused folders, and the exit status is 0

### Requirement: The run records refused folders that had datasets
When the crawl removed datasets because listing a folder failed with `EACCES` or `EPERM`, it SHALL record in its run the number of such folders, the number of datasets removed, and the first 100 folders in path order with the errno's name and the datasets removed under each.

#### Scenario: A refused folder in the run
- **WHEN** a tree with the datasets `groups/x/a.stand` and `groups/x/b.stand` is crawled, and in the next crawl listing `groups/x` fails with `EACCES`
- **THEN** its run records 1 refused folder, 2 datasets removed, and `/groups/x` with `EACCES` and 2

### Requirement: A crawl that finished with errors says so and exits with status 4
When the crawl kept folders because the file system did not answer, it SHALL log one error line per recorded folder naming the folder, the path that failed, the errno, the datasets kept and the number of crawls, one summary line for the folders beyond the first 100, and a closing error line with the counts per errno, and SHALL exit with status 4.

#### Scenario: The error line and the status
- **WHEN** a tree with the datasets `adhoc/lib/test-data/dm/a.stand` and `…/b.stand` is crawled, and the next crawl ends after listing `adhoc/lib/test-data/dm` failed with `ESTALE`
- **THEN** stderr has an error line naming `/adhoc/lib/test-data/dm`, `ESTALE` and 2 datasets kept, and a closing error line with `ESTALE 1`, and the exit status is 4

#### Scenario: More than 100 folders
- **WHEN** listing 150 sibling folders fails with `EIO` in one crawl
- **THEN** stderr has 100 error lines naming a folder and one line saying that 50 more folders did not answer, with `EIO 50`, and the exit status is 4

#### Scenario: A subtree crawl
- **WHEN** `crawl --path adhoc/lib/test-data` is run while listing `adhoc/lib/test-data/dm` fails with `ESTALE`
- **THEN** its run has outcome `finished`, records the folder, and the exit status is 4

### Requirement: The runs command shows a crawl that finished with errors
`modama-crawler runs` SHALL show a run that recorded folders the file system did not answer with the state `finished with errors` instead of `finished`, with the same counts; the line SHALL add the folders' number, their number per errno and up to three of them, and the refused folders' number, datasets removed and up to three of them. It SHALL stay one line per run, the state column equally wide on every line. `runs --follow` SHALL end with status 4 after such a run.

#### Scenario: The report line
- **WHEN** the latest run kept `/adhoc/a` and `/adhoc/b` after `EIO` and `/c/d` after `ESTALE`, and `modama-crawler runs | head -1` is run
- **THEN** the line has the state `finished with errors`, the datasets and records counts, and `did not answer: 3 folders (EIO 2, ESTALE 1): /adhoc/a, /adhoc/b, /c/d`

#### Scenario: Many folders on the line
- **WHEN** the latest run recorded 150 folders that did not answer
- **THEN** its line names three of them and `and 147 more`

#### Scenario: Aligned columns
- **WHEN** `runs` prints a run that finished with errors and one that finished
- **THEN** the end time starts in the same column on both lines

#### Scenario: Following a crawl that finishes with errors
- **WHEN** `modama-crawler runs --follow` follows a crawl that finishes with errors
- **THEN** its last line shows `finished with errors` and it exits with status 4

### Requirement: A crawl that finished with errors counts as finished
A run that recorded folders the file system did not answer SHALL count as finished for the timer's catch-up and for the comparison of a subtree crawl with the last crawl of the whole tree.

#### Scenario: The timer counts it as finished
- **WHEN** the last crawl of the whole tree finished with errors an hour ago and the timer starts
- **THEN** it does not crawl at once

#### Scenario: A subtree crawl after a crawl with errors
- **WHEN** the last crawl of the whole tree finished with errors and `crawl --path adhoc/lib/test-data` is run with a configuration other than that crawl's
- **THEN** it is refused as after a crawl that finished, naming the configuration of that crawl
