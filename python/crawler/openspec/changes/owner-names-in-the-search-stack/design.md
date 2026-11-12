# Design

## Context

`records.user_name(uid)` is `pwd.getpwuid(uid).pw_name`, cached per process, with `str(uid)` when the lookup raises `KeyError`; this change replaces it with `records.owner` (D10, D11). A crawl runs as its own process (`modama-crawler crawl`, started by the timer), so one crawl asks once per owner. The crawler's image knows only the users of `python:3.14-slim-trixie`. `store` rebuilds every record on every crawl (`store.py`), so a change of the mapping reaches every record at the next crawl, and so does a rollback.

`deploy/` gives its services the institute's users with one `sssd` container (`deploy/sssd`: Debian 13, `sssd` 2.10.1 with `libnss-sss`) whose sockets are in a volume `ssspipes`, mounted at `/var/lib/sss/pipes/` into every service that looks users up; those services have `libnss-sss`, so `getpwuid` asks sssd through the socket. Production mounts `/var/local/data-mgmt/sssd.conf` directly; the test deployment (`docker-compose.override.yml`) copies the file with `install -m 600` at start, because sssd accepts only a root-owned file not readable by others, and waits for its test directory (`deploy/ldap`) to be healthy, because sssd goes offline for a while when it asks too early.

The review of the proposal (`review.md`, 17 findings) is folded in below; each decision names its finding.

## Decisions

### D1. Reuse `deploy/sssd` and `deploy/ldap` as build contexts, with image names of our own

`build: ../../deploy/sssd`, `image: search-stack-sssd`; `build: ../../deploy/ldap`, `image: search-stack-ldap`. No copy of either Dockerfile, so a fix in `deploy/` reaches both; no `ghcr.io/...:latest` or `iffregistry...` tag, so a build here never replaces the image `deploy/` runs. Against: a change in `deploy/sssd` changes the search stack's sssd without a change here. Accepted: that is what the move to `deploy/` wants anyway.

### D2. One `sssd` service, its sockets mounted read-only into `crawler` and `crawl-timer`

In `docker-compose.yml`, so that test and staging share it; `sssd` and `ldap` join the stack's network `search`, as every service does (finding 15; the smoke test used its project's `default`). Volume `ssspipes` (the project's own, `search-stack_ssspipes`, not deploy's), mounted `ro` into the two crawler services: they connect to the socket, which works on a read-only mount (smoke test below). Both wait for `sssd` to be healthy (`depends_on: condition: service_healthy`). The crawler image gets `libnss-sss` (`apt-get install --no-install-recommends`), which adds `sss` to `passwd` and `group` in `/etc/nsswitch.conf` (smoke test: `passwd: files sss`). No other service looks users up: the warehouse, the index and the search only see the name in the record.

### D3. The configuration is copied at start, as a name service only

The service mounts its configuration file at `/sssd.conf.in` and starts with

```sh
umask 077 && sed -E 's/^services *=.*/services = nss/' /sssd.conf.in > /etc/sssd/sssd.conf && exec /usr/sbin/sssd --interactive
```

`umask 077` makes the copy mode 600, owned by root, which sssd demands. The `sed` turns any `services` line into `services = nss`: the crawler only asks for names, so the PAM responder, which a configuration made for `deploy/` lists, is not started. The rest of the file is used as it is (domain, `ldap_uri`, bind account, TLS options). Against: a rewrite of an operator's file is a surprise. Accepted for one line, which the comment in the compose file and the README name; the alternative, a second hand-made configuration on the server, duplicates the bind password.

### D4. Plain LDAP in the test stack: works, with `ldap_id_use_start_tls = false` said explicitly (197)

Smoke test (2026-11-12, a compose project of its own, `sssd-smoke-acc3`, no published ports: `deploy/ldap`, `deploy/sssd`, and `python:3.14-slim-trixie` with `libnss-sss`, running as uid 1000 with the sockets mounted read-only):

