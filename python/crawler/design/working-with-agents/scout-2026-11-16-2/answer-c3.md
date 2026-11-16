# C1 – Operator-declared skip patterns for a tree walker

**Variants**
- **R1 (synonyms):** An application traverses a huge folder hierarchy. Admins list, in a text config shipped with the deployment, the locations it must ignore. Globs can be rooted or float, and later lines can un-ignore earlier ones.
- **R2 (synonyms):** A crawler visits a big tree. Maintainers write exclusion masks, and add-on modules contribute baseline masks.
- **R3 (general):** A process enumerates items in a hierarchy, and an ordered, layered rule list decides which items are visited.
- **I (inversion):** "skip" becomes "include", so the rules form an allow-list. "Later overrides" becomes "first match wins". "Operators declare" becomes "packages provide defaults" (the provider's view).
- **S (structure):**
  - Generalisation: cascading match rules over hierarchical names.
  - Specialisation: VCS ignore files.
  - Composition: a pattern language plus a way to merge rule files from several sources.

**Candidates**
1. **gitignore syntax**, as reused by ripgrep/fd in `.ignore` files. *From R1 and R2.*
   - Fits: it matches nearly every stated property: wildcards, rooted vs. any-depth patterns, later lines win, `!` negation, and layered files. Python implementations exist, such as `pathspec` (third-party dependency).
   - Breaks: gitignore cannot re-include a path whose parent directory is excluded. This is correct for a pruning walker, but it must be documented. Its layering is per directory, not per package.
2. **conf.d drop-in directories plus Python entry points**, for the package-defaults part. *From I (provider view) and S (composition).*
   - Fits: packages register or ship a default pattern file. The program concatenates package defaults first and the operator file last, so the operator's lines win under gitignore ordering.
   - Breaks: this covers only the layering, not the pattern language. You must define the order between packages.
3. **rsync filter rules.** *From I (skip→include).*
   - Fits: they provide `+`/`-` include/exclude rules, anchoring, `**`, and merge files from several places.
   - Breaks: the first match wins, the opposite of what is required. The syntax is less familiar to operators than gitignore.
4. **systemd presets.** *From R3 and S (vendor vs. admin layering).*
   - Fits: this is the established convention for vendor defaults overridden by admin files that hold glob lines.
   - Breaks: presets match unit names, not paths, so there is no anchoring or depth. The first match wins.
5. **find `-prune` / `tar --exclude-from`.** *From R2.*
   - Fits: these are standard "skip subtree" mechanisms with pattern files.
   - Breaks: there is no negation, no layering and no standard anchoring semantics.

**Recommendation:** Use gitignore syntax, evaluated top-down, with package defaults loaded before the operator file. Document the "no re-include below an excluded directory" rule.

# C2 – Activating (group, name) handlers from installed packages

**Variants**
- **R1:** A program hosts many small independent plugins, each keyed by category and name and shipped by separate distributions. Each deployment enables whole categories or single plugins, starting from defaults, with exceptions both ways, in its config.
- **R2:** An extensible tool lets each site switch its components on or off.
- **R3 (general):** Selection over a two-level namespace with defaults and overrides.
- **I:** "enable" becomes "disable", giving an opt-out model. "Host finds handlers" becomes "packages advertise handlers". "Most specific wins" becomes "first match wins".
- **S:**
  - Composition: discovery plus selection policy.
  - Generalisation: a hierarchical config cascade, like Python `logging`, where `group.name` overrides `group`.

**Candidates**
1. **Python entry points.** *From R1 and I (packages advertise).*
   - Fits: installed packages declare named objects in groups, and the host discovers them without knowing the packages. This maps directly to (group, name).
   - Breaks: entry points handle discovery only, with no activation policy. Identical names from two packages collide, and loading everything can be slow.
2. **ruff/flake8-style `select` / `ignore` / `extend-select`.** *From R2 and R3.*
   - Fits: this is exactly "default set, group or single item, exceptions both ways, more specific wins", and developers already know it from `pyproject.toml`.
   - Breaks: ruff matches flat string prefixes. You need the boundary rule that `io` selects `io.*` but not `iox.*`, and you must define precedence (for example, does `select` replace the defaults?). Also decide what happens to selectors for uninstalled packages; a warning is the sensible choice.
3. **stevedore** (OpenStack), a third-party dependency. *From S (composition).*
   - Fits: it is a ready-made layer over entry points, with managers that load only named or enabled extensions.
   - Breaks: it supports only a list of names, with no group/default/exception semantics.
4. **pytest/pluggy plugin autoload.** *From I (opt-out).*
   - Fits: plugins are on by default via entry points, `-p no:name` disables one, and autoload can be switched off. Its users will recognise this.
   - Breaks: it is single-level, so there is no group selection.
5. **systemd presets.** *From I (first match).*
   - Fits: enable/disable lines with globs, vendor defaults plus admin overrides.
   - Breaks: the first match wins, not the most specific, and the convention is unfamiliar to Python developers.

**Recommendation:** Use entry points for discovery and ruff semantics for selection, with ids written as `group` or `group.name`:

```toml
[tool.myprog.handlers]
select = ["io", "calib.drift"]
ignore = ["io.legacy_ser"]
```

# C3 – Finding files in place across a huge shared tree

**Variants**
- **R1:** An institute holds millions of documents from many teams in one common hierarchy. Users want to locate them by content, author, type and time, including through natural-language queries, and get links that open them. The data stays put, and the team wants no in-house search engine.
- **R2:** A discovery service over records stored in place.
- **R3 (general):** An index that points to items rather than containing them.
- **I:**
  - "find" becomes "publish so others can find". Groups expose metadata, and a harvester or aggregator searches it.
  - "files are read by the indexer" becomes "storage reports its changes", giving incremental updates like IXFR or OAI-PMH "since last visit".
- **S:**
  - Composition: crawler plus extractor plus index plus UI, with an optional NL/vector layer.
  - Specialisation: desktop search, or a filesystem metadata database.
  - Provider's view: the storage system's own metadata and policy engine.

**Candidates**
1. **FSCrawler (with Apache Tika) feeding OpenSearch/Elasticsearch.** *From S (composition) and the library note that "documents must be sent by some other program".*
   - Fits: the files stay put, and you get full-text and faceted search by owner, type and date. Vector or hybrid search in OpenSearch can support NL queries.
   - Breaks:
     - It is still a search system you must operate.
     - Permissions are not respected unless ACLs are indexed and filtered.
     - Crawling millions of files is slow without change feeds.
     - Binary EM formats (dm4, emd, mrc, ser) have no text content, so "what is in them" means header metadata, which needs extra extractors such as RosettaSciIO.
     - Browsers often block `file://` and `smb://` links.
2. **Robinhood policy engine, or the policy engine/scans of the parallel filesystem.** *From I (provider's view) and from the LDAP-style "attribute filter within a subtree" match.*
   - Fits: fast queries over millions of files by owner, size, type and date, without reading contents.
   - Breaks: no content search and no NL queries.
3. **Recoll** (Xapian-based, with a web UI). *From S (specialisation to desktop search).*
   - Fits: an off-the-shelf indexer plus UI that indexes in place and needs almost no development.
   - Breaks: it is single-host, scaling to many millions of files is doubtful, it is not multi-user or permission-aware, and it has no NL search.
4. **iRODS with register-in-place and the iCAT metadata catalogue.** *From R2 ("records in place").*
   - Fits: you can attach and query metadata on files without moving them.
   - Breaks: it is heavy, changes how people work with the data, and does not search content.
5. **OAI-PMH / CKAN with Dublin Core.** *From I (find → publish).*
   - Fits: groups publish descriptions, an aggregator harvests them and offers search, and the items stay with the provider.
   - Breaks: it works at dataset level, not file level, and needs curation, so it does not cover millions of files automatically.

**Assessment:** Nothing gives "no system of our own" outright. The least building is candidate 1, optionally with candidate 2 as a change and metadata source. NL search over embeddings of millions of files is a separate cost, and for most EM data it only works on extracted metadata.

# C4 – Cross-platform file access with institute logins

**Variants**
- **R1:** Employees on three operating systems browse and deposit documents on a central repository over the LAN, authenticating with directory accounts, using their native file browsers.
- **R2 (general):** Authenticated remote access to items, integrated into the OS shell.
- **I:** "Users run a client" becomes "the server speaks a protocol the OS already has", which is the provider's view. "Upload" becomes "the server accepts writes".
- **S:** Composition: directory authentication (AD/LDAP/Kerberos) plus a network file protocol.

**Candidates**
1. **SMB** (Windows file server, or Samba joined to the directory). *From R1 and S.*
   - Fits: it is native in Explorer, Finder and GNOME/KDE file managers, and supports single sign-on via Kerberos.
   - Breaks: it is awkward outside the LAN or VPN, macOS SMB has performance quirks, and some Linux clients need extra packages.
2. **WebDAV** (Apache `mod_dav` with LDAP/Kerberos, or a Nextcloud endpoint). *From R2.*
   - Fits: HTTP-based and mountable on all three systems.
   - Breaks: Microsoft lists the Windows WebClient service as deprecated (2023), and it has file-size limits and other quirks.
3. **Nextcloud / ownCloud / Seafile with LDAP.** *From I (the existing version of "web interface plus small client").*
   - Fits: these already are the proposed custom web uploader with a sync client.
   - Breaks: they add their own database and data layer and are not the file manager. Nextcloud's external storage can front an existing SMB share.
4. **SFTP** (OpenSSH with SSSD/LDAP). *From R2.*
   - Fits: the CLI is built into all three systems, and Linux file managers support it natively.
   - Breaks: Explorer and Finder need third-party clients such as WinSCP or Cyberduck.
5. **NFSv4 with Kerberos.** *From S.*
   - Fits: native on Linux and macOS.
   - Breaks: the Windows client exists only in some editions, and identity mapping is painful.

**Assessment:** Use SMB. The custom upload interface reimplements candidates 1 and 3.