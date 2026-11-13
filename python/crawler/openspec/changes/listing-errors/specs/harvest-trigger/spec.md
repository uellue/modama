# Spec Delta

## ADDED Requirements

### Requirement: A crawl that finished with errors starts the harvest
A crawl that finished with folders the file system did not answer SHALL start the harvest as a finished crawl does, and SHALL exit with status 4 whether or not the harvest could be started; when it could not, the harvest's error line SHALL still be logged.

#### Scenario: The harvest starts after errors
- **WHEN** a crawl with an Airflow URL set kept a folder whose listing failed with `ESTALE`
- **THEN** Airflow gets a DAG run of `warehouse_harvest_and_index`, stderr says `harvest of <url> started: <run>`, and the exit status is 4

#### Scenario: Errors and a harvest that cannot be started
- **WHEN** a crawl kept a folder whose listing failed with `EIO`, and Airflow refuses the account
- **THEN** stderr says that the crawl finished but the harvest could not be started, and the exit status is 4
