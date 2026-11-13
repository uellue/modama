# Spec Delta

## ADDED Requirements

### Requirement: The runs command says what the next crawl will extract again
When any stored dataset carries an extractor identity other than the installation's, `modama-crawler runs` SHALL print one note on stderr before the runs, naming what changed against the installed identity, the number of stored datasets per format that the next crawl will extract again, and an estimate of the time this takes. When every stored dataset carries the installation's identity, and none is extracted for the first time (next requirement), it SHALL print no note.

#### Scenario: After an upgrade
- **WHEN** a tree with two DM4 files was crawled, the installed RosettaSciIO version changes, and `modama-crawler runs` is run
- **THEN** stderr starts with a note naming `rosettasciio 0.15.0 -> 0.16.0` and `em/dm4 2`, stdout carries the run lines as before, and `runs | head -1` still prints only the latest run's line

#### Scenario: Left over from an experiment
- **WHEN** a subtree crawl under one installation stored two DM4 datasets below one path, the installation was changed back, and a subtree crawl below another path ran with the installation now installed
- **THEN** the note counts `em/dm4 2` for the first path's datasets, although the last finished crawl's identity equals the installed one

#### Scenario: Nothing changed
- **WHEN** `modama-crawler runs` is run and every stored extraction carries the installed identity
- **THEN** stderr carries no note

### Requirement: The runs command says what the next crawl will extract for the first time
When any stored dataset of an installed format with an extractor has no extraction, the note of `modama-crawler runs` SHALL also give the number of these datasets per format, and its time estimate SHALL cover them at the mean time of the stored extractions. Only the stored format counts: a stored dataset that the installed formats would now recognise as another format (a single file by type that a new collection claims) is not counted.

#### Scenario: A format extracted for the first time
- **WHEN** two DM4 datasets are stored without an extraction (as by a crawl when `em/dm4` had no extractor yet), and `modama-crawler runs` is run
- **THEN** stderr carries one note with `extracts for the first time em/dm4 2 datasets`

#### Scenario: The estimate covers both
- **WHEN** two DM4 datasets are stored under another identity with 600 seconds of extraction each, two more without an extraction, and `MODAMA_CRAWLER_EXTRACT_WORKERS=2 modama-crawler runs` is run
- **THEN** the note names `em/dm4 2 datasets stored under` the other identity, `and for the first time em/dm4 2 datasets`, and `about 20 minutes on 2 processes`
