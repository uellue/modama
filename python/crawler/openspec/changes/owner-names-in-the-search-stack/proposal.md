# Proposal

## Why

A record's `dc:creator` is the owner's user name (records spec, "Dublin Core mapping"). `records.user_name` asks the system's user database (`pwd.getpwuid`) and falls back to the number when it has no name. In the search stack the crawler's container knows only the users of its image, so on staging nearly every record names its owner as a number, for example `10001` instead of `alice` (staging finding F10, `design/field-tests/search-stack-staging-findings.md`). `deploy/` solves the same problem for its services with an `sssd` container that answers name lookups from the institute's directory, through a shared volume of sockets (`ssspipes`). The search stack should do the same, so that the owners' names reach the records, the index and the search. Since the first crawl with names re-indexes nearly every record anyway, the records also take the owner's full name and primary group in this change (201, 202): one full re-index tonight, not two.

Decisions by @weber, 2026-11-12, taken into this change as given:

- **196**: an OpenSpec change here, proposal first, then an independent review, then apply.
- **197**: the test stack talks plain LDAP to the test directory inside the compose network first. "There was a reason the test deployment went to these lengths. I think it was some part of the chain refusing without TLS, I believe it was libpam or sth. So we may try if it works without, but if not you know the fix!" The fix is StartTLS with `deploy/`'s test CA, as `deploy/` does. Our sssd answers name lookups only (nss, no pam); a smoke test decides (design D4).
- **198**: in time for tonight's crawl on staging (19:00 UTC, 2026-11-12).
- **199**: the login name is enough for now; the full name and the organisational group may come later, not in this change. *Superseded the same day by 201 and 202.*
- **200**: it is fine that records, owners' names among them, reach Blablador through AI Mode (already in `design/requirements-pipeline.md`, "Except through the search API's language models").
- **201**: `dc:creator` is the owner's full name alone, the GECOS field of the user database (`pwd.getpwuid(uid).pw_gecos`, for example "Dieter Weber"); the login name when the GECOS field is empty; the number when the uid is unknown. @weber: "full name alone". On an sssd machine `getent passwd weber` gives `weber:*:20335:68100:Dieter Weber:/Users/weber:/bin/bash`; the directory entry has `cn: Dieter Weber` and no `gecos` attribute, so sssd fills GECOS from `cn` (the smoke test shows the same for the test directory: `alice` → `Alice Anderson`, design D10).
- **202**: the owner's primary group name (`grp.getgrgid(pw.pw_gid).gr_name`, for example `erc-1`) goes into the record's description line, next to type, size and folder. @weber: "yes, in the description". Left out when the uid or the gid is unknown.

From the review of 2026-11-12 (`review.md`), decided by the main session, two of them provisional while @weber confirms: the crawl fails when the check user cannot be looked up (finding 5, provisional), the description says `owner's group erc-1` (finding 11, provisional); no cache volume (3); staging's file path fixed (9).

## What Changes

