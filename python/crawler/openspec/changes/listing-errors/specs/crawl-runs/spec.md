# Spec Delta

## ADDED Requirements

### Requirement: The run records the folders the file system did not answer
When the crawl kept folders because the file system did not answer (spec `crawl`), it SHALL store its result and record its run with the outcome `finished` and the total number of such folders, their number per errno, and the first 100 of them in path order, each with the path that failed, the errno's name and the number of datasets kept. A run without such folders SHALL record none.

#### Scenario: The run records the folder
- **WHEN** a tree with the datasets `adhoc/lib/test-data/dm/a.stand` and `…/b.stand` is crawled, and the next crawl ends after listing `adhoc/lib/test-data/dm` failed with `ESTALE`
- **THEN** its run has outcome `finished` and records 1 folder, `ESTALE` 1, and the folder `/adhoc/lib/test-data/dm` with the path `/adhoc/lib/test-data/dm`, `ESTALE` and 2 datasets kept

#### Scenario: Not visible is no error
- **WHEN** a crawl skips a folder whose listing fails with `EACCES`
- **THEN** its run records no such folders and the exit status is 0

### Requirement: A crawl that finished with errors says so and exits with status 4
When the crawl kept folders because the file system did not answer, it SHALL log one error line per recorded folder naming the folder, the path that failed, the errno and the datasets kept, one summary line for the folders beyond the first 100, and a closing error line with the counts per errno, and SHALL exit with status 4.

#### Scenario: The error line and the status
- **WHEN** a tree with the datasets `adhoc/lib/test-data/dm/a.stand` and `…/b.stand` is crawled, and the next crawl ends after listing `adhoc/lib/test-data/dm` failed with `ESTALE`
- **THEN** stderr has an error line naming `/adhoc/lib/test-data/dm`, `ESTALE` and 2 datasets kept, and a closing error line with `ESTALE 1`, and the exit status is 4

#### Scenario: A file in recognition
- **WHEN** a crawl kept `adhoc/x` because reading `adhoc/x/notes` for its type failed with `EIO`
- **THEN** its run records the folder `/adhoc/x` with the path `/adhoc/x/notes` and `EIO`, and the exit status is 4

#### Scenario: More than 100 folders
- **WHEN** listing 150 sibling folders fails with `EIO` in one crawl
- **THEN** the run records the total 150, `EIO` 150 and the first 100 folders in path order; stderr has 100 error lines naming a folder and one line saying that 50 more folders did not answer, with `EIO` 50

#### Scenario: A subtree crawl
- **WHEN** `crawl --path adhoc/lib/test-data` is run while listing `adhoc/lib/test-data/dm` fails with `ESTALE`
- **THEN** its run has outcome `finished`, records the folder, and the exit status is 4

### Requirement: The runs command shows a crawl that finished with errors
`modama-crawler runs` SHALL show a run that recorded folders the file system did not answer with the state `finished with errors` instead of `finished`, and its line SHALL add the number of such folders, their number per errno and up to three of them, with the number of the others; it SHALL stay one line per run. Such a run SHALL count as finished for the timer's catch-up and for the comparison of a subtree crawl with the last crawl of the whole tree.

#### Scenario: The report line
- **WHEN** the latest run kept `/adhoc/a` and `/adhoc/b` after `EIO` and `/c/d` after `ESTALE`, and `modama-crawler runs | head -1` is run
- **THEN** the line has the state `finished with errors` and `did not answer: 3 folders (EIO 2, ESTALE 1): /adhoc/a, /adhoc/b, /c/d`

#### Scenario: Many folders on the line
- **WHEN** the latest run recorded 150 folders that did not answer
- **THEN** its line names three of them and `147 more`

#### Scenario: The timer counts it as finished
- **WHEN** the last crawl of the whole tree finished with errors an hour ago and the timer starts
- **THEN** it does not crawl at once, but waits for its time of day
