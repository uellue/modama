# C1: path exclusion patterns for a tree walker

**Method**
- **R1:** A program traversing a huge folder hierarchy needs an operator-maintained text list of locations to *ignore*.
- **R2:** A crawler reads a deployment-local rules file of glob expressions that *prune* subtrees, with anchored and floating patterns and later *re-inclusion*.
- **R3 (general):** A tool processes a set of *items* and filters them through an ordered, layered list of match/negate *rules*.
- **Inversions:** skip → include (an allow-list or "manifest"); operator writes → package writes defaults (a vendor layer); later overrides earlier → first match wins.
- **Structural:**
  - **G (generalise):** an ordered filter list with negation, plus layered config sources.
  - **S (specialise):** VCS ignore files.
  - **C (compose):** pattern semantics combined with a vendor/admin config-layering convention.
  - **O (other side):** the package author's view, i.e. "ship defaults the admin can extend".

**Candidates**
1. **gitignore syntax** (Python lib `pathspec`, `gitwildmatch` mode; Rust `ignore` crate).
   - *Fits:* it covers every requirement: wildcards, a leading or inner `/` anchors to one directory, matches otherwise apply at any depth, `**` is supported, `!` re-includes, and the last match wins. Most operators already know it.
   - *Breaks:* git cannot re-include a path whose parent directory is excluded. For a walker that "skips entirely" this is actually the right behaviour, but document it. Library implementations also differ in edge cases.
   - *Via:* R1 and S (VCS ignore files).
2. **Layered ignore files as in ripgrep/fd** (`.ignore`, `.rgignore`, global ignore file, all in the `ignore` crate).
   - *Fits:* defined precedence between several gitignore-syntax files. This maps directly onto "package defaults + operator additions".
   - *Breaks:* the precedence is per-directory and tool-specific, and the reference implementation is Rust only.
   - *Via:* C (pattern semantics + layering).
