# Spec Delta

## Purpose

A harvest that runs while a crawl writes its records must not lose them: the freshness time T of the `chain-trace` capability relies on it (review of 2026-11-05, finding 1; the backlog's "Datestamp window").

## ADDED Requirements

### Requirement: A harvest does not miss a crawl's records
While a crawl writes its records, the OAI-PMH server SHALL answer every request with HTTP 503 and a `Retry-After` header (OAI-PMH 2.0, flow control), and the records' datestamp SHALL be taken after the requests in flight have ended, so that a harvest either reads the records after their commit or finds them dated after its window.

#### Scenario: Requests come back later
- **WHEN** a request arrives while a crawl writes its records
- **THEN** the response is 503 with `Retry-After: 60`, and the same request succeeds after the commit

#### Scenario: The datestamp follows the requests in flight
- **WHEN** a crawl starts writing while a request is being answered
- **THEN** the records' datestamp is not before the end of that request

#### Scenario: The harvester comes back
- **WHEN** oaipmh-scythe, with the EOSC harvester's settings, lists records while a crawl writes, and the crawl commits within the retries
- **THEN** the harvest completes with every record
