# Existing solutions for C1–C4

None of the four needs a new design. C1, C2 and C4 are covered by well-known conventions or protocols. C3 is mostly product selection, with one gap: extracting content from electron-microscopy (EM) files.

## C1: Skip-list file for a tree walker

1. **gitignore pattern semantics, used through an existing library** (Python `pathspec` in gitwildmatch mode, Rust `ignore` crate)
   - Fits: does exactly what's asked. `*`, `?` and `**` wildcards; a leading or inner `/` anchors to one directory, a bare name matches at any depth; `!` negation; the last matching rule wins. Most developers already know it.
   - Breaks: a file can't be brought back if a parent directory is excluded. A walker that prunes whole directories has the same limit anyway, so this is behaviour you have to define either way. The format is defined only by Git's documentation, not a formal spec, so pick one library and treat it as the reference.
2. **Git's layering of ignore sources** (`core.excludesFile` → `.git/info/exclude` → `.gitignore`)
   - Fits: a known precedence model for "package defaults plus operator additions". You can copy it as: package-provided pattern files first, then the operator's file. Because the last match wins, the operator can override defaults in either direction.
   - Breaks: Git layers by repository and directory, not by installed package. You still have to define how package defaults are discovered and in what order, for example a `conf.d`-style drop-in directory or Python entry points.
3. **rsync filter rules** (`+`/`-` rules, merge files, `.rsync-filter`)
   - Fits: built for walking trees and pruning them, with include and exclude, anchoring via a leading `/`, and merge files for combining sources.
   - Breaks: the first match wins (the opposite of gitignore), the syntax is less familiar, and re-including a path also requires including its parent directories.
