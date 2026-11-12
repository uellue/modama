# Proposal

## Why

A record's `dc:creator` is the owner's user name (records spec, "Dublin Core mapping"). `records.user_name` asks the system's user database (`pwd.getpwuid`) and falls back to the number when it has no name. In the search stack the crawler's container knows only the users of its image, so on staging nearly every record names its owner as a number (for example `10001` instead of `alice`). `deploy/` solves the same problem for its services with an `sssd` container that answers name lookups from the institute's directory, through a shared volume of sockets (`ssspipes`). The search stack should do the same, so that the owners' login names reach the records, the index and the search.

Decisions by @weber, 2026-11-12, taken into this change as given:

- **196**: an OpenSpec change here, proposal first, then an independent review, then apply.
- **197**: the test stack talks plain LDAP to the test directory inside the compose network first. "There was a reason the test deployment went to these lengths. I think it was some part of the chain refusing without TLS, I believe it was libpam or sth. So we may try if it works without, but if not you know the fix!" The fix is StartTLS with `deploy/`'s test CA, as `deploy/` does. Our sssd answers name lookups only (nss, no pam); a smoke test decides (design D4).
- **198**: in time for tonight's crawl on staging (19:00 UTC, 2026-11-12).
- **199**: the login name is enough for now; the full name and the organisational group may come later, not in this change.
- **200**: it is fine that records, owners' names among them, reach Blablador through AI Mode (already in `design/requirements-pipeline.md`, "Except through the search API's language models").

## What Changes

- **An `sssd` service in the search stack** (`docker-compose.yml`), built from `deploy/sssd` as it is (no copy), with an image name of our own (`search-stack-sssd`). At start it copies its configuration file into place with `services = nss` (name lookups only) and mode 600, as `deploy/`'s test deployment copies its file with `install -m 600`. A health check tells when it answers.
- **The crawler image** (`crawler.Dockerfile`) gets `libnss-sss`, which adds `sss` to `passwd` and `group` in `/etc/nsswitch.conf`. `crawler` and `crawl-timer` mount sssd's socket volume read-only and start once sssd is healthy.
- **sssd keeps its cache in a volume**, so that a restarted sssd still names the owners it has seen while the directory is unreachable (design D7).
- **Test stack** (`docker-compose.override.yml`): the test directory server, built from `deploy/ldap` as it is (`search-stack-ldap`), with deploy's four test users (alice 10001, bob 10002, carol 10003, mallory 10004), and sssd's test configuration in `testconf/secrets/sssd.conf` (throwaway values, the test directory's bind account). `./runtest.sh` checks that the crawler names uid 10001 `alice`; the end-to-end test makes a file owned by 10001 and checks that its record's creator, the warehouse's and the index's, is `alice`.
- **Staging** (`docker-compose.staging.yml`): sssd reads `/var/local/data-mgmt/sssd.conf`, the file @weber keeps on the server for testing `deploy/` against the real directory; `STAGING_SSSD_CONF` in `staging.env` sets another path. No test directory on staging. The README and the staging runbook give @weber's commands, and say what the first crawl with names does: nearly every record's creator changes, so the harvest takes and indexes nearly every record again.
- **Records spec**: the requirement "Dublin Core mapping" says where the name comes from and what a record carries when there is none (the number, as the code does today), with a scenario each.

Behaviour towards the user: in the search stack, `dc:creator` (and the index's `creators`, which the search shows) carries the owner's login name instead of the number, for every owner the directory knows; an owner it does not know keeps the number, as today. On staging, the first crawl after the change re-dates nearly every record, so that harvest and indexing take about as long as a first full run. Operators: two more services in the test stack (`ldap`, `sssd`), one more on staging (`sssd`), and one more optional setting in `staging.env`. The crawler's code and its output format do not change.

Out of scope: the full name (`cn`) and the organisational group as record fields (199); StartTLS in the test stack unless plain LDAP fails (197); `deploy/`'s own sssd and its configuration (not touched); a guard in the crawler against a crawl with numbers during an outage of sssd (design D7, "What remains", proposed as a next step); access checks per user (BACKLOG, "Per-user views").

Serves: the records spec's "Dublin Core mapping" (owner's user name as creator), the decision-log row 2026-11-04 (warehouse inside the institute, owners' names stay internal), Q22 as narrowed; the backlog's "Deployment" (the move of the stack to `deploy/`, which brings the same sssd).

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `records`: "Dublin Core mapping" names the source of the creator's name (the system's user database, in the search stack the directory through sssd) and the fallback to the number.

## Impact

- `prototypes/search-stack/`: `docker-compose.yml` (service `sssd`, volumes `ssspipes` and `sssd-cache`, mounts and `depends_on` for `crawler` and `crawl-timer`), `docker-compose.override.yml` (service `ldap`, volume `ldapdata`, sssd waits for it), `docker-compose.staging.yml` (sssd's configuration file), `crawler.Dockerfile` (`libnss-sss`), `testconf/secrets/sssd.conf` (new), `runtest.sh` (services, one check), `test_e2e.py` (the owner test), `README.md`.
- `python/crawler/`: `openspec/specs/records/spec.md` (by the delta), `tests/test_records.py` (one test per scenario), `design/field-tests/search-stack-staging-runbook.md`, `BACKLOG.md`.
- No crawler code changes. No new Python dependency; one Debian package in the crawler image (`libnss-sss`, from trixie, the same sssd release as `deploy/sssd`'s image). `deploy/` is used as build contexts and not changed.
