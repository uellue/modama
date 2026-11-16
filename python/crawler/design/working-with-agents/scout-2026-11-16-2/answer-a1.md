Four answers follow. Each has up to five candidates, most fitting first, then a short verdict.

---

## C1: Path exclusion file for a tree walker

| # | Candidate | Why it fits | Where the fit breaks |
|---|---|---|---|
| 1 | **gitignore pattern syntax** (implementations: Python `pathspec` with `gitwildmatch`, Rust `ignore` crate) | It covers every requirement: wildcards, `**`, a leading `/` to anchor, a pattern without `/` matches at any depth, `!` re-includes, and the last matching entry wins. Git also layers several sources (`core.excludesFile`, `info/exclude`, per-directory files). | `!` cannot bring back a path inside a directory that is already excluded. For "skip entirely" this is actually the right behaviour, because it lets the walk prune, but users trip over it. Git also has no built-in notion of "package defaults". |
| 2 | **ripgrep/fd ignore layering** (`.ignore`, `.rgignore`, global ignore file, all via the `ignore` crate) | Same syntax as gitignore, plus a defined precedence order across several ignore sources. That maps well to "package defaults + operator additions". | It is tied to that tool family and is Rust only. The precedence rules are about per-directory files, not package-provided lists. |
| 3 | **rsync filter rules** (`--filter`, `.rsync-filter` merge files) | Built for walks that prune whole trees. It has include and exclude, anchoring with `/`, `**`/`***`, and merge files from several sources. | The **first** match wins, not the last. The syntax (`- `, `+ `, `:`, modifiers) is more arcane than gitignore. |
| 4 | **.dockerignore** | A plain file kept next to the deployment, with `!` re-inclusion and last-match-wins. | All patterns are relative to the root, so there is no "match at any depth" without `**/`. There is one file only, and Go `filepath.Match` semantics differ in small ways from gitignore. |
| 5 | **MANIFEST.in** (setuptools: `prune`, `graft`, `exclude`, `recursive-exclude`) | Ordered include/exclude commands where later lines override earlier ones, and `prune` drops whole subtrees. | It uses a command syntax, not a pattern list. Anchoring and depth are expressed through the command type, not the pattern. |

**Verdict:** Use gitignore semantics; don't design a new syntax. Build the effective list by concatenating, in order:
1. package-proposed defaults (e.g. discovered through entry points),
2. the operator's file.

Because the last match wins, operators can add exclusions and can also undo package defaults with `!`. Document the "can't re-include under an excluded directory" rule explicitly. *Dependency flag:* `pathspec` (Python) or `ignore` (Rust) would be new third-party dependencies.

---

## C2: Enable/disable plugin handlers by (group, name)

| # | Candidate | Why it fits | Where the fit breaks |
|---|---|---|---|
| 1 | **Ruff/Flake8 rule selection** (`select`, `extend-select`, `ignore`, `extend-ignore`) | It is exactly "whole groups or single items, a default set, exceptions in both directions". Python developers already read it fluently, and it lives in a TOML config. | Its IDs are prefix codes (`E`, `E501`), not (group, name) pairs. You have to state the conflict rule yourself; Ruff uses "more specific wins". |
| 2 | **Pylint `enable` / `disable`** (by category, by message, `all`) | Allows `disable=all` then `enable=X`, or the reverse. It accepts both symbolic names and categories, and is widely known. | Order and precedence across the two options are less obvious than in Ruff. Categories are fixed, not contributed by plugins. |
| 3 | **systemd preset files** (`enable`/`disable` lines with globs; vendor presets plus admin overrides) | Packages ship default enable/disable decisions and the administrator overrides them in their own file. This is the closest *structural* match for "packages propose, installation decides". | It is flat (unit names, no group level) and first-match-wins. It is applied at install time, not read at runtime. |
| 4 | **Python entry points** (`importlib.metadata`, group + name) | The native (group, name) identity for handlers in separately installed packages. Use it for *discovery*. | It only discovers; it has no activation or selection layer, so it must be combined with 1 or 2. |
| 5 | **Hierarchical log filters** (Rust `tracing` `EnvFilter` such as `info,crate::mod=off`; Python `logging` logger hierarchy) | Prefix-level defaults with per-leaf overrides in both directions, and well-defined "most specific wins" semantics. | Levels are not booleans. Developers associate the syntax with logging, not feature activation. |

