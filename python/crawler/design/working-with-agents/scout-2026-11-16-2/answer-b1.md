# C1. Skip-list for a directory walker

**Variants**
- **V1 (synonyms):** A traversal tool reads an exclusion list of glob patterns, anchored or floating, with re-inclusion.
- **V2 (synonyms):** A scanner prunes a filesystem walk using wildcard rules with negation.
- **V3 (general):** Items in a hierarchy are filtered by ordered rules that come from layered sources (vendor defaults plus local additions).
- **Inversion:** "skip" becomes "include": what to back up or copy.
- **Provider view:** Package authors ship defaults and admins override them.

**Candidates**

1. **gitignore pattern syntax** (implemented by `pathspec` in Python or the `ignore` crate in Rust). *From V1/V2.*
   - **Fits:** It covers every requirement verbatim: `*`, `**`, leading `/` for anchoring, `!` for re-inclusion, last match wins, and operators already know it.
   - **Breaks:** git documents that a file cannot be re-included if a parent directory is excluded. That collides directly with "skip entirely" (pruning). You must choose between pruning and full negation.

2. **Layered ignore sources as in git and ripgrep** (`core.excludesFile`, `.git/info/exclude`, `.gitignore`; `.ignore`, `.rgignore`, `--ignore-file`). *From V3 (compose).*
   - **Fits:** There is a defined precedence between system-wide, deployment and local sources.
   - **Breaks:** Precedence is tied to file location, not to the package that contributed a rule. You can't see or withdraw one package's defaults.

