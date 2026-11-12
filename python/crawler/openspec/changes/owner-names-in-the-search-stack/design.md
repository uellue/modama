# Design

## Context

`records.user_name(uid)` is `pwd.getpwuid(uid).pw_name`, cached per process, with `str(uid)` when the lookup raises `KeyError`. A crawl runs as its own process (`modama-crawler crawl`, started by the timer), so one crawl asks once per owner. The crawler's image knows only the users of `python:3.14-slim-trixie`.

`deploy/` gives its services the institute's users with one `sssd` container (`deploy/sssd`: Debian 13, `sssd` 2.10.1 with `libnss-sss`) whose sockets are in a volume `ssspipes`, mounted at `/var/lib/sss/pipes/` into every service that looks users up; those services have `libnss-sss`, so `getpwuid` asks sssd through the socket. Production mounts `/var/local/data-mgmt/sssd.conf` directly; the test deployment (`docker-compose.override.yml`) copies the file with `install -m 600` at start, because sssd accepts only a root-owned file not readable by others, and waits for its test directory (`deploy/ldap`) to be healthy, because sssd goes offline for a while when it asks too early.

## Decisions

### D1. Reuse `deploy/sssd` and `deploy/ldap` as build contexts, with image names of our own

`build: ../../deploy/sssd`, `image: search-stack-sssd`; `build: ../../deploy/ldap`, `image: search-stack-ldap`. No copy of either Dockerfile, so a fix in `deploy/` reaches both; no `ghcr.io/...:latest` or `iffregistry...` tag, so a build here never replaces the image `deploy/` runs. Against: a change in `deploy/sssd` changes the search stack's sssd without a change here. Accepted: that is what the move to `deploy/` wants anyway.

### D2. One `sssd` service, its sockets mounted read-only into `crawler` and `crawl-timer`

In `docker-compose.yml`, so that test and staging share it. Volume `ssspipes` (the project's own, `search-stack_ssspipes`, not deploy's), mounted `ro` into the two crawler services: they connect to the socket, which works on a read-only mount (smoke test below). Both wait for `sssd` to be healthy (`depends_on: condition: service_healthy`). The crawler image gets `libnss-sss` (`apt-get install --no-install-recommends`), which adds `sss` to `passwd` and `group` in `/etc/nsswitch.conf` (smoke test: `passwd: files sss`). No other service looks users up: the warehouse, the index and the search only see the name in the record.

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

So the test stack's `testconf/secrets/sssd.conf` says `ldap_id_use_start_tls = false` with a comment why, and no test CA is needed. The test directory then runs without a certificate (its entrypoint: "no certificate for ldap, running without StartTLS"). The bind password travels in plain text inside the stack's own network, which only the stack's containers join; it is the test directory's published test value. Staging and production use their own file, with TLS (D6).

### D5. Health check: sssd names a user that must exist

The `deploy/sssd` image has no `sssctl` (`sssd-tools` is not installed), so `sssctl domain-status` is not available without changing `deploy/`. The check is a lookup through sssd's own name service: `getent passwd "$${SSSD_CHECK_USER%%:*}"` (CMD-SHELL; the variable may be a `uid:gid` pair, the part before `:` is used), every 10 s. The deployment says which user: the test stack `10001` (`alice`), staging the user it already names, `STAGING_USER` (@weber, who is in the directory). A lookup that answers means sssd has reached the directory at least once for that user; afterwards the cache keeps it healthy through an outage (D7), which is what the crawler needs too. Against: a lookup per 10 s against the directory. Accepted: sssd answers it from its cache (`entry_cache_timeout`, 90 minutes by default) and asks the directory once per expiry.

### D6. Staging reads `/var/local/data-mgmt/sssd.conf`, overridable

`docker-compose.staging.yml` mounts `${STAGING_SSSD_CONF:-/var/local/data-mgmt/sssd.conf}` at `/sssd.conf.in`, read-only, with `create_host_path: false`, so that a missing file stops the start instead of creating a directory (as R1 of the staging review for the data tree). That is the file @weber keeps on the server for testing `deploy/` against the real directory (`docs/guide/src/development.md`, "Testing against the production LDAP"). The test stack mounts `${MODAMA_SECRETS_DIR}/sssd.conf` in `docker-compose.yml`; staging's mount replaces it (same target), since staging's `MODAMA_SECRETS_DIR` holds the throwaway test secrets. No test directory on staging (it is in the override file only).

