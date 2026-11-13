# Spec Delta

## ADDED Requirements

### Requirement: The status names the folders a crawl kept
When the crawl on `modama-chain status`'s crawl line recorded folders the file system did not answer, the line SHALL show the state `finished with errors` and the number of such folders, their number per errno and up to three of them; when the crawl that gives the freshness time T recorded such folders, the freshness line SHALL say that T does not hold for them and name up to three. Against a crawler database without these records, the lines SHALL stay as they are.

#### Scenario: A crawl with kept folders
- **WHEN** the latest crawl kept `/adhoc/a` after `EIO`, and the chain is otherwise complete for it
- **THEN** the crawl line shows `finished with errors` and `did not answer: 1 folder (EIO 1): /adhoc/a`, and the freshness line gives T and says `except in 1 folder kept by that crawl: /adhoc/a`

#### Scenario: An older crawler
- **WHEN** the crawler database has no record of kept folders
- **THEN** the crawl and freshness lines are as before
