# Design

## Context

Decisions in `design/architecture.md` (2026-11-04: our timer, the crawler starts the harvest; 2026-11-05: our own composition, a harvest after every crawl). The crawl lock and the store lock of the archived change `crawl-runs-and-chain-trace` (D11) already keep a harvest from reading half-written records; starting it after the commit makes the race need a manual trigger.

## Goals / Non-Goals

**Goals:** the chain runs by itself in the search stack; the crawler stays free of Airflow except one module; the stack is shaped for `deploy/`.
**Non-Goals:** production compose, other schedules, the watcher.

## Decisions

**D1. The trigger in the crawler, after the crawl lock is released.** `harvest.py` with the standard library (token, then a DAG run with `harvest_urls`); `cmd_crawl` calls it after its connection, and with it the crawl lock, is closed. *Alternative:* a DAG of ours in their Airflow (rejected 2026-11-04).

**D2. Exit status 3 for "crawled, not harvested".** The crawl's data are fine, so the run stays `finished`; a distinct status lets the timer's log and an admin tell it from a failed crawl (1, 2). `modama-chain status` shows "latest crawl not harvested yet" meanwhile.

**D3. The timer as a command that sleeps and spawns.** `modama-crawler timer --at HH:MM` in its own service: daily is all that is asked (crawl at night, requirements 2.11); a process per crawl keeps the timer free of the crawl's state (MIME database, memory). *Alternatives:* cron in the container (environment handling, a second process manager); a host systemd timer (fits `deploy/` later, not a self-contained stack); supercronic (a new dependency for one daily line).

**D4. Secrets as files per concern, in the composition.** Each service's `env_file` lists only what it needs; the names of the upstream code are kept (`POSTGRES_PASSWORD` etc.), which is why the crawler, whose own settings use the same names, gets no warehouse file, and the e2e test reads the test credentials from the mounted `testconf/`.

## Risks / Trade-offs

- [The timer stopped while a crawl runs] → the crawl process is killed with the container; its run shows as stale; the next crawl takes the lock (PostgreSQL released it).
- [Airflow down when a crawl finishes] → exit 3, logged; the next crawl starts a harvest that covers both.
- [Upstream renames the DAG or its conf] → the e2e test, whose crawls start their harvests, fails.
