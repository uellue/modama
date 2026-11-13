# chain-trace Specification

## Purpose

Following one path through every stage of the search chain (file tree, crawler, OAI-PMH, harvest, warehouse, OpenSearch, search) and stating how fresh the search is, so that an admin or an agent finds the first stage where an item went wrong with one command instead of four clients.

## Requirements

### Requirement: A trace shows every stage of one path
`modama-chain trace PATH`, with PATH relative to the data root, SHALL print on stdout one line per stage, in the order tree, crawler, OAI-PMH, harvest, warehouse, index, search. Each line SHALL name the stage, its state, the key under which the stage holds the item, and the stage's time for it (mtime and ctime in the tree, datestamp in the crawler and OAI-PMH, the harvest run's window, the warehouse record's sync time, the search rank).

#### Scenario: A file found everywhere
- **WHEN** a file of the e2e tree has been crawled, harvested and indexed, and its path is traced
- **THEN** every stage shows `ok` with its key (path, OAI identifier, the identifier as the warehouse keeps it, the URL as the index keeps it) and the search line shows rank 1, and the command exits with status 0

### Requirement: Each stage has one state
A stage's state SHALL be `ok`; `missing`; `differs` when the stage holds another version of the item than the stage before; `warn` for a search rank below 1; or one of the flags below.

#### Scenario: A version not harvested yet
- **WHEN** a record changed in the crawler after the harvest that took its earlier version, and no harvest has run since
- **THEN** the harvest line shows `differs`

### Requirement: A member is traced through its dataset
When PATH has no record of its own but is a member of a dataset, or lies inside a collapsed directory (whose contents the crawler doesn't list), the trace SHALL say which dataset holds it and SHALL trace that dataset from the crawler stage on.

#### Scenario: The raw file of an EMPAD pair
- **WHEN** the raw file of the e2e tree's EMPAD pair is traced
- **THEN** the crawler line names the XML header's dataset as the one holding it, and the following lines trace that dataset

#### Scenario: A file inside a collapsed environment
- **WHEN** a file inside the e2e tree's Python environment (`/env/env/pyvenv.cfg`) is traced
- **THEN** the crawler line reads `member of /env/env; basis: contains pyvenv.cfg`, and the following lines trace the environment's dataset (@weber, 248, 2026-11-13: on staging the trace said `missing` for a file in a conda install)

### Requirement: The first diverging stage is marked
The trace SHALL mark the first stage at which the item is missing or differs from the stage before it.

#### Scenario: A record missing from the harvest
- **WHEN** a record is published by the crawler and has no harvest event
- **THEN** the harvest line is the first one not `ok`, and the lines after it are `missing`

### Requirement: A record dated before the harvest window is flagged
The trace SHALL flag the harvest stage as `before-harvest-window` when the crawler publishes the record, no closed harvest run has an event for its current version, and its datestamp is before the `until` of the endpoint's last closed harvest run, cut to the second as the harvester sends it: the next incremental harvest starts there, so no harvest will take the record.

#### Scenario: A record dated before the harvest window
- **WHEN** a record's datestamp in the crawler is set before the end of the last harvest run, and the next incremental harvest has run
- **THEN** the trace of its path shows the crawler and OAI-PMH as `ok`, the harvest as `before-harvest-window` with both times, and the later stages as `missing`

### Requirement: A synced record without an index document is flagged
The trace SHALL flag the index stage as `synced-without-document` when the warehouse marks the record as synced and the index has no document for its URL.

#### Scenario: A lost index document
- **WHEN** the index document of a harvested and indexed record is deleted directly in OpenSearch
- **THEN** the trace shows the warehouse as `ok` and the index as `synced-without-document`

### Requirement: Entries the crawler no longer publishes are flagged
The trace SHALL flag a downstream stage as `stale` when it holds the item while the crawler no longer publishes it.

#### Scenario: A renamed file
- **WHEN** a file is renamed, and the chain has crawled and harvested since
- **THEN** the trace of the old path shows the tree and crawler as `missing` and the warehouse and index as `stale`

### Requirement: A dataset that is not the first hit is a warning
The search stage SHALL query the search API with the dataset's path and SHALL report the dataset's rank among the hits: rank 1 is `ok`, a lower rank is a warning that does not change the exit status, and absence from the hits is `missing`.

#### Scenario: Rank below 1
- **WHEN** the dataset of a traced path is among the hits of its path query but not the first
- **THEN** the search line shows its rank and the first hit's URL as a warning, and the exit status is as if the search were `ok`

### Requirement: The trace's exit status says whether the chain is consistent
The trace SHALL exit with status 0 when no stage is flagged or missing after the first stage that has the item, with status 1 when one is, and with status 2 when a store cannot be reached, naming the store on stderr.

#### Scenario: The warehouse database is down
- **WHEN** the warehouse database is stopped and a path is traced
- **THEN** the stages before the harvest are shown, stderr names the warehouse database as unreachable, and the exit status is 2

### Requirement: The status states the freshness time
`modama-chain status` SHALL print one line per stage (crawl, harvest, indexing) with its last run, outcome and time, and a last line with the freshness time T: the start of the most recent finished crawl run that ended before the `until` of a closed harvest run of the crawler's endpoint, where that harvest run and every closed run before it were followed by a successful indexing run. When no crawl qualifies, the last line SHALL say so and name the stage that is missing.

#### Scenario: A complete chain
- **WHEN** a crawl finished, a harvest closed after its end, and the indexing run triggered by that harvest succeeded
- **THEN** the status shows each run as `ok` and T equal to the start of that crawl

#### Scenario: A crawl that is not harvested yet
- **WHEN** a second crawl finished after the last harvest
- **THEN** T stays at the start of the first crawl, and the harvest line says that the latest crawl is not harvested yet

#### Scenario: A failed harvest
- **WHEN** the last harvest run of the endpoint failed
- **THEN** the harvest line shows it as failed with its time, and T is taken from the runs before it

### Requirement: The chain tool only reads
`modama-chain` SHALL NOT write to the data tree, the crawler's database, the warehouse's database, the index, or Airflow, and SHALL NOT trigger anything. It SHALL take every address and credential from its environment, not from its code.

#### Scenario: Read-only accounts suffice
- **WHEN** the chain tool runs with a read-only warehouse database account and an Airflow account in the Viewer role
- **THEN** `trace` and `status` produce their full output
