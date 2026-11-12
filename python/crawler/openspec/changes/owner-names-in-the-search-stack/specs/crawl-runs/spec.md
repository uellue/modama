## ADDED Requirements

### Requirement: A crawl stores no records while the user database cannot name its check user
When `SSSD_CHECK_USER` is set (a uid, or `uid:gid`), a crawl SHALL look that uid up in the user database before it stores its records; when the lookup fails, the crawl SHALL store nothing, record its run as `failed` with a message that names the check user, and exit with a non-zero status. A value that is not a uid SHALL stop the crawl before its run is recorded. Without the setting, the crawl SHALL not check (design D7, review finding 5).

#### Scenario: The name service is down
- **WHEN** `SSSD_CHECK_USER` names a uid the user database does not know, and a crawl runs on a tree whose records are stored
- **THEN** the run has outcome `failed` with a message naming that uid, the crawl exits with a non-zero status, and no record was changed

#### Scenario: The name service answers
- **WHEN** `SSSD_CHECK_USER` is `<uid>:<gid>` of the user running the crawl
- **THEN** the crawl finishes and stores its records

#### Scenario: Not a uid
- **WHEN** `SSSD_CHECK_USER` is `alice`
- **THEN** the crawl exits with status 2 and a message naming the setting, and no run is recorded
