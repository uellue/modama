# C1: Path exclusion file for a tree walker

1. **gitignore pattern format**, used through a library such as `pathspec` (Python, `GitIgnoreSpec`) or the Rust `ignore` crate that ripgrep uses.
   - **Fit:** It matches every requirement directly. Wildcards and `**` are supported. A leading `/` anchors a pattern; without it the pattern matches at any depth. `!` negates an earlier entry, and the last match wins. It also has a layered-source model (global, repo-level and per-directory files), and many developers already know the syntax.
   - **Breaks:** There is no built-in idea of "package-contributed defaults", so you define the merge order yourself: package defaults first, operator file last. Also, a child cannot be re-included once its parent directory is excluded. For a walker that "skips entirely", that rule is the correct semantics, but you must document it.
2. **rsync filter rules** (`--filter`, `merge` and `dir-merge` files such as `.rsync-filter`).
   - **Fit:** Merge files are a ready-made way for packages to contribute rule files that operators extend. It has anchoring with `/` and supports `**`.
   - **Breaks:** The first match wins, which is the opposite of your "later entry brings back" requirement. The syntax (`+`/`-`/`P`/modifiers) is also harder to read than gitignore.
3. **`.dockerignore`**.
   - **Fit:** It is a plain file next to the deployment, with wildcards, `**` and `!` re-inclusion where the last match wins.
   - **Breaks:** Every pattern is anchored at the context root, so matching at any depth needs an explicit `**/`. It also has only one file and no layering.
4. **ripgrep/fd `.ignore` / `.fdignore` layering.**
   - **Fit:** These tools already combine several ignore sources in a defined precedence order, using gitignore syntax. That is the same structure as "package defaults + operator additions".
   - **Breaks:** The precedence rules are tied to those tools. You would copy the concept, not reuse a component.
5. **`find -prune` expressions.**
   - **Fit:** This is the classic "don't descend" primitive for very large trees.
   - **Breaks:** It is not a declarative file format and has no negation or layering.

**Recommendation:** Use gitignore syntax via `pathspec` (a new dependency) and concatenate `[package defaults…, operator file]`. Prefer `GitIgnoreSpec` over the plain gitwildmatch mode so edge cases behave like git.

# C2: Activating plugin handlers by (group, name)

1. **Python entry points** (`importlib.metadata.entry_points`, standard library) for discovery, combined with **Ruff/flake8-style `select` / `extend-select` / `ignore` / `extend-ignore`** for activation.
   - **Fit:** Entry points are literally (group, name) contributed by separately installed packages. The Ruff/flake8 keys express "default set + whole groups or single items + exceptions both ways" in TOML/INI, and Python developers already read these keys fluently.
   - **Breaks:** Ruff resolves conflicts by prefix specificity, and selection then wins over ignore at equal specificity. That rule surprises people, so you must write down your own precedence rule.
2. **clang-tidy `Checks`** (for example `-*,group-*,-group-noisy`).
   - **Fit:** It is one ordered glob list with `+`/`-` that covers groups, single items and exceptions in both directions. It is very compact.
   - **Breaks:** It is order-dependent, crammed into one string, and harder to read in reviews than separate keys.
3. **systemd preset files** (`enable`/`disable` lines with globs, vendor defaults overridden by admin files).
   - **Fit:** It has the same vendor-default and operator-override layering.
   - **Breaks:** The first match wins, and it applies only at install or enable time, not as live configuration.