- Without the StartTLS option, sssd 2.10.1 starts TLS on its own and fails, `START TLS result: Protocol error(2), unsupported extended operation`, then `Failed to connect, going offline`; `getent passwd 10001` finds nothing. This is the part of the chain that refuses without TLS (197): not PAM, but sssd itself, which in this release uses StartTLS for the bind with a password unless told not to.
- With `ldap_id_use_start_tls = false` in the domain: `getent passwd 10001` gives `alice:*:10001:10000:Alice Anderson:/home/alice:/bin/bash`, and `python -c 'import pwd; print(pwd.getpwuid(10001).pw_name)'` gives `alice`; 10002 to 10004 give `bob`, `carol`, `mallory`; 4242 raises `KeyError` (the crawler then writes `4242`).

So the test stack's `testconf/secrets/sssd.conf` says `ldap_id_use_start_tls = false` with a comment why, and no test CA is needed. The test directory then runs without a certificate (its entrypoint: "no certificate for ldap, running without StartTLS"). The bind password travels in plain text inside the stack's own network, which only the stack's containers join; it is the test directory's published test value.

### D5. Health check: sssd names a user that must exist

The `deploy/sssd` image has no `sssctl` (`sssd-tools` is not installed), so `sssctl domain-status` is not available without changing `deploy/`. The check is a lookup through sssd's own name service: `getent passwd "$${SSSD_CHECK_USER%%:*}"` (CMD-SHELL; the variable may be a `uid:gid` pair, the part before `:` is used), every 10 s, with `start_period: 120s`, because sssd stays offline for 60 s after a failed first contact (`ldap_offline_timeout`, finding 4). The deployment says which user: the test stack `10001` (`alice`), staging the user it already names, `STAGING_USER` (@weber, who is in the directory). The crawler gets the same variable for its own check (D7). A lookup that answers means sssd has reached the directory at least once for that user; afterwards its cache keeps it healthy through a short outage. Against: a lookup per 10 s. Accepted: sssd answers it from its cache (`entry_cache_timeout`, 90 minutes by default) and asks the directory once per expiry.

### D6. The configuration file: the override mounts the test one, staging `/var/local/data-mgmt/sssd.conf`

The base file mounts no configuration (finding 1: a mount from `${MODAMA_SECRETS_DIR}` breaks a secrets folder of one's own, such as the e2e test's `~/.config/modama/e2e-secrets`, which has no `sssd.conf`; Docker then makes a directory and sssd never starts). `docker-compose.override.yml` mounts `./testconf/secrets/sssd.conf`, next to the `ldap` service it points at. `docker-compose.staging.yml` mounts `/var/local/data-mgmt/sssd.conf` (fixed, finding 9: no setting without a requester), read-only, long syntax with `create_host_path: false`, so that a missing file stops the start instead of creating a directory (smoke test: `bind source path does not exist`, as R1 of the staging review for the data tree). That is the file @weber keeps on the server for testing `deploy/` against the real directory (`docs/guide/src/development.md`, "Testing against the production LDAP"). No test directory on staging (it is in the override file only).

Not known here (no access to the server, and the file holds a secret): whether that file names files of its own, for example `ldap_tls_cacert` with a path under `/certs/`. The production template (`deploy/sssd/sssd.conf.template`) has `ldap_tls_reqcert = never` and no CA file. The runbook has @weber check the option names, not the values, before the start (`sudo grep -o '^[a-z_]*' /var/local/data-mgmt/sssd.conf`, which prints no values); a CA file would need one more mount, done then.

### D7. sssd offline or slow: start order, health check, and a check in the crawl

What a crawl does when sssd cannot answer (smoke test): with the directory stopped and sssd restarted in the same container, owners looked up before are still named (`alice`), from sssd's cache in `/var/lib/sss/db`, which lives in the container's layer and survives a restart, not a recreated container; an owner never looked up gets no name. With sssd itself stopped, `getpwuid` raises `KeyError` at once (0.000 s), so a crawl would write numbers. A crawl with numbers changes those records' creator, the next crawl with names changes them back: each flip moves the datestamp and is harvested and indexed again, on staging a full re-index each time (D8).

Guards:

