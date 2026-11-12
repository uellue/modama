# Tasks

Written with the leans of the brief (2026-11-12) as assumptions, changed where the smoke test showed otherwise: D4 (StartTLS off said explicitly), D5 (a lookup as the health check, no `sssctl` in the image). @weber's decisions 196 to 200 are in proposal.md. Deadline: merged before 18:00 UTC for the crawl at 19:00 UTC (198).

## 1. Records spec and unit tests

- [ ] 1.1 `tests/test_records.py`: the existing `test_dublin_core_mapping` asserts the creator (Single file); a new test for An owner without a name (`pwd.getpwuid` patched to raise `KeyError`, `user_name.cache_clear()` before and after). Verify: `pytest tests/test_records.py` in `python/crawler`, then the crawler's whole suite, with the number of skipped tests.

## 2. Search stack

- [ ] 2.1 `crawler.Dockerfile`: `libnss-sss` beside `shared-mime-info`. Verify: in the built image, `grep -E '^(passwd|group)' /etc/nsswitch.conf` shows `files sss`.
- [ ] 2.2 `docker-compose.yml`: service `sssd` (D1, D3, D5: build `../../deploy/sssd`, image `search-stack-sssd`, `restart: unless-stopped`, `tmpfs: /run`, the sockets in `ssspipes`, the cache in `sssd-cache`, `${MODAMA_SECRETS_DIR}/sssd.conf` at `/sssd.conf.in:ro`, the start command, the health check with `SSSD_CHECK_USER`); `crawler` and `crawl-timer` mount `ssspipes` read-only and wait for `sssd` healthy (D2). Verify: `docker compose config` of the test deployment and of staging (with a throwaway `staging.env`, not the server's) show the mounts, the dependency and the health check.
- [ ] 2.3 `docker-compose.override.yml`: service `ldap` (build `../../deploy/ldap`, image `search-stack-ldap`, volume `ldapdata`), `sssd` waits for it healthy and has `SSSD_CHECK_USER: "10001"`; `testconf/secrets/sssd.conf` (D4: nss only, plain LDAP with `ldap_id_use_start_tls = false`, the test bind account). Verify: the smoke test's commands against the stack (2.5).
- [ ] 2.4 `docker-compose.staging.yml`: sssd's configuration from `${STAGING_SSSD_CONF:-/var/local/data-mgmt/sssd.conf}`, long syntax, read-only, `create_host_path: false`; `SSSD_CHECK_USER: ${STAGING_USER}` (D5, D6). Verify: `docker compose config` with a throwaway `staging.env` shows the source path, and with `STAGING_SSSD_CONF` set, that path; in a small project of its own, a recreated sssd with the directory stopped still names 10001 (D7, the cache volume).
- [ ] 2.5 `runtest.sh`: `sssd` and `ldap` in `SERVICES`, the check "the crawler names uid 10001 alice (through sssd)". `test_e2e.py`: the owner test changes the owner to 10001 and checks `alice` in the crawler's record, the warehouse's record and the index (scenario An owner from the directory, D9). Verify: when the VM's stack is free (not before), `./downtest.sh --reset && ./uptest.sh && ./runtest.sh e2e` with `MODAMA_SECRETS_DIR=/home/dev/.config/modama/e2e-secrets`, and `./runtest.sh`: PASS, with the number of skipped tests.

## 3. Documentation

- [ ] 3.1 `prototypes/search-stack/README.md`: a section "Owners' names" (sssd from `deploy/`, the copy with `services = nss`, the test directory and its users, plain LDAP and why the option, staging's file and `STAGING_SSSD_CONF`, what an outage does, D7, and what the first crawl with names does on staging, D8); `ldap` and `sssd` in the overview. Verify: the commands in it run as written in the test deployment.
- [ ] 3.2 Staging runbook (`design/field-tests/search-stack-staging-runbook.md`): `STAGING_SSSD_CONF` in "Settings" (optional), and a section with @weber's commands for tonight, in order: pull, the check of the option names (D6), `./upstaging.sh --build`, `dc exec crawler getent passwd "$(id -u)"`, what the 19:00 crawl then does (D8) and how to see it. Verify: read against `docker-compose.staging.yml`; every command self-contained.
- [ ] 3.3 `BACKLOG.md`: the change's state, and the next step of D7 (a guard in the crawler against a crawl with numbers while the name service is unavailable), and full name and group later (199). Verify: the items link this change.

## 4. Checks and hand-over

- [ ] 4.1 `uvx ruff format --check --diff` and `uvx ruff check` from the repo root. Verify: their output.
- [ ] 4.2 Smoke project torn down (`docker compose -p sssd-smoke-acc3 down --volumes`), only that project. Verify: `docker ps -a --filter name=sssd-smoke` empty.
- [ ] 4.3 Sync the delta into `openspec/specs/records/spec.md` when @weber accepts. Verify: `openspec validate owner-names-in-the-search-stack`.
