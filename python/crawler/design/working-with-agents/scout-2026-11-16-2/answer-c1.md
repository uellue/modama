# C1: Operator-declared skip patterns for a tree walker

**Method**
- **Restated:**
  - (R1) A traverser of a huge hierarchy reads a deployment-local text list of path globs to prune.
  - (R2) A scanner omits subtrees named by wildcard rules, which can be anchored or floating, and a later rule can override an earlier one.
  - (R3, general) An ordered rule list decides membership of items in a hierarchical namespace, with layered sources.
- **Inverted:** "skip" becomes "include", giving include/exclude filters. "Operator declares" becomes "vendor declares, admin overrides". "Walker" becomes "copier, backup tool or search tool".
- **Structural:**
  - Generalise: ordered rule list with override (V1).
  - Specialise: VCS ignore files (V2).
  - Compose: pattern syntax plus vendor/admin layering plus plugin discovery (V3).
  - Provider view: a package author ships defaults (V4).

**Candidates**
1. **gitignore syntax** (implemented in Python by `pathspec`, a new dependency)
   - Fits: matches the spec point for point. It has wildcards and `**`. A leading or middle `/` anchors a pattern, otherwise it matches at any depth. The last match wins. `!` re-includes. Files are layered.
   - Breaks: gitignore cannot re-include a file whose parent directory is excluded. You must accept the same rule, because "skip entirely" means you never descend. Package defaults are not a gitignore concept, so you must define the layering yourself.
   - Via: R2, V2
2. **ripgrep/fd ignore files** (`.ignore`, `.rgignore`, `.fdignore`, global ignore, implemented in Rust by the `ignore` crate)
   - Fits: a directory *walker*, not a VCS, that uses gitignore semantics with several layered files and a defined precedence. This is the closest structural twin to your program.
   - Breaks: it is per-directory and user-oriented. It has no notion of a deployment-level file or of package-supplied defaults.
   - Via: inversion "walker" → "search tool", R1
3. **systemd presets / drop-in directories** (`/usr/lib/...` for vendor files, `/etc/...` for admin files, where a same-name file in `/etc` overrides)
   - Fits: the layering model for "packages propose defaults, operators add or override". Packages drop files into a vendor directory and the deployment file sits in an admin directory.
   - Breaks: presets are first-match-wins over unit names. There are no paths, anchoring or depth. Take the directory convention, not the matching.
   - Via: V3, V4
4. **rsync filter rules / borg `--patterns-from`**
   - Fits: include/exclude over paths during a tree traversal, with `/` anchoring, `**`, mergeable rule files (rsync `dir-merge`), and borg's `!` meaning "exclude and don't recurse".
   - Breaks: the first match wins, the opposite of your "later entry brings back". Operators who know gitignore will misread it.
   - Via: inversion "skip" → "include/exclude", "walker" → "copier/backup"
5. **Python entry points** (or package data files)
   - Fits: lets installed extension packages contribute default pattern lists without the host knowing them in advance.
   - Breaks: discovery only. It says nothing about matching or precedence.
   - Via: V4, V3

**Recommendation:** Use gitignore syntax via `pathspec`. Concatenate the package defaults (from entry points) first and the operator file last, so the operator always has the last word. Document the "cannot re-include under a pruned directory" rule.

# C2: Activating plugin handlers by (group, name)

**Method**
- **Restated:**
  - (R1) Many small units with two-part keys come from separate packages. Each install enables or disables them in config.
  - (R2) Contributed checks are switched on by group or individually, from a default set, with exceptions both ways.
  - (R3, general) Selection over a two-level hierarchical namespace with most-specific-wins.
- **Inverted:** "activate" becomes "suppress". "Host decides" becomes "package declares a default".
- **Structural:**
  - Specialise: linter rule codes (V1).
  - Compose: plugin discovery plus a selection policy (V2).
  - Generalise: dotted hierarchy where the most specific setting wins (V3).
  - Maintainer's view: it must read familiar (V4).

**Candidates**
1. **flake8 plugin model** (entry points `flake8.extension` plus `select`/`extend-select`/`ignore`/`extend-ignore` by code prefix)
   - Fits: this is exactly a composition of discovery and selection. Separately installed packages contribute checks under code prefixes, and config picks groups or single checks.
   - Breaks: identifiers are flat string prefixes (`E501`), not (group, name). You would encode the key as a string, e.g. `group.name`.
   - Via: V2, R2
2. **ruff `select`/`extend-select`/`ignore`**
   - Fits: has an explicit "more specific selector wins" rule over a default set. Python developers know it, so it is immediately readable.
   - Breaks: ruff rules are built in, not plugin-contributed. Prefix matching on codes is not a formal two-level key.
   - Via: V1, V4
3. **Python entry points** (`importlib.metadata`, stdlib)
   - Fits: entry points are natively (group, name) pairs from installed packages, discovered at run time.
   - Breaks: everything installed is visible. There is no activation policy, so you must add one (see 1 and 2).
   - Via: R1, V2