Not known here (no access to the server, and the file holds a secret): whether that file names files of its own, for example `ldap_tls_cacert` with a path under `/certs/`. The production template (`deploy/sssd/sssd.conf.template`) has `ldap_tls_reqcert = never` and no CA file. The runbook has @weber check the option names, not the values, before the start (`grep -o '^[a-z_]*' /var/local/data-mgmt/sssd.conf`, which prints no values); a CA file would need one more mount, done then.

### D7. sssd offline or slow: start order, health check, cache in a volume

What a crawl does when sssd cannot answer (smoke test): with the directory stopped and sssd restarted in the same container, owners looked up before are still named (`alice`), from sssd's cache in `/var/lib/sss/db`; an owner never looked up gets no name. With sssd itself stopped, `getpwuid` raises `KeyError` at once (0.000 s), so the crawl writes numbers. A crawl with numbers changes those records' creator, the next crawl with names changes them back: each flip moves the datestamp and is harvested and indexed again.

Guards, the simplest that cover the common cases:

- **Start order and health check** (D2, D5): the crawler services start only when sssd answers, so the first crawl after a start (the timer crawls at once when the last crawl is old) has names.
- **The cache in a volume** `sssd-cache` at `/var/lib/sss/db`: a recreated sssd container (after `--build`, a changed configuration) keeps the names it knew, and serves them while the directory is unreachable. That sssd also serves entries past `entry_cache_timeout` while offline is its documented offline behaviour as we understand it; the smoke test showed it only for fresh entries, task 2.4 checks a recreated container. `deploy/` does not keep its cache either; it does not need to for this reason (its services check logins, not names for records).

What remains: an owner that sssd has never seen, during an outage of the directory, gets the number for that crawl; sssd stopped or crashed (`restart: unless-stopped` brings it back) gives numbers for every owner in a crawl that runs meanwhile; a slow directory delays a crawl's lookups by up to sssd's timeouts, once per owner and crawl (the per-process cache). A guard in the crawler (stop a crawl, or keep the stored creator, when the name service is unavailable) needs a way to tell "no such user" from "sssd unavailable", which `pwd` does not give; proposed as a next step (BACKLOG), not built.

### D8. What the first crawl with names does on staging

Nearly every record's creator changes from the number to the login name, so its content and datestamp change ("The datestamp moves when the record changes"). The harvest after that crawl takes nearly every record again (incremental by datestamp), and the indexing embeds nearly every record again: about as long as the first full harvest and indexing on staging. Records of owners the directory does not know keep the number and their datestamp. The README and the runbook say so, with the check afterwards (`modama-chain status`, a search that shows a login name).

### D9. Tests

- `tests/test_records.py`: one test per scenario of "Dublin Core mapping": Single file (the existing test, with the creator asserted, the current user's name), An owner without a name (`pwd.getpwuid` patched to raise `KeyError` for 4242, `user_name`'s cache cleared).
- `test_e2e.py`, `test_a_changed_record_replaces_the_old_one`: the file's owner changes from root to 10001, and its record's, the warehouse's and the index's creator become `alice` (scenario An owner from the directory). Today it changes to 4242 and checks `4242`; the fallback moves to the unit test above, and the e2e test checks the path through sssd, which nothing else checks.
- `runtest.sh`: `sssd` and `ldap` in the list of services, and one check, "the crawler names uid 10001 alice (through sssd)", with `getent passwd 10001` in `crawler`.

## Risks

- **The real configuration does not work in our container** (a CA file, a host name the stack's network cannot resolve, a firewall rule for the dev server's Docker network): sssd stays unhealthy, `./upstaging.sh` fails after its timeout, and the crawler services do not start, so tonight's crawl would not run. Mitigation: the runbook's check of the option names before the start, and `dc logs sssd` names the failing step; rollback is to start the previous commit, which has no sssd.
- **The bind password reaches a second container** on staging (our sssd, besides deploy's). Same file, same host, same admin; the file is mounted read-only and copied with mode 600 inside the container.
- **Mallory** (`outsiders`) is named too: the access filter of deploy's configuration is a PAM matter, and a name lookup is not access. The record shows whose file it is, as with a number.

## Not now

The full name and the group in the records (199); StartTLS in the test stack (D4 made it unnecessary); `sssd-tools` in deploy's image for a `sssctl` health check; a guard in the crawler for an unavailable name service (D7).
