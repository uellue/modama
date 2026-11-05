# Spec Delta

## Purpose

Making the search chain run by itself: the crawler crawls on a timer, and every crawl starts the harvest of its own endpoint once its records are committed, so that no harvest races a crawl and the freshness time moves on without manual steps.

## ADDED Requirements

### Requirement: A finished crawl starts the harvest of its endpoint
When `MODAMA_CRAWLER_AIRFLOW_URL` is set, `modama-crawler crawl` SHALL, after its records are committed and its run is finished, start the warehouse's harvest DAG for the endpoint `OAI_BASE_URL` with the account in `MODAMA_CRAWLER_AIRFLOW_USER` and `MODAMA_CRAWLER_AIRFLOW_PASSWORD`, also when no record changed, and SHALL log the started run.

#### Scenario: A crawl starts the harvest
- **WHEN** a crawl of a test tree finishes with an Airflow URL set
- **THEN** Airflow gets a token request and a DAG run of `warehouse_harvest_and_index` with the conf `harvest_urls` = [`OAI_BASE_URL`], and stderr says `harvest of <url> started: <run>`

#### Scenario: An unchanged crawl starts a harvest too
- **WHEN** the same tree is crawled twice with an Airflow URL set
- **THEN** two harvests are started

#### Scenario: No Airflow URL
- **WHEN** a crawl finishes without `MODAMA_CRAWLER_AIRFLOW_URL`
- **THEN** no harvest is started and the crawl exits with status 0

### Requirement: A harvest that cannot be started is an error, not a failed crawl
When the harvest cannot be started, the crawl's run SHALL stay finished, and `crawl` SHALL log the reason and exit with status 3, without a traceback.

#### Scenario: Airflow refuses the account
- **WHEN** the account's password is wrong
- **THEN** stderr says that the crawl finished but the harvest could not be started, with `HTTP 401`, the run is `finished`, and the exit status is 3

### Requirement: The timer crawls every day
`modama-crawler timer --at HH:MM` SHALL run `crawl` as a process of its own every day at that time (UTC) until it is stopped, logging the next time and each crawl's exit status; a time that is not `HH:MM` SHALL end it with status 2 and an error line.

#### Scenario: The next crawl
- **WHEN** the timer is set to 02:00 and it is 01:00, 02:00 or 23:30
- **THEN** the next crawl is today at 02:00, tomorrow at 02:00 and tomorrow at 02:00

#### Scenario: A time that is not HH:MM
- **WHEN** `modama-crawler timer --at 2am` is run
- **THEN** it exits with status 2 and `--at takes HH:MM`