4. **pytest plugin control** (`-p name`, `-p no:name`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD`).
   - **Fit:** It is the same problem of autoloaded entry-point plugins with opt-out and opt-in.
   - **Breaks:** It works at the level of single plugins only, with no group wildcards.
5. **Python `logging` dictConfig hierarchy.**
   - **Fit:** Dotted names inherit settings from their parents, which is a way to express group defaults with per-item overrides.
   - **Breaks:** It is built for levels, not on/off switches, so it would be misused here.

**Recommendation:** Use entry points for discovery (no new dependency) and Ruff-style `select`/`ignore` keys addressing `group` or `group.name`. State the precedence rule explicitly, for example "more specific wins, ignore wins ties", and log the resolved active set at startup.

# C3: Search over a shared file tree without building a search system

Nothing fits completely. No off-the-shelf indexer understands the contents of EM formats (`.dm3/.dm4`, `.emd`, `.ser`, `.mrc`, and others). Generic crawlers extract text from Office and PDF files through Apache Tika and otherwise see only file-system metadata. Some extractor, for example one based on RosettaSciIO/HyperSpy readers, is the unavoidable custom part. Also, search must respect the share's access rights, or it will leak file names and contents.

1. **The institute's existing enterprise search, if there is one** (for example Microsoft Search/Copilot with a file-share connector, or a central IT search service).
   - **Fit:** Files stay in place, results come with links, there is natural-language querying, and someone else runs it.
   - **Breaks:** Indexed content goes to that service, so data-protection approval is needed. EM file contents stay opaque. Ask central IT first.
2. **Elasticsearch/OpenSearch + FSCrawler.**
   - **Fit:** It is an off-the-shelf crawler that indexes in place, with Tika extraction and date/owner/type facets. It scales to millions of documents, and you can add a natural-language layer on top.
   - **Breaks:** You still operate a cluster and the crawler. Results are not filtered by permission out of the box. This is close to "building your own".
3. **Nextcloud with External Storage + Full Text Search** (Elasticsearch backend), with its optional AI features.
   - **Fit:** It mounts the existing share without moving files, provides a search UI and links, applies user permissions, and could cover C4 as well.
   - **Breaks:** It has the same Elasticsearch operating burden. Indexing millions of external-storage files is slow, and change detection on external storage is weak.
4. **Samba Spotlight backend with Elasticsearch.**
   - **Fit:** Mac users search the SMB share from Finder with no new interface.
   - **Breaks:** It is macOS-only on the client side, still needs Elasticsearch, and offers no natural-language search.
5. **Storage metadata catalogues** (Robinhood policy engine; commercial tools such as Starfish).
   - **Fit:** They are built for fast queries by owner, type, size and date over hundreds of millions of files at HPC scale.
   - **Breaks:** They do not index content and have no natural-language search. They are admin tools, not end-user search.

**Recommendation:** Check whether central IT already offers option 1. If not, the realistic minimum is option 2 or 3 plus a domain metadata extractor. The team should accept that this is a system they will maintain.

# C4: Cross-platform network file access with institute login

1. **SMB with Kerberos/AD authentication.**
   - **Fit:** It is native in Windows Explorer, macOS Finder and Linux file managers (GVFS/KIO), uses institute accounts, and works for both reading and writing.
   - **Breaks:** Outside the network it needs a VPN, because port 445 is rarely opened externally. On unmanaged Linux machines, setting up Kerberos is a hurdle.
2. **Sync-and-share platform** (Nextcloud, ownCloud or Seafile) with LDAP or SAML/OIDC login.
   - **Fit:** It *is* the proposed "web upload UI + small client", already built and maintained, with WebDAV access and desktop clients on all three platforms.
   - **Breaks:** It is another service to run. Very large EM datasets strain sync clients and web uploads. Check whether central IT already offers one.
3. **WebDAV over HTTPS.**
   - **Fit:** It works through firewalls, Finder and Linux file managers mount it natively, and institute login works via the web server.
   - **Breaks:** The built-in Windows client (WebClient service) is weak, and as far as I know Microsoft has listed it as deprecated. Windows users would likely need a third-party client.
4. **SFTP with institute accounts** (via PAM/SSSD).
   - **Fit:** It is simple and secure, and Linux file managers support it natively.
   - **Breaks:** Windows and macOS file managers do not support it natively, so users need WinSCP, Cyberduck or FileZilla.
5. **Globus.**
   - **Fit:** It is designed for large research-data transfers, supports federated institutional login, and resumes interrupted transfers.
   - **Breaks:** It is not a file manager. It is a transfer service with its own interface and licensing.

**Recommendation:** Use SMB inside the network, plus an existing sync-and-share or WebDAV endpoint for remote access. A custom web uploader with its own client would recreate option 2 while adding the authentication, resumable upload and client maintenance burden yourselves.