- **An `sssd` service in the search stack** (`docker-compose.yml`), built from `deploy/sssd` as it is (no copy), with an image name of our own (`search-stack-sssd`). At start it copies its configuration file into place with `services = nss` (name lookups only) and mode 600, as `deploy/`'s test deployment copies its file with `install -m 600`. A health check tells when it names the deployment's check user (`SSSD_CHECK_USER`).
- **The crawler image** (`crawler.Dockerfile`) gets `libnss-sss`, which adds `sss` to `passwd` and `group` in `/etc/nsswitch.conf`. `crawler` and `crawl-timer` mount sssd's socket volume read-only and start once sssd is healthy.
- **A crawl stores nothing when the check user cannot be looked up** (design D7, review finding 5): with `SSSD_CHECK_USER` set, the crawl looks it up before it stores; when that fails, the run fails with a message naming it, and the records stay as they were, instead of turning names into numbers.
- **Test stack** (`docker-compose.override.yml`): the test directory server, built from `deploy/ldap` as it is (`search-stack-ldap`), with deploy's four test users (alice 10001, bob 10002, carol 10003 in group `iff`, mallory 10004 in `outsiders`), and sssd's test configuration, `testconf/secrets/sssd.conf` (throwaway values, the test directory's bind account), mounted by the override file itself, so that a secrets folder of one's own (the e2e test's) needs no copy. `./runtest.sh` checks that the crawler names uid 10001 `Alice Anderson` in group `iff`; the end-to-end test makes a file owned by 10001 and checks its record's creator (the crawler's, the warehouse's and the index's) and the group in its description.
- **Staging** (`docker-compose.staging.yml`): sssd reads `/var/local/data-mgmt/sssd.conf`, the file @weber keeps on the server for testing `deploy/` against the real directory. No test directory on staging. The README and the staging runbook give @weber's commands, in order, and say what the first crawl with names costs (D8).
- **The creator is the owner's full name** (201, design D10): `records.owner(uid)` replaces `records.user_name`; the full name is the GECOS field up to its first comma (the passwd(5) convention: full name, then office and phone numbers; Debian's `adduser` writes `,,,` when it has no name), else the login name, else the number.
- **The description names the owner's primary group** (202, D11): `Plain text document, 1 file, 1.2 kB, in notes/, owner's group erc-1`; nothing is added when the uid or the gid is unknown.
- **Specs**: records, "Dublin Core mapping": where the creator comes from, a scenario per case; "Every record carries a description": the group. That requirement is still in the pending change `em-formats-and-extraction` (not archived), so this change is archived after that one (`openspec validate` says so). crawl-runs: the new requirement for the check user.
- **Requirements and decision log**: rows for 201 and 202 in `design/architecture.md`; `design/requirements.md` 2.9 and Q22 say that full names and groups, not only login names, are in the records.

Behaviour towards the user: in every deployment of the crawler, `dc:creator` carries the owner's full name where the user database has one (before: the login name), and `dc:description` ends with the owner's primary group (`, owner's group iff`). In the search stack, both come from the directory through sssd, for every owner it knows (before: the number, and no group); an owner it does not know keeps the number and no group. The search shows the creator (the index's `creators`) and searches the description. A crawl with `SSSD_CHECK_USER` set fails instead of storing when the check user cannot be looked up. On staging, the first crawl after the change changes nearly every record (1,451,848), so the harvest and the indexing that follow take as long as a first full run: about 5 h for the harvest and 8 to 19 h for the indexing (D8). Operators: two more services in the test stack (`ldap`, `sssd`), one more on staging (`sssd`). `modama-crawler records` shows the new creator and description.

Out of scope: other attributes of the directory (`ou`, `departmentNumber`, mail) and the secondary groups; StartTLS in the test stack unless plain LDAP fails (197); `deploy/`'s own sssd and its configuration (not touched); a setting for staging's sssd path (finding 9: a next step if needed); access checks per user (BACKLOG, "Per-user views").

Serves: the records spec's "Dublin Core mapping" (owner as creator), staging finding F10, the decision-log row 2026-11-04 (warehouse inside the institute, owners' names stay internal), Q22 as narrowed; the backlog's "Deployment" (the move of the stack to `deploy/`, which brings the same sssd).

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `records`: "Dublin Core mapping": the creator is the full name, else the login name, else the number, from the system's user database (in the search stack the directory through sssd). "Every record carries a description" (from `em-formats-and-extraction`): the owner's primary group after the folder.
- `crawl-runs`: a crawl stores no records while the user database cannot name its check user.

## Impact

- `prototypes/search-stack/`: `docker-compose.yml` (service `sssd`, volume `ssspipes`, mounts, `SSSD_CHECK_USER` and `depends_on` for `crawler` and `crawl-timer`), `docker-compose.override.yml` (service `ldap`, volume `ldapdata`, sssd's test configuration, sssd waits for the directory), `docker-compose.staging.yml` (sssd's configuration file, the check user), `crawler.Dockerfile` (`libnss-sss`), `testconf/secrets/sssd.conf` (new), `runtest.sh` (services, one check), `test_e2e.py` (the owner test), `README.md`.
- `python/crawler/`: `src/modama_crawler/records.py` (`owner` instead of `user_name`, the group in `description`), `src/modama_crawler/cli.py` (the check before the store), `src/modama_crawler/testing.py` (a fixture with a fixed owner for tests that compare whole descriptions), `tests/test_records.py`, `tests/test_server.py`, `tests/test_cli.py`, `README.md` (the description's example, the creator, `SSSD_CHECK_USER`), the specs (by the deltas), `design/architecture.md`, `design/requirements.md`, `design/field-tests/search-stack-staging-runbook.md`, `BACKLOG.md`.
- `python/modama-formats-em/`: three tests that compare a whole description (`k2is`, `dm`) use that fixture.
- No new Python dependency (`grp` is in the standard library); one Debian package in the crawler image (`libnss-sss`, from trixie, the same sssd release as `deploy/sssd`'s image). `deploy/` is used as build contexts and not changed.
