# Proposal

## Why

A record's `dc:creator` is the owner's user name (records spec, "Dublin Core mapping"). `records.user_name` asks the system's user database (`pwd.getpwuid`) and falls back to the number when it has no name. In the search stack the crawler's container knows only the users of its image, so on staging nearly every record names its owner as a number (for example `10001` instead of `alice`). `deploy/` solves the same problem for its services with an `sssd` container that answers name lookups from the institute's directory, through a shared volume of sockets (`ssspipes`). The search stack should do the same, so that the owners' names reach the records, the index and the search; and since the first crawl with names re-indexes nearly every record anyway, the records take the owner's full name and primary group in the same change (201, 202), so that there is one full re-index tonight, not two.

Decisions by @weber, 2026-11-12, taken into this change as given:

- **196**: an OpenSpec change here, proposal first, then an independent review, then apply.
- **197**: the test stack talks plain LDAP to the test directory inside the compose network first. "There was a reason the test deployment went to these lengths. I think it was some part of the chain refusing without TLS, I believe it was libpam or sth. So we may try if it works without, but if not you know the fix!" The fix is StartTLS with `deploy/`'s test CA, as `deploy/` does. Our sssd answers name lookups only (nss, no pam); a smoke test decides (design D4).
- **198**: in time for tonight's crawl on staging (19:00 UTC, 2026-11-12).
- **199**: the login name is enough for now; the full name and the organisational group may come later, not in this change. *Superseded the same day by 201 and 202.*
- **200**: it is fine that records, owners' names among them, reach Blablador through AI Mode (already in `design/requirements-pipeline.md`, "Except through the search API's language models").
- **201**: `dc:creator` is the owner's full name alone, the GECOS field of the user database (`pwd.getpwuid(uid).pw_gecos`, for example "Dieter Weber"); the login name when the GECOS field is empty; the number when the uid is unknown. @weber: "full name alone". On an sssd machine `getent passwd weber` gives `weber:*:20335:68100:Dieter Weber:/Users/weber:/bin/bash`; the directory entry has `cn: Dieter Weber` and no `gecos` attribute, so sssd fills GECOS from `cn` (the smoke test shows the same for the test directory: `alice` → `Alice Anderson`, design D10).
- **202**: the owner's primary group name (`grp.getgrgid(pw.pw_gid).gr_name`, for example `erc-1`) goes into the record's description line, next to type, size and folder. @weber: "yes, in the description". Left out when the uid or the gid is unknown.

## What Changes

- **An `sssd` service in the search stack** (`docker-compose.yml`), built from `deploy/sssd` as it is (no copy), with an image name of our own (`search-stack-sssd`). At start it copies its configuration file into place with `services = nss` (name lookups only) and mode 600, as `deploy/`'s test deployment copies its file with `install -m 600`. A health check tells when it answers.
- **The crawler image** (`crawler.Dockerfile`) gets `libnss-sss`, which adds `sss` to `passwd` and `group` in `/etc/nsswitch.conf`. `crawler` and `crawl-timer` mount sssd's socket volume read-only and start once sssd is healthy.
- **sssd keeps its cache in a volume**, so that a restarted sssd still names the owners it has seen while the directory is unreachable (design D7).
- **Test stack** (`docker-compose.override.yml`): the test directory server, built from `deploy/ldap` as it is (`search-stack-ldap`), with deploy's four test users (alice 10001, bob 10002, carol 10003, mallory 10004), and sssd's test configuration in `testconf/secrets/sssd.conf` (throwaway values, the test directory's bind account). `./runtest.sh` checks that the crawler names uid 10001 `alice`; the end-to-end test makes a file owned by 10001 and checks that its record's creator, the warehouse's and the index's, is `alice`.
- **Staging** (`docker-compose.staging.yml`): sssd reads `/var/local/data-mgmt/sssd.conf`, the file @weber keeps on the server for testing `deploy/` against the real directory; `STAGING_SSSD_CONF` in `staging.env` sets another path. No test directory on staging. The README and the staging runbook give @weber's commands, and say what the first crawl with names does: nearly every record's creator changes, so the harvest takes and indexes nearly every record again.
- **The creator is the owner's full name** (201, design D10): `records.owner(uid)` replaces `records.user_name`; the full name is the GECOS field up to its first comma (the passwd(5) convention: full name, then office and phone numbers; Debian's `adduser` writes `,,,` when it has no name), else the login name, else the number.
- **The description names the owner's primary group** (202, D11): `Plain text document, 1 file, 1.2 kB, in notes/, group erc-1`; nothing is added when the uid or the gid is unknown.
- **Records spec**: "Dublin Core mapping" says where the creator comes from, with a scenario per case (full name, login name, number, the directory in the search stack); "Every record carries a description" gets the group. That requirement is still in the pending change `em-formats-and-extraction` (not archived), so this change is archived after that one (`openspec validate` says so).

Behaviour towards the user: in every deployment of the crawler, `dc:creator` carries the owner's full name where the user database has one (before: the login name), and `dc:description` ends with the owner's primary group (`, group iff`). In the search stack, both come from the directory through sssd, for every owner it knows (before: the number, and no group); an owner it does not know keeps the number and no group. The search shows the creator (the index's `creators`) and searches the description. On staging, the first crawl after the change re-dates nearly every record, so that harvest and indexing take about as long as a first full run. Operators: two more services in the test stack (`ldap`, `sssd`), one more on staging (`sssd`), and one more optional setting in `staging.env`. `modama-crawler records` shows the new creator and description.

Out of scope: other attributes of the directory (`ou`, `departmentNumber`, mail) and the secondary groups; StartTLS in the test stack unless plain LDAP fails (197); `deploy/`'s own sssd and its configuration (not touched); a guard in the crawler against a crawl with numbers during an outage of sssd (design D7, "What remains", proposed as a next step); access checks per user (BACKLOG, "Per-user views").

Serves: the records spec's "Dublin Core mapping" (owner's user name as creator), the decision-log row 2026-11-04 (warehouse inside the institute, owners' names stay internal), Q22 as narrowed; the backlog's "Deployment" (the move of the stack to `deploy/`, which brings the same sssd).

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `records`: "Dublin Core mapping": the creator is the full name, else the login name, else the number, from the system's user database (in the search stack the directory through sssd). "Every record carries a description" (from `em-formats-and-extraction`): the owner's primary group after the folder.

## Impact

- `prototypes/search-stack/`: `docker-compose.yml` (service `sssd`, volumes `ssspipes` and `sssd-cache`, mounts and `depends_on` for `crawler` and `crawl-timer`), `docker-compose.override.yml` (service `ldap`, volume `ldapdata`, sssd waits for it), `docker-compose.staging.yml` (sssd's configuration file), `crawler.Dockerfile` (`libnss-sss`), `testconf/secrets/sssd.conf` (new), `runtest.sh` (services, one check), `test_e2e.py` (the owner test), `README.md`.
- `python/crawler/`: `src/modama_crawler/records.py` (`owner` instead of `user_name`, the group in `description`), `tests/test_records.py` and `tests/test_server.py` (one test per scenario, the expected descriptions), `README.md` (the description's example, the creator), `openspec/specs/records/spec.md` (by the delta), `design/field-tests/search-stack-staging-runbook.md`, `BACKLOG.md`.
- `python/modama-formats-em/`: three tests that compare a whole description (`k2is`, `dm`) expect the group of the user running them.
- No new Python dependency (`grp` is in the standard library); one Debian package in the crawler image (`libnss-sss`, from trixie, the same sssd release as `deploy/sssd`'s image). `deploy/` is used as build contexts and not changed.
