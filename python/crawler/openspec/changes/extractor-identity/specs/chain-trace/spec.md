# Spec Delta

## ADDED Requirements

### Requirement: The trace names the identity behind a description
For a dataset with a stored extraction, the trace's crawler line SHALL name the extractor and the short form of the identity that produced it, and SHALL say whether that identity is the one of the last finished crawl. This is a detail of the line; it SHALL NOT change the stage's state or the exit status.

#### Scenario: A description from the current installation
- **WHEN** a DM4 file of the e2e tree has been crawled and its path is traced
- **THEN** the crawler line names `em/dm4` and the identity of the last finished crawl, marked as current

#### Scenario: A description left from another installation
- **WHEN** a dataset's stored extraction carries an identity other than the last finished crawl's (a subtree crawl ran with another installation since)
- **THEN** the crawler line names both identities and says that they differ, and the stage's state is unchanged

### Requirement: The status shows the last crawl's re-extraction
`modama-chain status` SHALL show, on the crawl line, the short form of the last finished crawl's extractor identity and, when that crawl extracted datasets again because the identity changed, their number and how many of their extraction results changed.

#### Scenario: After a crawl that extracted again
- **WHEN** the last finished crawl extracted two datasets again for a new identity and one of their results changed
- **THEN** the status's crawl line shows the identity, `2 extracted again` and `1 result changed`
