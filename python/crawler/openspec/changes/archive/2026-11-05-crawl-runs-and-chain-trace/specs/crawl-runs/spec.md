# Spec Delta

## Purpose

Recording every crawl as a run, with its start, end, outcome, counts and progress, so that people and tools can tell what was crawled when, whether a crawl is running and how far it is.

## ADDED Requirements

### Requirement: Every crawl is recorded as a run
The crawl SHALL record a run in the index before it starts walking, with the time it started and the data root, and SHALL record when it ends the end time, the outcome `finished`, and the numbers of datasets, warnings and changed records. The start time SHALL be taken before the first directory is listed.

#### Scenario: A finished crawl
- **WHEN** `modama-crawler crawl` walks a test tree with three files and ends normally
- **THEN** the index holds one run with outcome `finished`, a start time before the earliest record datestamp it wrote, an end time not before its latest record datestamp, and the counts the crawl logged

#### Scenario: An unchanged crawl leaves a run
- **WHEN** the same tree is crawled a second time without changes
- **THEN** a second run with outcome `finished` and zero changed records is recorded, although no record datestamp moved

### Requirement: A failed crawl is recorded as failed
When the crawl stops on an error after its run was recorded, it SHALL record the outcome `failed`, the end time and the error message, and SHALL still exit with a non-zero status.

#### Scenario: The root disappears
- **WHEN** the data root cannot be listed after the run was recorded
- **THEN** the run has outcome `failed` with the error message, and no record was changed

### Requirement: A running crawl reports progress
While the walk runs, the crawl SHALL update its run at least once a minute with the number of directories and files seen so far and the time of the update, and SHALL log the same numbers at info level on stderr at most once a minute.

#### Scenario: Progress of a slow walk
- **WHEN** a crawl's walk takes longer than one minute
- **THEN** its run shows growing numbers of directories and files and an update time less than a minute old while it runs, and stderr carries a progress line per minute

### Requirement: A killed crawl does not look finished
A run without an end time SHALL be shown as running only while its last update is recent; when the last update is older than twice the update interval, it SHALL be shown as stale, with the time of its last update.

#### Scenario: A crawl killed during the walk
- **WHEN** a crawl is killed with SIGKILL during its walk and `modama-crawler runs` is run three minutes later
- **THEN** the run is shown as stale since its last update, not as running and not as finished

### Requirement: The runs command shows recent runs
`modama-crawler runs` SHALL print the most recent runs, newest first, one per line on stdout: start, end or state, outcome, counts, and progress for a running crawl. Diagnostics SHALL go to stderr; a closed output pipe and Ctrl-C SHALL end the command without a traceback.

#### Scenario: No crawl yet
- **WHEN** `modama-crawler runs` is run against an index without runs
- **THEN** it prints a line saying that no crawl has run and exits with status 0

#### Scenario: Piped into head
- **WHEN** `modama-crawler runs | head -1` is run with several runs recorded
- **THEN** one line is printed and the command exits without a traceback

### Requirement: The runs command follows a running crawl
`modama-crawler runs --follow` SHALL repeat the output of the running crawl's progress until it ends and then print its final line. When no crawl is running it SHALL print the latest run's line; when the followed run turns stale it SHALL end with status 1.

#### Scenario: Following a crawl
- **WHEN** `modama-crawler runs --follow` is started while a crawl runs
- **THEN** it prints progress lines until the crawl ends, then the finished run's line, and exits with status 0

### Requirement: One crawl at a time
A crawl SHALL refuse to start, with an error line naming the latest run and a non-zero exit status, while another crawl runs against the same index; it SHALL record no run then. A crawl that ended in any way, including a crash, SHALL not keep another from starting.

#### Scenario: A second crawl is refused
- **WHEN** a crawl is started while another one runs against the same index
- **THEN** it exits with status 1 and "another crawl is running on this database" on stderr, and no run is recorded

#### Scenario: A crashed crawl leaves no lock
- **WHEN** the crawler holding the lock is killed with SIGKILL
- **THEN** the next crawl starts