**Verdict:** Discover handlers via entry points (e.g. `group:name`). Select them with Ruff-style keys in the installation's config:

```toml
[handlers]
select = ["io", "filters:median"]
ignore = ["io:legacy_ser"]
```

Write down one precedence rule: more specific beats less specific, and at equal specificity `ignore` wins.

---

## C3: Search across millions of in-place files (content, owner, kind, date, natural language)

| # | Candidate | Why it fits | Where the fit breaks |
|---|---|---|---|
| 1 | **Managed enterprise search with a file-share connector** (e.g. Microsoft 365 Copilot/Graph connector for file shares, Glean) | Indexes files in place, is permission-aware, supports natural-language queries, returns links, and the vendor runs it. | Content gets copied into a cloud index, which is a data-governance and sovereignty question for a research centre. There are cost and connector scale limits; check current limits, I have not verified them. It cannot read EM formats (`.dm4`, `.emd`, `.mrc`, …). |
| 2 | **OpenSearch/Elasticsearch + FSCrawler** (Apache Tika for extraction) | Open source, crawls in place, extracts content plus owner, type and mtime. Vector/semantic search is available for natural-language queries. | You operate a search cluster, which is exactly what the team wants to avoid. Permission trimming and natural-language/RAG are extra work. |
| 3 | **GUFI** (LANL Grand Unified File Index) or **Robinhood** (Lustre/HPC policy engine) | Built for metadata queries (owner, kind, size, date) over very large shared filesystems. GUFI respects POSIX permissions. | Metadata only: no content search and no natural language. |
| 4 | **Filesystem-native indexing** (Windows Search on a Windows file server; Spotlight on macOS servers) | No new system to build. Integrates into Explorer or Finder and respects access control lists (ACLs). | Platform-bound, opaque at this scale, and no real natural-language support. Unlikely to fit a Linux or GPFS backend. |
| 5 | **Research data management / catalogue layer** (iRODS metadata catalogue, or a data repository using metadata extracted with RosettaSciIO/HyperSpy) | Handles domain metadata (instrument, mode, sample) that generic tools can't extract from EM files. | It is a system in its own right. iRODS usually wants to own the data path, which conflicts with "files stay where they are". |

**Verdict:** Nothing off the shelf covers all of it: in place, millions of files, content plus natural language, near-zero maintenance, permission trimming across groups, *and* EM formats. A realistic split:
- a metadata index (3, or the storage system's own policy engine) for who, kind and date;
- one search service (1 if data policy allows, otherwise 2) for content and natural language.

A small custom extractor for EM metadata is probably unavoidable.

---

## C4: Cross-platform network file access with institute accounts

| # | Candidate | Why it fits | Where the fit breaks |
|---|---|---|---|
| 1 | **SMB 3 with Kerberos/AD auth** (Windows Server or Samba) | Native in Explorer, Finder, and GNOME/KDE (gvfs/kio), with single sign-on through institute accounts. Read and write work out of the box. | Port 445 is normally blocked outside the campus, so off-site use needs a VPN. Linux Kerberos setup and macOS SMB quirks need attention. |
| 2 | **WebDAV over HTTPS** (Apache `mod_dav`, or the Nextcloud/ownCloud endpoint) | Firewall-friendly and mountable in all three file managers (`davs://`, Finder "Connect to Server", Windows "Map network drive"). Authenticates via LDAP/Kerberos. | The Windows WebClient is flaky and has a low default file-size limit (configurable via registry). Large EM datasets suffer. |
| 3 | **Nextcloud / Seafile** (web UI + desktop sync clients + LDAP/SAML) | It is literally "web upload interface + small client program", already built and maintained. | Sync semantics rather than a mounted share, and another service to run. Sync clients are a poor fit for very large datasets. |
| 4 | **SFTP over SSH** (LDAP/Kerberos accounts) | Secure, runs everywhere, and Linux file managers mount `sftp://` natively. | Windows Explorer and Finder need extra tools (WinSCP, Cyberduck, macFUSE). |
| 5 | **Globus** (Connect Server endpoint) | Designed for large research data transfers, with institutional login and resumable transfers. | Not a file-manager integration, and the service and licensing depend on the institute's setup. |

**Verdict:** Don't build the custom web uploader. Use SMB with Kerberos as the primary on-campus path. Add WebDAV or Nextcloud only if browser or off-site access without VPN is a real requirement. Consider Globus if multi-GB EM datasets also have to move between sites.