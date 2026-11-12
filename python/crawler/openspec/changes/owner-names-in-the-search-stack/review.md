# Review of owner-names-in-the-search-stack (b5c0ba4 + 516c8db), independent reviewer, 2026-11-12

Verdict: sound, 201/202 in; not to be applied as written. Each finding with what to do; the
"Decision" lines are mine (main session) unless marked @weber.

1. blocker: the base compose mounts `${MODAMA_SECRETS_DIR}/sssd.conf`; the e2e secrets folder
   (`/home/dev/.config/modama/e2e-secrets`) has no sssd.conf, Docker makes a directory there, sssd
   never gets healthy. Fix: the test config mount (`./testconf/secrets/sssd.conf:/sssd.conf.in:ro`)
   in `docker-compose.override.yml` next to `ldap`; the base has no config mount; staging adds its
   own (D6's "replaces it, same target" goes away).
2. should: tonight's cost in numbers, in D8, README and runbook: 1,451,848 records
   (staging findings :57), harvest 5 h 14 min (:127), 726 indexing batches at about 14 per
   10 min after the worker restart (:136, :203) = roughly 8–9 h, at 4.5 per 10 min (:144) about
   19 h; `store.py:455` rebuilds every record each crawl, so a rollback after 19:00 costs another
   full re-index. Say the expected end (mid-morning tomorrow at best, may run into tomorrow's
   19:00 crawl).
3. should: the `sssd-cache` volume holds `config.ldb` with the bind password (grep -c in the smoke
   container: 1); a third persistent copy of the real secret on staging, surviving downstaging.sh
   without --reset; the cache already survives a restart in the container layer.
   Decision: drop the volume (and task 2.4's extra check).
4. should: health check every 10 s with default 3 retries (~30 s); sssd goes offline for 60 s
   after a failed first contact (`ldap_offline_timeout` 60 in the smoke log).
   Fix: `start_period: 120s` (or retries 12).
5. should: D7 "needs a way to tell no such user from sssd unavailable" overstates it: the canary
   (`SSSD_CHECK_USER`) must exist; if `getpwuid(canary)` raises, the name service is down.
   Options: (a) ~10 lines in the crawl: canary fails before the store → the run fails (retry),
   no numbers stored; (b) no guard, the runbook counts numeric creators after each crawl
   (`SELECT count(*) FROM records WHERE metadata->'creator'->>0 ~ '^[0-9]+$'`).
   Decision: (a), per @weber's standing principle "the same data gives the same result or a
   failure"; I am confirming with @weber, build (a) unless I say otherwise. Keep the canary's
   configuration minimal (the same setting the health check uses).
6. should: unit tests take the expected group from `records.owner(os.getuid())`, the code under
   test, and differ per machine (VM user `dev`, empty GECOS, group `dev`; the stack image runs as
   root; a uid without passwd entry gets no group). Affected: `tests/test_records.py:105,124,178`,
   `tests/test_server.py:95,96`, `modama-formats-em` `dm/tests/test_extract.py:39`,
   `k2is/tests/test_extract.py:90,119`. Fix: an explicit fixture (not autouse) in
   `modama_crawler.testing` (the pytest11 plugin, also used by the EM tests) that patches the
   lookup to a fixed "Alice Anderson" / "erc-1"; assertions become literal strings.
7. should: no tasks for the decision log (`design/architecture.md`: rows for 201/202) and
   `design/requirements.md:148` (row 2.9) and Q22 (:164), which still say login names only; full
   names and groups now reach the warehouse, the index and Blablador (200 accepted that).
8. should: stale after 201: `proposal.md:22` (creator `alice` → `Alice Anderson`), `design.md:61`
   ("a login name" → a full name). Runbook outcome checks: before 19:00
   `dc exec crawler python -c 'from modama_crawler.records import owner; print(owner(20335))'`;
   after the crawl the numeric-creator count of 5.
9. should: `STAGING_SSSD_CONF` has no requester. Decision: hard-code
   `/var/local/data-mgmt/sssd.conf` in the staging compose; the setting is a next step if needed.
10. should: tonight's commands miss (a) a check that the running harvest and indexing have
    finished before `./upstaging.sh --build` recreates `crawler` and `crawl-timer`, and (b) whether
    the recreated timer crawls at once (`cli.py:457-459`: when the last finished crawl is more than
    a day old). Add both with times. The VM stack: see my message.
11. nit: "group erc-1" reads like the file's group; CONTEXT.md lists "Group" under _Avoid_ and
    "Owner" is a project's owner there. Decision (provisional, asking @weber): "owner's group
    erc-1" in the description; raise a glossary entry for it in your hand-over.
12. nit: D10 agreed; add a unit case "Weber, Dieter" → "Weber" to make the accepted loss visible.
13. nit: `/var/lib/sss/pipes/private/sbus-master` is `srw------- root`: the test stack's crawler
    runs as root and can reach it; one line in Risks.
14. nit: the production template has `ldap_tls_reqcert = never`: "with TLS" overstates the bind
    password's protection; say so in Risks (deploy's practice, not this change's to fix).
15. nit: every service sets `networks: [search]`; the smoke test used `default`. State in D2 that
    `sssd` and `ldap` join `search`.
16. nit: the worktree's `testconf/secrets/sssd.conf` lacks `ldap_id_use_start_tls = false`
    (D4 requires it; the scratchpad smoke copy had it).
17. nit: applying started before the review (records.py, test_records.py, test_server.py
    modified); fine now, note it in the hand-over. Archive must wait for em-formats-and-extraction
    (task 4.3). Cite finding F10 (`search-stack-staging-findings.md:328`) in the proposal.

Checked fine by the reviewer: D4's StartTLS claim; deploy/sssd's nsswitch; one lookup per owner per
crawl; compose merges staging's volumes by target; reuse of deploy/ without copies; the bind
password is not logged even at debug_level 6; the sed removes the PAM responder.
