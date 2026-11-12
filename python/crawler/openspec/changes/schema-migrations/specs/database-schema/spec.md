# Spec Delta

## Purpose

How the crawler's database gets its schema and keeps it in step with the code, so that a schema change reaches an existing database in place, with its data (R42).

## ADDED Requirements

### Requirement: migrate brings the database to the code's schema
`modama-crawler migrate` SHALL apply every migration the database lacks, in order, and log the schema version before and after. On a database that is already at the code's version it SHALL change nothing, log that it is up to date and exit with status 0.

#### Scenario: A fresh database
- **WHEN** `migrate` runs on an empty database
- **THEN** it creates the tables `datasets`, `members`, `directories`, `records` and `crawl_runs`, logs `INFO schema migrated from none to <head>`, and exits with status 0

#### Scenario: Run again
- **WHEN** `migrate` runs a second time on the same database
- **THEN** it logs `INFO schema up to date at <head>`, the schema is unchanged, and it exits with status 0

#### Scenario: Nothing to do while a crawl runs
- **WHEN** `migrate` runs on a database at the code's version while another process holds the crawl lock
- **THEN** it logs `INFO schema up to date at <head>` and exits with status 0 at once, without waiting for the lock

### Requirement: An existing database migrates in place
`migrate` SHALL bring a database made by an earlier version of the crawler to the code's schema without losing its rows. A database whose tables were made before migrations existed SHALL be taken as revision `0001_baseline`.

#### Scenario: A database made before migrations
- **WHEN** `migrate` runs on a database made by the crawler before this change, holding a finished run, a dataset with a member, a stored listing and a record
- **THEN** it logs that it adopted the existing tables as `0001_baseline`, every row and every datestamp is unchanged, and the schema equals that of a fresh database migrated to the same version

#### Scenario: A column is added to a filled database
- **WHEN** a database at revision 0001 with the rows above is migrated by a revision that adds a nullable column to `crawl_runs`
- **THEN** the old run has the column with NULL, and every other row and datestamp is unchanged

### Requirement: Commands refuse a database that is behind the code
`crawl`, `runs`, `timer` and `serve` SHALL NOT change the schema. On a database whose schema version is older than the code's, or that has none, they SHALL exit with status 2 and an error that names both versions and the command `modama-crawler migrate`, before recording or serving anything. `records` SHALL work without a database, as before.

#### Scenario: One migration missing
- **WHEN** `modama-crawler crawl` runs against a database at `0001_baseline` while the code is at `0002_crawl_runs_scope`
- **THEN** it exits with status 2, stderr holds `ERROR the database schema is at 0001_baseline, this crawler needs 0002_crawl_runs_scope: run modama-crawler migrate`, and no run is recorded

#### Scenario: No schema yet
- **WHEN** `modama-crawler serve` starts against an empty database
- **THEN** it exits with status 2 with an error naming no version, the code's version and `modama-crawler migrate`, and creates no table

### Requirement: Commands refuse a database that is ahead of the code
Every database command, `migrate` included, SHALL exit with status 2 on a database whose schema version the code does not know, with an error that names that version and says that a newer crawler made it. `migrate` SHALL change nothing then.

#### Scenario: An image rolled back
- **WHEN** a database migrated to `0002_crawl_runs_scope` is used by a crawler whose newest revision is `0001_baseline`
- **THEN** `crawl`, `runs`, `timer`, `serve` and `migrate` each exit with status 2, the error names `0002_crawl_runs_scope` as unknown to this crawler, and the database is unchanged

### Requirement: One migration at a time, and none during a crawl
A migration that has revisions to apply SHALL hold the crawl lock while it runs. A second migration started meanwhile SHALL wait and then find the database up to date. A migration with revisions to apply started while a crawl runs SHALL log that it waits for the crawl lock and SHALL start once the crawl has ended.

#### Scenario: Two migrations start at once
- **WHEN** two `migrate` processes start against the same database that lacks one migration
- **THEN** both exit with status 0, the migration is applied once, and one of them logs `up to date`

#### Scenario: A crawl is running
- **WHEN** `migrate` starts on a database that lacks a migration while another process holds the crawl lock
- **THEN** it logs `INFO waiting for the crawl lock (a crawl or another migration holds it)`, changes nothing while the lock is held, and migrates after the lock is released

#### Scenario: A crawl starts during a migration
- **WHEN** `crawl` starts while `migrate` holds the crawl lock
- **THEN** it exits with a non-zero status and records no run

### Requirement: A failed migration changes nothing
All migrations of one `migrate` run SHALL be applied in one transaction. If any of them fails, `migrate` SHALL exit with status 1 and an error naming the revision that failed and the version the database is still at, and the database SHALL be left with the schema and the version it had before the run.

#### Scenario: The second of two migrations fails
- **WHEN** `migrate` applies two pending migrations to a database at `0001_baseline`, and the second fails after the first has added a column
- **THEN** it exits with status 1, stderr holds `ERROR migration <second revision> failed, the database is unchanged at 0001_baseline:` followed by the database's error, the column is not there, and the database is still at `0001_baseline`

#### Scenario: A lock on a table is not granted in time
- **WHEN** a migration's statement waits longer than the lock timeout for a table that another transaction holds
- **THEN** `migrate` exits with status 1 with an error saying that the lock was not granted and to run `migrate` again, and the database is unchanged

### Requirement: A downgrade with no way back refuses with the step
Every migration SHALL have a downgrade. Where a migration cannot be undone so that the older code reads the result correctly, its downgrade SHALL refuse with an error that names the migration and says to restore the dump taken before the upgrade, and SHALL change nothing.

#### Scenario: Downgrading below the baseline
- **WHEN** `alembic downgrade base` runs on a database at `0001_baseline`
- **THEN** it exits with status 1, its last line is `NotImplementedError: no downgrade from 0001_baseline: restore the dump taken before the upgrade (README, Upgrade)`, and the database is still at `0001_baseline` with its tables and rows
