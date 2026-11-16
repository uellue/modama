# C1: Path skip list for a tree walker

**Variants**
- **R1** Operators list, in a text file shipped with the deployment, the paths the walker must leave out.
- **R2** An ordered set of name patterns, anchored or unanchored with wildcards, decides which subtrees are pruned. Later lines override earlier ones.
- **R3 (general)** Ordered rules over hierarchical names decide include or exclude, with defaults contributed by several parties.
- **I** "Skip" becomes "include". "Operator declares" becomes "package proposes". "Later wins" becomes "first wins".
- **G** Ordered match rules over hierarchical names with layered sources, as in gitignore, rsync and firewall chains.
- **C** Pattern semantics plus a way to discover package defaults.
- **O** The package author's view: "ship a default file that the host finds".

**Candidates**

1. **gitignore syntax**, via the Python library `pathspec` (third-party dependency).
   - *Fits:* It matches nearly every stated requirement: wildcards, `**`, anchoring with a leading or middle `/`, last match wins, `!` re-includes, and layered files.
   - *Breaks:* git does not descend into an excluded directory, so `!` cannot bring back a file under an excluded parent. That is exactly the "skip entirely" pruning you want, but operators must be told.
   - *Variant:* R2.
2. **Python entry points** combined with gitignore files.
   - *Fits:* Each extension package declares an entry point (e.g. group `myprog.ignore_defaults`) that points to its default pattern file. The host loads the package defaults first and the operator file last, so the operator file wins.
   - *Breaks:* It only solves discovery. Ordering among several packages must be defined, e.g. sorted by name.
   - *Variant:* C, O.
3. **The `ignore` crate behind ripgrep/fd** (`.ignore`, `.gitignore`, global ignore, with fixed precedence).
   - *Fits:* It is a working example of layered gitignore-style files with defined precedence across sources, applied while walking huge trees.
   - *Breaks:* It is Rust. For Python, use it as a design reference rather than a library.
   - *Variant:* G.
4. **rsync filter rules** (`- pattern`, `+ pattern`, `merge`/`dir-merge`).
   - *Fits:* Include and exclude rules over a tree walk, with rule files merged from several places.
   - *Breaks:* The first match wins, which is the opposite of the requirement. The syntax is also less familiar to most operators than gitignore.
   - *Variant:* I.
5. **systemd presets** (vendor directory plus admin directory).
   - *Fits:* A layering model in which vendor files supply defaults and admin files override them by name and directory precedence.
   - *Breaks:* The first match wins, and the globs apply to unit names, not paths. Borrow the directory convention, not the syntax.
   - *Variant:* R3, O.

**Recommendation:** Use gitignore syntax via `pathspec`. Load package defaults through entry points, then the operator file last. Document the pruning rule.

---

# C2: Selecting which plugin handlers are active

**Variants**
- **R1** Many small plug-ins, each named `group.name`, come from separately installed packages. Each deployment enables or disables them by group or individually, starting from defaults.
- **R2** Configuration chooses active components through coarse and fine selectors, with exceptions in both directions.
- **R3 (general)** A set of hierarchically named items gets a per-item state from rules of differing specificity.
- **I** "Activate" becomes "suppress". "Package offers a handler" becomes "host looks for handlers".
- **G** A per-name setting along a dotted hierarchy where the most specific rule wins, as in logging levels and linter rules.
- **C** Discovery plus selection.
- **O** The maintainer's view: the result must be readable by people who did not write it.

**Candidates**

1. **ruff/flake8-style `select` / `extend-select` / `ignore` / `extend-ignore`.**
   - *Fits:* A default set, selection by group or single rule, exceptions in both directions, and the more specific selector wins. Many Python developers already know this pattern from `pyproject.toml`.
   - *Breaks:* ruff uses prefix codes (`E5`). With `group.name` you need an explicit specificity rule, such as group < group.name, and an explicit tie-break.
   - *Variant:* R1, O.
2. **Python entry points** (`importlib.metadata`).
   - *Fits:* This is the standard way for separately installed packages to contribute named objects to a host.
   - *Breaks:* It only handles discovery, not selection. Entry-point groups are plugin *types*, so map your handler group into the name (`group.name`) or into one entry-point group per handler group.
   - *Variant:* C.
3. **stevedore** (`NamedExtensionManager`, `EnabledExtensionManager`; third-party dependency).
   - *Fits:* Entry-point loading with enable lists and filter functions, already used in OpenStack.
   - *Breaks:* It does not provide the select/ignore specificity logic. You still write that, and it adds a dependency for a thin layer.
   - *Variant:* C.
4. **Python `logging` logger hierarchy** (`dictConfig`).
   - *Fits:* Dotted names, settings on a parent apply to children, and the most specific configuration wins. Most Python developers understand it.
   - *Breaks:* It is a precedent for the resolution rule, not a plugin selector. Its levels are graded, while you need a binary state.
   - *Variant:* G, R3.
5. **systemd presets** (`enable foo*`, `disable *`).
   - *Fits:* Group globs plus single names, enable and disable, vendor default plus admin override.
   - *Breaks:* The first match wins by line order rather than by specificity, which is harder to read for exceptions in both directions.
   - *Variant:* I.

**Recommendation:** Use entry points for discovery and a ruff-style select/ignore block in the installation's TOML. Add an explicit rule: the more specific selector wins, and on a tie `ignore` wins. Provide a `--show-active` command that prints the resolved list.

---

# C3: Searching a huge shared file tree without moving files

