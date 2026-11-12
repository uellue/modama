# Tasks

Written with the leans of the brief (2026-11-12) as assumptions, changed where the smoke test showed otherwise: D4 (StartTLS off said explicitly), D5 (a lookup as the health check, no `sssctl` in the image). @weber's decisions 196 to 202 are in proposal.md (201 and 202 added the same day, superseding 199); the review's findings (`review.md`) in design.md, by number. Deadline: merged before 18:00 UTC for the crawl at 19:00 UTC (198).

## 1. Crawler: creator, group, the check before the store

- [ ] 1.1 `records.py`: `owner(uid)` (D10) instead of `user_name`, `dc_metadata`'s creator from it, `description` with `, owner's group <name>` (D11). Verify: tests of 1.3.
- [ ] 1.2 `cli.py`: `SSSD_CHECK_USER` read in `cmd_crawl` before the run is recorded (not a uid: status 2), and looked up in `crawl_tree` before `store` (D7). Verify: `tests/test_cli.py`, one test per scenario of "A crawl stores no records while the user database cannot name its check user".
- [ ] 1.3 `testing.py`: the fixture `fixed_owner` (D9, finding 6). `tests/test_records.py`, one test per scenario: "Dublin Core mapping": Single file, An owner without a full name, A full name with a comma, An owner without a name; "Every record carries a description": A file without an extractor, An owner without a known group; the whole-description comparisons in `test_records.py`, `test_server.py` and `modama-formats-em` (`k2is`, `dm`) with `fixed_owner` and literal strings. Verify: `pytest` in `python/crawler` and in `python/modama-formats-em`, each with the number of skipped tests.
- [ ] 1.4 `README.md` (crawler): the description's example with the group, the creator's source and fallbacks, `SSSD_CHECK_USER`. Verify: the sentences match the specs.
- [ ] 1.5 `design/architecture.md`: decision-log rows for 201 and 202 (and the check of D7, provisional); `design/requirements.md` 2.9 and Q22: full names and groups, not only login names, are in the records and reach the warehouse, the index and Blablador (finding 7). Verify: `git diff` shows them.

## 2. Search stack

- [ ] 2.1 `crawler.Dockerfile`: `libnss-sss` beside `shared-mime-info`. Verify: in the built image, `grep -E '^(passwd|group)' /etc/nsswitch.conf` shows `files sss`.
- [ ] 2.2 `docker-compose.yml`: service `sssd` (D1, D3, D5: build `../../deploy/sssd`, image `search-stack-sssd`, `restart: unless-stopped`, `tmpfs: /run`, the sockets in `ssspipes`, no configuration mount, no cache volume, the start command, the health check with `start_period: 120s`); `crawler` and `crawl-timer` mount `ssspipes` read-only and wait for `sssd` healthy (D2). Verify: `docker compose config` of the test deployment and of staging (with a throwaway env file in the scratchpad, not the server's) show the mounts, the dependency, the health check and `SSSD_CHECK_USER` in `sssd`, `crawler` and `crawl-timer`.
- [ ] 2.3 `docker-compose.override.yml`: service `ldap` (build `../../deploy/ldap`, image `search-stack-ldap`, volume `ldapdata`); `sssd` mounts `./testconf/secrets/sssd.conf` (finding 1), waits for `ldap` healthy; `SSSD_CHECK_USER: "10001"` for `sssd`, `crawler`, `crawl-timer`. `testconf/secrets/sssd.conf` (D4: nss only, plain LDAP with `ldap_id_use_start_tls = false`, the test bind account). Verify: 2.5.
- [ ] 2.4 `docker-compose.staging.yml`: sssd's configuration `/var/local/data-mgmt/sssd.conf`, long syntax, read-only, `create_host_path: false`; `SSSD_CHECK_USER: ${STAGING_USER}` for `sssd`, `crawler`, `crawl-timer` (D5, D6). Verify: `docker compose config` with the throwaway env file; a missing source fails (smoke test, done: `bind source path does not exist`).
- [ ] 2.5 `runtest.sh`: `sssd` and `ldap` in `SERVICES`, the check of D9. `test_e2e.py`: the owner test of D9. Verify: when the VM's stack is free (not before), `./downtest.sh --reset && ./uptest.sh && ./runtest.sh e2e` with `MODAMA_SECRETS_DIR=/home/dev/.config/modama/e2e-secrets`, and `./runtest.sh`: PASS, with the number of skipped tests.

## 3. Documentation

- [ ] 3.1 `prototypes/search-stack/README.md`: a section "Owners' names" (sssd from `deploy/`, the copy with `services = nss`, the test directory and its users, plain LDAP and why the option, staging's file, the check user, what an outage does, D7, and what the first crawl with names costs on staging, D8); `ldap` and `sssd` in the overview. Verify: the commands in it run as written in the test deployment.
- [ ] 3.2 Staging runbook (`design/field-tests/search-stack-staging-runbook.md`): a section with @weber's commands for tonight, in order, with times (finding 10): the checkout has the change; the harvest and indexing of the last crawl have finished (`modama-chain status`) before `./upstaging.sh --build` recreates the crawler services; the check of the option names (D6); whether the recreated timer crawls at once (the last finished crawl more than a day old) or at 19:00; `./upstaging.sh --build`; `dc exec crawler python -c 'from modama_crawler.records import owner; print(owner(<uid>))'` (finding 8); after the crawl, the count of records with a number as creator; the cost of D8. Verify: read against `docker-compose.staging.yml` and `cli.py`'s timer; every command self-contained.
- [ ] 3.3 `BACKLOG.md`: the change's state; a glossary entry for the owner's primary group in `/CONTEXT.md` (finding 11, proposed, not written). Verify: the items link this change.

## 4. Checks and hand-over

- [ ] 4.1 `uvx ruff format --check --diff` and `uvx ruff check` from the repo root. Verify: their output.
- [ ] 4.2 Smoke project torn down (`docker compose -p sssd-smoke-acc3 down --volumes`), only that project. Verify: `docker ps -a --filter name=sssd-smoke` empty.
- [ ] 4.3 Archive after `em-formats-and-extraction` (its "Every record carries a description" is the requirement this change modifies), when @weber accepts. Verify: `openspec validate owner-names-in-the-search-stack` without the archive notice.
