# Spec Delta

## MODIFIED Requirements

### Requirement: Every crawl is recorded as a run
The crawl SHALL record a run in the index before it starts walking, with the time it started, the data root, the configuration it runs with (the file's name, the selection, the per-path ignores and the exclusions) and, for a subtree crawl, its path, and SHALL record when it ends the end time, the outcome `finished`, and the numbers of datasets, warnings and changed records. The start time SHALL be taken before the walk lists its first directory; a subtree crawl's checks of the directories down to its path come before it.

#### Scenario: A finished crawl
- **WHEN** `modama-crawler crawl` walks a test tree with three files and ends normally
- **THEN** the index holds one run with outcome `finished`, a start time before the earliest record datestamp it wrote, an end time not before its latest record datestamp, and the counts the crawl logged

#### Scenario: An unchanged crawl leaves a run
- **WHEN** the same tree is crawled a second time without changes
- **THEN** a second run with outcome `finished` and zero changed records is recorded, although no record datestamp moved

#### Scenario: A subtree crawl records its path
- **WHEN** `modama-crawler crawl --path /adhoc/libertem/libertem-test-data` ends normally
- **THEN** its run holds the data root and the path `/adhoc/libertem/libertem-test-data`, in the form of the anchors, and a crawl of the whole tree holds no path

#### Scenario: A run records its configuration
- **WHEN** `modama-crawler --config full.toml crawl` ends normally, `full.toml` excluding `.snapshot/`
- **THEN** its run holds the name `full.toml`, the selection, the per-path ignores and the exclusion `.snapshot/`

### Requirement: The runs command shows recent runs
`modama-crawler runs` SHALL print the most recent runs, newest first, one per line on stdout: start, end or state, outcome, counts, progress for a running crawl, and the path of a subtree crawl after the data root, as a canonical path (without a leading `/`). Diagnostics SHALL go to stderr; a closed output pipe and Ctrl-C SHALL end the command without a traceback.

#### Scenario: No crawl yet
- **WHEN** `modama-crawler runs` is run against an index without runs
- **THEN** it prints a line saying that no crawl has run and exits with status 0

#### Scenario: Piped into head
- **WHEN** `modama-crawler runs | head -1` is run with several runs recorded
- **THEN** one line is printed and the command exits without a traceback

#### Scenario: A subtree crawl's line
- **WHEN** a subtree crawl of `adhoc/libertem/libertem-test-data` under the data root `/data` finished and `modama-crawler runs` is run
- **THEN** its line ends with `/data  adhoc/libertem/libertem-test-data`, and the line of a crawl of the whole tree ends with `/data`