**Variants**
- **R1** Millions of files in one shared tree must be searchable by content, owner, type and date, including natural-language queries, with clickable links back to the files.
- **R2** Items stay in place, and an index of descriptions plus extracted text answers queries.
- **R3 (general)** A discovery service over records that describe resources held elsewhere.
- **I** "Find" becomes "publish descriptions so that others can find". "Search system" becomes "a record provider for an existing searcher".
- **S** Owner, type and date are inode metadata. "Content" is text extraction, which for EM data means header metadata.
- **C** Crawler, extractor and index server.
- **O** The storage provider's view: expose metadata and let existing tools index it.

**Candidates**

1. **OpenSearch/Elasticsearch fed by FSCrawler (uses Apache Tika).**
   - *Fits:* Your library entry says these servers need "some other program" to send documents. FSCrawler is that program for file trees. The files stay in place, the index stores paths you can turn into links, it supports facets on owner, type and date, and OpenSearch has vector/hybrid search for natural-language queries.
   - *Breaks:* You still operate a cluster. Tika extracts nothing useful from DM3/DM4/EMD/MRC, so you need a custom extractor (e.g. RosettaSciIO readers, third-party) for header metadata. Results must respect file ACLs, which is not automatic. Natural-language search needs an on-premises embedding model, not an external API, given the data.
   - *Variant:* C, R2.
2. **GUFI (LANL) or Robinhood policy engine.**
   - *Fits:* Built for indexing metadata of filesystems with billions of entries. GUFI respects POSIX permissions in queries. They cover owner, type and date well.
   - *Breaks:* No content search and no natural language. They are CLI/SQL oriented, not a portal for end users.
   - *Variant:* S.
3. **iRODS** (register files in place, attach AVU metadata, rule engine).
   - *Fits:* A metadata catalogue over storage that you do not move, with rules that can extract metadata when files are registered.
   - *Breaks:* It is a full data management system with its own operational load. It has no full-text or natural-language search unless you pair it with an index (iRODS has Elasticsearch indexing integration; check its current maturity).
   - *Variant:* R3, O.
4. **OAI-PMH with Dublin Core, harvested into CKAN or another aggregator.**
   - *Fits:* A provider exposes records while the items stay at the provider. Existing harvesters and aggregators handle the search, so you build less on the searcher side.
   - *Breaks:* It is meant for datasets or publications, not millions of individual files. It has no content extraction and no file-level ACLs, and CKAN is not built for file-level records at this scale. It is suitable only if you publish curated dataset-level records.
   - *Variant:* I, O.
5. **Nextcloud external storage with its full-text search app** (backed by Elasticsearch).
   - *Fits:* It mounts the existing tree without moving files and provides a ready search UI with working links.
   - *Breaks:* Scanning millions of files through Nextcloud is slow and fragile. Underneath it is still Elasticsearch. Permissions are duplicated between Nextcloud and the file system.
   - *Variant:* R1.

**Assessment:** Nothing existing covers content, metadata, natural language, ACLs and EM formats without some building. The least-build path is candidate 1. Start with metadata only (owner, type, date, path), which is cheap and permission-filterable. Then add text extraction, EM header extraction, and on-premises vector search as separate, documented stages.

---

# C4: Cross-platform access to a central file store with institute logins

**Variants**
- **R1** Windows, macOS and Linux users read and write a central repository over the LAN with directory credentials, from their native file browsers.
- **R2** A remote file hierarchy is mounted with centralised authentication.
- **R3 (general)** Authenticated network access to a shared store.
- **I** "Read and add" becomes "the server receives and serves". "Custom client" becomes "the client already built into the OS".
- **S** "Institute accounts" means LDAP/AD/Kerberos.
- **O** The operator's view: what they can run without maintaining client software.

**Candidates**

1. **SMB** (Samba on Linux, or a Windows/NAS server joined to the institute directory).
   - *Fits:* Native in Explorer, Finder and GNOME/KDE file managers. Users log in with AD/Kerberos accounts, read and write, and nothing needs installing.
   - *Breaks:* Port 445 is normally blocked from outside, so remote access needs VPN. macOS performance and metadata quirks exist. POSIX/ACL mapping needs care on Samba.
   - *Variant:* R1, S.
2. **WebDAV over HTTPS**, e.g. Apache `mod_dav` with LDAP auth.
   - *Fits:* Mountable in all three OSes and works through HTTP firewalls.
   - *Breaks:* Microsoft has announced deprecation of the Windows WebClient (WebDAV) service, and it has a default file-size limit; verify the current status. It is clunkier than SMB in Finder and Explorer, and it uses basic auth unless you add SSO.
   - *Variant:* R2.
3. **Nextcloud/ownCloud** (WebDAV + web UI + desktop clients + LDAP).
   - *Fits:* This is essentially the proposed "web upload interface with a small client", already built and maintained, and it can front the existing storage.
   - *Breaks:* Its sync-client model differs from browsing in the native file manager. It is another stateful service to run, with its own permission layer.
   - *Variant:* I, O.
4. **NFSv4 with Kerberos** (`sec=krb5`).
   - *Fits:* A good fit for Linux workstations and compute nodes, and macOS can mount it.
   - *Breaks:* The Windows NFS client is limited and not in all editions. Without Kerberos, authentication is only UID-based.
   - *Variant:* R2.
5. **LDAP/AD as the shared authentication backend.**
   - *Fits:* This is the "institute accounts" part for whatever protocol you choose. Use the existing directory, not separate accounts.
   - *Breaks:* It is not an access protocol by itself.
   - *Variant:* S.

**Recommendation:** Use SMB against the institute directory as the primary path, with optional WebDAV or Nextcloud for browser and off-site access. A custom web interface and client is justified only if uploads need special ingest steps, such as capturing metadata or checksums at upload. Even then, a server-side watch or ingest hook on the SMB share is usually the better approach.

---

I did not check current project status, maintenance or versions online, in particular FSCrawler, GUFI, iRODS indexing and the Windows WebClient deprecation. Verify these before committing.