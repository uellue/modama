# Spec Delta

## ADDED Requirements

### Requirement: The runs command says what the next crawl will extract again
When any stored dataset carries an extractor identity other than the installation's, `modama-crawler runs` SHALL print one note on stderr before the runs, naming what changed against the installed identity, the number of stored datasets per format that the next crawl will extract again, and an estimate of the time this takes. When every stored dataset carries the installation's identity it SHALL print no note.

#### Scenario: After an upgrade
- **WHEN** a tree with two DM4 files was crawled, the installed RosettaSciIO version changes, and `modama-crawler runs` is run
- **THEN** stderr starts with a note naming `rosettasciio 0.15.0 -> 0.16.0` and `em/dm4 2`, stdout carries the run lines as before, and `runs | head -1` still prints only the latest run's line

#### Scenario: Left over from an experiment
- **WHEN** a subtree crawl under one installation stored two DM4 datasets below one path, the installation was changed back, and a subtree crawl below another path ran with the installation now installed
- **THEN** the note counts `em/dm4 2` for the first path's datasets, although the last finished crawl's identity equals the installed one

#### Scenario: Nothing changed
- **WHEN** `modama-crawler runs` is run and every stored extraction carries the installed identity
- **THEN** stderr carries no note