4. **Borg Backup pattern files** (`--patterns-from`: `+` include, `-` exclude, `!` exclude and don't descend)
   - Fits: separates "exclude" from "skip entirely" explicitly, which is exactly your pruning case, and supports several pattern styles (`sh:`, `fm:`, `re:`).
   - Breaks: the first match wins, and the format is specific to Borg with little use elsewhere.
5. **`.dockerignore`**
   - Fits: gitignore-like with `!` exceptions and last-match-wins, so many people know it.
   - Breaks: every pattern is anchored at the context root. Matching at any depth needs an explicit `**/`, so you'd lose the "unanchored name" convention.

**Recommendation:** gitignore syntax and semantics through an existing library, plus a documented order of sources (package defaults, then the operator file). State in the docs that a directory that has been pruned can't be re-included.

## C2: Enabling and disabling (group, name) handlers from plugins

1. **Python entry points** (packaging "Entry points specification", `importlib.metadata`)
   - Fits: this is the standard way for separately installed packages to contribute named objects, and it already identifies them by (group, name).
   - Breaks: it only covers discovery, not which handlers are active. An entry-point "group" is usually an interface type, so either map your groups onto entry-point groups (`myapp.handlers.<group>`) or encode the group in the name.
2. **Ruff / Flake8 rule selection** (`select`, `extend-select`, `ignore`, `extend-ignore`)
   - Fits: a default set, enabling whole groups by prefix, exceptions in both directions, and it lives in `pyproject.toml`. Python developers recognise it straight away.
   - Breaks: identifiers are prefix codes (`E501`), not (group, name) pairs. Use `group` and `group.name` strings and adopt Ruff's "more specific selector wins" rule, stated explicitly.
3. **ESLint flat config**
   - Fits: rules from plugins are namespaced as `plugin/rule`, defaults come from a shared `recommended` config, and individual rules can be switched on or off.
   - Breaks: you can't switch a whole group with a wildcard (you switch configs instead), and it belongs to the JavaScript ecosystem.
4. **systemd preset files** (`enable`/`disable` lines with globs)
   - Fits: vendor defaults and admin overrides are layered by file, with exceptions in both directions. This is the same structure as package defaults plus installation choice.
   - Breaks: the first match wins, unit names are flat, and groups exist only through glob conventions.
5. **pytest plugin control** (`-p no:name`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD` plus explicit `-p`)
   - Fits: switching auto-discovered plugins on or off per installation.
   - Breaks: it works per plugin only, with no groups and no config-file syntax that reads well.

**Recommendation:** entry points for discovery, plus Ruff-style `select` / `extend-select` / `ignore` lists of `"group"` or `"group.name"`. Document one precedence rule; "most specific wins, then ignore beats select" is a common choice.

## C3: Searching a large shared file tree without moving files

1. **On-premises enterprise search products with file-share connectors** (for example IntraFind iFinder, Mindbreeze InSpire, Sinequa)
   - Fits: they index content and metadata in place, respect access permissions when showing results, and offer natural-language or RAG-style querying as a product. You configure them rather than build them.
   - Breaks: licence cost and procurement. Their generic parsers won't understand EM formats (see the gap below).
2. **Microsoft Search with the Graph file-share connector, and Copilot** (if the institute already uses Microsoft 365)
   - Fits: indexes on-premises SMB shares, results respect permissions, and natural-language queries come through Copilot.
   - Breaks: the index lives in Microsoft's cloud, which needs clearing by data protection and information security first. It needs a Windows connector agent and has index quotas that may not cover millions of items.
3. **Elasticsearch or OpenSearch with FSCrawler** (Apache Tika for text extraction)
   - Fits: open source, indexes in place, and has metadata fields, faceting and vector/semantic search.
   - Breaks: this is the "own search system" the team wants to avoid. You run the cluster, the crawler and the user interface.
4. **Filesystem metadata catalogues** (Starfish; Robinhood for Lustre; your storage vendor's own analytics or catalogue tool)
   - Fits: fast, cheap search across millions of files by owner, type, size and date, usually from inside the storage layer.
   - Breaks: no content search and little or no natural language.
5. **Desktop or personal indexers** (Recoll, DocFetcher)
   - Fits: free full-text search over mounted shares.
   - Breaks: single-user, with no shared index and no permission handling at this scale. I list it only to rule it out.

**Gaps that apply whatever you pick:**
- **What's inside the files.** For EM data, "what is in them" means metadata from binary formats (DM3/DM4, EMD, MRC and others). No generic indexer reads these. A small extractor using an existing reader such as RosettaSciIO (from the HyperSpy project) and feeding the chosen indexer is probably the one thing you'd have to build.
- **"Links that open the files".** Browsers block `file://` and `smb://` links, so clickable results need a web or WebDAV access layer. That connects this problem to C4.

## C4: Cross-platform access to a central store with institute accounts

1. **SMB** (Windows file server or Samba, Active Directory / Kerberos login)
   - Fits: works natively in Explorer, Finder (`smb://`) and Linux file managers (GVFS, KIO), with single sign-on through institute accounts.
   - Breaks: unsuitable outside the internal network (port 445 normally blocked, slow over long distances), so it needs a VPN. Linux setup and the experience vary by distribution.
2. **WebDAV over HTTPS** (Apache `mod_dav`, or the WebDAV interface of a sync-and-share platform)
   - Fits: a single HTTPS port, mountable in Explorer, Finder and GVFS or davfs2, and it also provides the web links C3 needs.
   - Breaks: the Windows WebClient service is quirky (download size limit of about 50 MB by default, locking problems), and single sign-on usually ends up as Basic auth or app passwords.
3. **Nextcloud, ownCloud or Seafile** (LDAP/AD or SAML login; can expose an existing store as external storage)
   - Fits: this is the proposed "web upload interface plus small client", already built, with desktop clients, mobile apps, sharing and WebDAV. It's worth checking whether the institute or Helmholtz already runs one; I haven't verified what exists.
   - Breaks: a separate service to operate. The main model is sync rather than a plain network drive, though virtual-files mode helps. Mapping its permissions onto existing filesystem ACLs can be awkward.
4. **SFTP** (OpenSSH, optionally Kerberos via GSSAPI)
   - Fits: secure, robust over long distances, and native in Linux file managers (`sftp://`).
   - Breaks: Explorer and Finder don't support it, so Windows and Mac users need WinSCP, Cyberduck or similar.
5. **NFSv4 with Kerberos**
   - Fits: native on Linux and supported on macOS, with good performance on the local network.
   - Breaks: Windows support is limited to some editions and is clumsy, and Kerberos-secured NFS takes real effort to set up.

**Recommendation:** SMB for on-site use, plus WebDAV or a sync-and-share platform for remote access and web links. A custom upload interface plus client would rebuild option 3 without its existing clients. For very large dataset transfers, also look at Globus.