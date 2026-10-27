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

#### Scenario: A warning carried by a dataset
- **WHEN** `records PATH` is run without `--verbose` on a directory with a Zarr store whose `zarr.json` cannot be parsed
- **THEN** standard error has a warning line naming the store and the summary line counts it

### Requirement: Selective listing
`records` SHALL accept `--from` and `--until` with the protocol's datestamp syntax, filtering on the record date, and SHALL accept `--select` and `--ignore` ids that override the configuration's selection for this run; an option may carry several ids separated by commas, as ruff does, and may be repeated.

#### Scenario: Several ids in one option
- **WHEN** `records --ignore collapse,zarr PATH` is run
- **THEN** it has the same effect as `records --ignore collapse --ignore zarr PATH`

#### Scenario: Trying a different selection
- **WHEN** `records --ignore empad` is run on a directory with an EMPAD pair
- **THEN** the XML and raw files appear as single-file datasets of generic types and no EMPAD dataset

### Requirement: Options are accepted where users put them
All options of `records` (`--verbose`, `--from`, `--until`, `--select`, `--ignore`, `--config`) SHALL be accepted after the subcommand, in any order, as the examples in the documentation show them; `--verbose` and `--config` SHALL also be accepted before the subcommand.

#### Scenario: Verbose after the subcommand
- **WHEN** `records --verbose` is run
- **THEN** it runs with per-dataset diagnostics on standard error, the same as `--verbose records`

#### Scenario: Options in any order
- **WHEN** `records --ignore empad --verbose PATH --from 2020-01-01` is run
- **THEN** every option takes effect and the exit status is zero

#### Scenario: Help lists every option
- **WHEN** `records --help` is run
- **THEN** the help text lists `--verbose` and `--config` along with the other options

### Requirement: A closed output pipe ends the command quietly
When the reader of standard output goes away before all records are written, for example `records | less` quit early, `records` SHALL stop without a traceback or an error message and exit with status zero.

#### Scenario: Piped into head
- **WHEN** `records PATH | head -c 200` is run on a directory with hundreds of files
- **THEN** `records` exits with status zero and writes nothing about a broken pipe to standard error

### Requirement: Failures are visible
When the crawl cannot complete, `records` SHALL print the reason on standard error and exit with a non-zero status; warnings from the recognition result SHALL NOT change the exit status.

#### Scenario: Path does not exist or cannot be read
- **WHEN** `records /no/such/path` is run, or PATH is a directory the user cannot list
- **THEN** the exit status is non-zero and standard error names the path

#### Scenario: Configuration file cannot be read
- **WHEN** `records --config /no/such.toml PATH` is run
- **THEN** the exit status is non-zero, standard error names the file, and there is no traceback
