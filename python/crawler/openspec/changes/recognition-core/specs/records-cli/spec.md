# Spec Delta

## Purpose

A command that runs the whole pipeline on a path and prints what the OAI-PMH endpoint would serve for it, without a database or a server, so that every part of the stack can be inspected in one go.

## ADDED Requirements

### Requirement: Records for a path
`records [PATH]` SHALL crawl PATH (default: the current directory) with the enabled formats and print on standard output an OAI-PMH `ListRecords` response in `oai_dc` with one record per dataset, without pagination or sets, after the walk has finished.

#### Scenario: Default invocation
- **WHEN** `records` is run in a directory containing one text file
- **THEN** standard output is a `ListRecords` response with one record, valid against the OAI-PMH and `oai_dc` schemas, and the exit status is zero

### Requirement: Diagnostics stay off standard output
Progress, warnings and, with `--verbose`, per-dataset diagnostics (format id and version, basis, warnings, and timings) SHALL go to standard error, so that standard output is always a single valid document.

#### Scenario: Verbose run piped
- **WHEN** `records --verbose` is run and standard output is piped to a schema validator
- **THEN** the document validates and the diagnostics appear on standard error

### Requirement: Selective listing
`records` SHALL accept `--from` and `--until` with the protocol's datestamp syntax, filtering on the record date, and SHALL accept `--select` and `--ignore` ids that override the configuration's selection for this run.

#### Scenario: Trying a different selection
- **WHEN** `records --ignore empad` is run on a directory with an EMPAD pair
- **THEN** the XML and raw files appear as single-file datasets and no EMPAD dataset

### Requirement: Failures are visible
When the crawl cannot complete, `records` SHALL print the reason on standard error and exit with a non-zero status; warnings from the recognition result SHALL NOT change the exit status.

#### Scenario: Path does not exist
- **WHEN** `records /no/such/path` is run
- **THEN** the exit status is non-zero and standard error names the path
