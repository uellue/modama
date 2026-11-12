# Spec Delta

## ADDED Requirements

### Requirement: The records summary names the extractor identity
When any enabled format has an extractor, the summary of `modama-crawler records` SHALL name the short form of the extractor identity it extracted with, the same form that `runs` and `modama-chain` show, so that its output can be matched to a crawl's.

#### Scenario: Records of a DM file
- **WHEN** `modama-crawler records --verbose` is run on a fixture holding a DM4 file
- **THEN** the summary names the identity, and it equals the one a crawl in the same installation records with its run