3. **Drop-in directory convention** (`*.d/` with lexical order; systemd's vendor `/usr/lib/…` vs admin `/etc/…`, where a same-named file masks the vendor one). *From the provider view.*
   - **Fits:** Each package drops in `50-pkg.ignore` and operators add `90-local.ignore`. File order maps directly onto last-match-wins.
   - **Breaks:** It is only a layout convention and still needs a pattern syntax (#1). Masking works per file, not per rule.

4. **Borg backup pattern files** (`--patterns-from`: `+`, `-`, and `!` meaning "exclude and don't recurse"; `R` for roots; fnmatch, shell or regex styles). *From the inversion (skip → include in a backup).*
   - **Fits:** It separates "exclude but keep descending" from "prune". That resolves the conflict described in #1.
   - **Breaks:** First match wins, the opposite of gitignore. Few operators know the syntax.

5. **rsync filter rules** (`--filter`, per-directory `.rsync-filter` merge files, `+`/`-`, `/` anchoring, `**`). *From the inversion (include for copying).*
   - **Fits:** It is mature and supports anchoring, include/exclude and per-directory files.
   - **Breaks:** First match wins. Re-including a deep path requires explicitly including every parent directory, which is a well-known trap.

**Recommendation:** Use gitignore syntax (#1) with a drop-in directory (#3). Document the pruning rule explicitly, or add a Borg-style "prune" marker. Note that `pathspec` would be a new third-party dependency.

---

# C2. Enabling and disabling (group, name) handlers

**Variants**
- **V1 (synonyms):** A program made of many plug-in components named (category, name), shipped by separately installed distributions, which each deployment toggles.
- **V2 (synonyms / specialisation):** Rule or check selection: enable whole families or single checks, starting from defaults, with exceptions both ways.
- **V3 (general):** Selecting a subset of a two-level namespace using wildcards and overrides.
- **Inversion:** "installation activates" becomes "package registers itself as available".
- **Provider view:** The vendor proposes a default and the admin decides.

**Candidates**

1. **Ruff/flake8 `select` / `ignore` / `extend-select` / `extend-ignore`** in TOML. *From V2.*
   - **Fits:** It is almost exactly this: a default set, enabling families by prefix, ignoring single rules, all as readable TOML lists that developers already know.
   - **Breaks:** Ids are terse codes rather than (group, name). The "more specific prefix wins" resolution isn't obvious to readers.

2. **clang-tidy `Checks:`** (`-*,bugprone-*,-bugprone-foo`). *From V3.*
   - **Fits:** Two-part names, globs, ordered rules with later ones winning, and exceptions both ways.
   - **Breaks:** A single comma-separated string becomes unreadable at scale. The `-` separator is ambiguous because names also contain dashes.

3. **ESLint `rules: {"plugin/rule": "off"}` plus shared configs as default sets.** *From V1.*
   - **Fits:** Literally a (package, name) id, where packages are installed separately.
   - **Breaks:** There is no wildcard to toggle a whole plugin. The effective set is hidden inside composed configs.

4. **systemd preset files** (`enable foo.service`, `disable *`, vendor presets plus admin overrides). *From the provider view.*
   - **Fits:** Packages propose a default and the installation decides, with wildcards.
   - **Breaks:** Names are single-level. First-match-wins across multiple files confuses people.

5. **Python entry points** (`[project.entry-points."app.handlers"]`, `importlib.metadata`). *From the inversion.*
   - **Fits:** An entry point's identity is literally (group, name), and it handles discovery from separately installed packages.
   - **Breaks:** It only provides discovery, with no enable/disable semantics. pytest, for example, adds `-p no:name` on top.

**Recommendation:** Use #5 for discovery and #1-style TOML for selection, e.g. `enable = ["io.*"]` and `disable = ["io.legacy_tiff"]` with a documented "most specific wins" rule. Add a command that prints the effective set.

**Cross-link:** C1 and C2 have the same structure (layered defaults, ordered rules, exceptions both ways). One shared semantics for both would reduce learning effort.

---

# C3. Searching a shared file tree in place

**Variants**
- **V1 (synonyms):** Query a large network share by content, author, type and date, including in natural language, getting openable links, without moving files.
- **V2 (synonyms):** Index an existing file server for full-text and metadata search.
- **V3 (general):** Make a document collection discoverable (enterprise search or data catalog).
- **Inversion:** "find" becomes "publish so that others can find": describe or expose the files so that an existing engine picks them up.
- **Provider view:** The storage system already knows owner, date and size.
- **Composition:** metadata inventory + content extraction + search index + natural-language layer.

**Candidates**

1. **Microsoft Search / Microsoft 365 Copilot with the Graph connector for file shares**, if the institute uses M365. *From V3 (an existing institutional service).*
   - **Fits:** It indexes SMB shares in place, respects NTFS ACLs, answers natural-language queries and links back to the files. Nothing to build.
   - **Breaks:** Indexed content goes into the cloud tenant, which needs data-protection and classification approval. It requires a Windows agent and SMB, and licensing costs.

2. **Elasticsearch or OpenSearch with FSCrawler (Apache Tika).** *From V2.*
   - **Fits:** An off-the-shelf crawler for a directory tree that extracts content, owner, MIME type and dates. Semantic/hybrid search covers natural language.
   - **Breaks:** You still operate a cluster. Permission filtering per group is your own job. Tika over millions of files and incremental re-crawls are costly.

3. **Nextcloud with External Storage, Full Text Search (Elasticsearch backend), and Assistant/Context Chat.** *From the composition.*
   - **Fits:** Files stay where they are, users log in with institute accounts, and links open in the browser. It also solves C4.
   - **Breaks:** Scanning millions of external files into Nextcloud's file cache is slow. Context Chat needs an LLM backend. It is a heavy stack.

4. **Filesystem metadata engines: Robinhood Policy Engine, Starfish (commercial), or the IBM Storage Scale policy `LIST`.** *From the provider view.*
   - **Fits:** Cheap queries by owner, kind and date at a scale of millions to billions of files.
   - **Breaks:** No content search and no natural language. They only apply to suitable filesystems.

5. **Publish metadata: per-folder RO-Crate (`ro-crate-metadata.json`) or README conventions, harvested by an existing institutional catalog or intranet crawler.** *From the inversion.*
   - **Fits:** Nothing new to operate if a harvester already exists.
   - **Breaks:** People must write the metadata, and the content of arbitrary files stays unindexed.

**Cross-cutting issues:**
- **Security trimming is the real hard part:** results must not leak content from files the user can't read. Check every candidate for this first.
- **Links depend on the access protocol:** `file://` and `smb://` links behave differently on each OS, so the link format follows from C4.

---

# C4. Central file store for Windows, macOS and Linux

**Variants**
- **V1 (synonyms):** Users on three operating systems browse and upload to a central file server over the LAN with institute credentials, from native file managers.
- **V2 (synonyms):** Network file sharing with directory-service authentication.
- **V3 (general):** Remote access to shared storage with single sign-on.
- **Inversion:** "a client program we write" becomes "which protocol does every file manager already speak?"
- **Composition:** The proposal itself (web UI + client) is a known product category.

**Candidates**

1. **SMB** (Windows file server, Samba, or a NAS) joined to the institute's AD/Kerberos. *From V1/V2.*
   - **Fits:** Native in Explorer, in Finder (`smb://`) and in GNOME/KDE. Single sign-on via Kerberos.
   - **Breaks:**
     - The Linux desktop setup (gvfs or cifs with Kerberos tickets) is clunkier.
     - Port 445 is blocked off-site, so off-site use needs a VPN.
     - Mixing POSIX and NT ACLs on Samba is fiddly.

2. **Nextcloud, ownCloud Infinite Scale or Seafile.** *From the composition.*
   - **Fits:** This is the proposed "web upload interface + small client", already built: web UI, sync clients for all three systems, WebDAV, and LDAP/SAML/OIDC login.
   - **Breaks:**
     - The sync model differs from direct file access.
     - It is another stack to operate.
     - Seafile stores files in its own block format, so they are no longer plain files in the tree.

3. **WebDAV over HTTPS** (Apache `mod_dav`, or via #2). *From V3.*
   - **Fits:** It passes through firewalls and can be mounted in Finder, in Linux file managers (`davs://`) and on Windows.
   - **Breaks:**
     - Microsoft has deprecated the Windows WebClient service, so Windows is the weak point.
     - There are quirks with large files and locking.

4. **NFSv4 with Kerberos (`sec=krb5p`).** *From V2.*
   - **Fits:** Native on Linux, and Finder supports `nfs://`.
   - **Breaks:**
     - Windows clients are limited and only available in some editions.
     - Uid/gid mapping (idmapd) adds administration work.

5. **SFTP** (OpenSSH with SSSD/LDAP). *From the inversion.*
   - **Fits:** The server is trivial, and Linux file managers support `sftp://`.
   - **Breaks:** Explorer and Finder have no native SFTP, so users need a client program after all (WinSCP, Cyberduck).

**Recommendation:** Use SMB (#1), preferably on a dual-protocol SMB+NFS filer, as the default. Add #2 only if browser or off-site access is needed. Before building a custom web interface, ask central IT what they already operate. Build it only if there is a concrete requirement that none of these candidates meets.