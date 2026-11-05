# Review of the implementation, 2026-11-05

By an agent that did not write the code, given the code, the two spec deltas, `design/requirements-pipeline.md` and the standing rules, and not this change's design until it had formed its view (`design/review.md` pattern). Findings verified by reading the code and upstream's harvester before acting; the full report is in the session transcript.

| # | Finding | Outcome |
|---|---|---|
| 1 | T is not a guarantee when a harvest starts while `store()` upserts: the records' datestamp is taken before the upsert, the harvest's `until` falls after it but it sees nothing before the commit, the next window starts after the datestamp, and the records are never harvested while T moves past them (the BACKLOG's "Datestamp window") | **Open, for @weber**: needs a decision (see below) |
| 2 | T turns unknown for good once the oldest harvest's indexing run is older than the newest 100 Airflow runs | Fixed: all indexing runs, page by page; all crawl runs |
| 3 | Progress written only after a directory listing; a long directory or `store()` leaves a healthy crawl stale and `runs --follow` exits 1 | Fixed: heartbeat thread with its own connection (D2) |
| 4 | `status` printed T in the crawler database's session time zone, labelled `Z` | Fixed: printed in UTC |
| 5 | Index stage could not be `differs` (newer version in the warehouse, not synced, old document still indexed) | Fixed |
| 6 | Harvest `ok` from an event of a failed or open run | Fixed: closed runs only |
| 7 | `BEFORE-HARVEST-WINDOW` fired one harvest late, and ignored that the harvester sends `from`/`until` cut to seconds (`harvester_oaipmh.py`) | Fixed: compare with the last `until`, cut to the second; spec and D6 updated |
| 8 | Tests passing while broken: a path in no stage counted as consistent in `assert_consistent`; `t == t_before` with both `None`; the failed-crawl test on an empty database; the pipe test racing | Fixed: crawler stage must be `ok`; T asserted; failed crawl on existing records; a `runs \| true` case. Not fixed: "start taken before the walk" is indistinguishable at second resolution; the key-equivalence unit test skips without the crawler installed (the e2e test's traces of every record cover it) |
| 9 | Overlapping crawls: an older crawl committing after a newer one deletes the newer one's records while T moves on | **Open, for @weber**: an advisory lock in `cmd_crawl` (fail fast) is cheap; the design left overlap to the scheduling change |
| 10 | Read-only only by account | Fixed: every session `default_transaction_read_only`; default privileges for tables added later. Left: the Airflow password is in argv of `airflow users create` inside the e2e container (no stdin option) |
| 11 | Stale judged by the reader's clock | Fixed: database `now()` (D3) |
| 12 | Positional 12-tuples; `ET.ParseError` escaping; `end_run` failure masking the original error | Fixed: typed rows; parse error reported as an unreachable store; original error kept. Left: SIGTERM leaves a stale run rather than a failed one (acceptable per spec; a handler with the timer change) |

Finding 1, options:
- (a) The crawler writes datestamps that cannot fall behind a harvest window: a datestamp after the commit is not possible in one transaction, but the upsert can be kept short (write into a staging table during the store, then one short UPDATE), which narrows the race without closing it.
- (b) T excludes a crawl, and caps itself at that crawl's start, when a harvest's `until` falls between the crawl's datestamp and its commit; needs the store's start time in `crawl_runs`. Honest, and T then stays capped until the lost records are re-harvested (a purge or a full harvest).
- (c) Avoid the overlap by scheduling: the crawler triggers the harvest after its commit (decision 2026-11-04), and upstream's cron stays off (`HARVEST_SCHEDULE` empty); then the race needs a manual trigger. Document the condition next to T.
- (d) An overlap margin on `from` in the harvester (BACKLOG): upstream change, wishlist.
