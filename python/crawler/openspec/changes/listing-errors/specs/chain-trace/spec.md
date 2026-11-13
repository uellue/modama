# Spec Delta

## ADDED Requirements

### Requirement: The status names the folders a crawl kept
When the crawl on `modama-chain status`'s crawl line kept folders the file system did not answer, the line SHALL show the state `finished with errors`, the number of folders, their number per errno and up to three of them; when the crawl that gives the freshness time T kept folders, the freshness line SHALL say that T does not hold for them. The state column SHALL be as wide as `finished with errors`.

#### Scenario: A crawl with kept folders
- **WHEN** the latest crawl kept `/adhoc/a` after `EIO`, and the chain is otherwise complete for it
- **THEN** the crawl line shows `finished with errors` and `did not answer: 1 folder (EIO 1): /adhoc/a`, and the freshness line gives T and adds `except where that crawl kept the stored state: 1 folder (EIO 1): /adhoc/a`

#### Scenario: An older crawler
- **WHEN** the crawler database has no record of kept folders
- **THEN** the crawl and freshness lines show no kept folders, and the crawl line's `started` follows the state padded to the width of `finished with errors`