3. **conf.d drop-in convention** (systemd: `/usr/lib/<prog>.d/*.conf` for vendor files, `/etc/<prog>.d/*.conf` for admin files that override by name or extend).
   - *Fits:* this is the standard answer to "packages propose defaults, operators add or override". Pair it with gitignore syntax inside each file. In Python, packages can also register their default pattern list via entry points.
   - *Breaks:* it defines only file layering and ordering (lexical file names), not pattern semantics.
   - *Via:* O (package author's view) and inversion operator → package.
4. **rsync filter rules** (`--filter`, `--exclude-from`, `+`/`-` rules, `.rsync-filter` merge files).
   - *Fits:* a mature include/exclude language with anchoring, `**`, and per-directory merge files.
   - *Breaks:* the first match wins, the reverse of your "later entry brings back" requirement, and fewer people know the syntax.
   - *Via:* inversion later-wins → first-wins, and R2.
5. **`.dockerignore`** (Go `filepath.Match` + `**`, `!`, last match wins).
   - *Fits:* a familiar, simplified gitignore dialect.
   - *Breaks:* every pattern is anchored at the context root, so "any depth" needs an explicit `**/`. Only one file, no layering.
   - *Via:* R3 (filter a set of items).

**Recommendation:** gitignore semantics via `pathspec` (a new dependency, if Python), with files layered by the conf.d convention.

# C2: enabling and disabling plugin handlers

**Method**
- **R1:** An application holds many small, separate callbacks named by (category, key), shipped by add-on packages. Each deployment picks which are switched on.
- **R2:** *Rules/checks* from installed *plugins* get *selected* per installation, either by family or individually, starting from defaults, with exclusions and re-additions.
- **R3 (general):** The *components* of an extensible system get *activated* by a declarative selection policy.
- **Inversions:** activate → deactivate (a deny-list); the installation chooses → the package declares itself (registration/discovery); the consumer config → the provider's preset.
- **Structural:**
  - **G:** feature toggles or rule selection with hierarchical identifiers.
  - **S:** linter rule codes.
  - **C:** plugin discovery combined with a selection policy.
  - **O:** the distributor's view, i.e. presets.

**Candidates**
1. **Ruff/flake8 rule selection** (`select`, `extend-select`, `ignore`, `extend-ignore` in `pyproject.toml`, with codes like `E` vs `E501`).
   - *Fits:* exactly "whole groups or single items, a default set, exceptions both ways". Python developers recognise it immediately. flake8 plugins contribute codes through entry points.
   - *Breaks:* the identifiers are prefix strings, not real (group, name) pairs. The precedence rules (the more specific selector wins in Ruff) must be stated explicitly, not assumed.
   - *Via:* R2 and S (linter rules).
2. **Python entry points** (`[project.entry-points."<prog>.<group>"] name = "pkg.mod:func"`, read with `importlib.metadata`).
   - *Fits:* this *is* a (group, name) identifier contributed by separately installed packages.
   - *Breaks:* it covers discovery only. It has no notion of enabled/disabled, so you still need a selection layer such as #1.
   - *Via:* inversion installation chooses → package registers, and O.
3. **systemd presets** (`enable foo.service`, `disable *`, with vendor and admin preset files).
   - *Fits:* package-supplied defaults, admin overrides, glob patterns.
   - *Breaks:* the first match wins, names are flat, and the syntax is systemd-specific.
   - *Via:* O (the distributor's preset).
4. **pylint `enable`/`disable`** (by message, by checker name, or `disable=all` then `enable=…`).
   - *Fits:* group-level and item-level toggles with both-direction exceptions.
   - *Breaks:* the ordering semantics are idiosyncratic and less readable than #1.
   - *Via:* R1 and inversion activate → deactivate.
5. **pluggy / pytest `-p no:<name>`.**
   - *Fits:* blocks installed plugins by name.
   - *Breaks:* it works at plugin level, not handler level, and is CLI-oriented.
   - *Via:* R3 (activate components).

**Recommendation:** entry points for discovery, plus Ruff-style `select`/`extend-select`/`ignore` keys taking `"group"` or `"group.name"`, with "more specific wins" documented.

# C3: searching a large shared file tree in place

**Method**
- **R1:** An institute wants to *search* millions of shared files by content, author, type and date, without moving them.
- **R2:** Users need to *query* a huge network share, including in natural language, and *retrieve* links, without the team operating its own *index*.
- **R3 (general):** *Discover* *records* in a large collection through their content and metadata.
- **Inversions:** find → publish so others can find (a catalogue or registration); files stay put → the index points to them (register in place); the user asks → the producer describes.
- **Structural:**
  - **G:** enterprise search, or a metadata catalogue.
  - **S:** a filesystem metadata index on the storage system.
  - **C:** a crawler and extractor, a search engine, and an NL/RAG layer.
  - **O:** the storage operator's view (policy engines), or the data producer's view (catalogues).

**Candidates**
1. **Microsoft 365 Search + Microsoft Graph file-share connector + Copilot**, if the institute already has an M365 tenant.
   - *Fits:* this is the only option where the team truly builds and operates nothing, and it includes NL questions and links.
   - *Breaks:* the index content goes to the cloud, which raises data protection and FZJ policy questions. It needs licences and an on-prem connector agent, and parsing of microscopy formats is weak.
   - *Via:* R2 ("without operating an index").
2. **Elasticsearch/OpenSearch + FSCrawler (Apache Tika) + a stock search UI**, with optional semantic/vector search for NL.
   - *Fits:* off-the-shelf crawler and engine with no custom search code. Owner, mtime and MIME type come for free.
   - *Breaks:* you still *run* a search cluster at a scale of millions of files, which is the burden you wanted to avoid. ACL mirroring is extra work.
   - *Via:* C (crawler + engine).
3. **Storage-side metadata indexers:** IBM Spectrum/Storage Discover (if the tree is on IBM Storage Scale), Starfish, Robinhood (Lustre).
   - *Fits:* they scan in place at file-system scale and handle owner, type and date queries well.
   - *Breaks:* they index metadata, not content, and offer no NL. They are commercial (except Robinhood) and tied to the storage platform. Check current product names with your storage team; I'm not certain of the latest IBM branding.
   - *Via:* S and O (the storage operator's view).
4. **Research data catalogues: SciCat, iRODS (register-in-place), OMERO in-place import for images.**
   - *Fits:* files stay where they are, and rich domain metadata (instrument, sample, user) yields links. This is the natural fit for EM data.
   - *Breaks:* they need an ingestion/registration workflow and producer discipline. There is no full-text or NL search out of the box.
   - *Via:* inversions find → publish and files stay put → index points to them.
5. **Nextcloud with External Storage + Full Text Search app + Assistant/Context Chat.**
   - *Fits:* in-place access, search, NL questions and shareable links in one product. It would also solve C4.
   - *Breaks:* scanning external storage at millions of files is known to be heavy, its Elasticsearch backend means you run #2 anyway, and NL needs a local LLM.

  *Via:* C (one product covering search and access).

**Note:** generic extractors (Tika) don't read EM formats such as DM3/DM4, EMD or MRC. The "by what is in them" requirement for those files needs a format reader such as RosettaSciIO (from HyperSpy) wherever ingestion happens.

**Verdict:** nothing self-hosted is zero-maintenance. The real choice is between a managed cloud service (#1) and operating standard components without custom code (#2–#5).

# C4: shared file store for Windows, macOS and Linux

**Method**
- **R1:** Users on all three desktop OSes must *download from* and *upload to* a central repository on the LAN, authenticating with institute credentials, ideally from their native file browser.
- **R2:** Clients need *read/write access* to a networked *share* with directory-backed *login*.
- **R3 (general):** Remote access to a *resource store* with federated identity.
- **Inversions:** client pulls → server exports (a network file system); a custom client → the OS's built-in client; upload via web → mount as a drive.
- **Structural:**
  - **G:** a network file protocol plus SSO.
  - **S:** a Kerberos/AD-authenticated share.
  - **C:** a storage protocol plus an identity provider.
  - **O:** IT's view, i.e. what every OS already ships.

**Candidates**
1. **SMB 3 (Samba or a Windows/NAS file server) with AD/Kerberos.**
   - *Fits:* native in Explorer and Finder, and in Nautilus/Dolphin via gvfs/kio. It works with institute accounts, often via SSO, so no client needs installing.
   - *Breaks:* SMB is usually blocked off-campus without VPN, and Linux user-mounts with Kerberos need some setup.
   - *Via:* R1 and inversion custom client → built-in client.
2. **WebDAV over HTTPS** (e.g. Nextcloud/ownCloud, or Apache `mod_dav`, with LDAP or SAML/OIDC).
   - *Fits:* Explorer "Map network drive", Finder "Connect to Server" and gvfs/davfs2 all work, it passes firewalls, and you get a web UI for free.
   - *Breaks:* the Windows WebClient has quirks (a default file-size limit, slow handling of large trees), and SSO via SAML/OIDC needs app passwords.
   - *Via:* inversion upload via web → mount as a drive. This is what the custom web interface would reinvent.
3. **SFTP** (OpenSSH with SSSD/LDAP or Kerberos).
   - *Fits:* simple and secure, native in Linux file managers.
   - *Breaks:* neither Finder nor Explorer browses SFTP natively, so WinSCP or Cyberduck is needed.
   - *Via:* R2 (read/write access with directory login).
4. **NFSv4 with `sec=krb5`.**
   - *Fits:* native on Linux/macOS, with strong identity mapping.
   - *Breaks:* Windows client support is poor (only some editions, no Kerberos-friendly experience).
   - *Via:* inversion client pulls → server exports, and S.
5. **S3-compatible object storage (Ceph RGW, MinIO) or Globus for large transfers.**
   - *Fits:* scales well and suits large EM datasets and automation.
   - *Breaks:* no native file-manager integration (needs Cyberduck, rclone, or the Globus web/Connect), and the identity integration is more involved.
   - *Via:* G (remote access to a resource store with federated identity).

**Verdict:** the proposed custom web upload with a client program reimplements #2 badly. Use SMB on campus, and add WebDAV, optionally through Nextcloud (which also partly covers C3), for off-site and browser access.