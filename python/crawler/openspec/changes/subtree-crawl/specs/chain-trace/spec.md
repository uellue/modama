# Spec Delta

## MODIFIED Requirements

### Requirement: The status states the freshness time
`modama-chain status` SHALL print one line per stage (crawl, harvest, indexing) with its last run, outcome and time, and a last line with the freshness time T: the start of the most recent finished crawl run of the whole tree that ended before the `until` of a closed harvest run of the crawler's endpoint, where that harvest run and every closed run before it were followed by a successful indexing run. Subtree crawls SHALL NOT count for T. When no crawl qualifies, the last line SHALL say so and name the stage that is missing.

#### Scenario: A complete chain
- **WHEN** a crawl finished, a harvest closed after its end, and the indexing run triggered by that harvest succeeded
- **THEN** the status shows each run as `ok` and T equal to the start of that crawl

#### Scenario: A crawl that is not harvested yet
- **WHEN** a second crawl finished after the last harvest
- **THEN** T stays at the start of the first crawl, and the harvest line says that the latest crawl is not harvested yet

#### Scenario: A failed harvest
- **WHEN** the last harvest run of the endpoint failed
- **THEN** the harvest line shows it as failed with its time, and T is taken from the runs before it

#### Scenario: A subtree crawl does not move T
- **WHEN** a crawl of the whole tree finished, then a subtree crawl of `adhoc/libertem/libertem-test-data`, and the harvest and indexing after the subtree crawl succeeded
- **THEN** T is the start of the crawl of the whole tree, and the crawl line shows the subtree crawl with its path