4. **pytest/pluggy plugins** (`pytest11` entry points, `-p no:name`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD`)
   - Fits: auto-discovered handlers with per-run opt-out, plus a "nothing by default" switch.
   - Breaks: disabling only works for whole plugins. There is no group-level selection or re-enable exceptions.
   - Via: inversion "activate" → "suppress"
5. **systemd presets** (`enable`/`disable` lines with globs, vendor and admin files)
   - Fits: defaults per installation with glob exceptions in both directions.
   - Breaks: first-match ordering is less intuitive than specificity, and the names are flat.
   - Via: V3, R3

**Recommendation:** Discover handlers with entry points and select them with ruff-style `select`/`ignore` lists over `group` or `group.name`, where the most specific entry wins. This adds no new dependency.

# C3: Searching millions of files in place without building search

**Method**
- **Restated:**
  - (R1) Locate items in a large shared store by content, author, type and date, with natural-language queries and links back to the files.
  - (R2) Index documents in place and query by full text, facets and semantics.
  - (R3, general) Discovery over records that stay at the source.
- **Inverted:** "find" becomes "publish metadata so others can find". "Searcher" becomes "provider exposing records". "Read content" becomes "extract metadata".
- **Structural:**
  - Compose: C1-style walker, plus type/content extraction, plus an indexing server, plus a UI (V1).
  - Specialise: file system metadata only (owner, mtime, type) (V2).
  - Generalise: data catalogue (V3).
  - Provider's view: the storage layer itself knows owner, date and path (V4).

**Candidates**
1. **Elasticsearch/OpenSearch fed by FSCrawler (uses Apache Tika)**
   - Fits: crawls a tree, extracts text, MIME type, owner and dates, and indexes them with paths while the files stay put. It supports full-text and faceted search, and vector/hybrid search for semantic queries.
   - Breaks: you still operate a cluster and a crawler. FSCrawler is essentially a single-maintainer project. Natural-language → query needs an embedding model or LLM layer. Tika cannot read most EM formats (`.dm4`, `.emd`, `.mrc`), so you need a metadata extractor such as RosettaSciIO (a new dependency). Results must be filtered by each user's file permissions, or the index leaks other groups' names and content.
   - Via: V1, R2
2. **File system metadata engines** (Robinhood Policy Engine for Lustre/POSIX; the IBM Storage Scale policy engine if the tree is on GPFS)
   - Fits: built for fast queries by owner, group, type and date over very large file counts, using the storage's own metadata.
   - Breaks: no content search and no natural language. I can't verify Robinhood's current maintenance status, so check before adopting it.
   - Via: V2, V4
3. **iRODS** (register files in place with `ireg`; attribute metadata in the catalogue)
   - Fits: attaches searchable metadata to files that stay where they are, at institute scale.
   - Breaks: heavyweight, and it tends to become the access layer. It has no native full text or natural language.
   - Via: V4, inversion "read content" → "extract metadata"
4. **CKAN, or OAI-PMH/DataCite metadata published to an existing repository or aggregator**
   - Fits: the data stays put, and descriptions are published so that existing search systems find them. Here someone else runs the search.
   - Breaks: works at dataset granularity, not for millions of files. Content queries only work as well as the extracted metadata.
   - Via: inversion "find" → "publish to be found", V3
5. **OS desktop search over shares** (Windows Search, Spotlight, Recoll)
   - Fits: zero development, and links open the files directly.
   - Breaks: per user and per machine. It does not scale to millions of shared files and has no central index.
   - Via: R1, specialise to a single user

**Recommendation:** No off-the-shelf product removes all the operating effort. Candidate 1 (FSCrawler + OpenSearch) is the least-build option. Settle permission filtering and EM-format metadata extraction first.

# C4: Shared store from Windows, macOS and Linux file managers

**Method**
- **Restated:**
  - (R1) Clients on three operating systems read and write a central repository over the LAN with directory accounts.
  - (R2) Mount a network share with single sign-on in the native file browser.
  - (R3, general) An authenticated remote hierarchy with read/write operations.
- **Inverted:** "custom upload UI plus client" becomes "existing protocol the operating systems already speak". "User uploads" becomes "server exports".
- **Structural:**
  - Specialise: network file protocol (V1).
  - Generalise: HTTP resource hierarchy (V2).
  - Provider's view: the storage team already runs AD/LDAP or Kerberos (V3).

**Candidates**
1. **SMB** (Windows Server or Samba joined to the institute AD, Kerberos)
   - Fits: native in Explorer, Finder (`smb://`) and GNOME/KDE (GVFS/KIO), with institute logins and single sign-on.
   - Breaks: off-site use needs a VPN. Mixing POSIX and NTFS ACLs on the server needs care.
   - Via: R2, V1, V3
2. **WebDAV** (Apache `mod_dav` with LDAP auth, or Nextcloud/ownCloud/Seafile)
   - Fits: an HTTP hierarchy that all three operating systems can mount. The Nextcloud-style products are already "a web upload UI plus a small client", which is the proposal, already built.
   - Breaks: the Windows WebClient is quirky (default file size limit, needs HTTPS for basic auth). Performance is poor with many small files.
   - Via: V2, inversion "custom UI" → "existing protocol"
3. **NFSv4 with Kerberos**
   - Fits: native mounting on Linux and macOS, with directory-based identity.
   - Breaks: Windows has only a limited built-in client (NFSv3, not in Home editions), and it is not file-manager friendly there.
   - Via: V1
4. **SFTP** (sshd with SSSD/LDAP)
   - Fits: institute login, and native in GNOME/KDE file managers.
   - Breaks: Explorer and Finder have no native SFTP, so users need WinSCP, Cyberduck or sshfs.
   - Via: R3, V3
5. **S3** (MinIO or Ceph RGW with LDAP/OIDC)
   - Fits: a central store with read and add operations over HTTP that scales well.
   - Breaks: not a file system. There are no native file managers, and users work with keys rather than their account passwords.
   - Via: R3, generalise

**Recommendation:** Use SMB against the institute directory. Add WebDAV, via an existing sync-and-share product rather than custom code, only if browser or off-site access is needed. Ask central IT what they already operate before building the custom upload tool.