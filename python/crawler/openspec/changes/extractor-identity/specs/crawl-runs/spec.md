# Spec Delta

## ADDED Requirements

### Requirement: The runs command says what the next crawl will extract again
When the installation's extractor identity differs from that of the last finished crawl, `modama-crawler runs` SHALL print, on stderr before the runs, one note naming what changed, the number of stored datasets per format that the next crawl will extract again, and an estimate of the time from their stored extraction times, divided by the number of extraction processes. When the identities are equal it SHALL print no note.

#### Scenario: After an upgrade
- **WHEN** a tree with two DM4 files was crawled, the installed RosettaSciIO version changes, and `modama-crawler runs` is run
- **THEN** stderr starts with a note naming `rosettasciio 0.15.0 -> 0.16.0` and `em/dm4 2`, stdout carries the run lines as before, and `runs | head -1` still prints only the latest run's line

#### Scenario: Nothing changed
- **WHEN** `modama-crawler runs` is run with the installation of the last finished crawl
- **THEN** stderr carries no note
