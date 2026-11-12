# Spec Delta

## Purpose

The way every collection tests its formats: fixture directories of wild files, one manifest of their provenance, recorded expected results, and a pytest plugin that runs all of it for any collection without code of its own.

## ADDED Requirements

### Requirement: Fixtures are directories of wild files
A collection's fixtures SHALL live under its `tests/fixtures/`, one directory per fixture, containing only what the wild contains; files the test harness needs SHALL live outside the fixture tree.

#### Scenario: Sidecar in the fixture tree
- **WHEN** a fixture directory contains a file that the manifest does not describe as part of the wild content
- **THEN** the collection's tests fail naming that file

### Requirement: Every fixture has provenance
A manifest file per collection SHALL name every fixture with its purpose (representative or reproducer), how its validity is known, its licence and its source; a fixture without an entry, or an entry without a fixture, SHALL fail the tests.

#### Scenario: Missing manifest entry
- **WHEN** a fixture directory exists without a manifest entry
- **THEN** the collection's tests fail naming the fixture

### Requirement: Expected results are recorded and compared
The plugin SHALL run recognition on each fixture and compare the recognition result with the recorded result stored next to the fixtures; a difference SHALL fail naming the datasets that differ, and a regeneration option SHALL rewrite the recorded results and fail for each one that changed, naming the datasets, so that the run itself asks for the review (decision T4).

#### Scenario: First run records
- **WHEN** a fixture has no recorded result, with or without regeneration enabled
- **THEN** the result is written and the test fails asking for a review; the next run passes

#### Scenario: Regeneration names what changed
- **WHEN** the tests run with regeneration enabled and a recorded result differs from the recognition result
- **THEN** the result is rewritten and the test fails naming the file and the changed datasets; unchanged results pass

#### Scenario: A rule change alters the result
- **WHEN** a format's rules change so that a fixture's dataset type differs from the recorded one
- **THEN** the test fails and shows the old and new type

### Requirement: A collection is tested with its own definitions
The plugin SHALL classify a collection's fixtures with the MIME definitions of that collection and of the core only, whatever else is installed, so that recorded results do not depend on the environment.

#### Scenario: Another collection adds a rule
- **WHEN** an installed collection other than the one under test defines a glob that would match one of its fixture files
- **THEN** the fixture's recorded result is unaffected

### Requirement: Every own rule is covered
For the rules a collection defines itself (its XML rules and its recognizers), the plugin SHALL fail if a rule fires on no representative fixture of the collection; vendored upstream definitions are exempt.

#### Scenario: Uncovered glob
- **WHEN** a collection's XML defines a glob that no representative fixture matches
- **THEN** the collection's tests fail naming the rule

### Requirement: Tests run offline
A collection's tests SHALL run after installation without network access; fixtures that a real producer generates at test time SHALL be generated locally.

#### Scenario: No network
- **WHEN** the tests run with network access blocked
- **THEN** they pass or fail on content, never on connectivity

### Requirement: Generated fixtures count when a real producer writes them
A fixture written at test time by the software that writes the format in practice SHALL count as representative and SHALL carry its producer in the manifest.

#### Scenario: Zarr written by zarr-python
- **WHEN** a fixture is created by the Zarr library at test time
- **THEN** its manifest entry names the producer and the coverage rule counts it
