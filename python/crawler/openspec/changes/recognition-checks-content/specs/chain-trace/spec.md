# Spec Delta

## ADDED Requirements

### Requirement: The crawler line shows the dataset's basis
The crawler line of a trace SHALL show the basis of the dataset that holds the path, as the crawler stored it, so that a type a format dropped is visible with the format and its reason.

#### Scenario: A text file named like a K2IS tag file
- **WHEN** the e2e tree holds `notes.gtg` holding `hello\n`, it has been crawled, and its path is traced
- **THEN** the crawler line's detail shows `basis: single file; em/k2is: not application/x.dm-gtg, no DM4 header`

#### Scenario: A plain file
- **WHEN** a text file of the e2e tree that no format claims is traced
- **THEN** the crawler line's detail shows `basis: single file`