- **Start order and health check** (D2, D5): the crawler services start only when sssd answers, so the first crawl after a start (the timer crawls at once when the last finished crawl is more than a day old) has names.
- **The crawl checks the check user before it stores** (finding 5, provisional decision of the main session while @weber confirms; @weber's principle "the same data gives the same result or a failure"): with `SSSD_CHECK_USER` set, `crawl_tree` looks the uid up with `pwd.getpwuid` after the walk and the extraction, right before `store`. The check user must exist, so a failure means the name service is down: the crawl raises, its run is recorded as `failed` with the message `the user database does not know SSSD_CHECK_USER <uid>; is sssd running? No records stored`, and the stored records stay as they were. The timer crawls again at the next 19:00. A value that is not a uid stops the crawl before its run is recorded, like the other settings. Without the setting (a developer's machine, CI) nothing is checked. The configuration is the health check's variable, no second one.
- **No cache volume** (finding 3): `/var/lib/sss/db` also holds `config.ldb` with the bind password (the reviewer's `grep -c` in the smoke container: 1), which a volume would keep as a third persistent copy of the real secret on staging, beyond `./downstaging.sh`. The smoke test showed that a cache volume keeps the names across a recreated container while the directory is down; the check in the crawl covers the case it would cover.

What remains: lookups are made during the store, after the check, so an outage that begins in the seconds between the check and the end of the store gives numbers for the owners looked up after it; an owner that sssd has never seen, during an outage of the directory while sssd itself answers, gets the number; a slow directory delays a crawl's lookups by up to sssd's timeouts, once per owner and crawl (the per-process cache). After a crawl, the runbook counts the records with a number as creator (D8).

### D8. What the first crawl with names does on staging (finding 2)

Nearly every record's creator changes from the number to the full name, and its description gains the group, so its content and datestamp change ("The datestamp moves when the record changes"). Staging's last full crawl (run 3, findings F16, F17) had 1,451,848 records. The harvest after the crawl takes all changed records again (incremental by datestamp): run 3's full harvest took 5 h 14 min. The indexing then embeds them again, in 726 batches of 2,000: at the rate seen after the default worker's restart in run 3 (about 14 batches per 10 minutes) about 8 to 9 h, at run 3's slow rate (4.5 per 10 minutes) about 27 h. Since then the broker's acknowledgement timeout (F17), the CPU budget and the one-validator patch changed the indexing, not measured on staging yet. So tonight: the crawl from 19:00 (run 3: 1 h 17 min), the harvest to about 01:30, the indexing to mid-morning tomorrow at best; at the slow rate it runs into tomorrow's 19:00 crawl. A rollback after 19:00 costs another full re-index, since every crawl rebuilds every record. Records of owners the directory does not know keep the number and their datestamp. The README and the runbook say so, with the checks before (`owner(<uid>)` in the crawler) and after (`modama-chain status`, the count of records with a number as creator).

### D9. Tests

- `tests/test_records.py`: one test per scenario of "Dublin Core mapping" and of the description's group, with a user database of the test's own (`pwd.getpwuid` and `grp.getgrgid` patched, `owner`'s cache cleared around each): Single file (`alice`, `Alice Anderson`, `iff`), An owner without a full name (GECOS empty, `,,,`, ` ,room 1`), A full name with a comma (`Weber, Dieter` → `Weber`, finding 12), An owner without a name (`KeyError` for 4242), A file without an extractor (`, owner's group erc-1`), An owner without a known group (uid unknown; gid without a name).
- The tests that compare a whole description (`test_records.py`, `test_server.py`, and three in `modama-formats-em`) take a fixture `fixed_owner` from `modama_crawler.testing` (the pytest plugin, which the EM tests load too; explicit, not autouse; finding 6): it replaces `records.owner` by one that gives `Alice Anderson` and `erc-1` for any uid, so the expected strings are literal and the same in the VM (`dev`, empty GECOS), in CI and in the stack's image (root).
- `tests/test_cli.py`: one test per scenario of the crawl-runs requirement (The name service is down, The name service answers, Not a uid).
- `test_e2e.py`, `test_a_changed_record_replaces_the_old_one`: the file's owner changes from root to 10001, and its record's, the warehouse's and the index's creator become `Alice Anderson`, and the description ends in `, owner's group iff` (scenario An owner from the directory). Today it changes to 4242 and checks `4242`; the fallback moves to the unit test above, and the e2e test checks the path through sssd, which nothing else checks. Before the change the creator is `root` (root's GECOS in the image is `root`) and the group `root`.
- `runtest.sh`: `sssd` and `ldap` in the list of services, and one check, "the crawler names uid 10001 Alice Anderson, group iff (through sssd)".

### D10. The creator: GECOS up to its first comma, else the login name, else the number (201)

`records.owner(uid)` (cached per process, as `user_name` was) returns the creator and the group name. The creator is `pw_gecos.split(",")[0].strip()`, else `pw_name`, else `str(uid)`. Up to the first comma because that is the GECOS field's convention (passwd(5): the full name, then office, phones; `chfn` writes it so), and Debian's `adduser` writes `,,,` for a user without a name, which would otherwise be the creator. Evidence for sssd: it fills GECOS from `cn` when the entry has no `gecos` attribute (@weber's entry, and the smoke test: `pwd.getpwuid(10001).pw_gecos` is `'Alice Anderson'` from `cn: Alice Anderson`, the entry has no `gecos`; `mallory` gives `'Mallory Miller'`). Against: a directory whose `cn` holds a comma ("Weber, Dieter") loses the given name; a unit test shows it (finding 12). Accepted for now: FreeIPA's `cn` is "Given Family", and the alternative, the whole field, puts `,,,` and phone numbers into records.

### D11. The group in the description (202)

`description` appends `owner's group <name>` after the folder, as one more comma-separated part: `Plain text document, 1 file, 1.2 kB, in notes/, owner's group erc-1`; with extracted values first as before. "owner's group", not "group", so that it does not read as the file's group (finding 11, provisional while @weber confirms; `/CONTEXT.md` lists "Group" under _Avoid_ for a project, and has no entry for a user's primary group: one is proposed in the hand-over). The group is the owner's primary group (`grp.getgrgid(pw.pw_gid).gr_name`), not the file's group: it names the people the owner belongs to, which the file's group, often a project group or the user's own, does not. Smoke test: 10001 → gid 10000 → `iff`, 10004 → 10100 → `outsiders`. Left out when `getpwuid` or `getgrgid` raises `KeyError`. The search's keyword leg searches the description, so a search for the group finds the group's records (not tested; the e2e test checks the description in the crawler's record only).

## Risks

- **The real configuration does not work in our container** (a CA file, a host name the stack's network cannot resolve, a firewall rule for the dev server's Docker network): sssd stays unhealthy, `./upstaging.sh` fails after its timeout, and the crawler services do not start, so tonight's crawl would not run. Mitigation: the runbook's check of the option names before the start, and `dc logs sssd` names the failing step; rollback is to start the previous commit, which has no sssd (and, after 19:00, a full re-index, D8).
- **The bind password reaches a second container** on staging (our sssd, besides deploy's). Same file, same host, same admin; the file is mounted read-only and copied with mode 600 inside the container; no volume keeps a copy (D7).
- **"With TLS" is not much protection for the bind password** on staging: the production template has `ldap_tls_reqcert = never`, so the server's certificate is not checked (finding 14). That is `deploy/`'s practice, which this change takes over and does not fix.
- **sssd's private socket**: `/var/lib/sss/pipes/private/sbus-master` is `srw------- root`; in the test stack the crawler runs as root and could reach it through the shared volume (read-only mounts do not stop a socket connect). On staging the crawler runs as `STAGING_USER` and cannot (finding 13).
- **Mallory** (`outsiders`) is named too: the access filter of deploy's configuration is a PAM matter, and a name lookup is not access. The record shows whose file it is, as with a number.
- **Full names and groups are more personal than login names.** Within what the decision log (2026-11-04, records stay inside the institute) and 200 (Blablador) accept; 201 and 202 are @weber's decisions, recorded in the decision log and in `design/requirements.md` (2.9, Q22) by this change (finding 7).
- **Outside the search stack** (a developer's machine, CI) the creator changes from the login name to the full name where the user database has one, and every description gains a group.

## Not now

Other directory attributes (`ou`, `departmentNumber`, mail) and secondary groups (201, 202 take the full name and the primary group only); StartTLS in the test stack (D4 made it unnecessary); `sssd-tools` in deploy's image for a `sssctl` health check; a setting for staging's sssd path (finding 9).
