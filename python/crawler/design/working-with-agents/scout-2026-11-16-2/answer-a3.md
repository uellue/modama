# C1: Declarative skip list for a tree walker

This problem has the same structure as **`.gitignore`**, so you don't need a new pattern language.

1. **gitignore syntax** (`gitwildmatch`)
   - *Fits:* It covers every requirement: wildcards, `**`, a leading `/` to anchor, unanchored patterns that match at any depth, `!` to re-include, last match wins, `#` comments. Most of your operators already know it.
   - *Breaks:* Git cannot re-include a path whose parent directory is excluded. For a walker that prunes skipped directories this is the behaviour you want, but you have to document it. Git's layering also assumes ignore files spread through the tree, while you have one deployment file plus package defaults.
2. **rsync filter rules** (`--exclude-from`, `--include`, merge files)
   - *Fits:* It was built for walking large trees. It has anchored and unanchored patterns, include-back rules, and merge files for layering several sources.
   - *Breaks:* The first matching rule wins, the opposite of gitignore. Operators find the syntax harder to read, and re-including something inside an excluded directory needs extra include rules for its parents.
3. **Borg / restic exclude files**
   - *Fits:* They are the same problem: a backup tool walking huge trees from an operator-maintained pattern file. Borg's `+`/`-`/`!` prefixes cover include, exclude and "don't recurse".
   - *Breaks:* Borg's style prefixes (`sh:`, `fm:`, `pp:`) and its first-match rule are unfamiliar to most operators.
4. **`.dockerignore`**
   - *Fits:* It is a single root file next to a deployment artifact and supports `!` exceptions.
   - *Breaks:* Every pattern is anchored to the root, so matching at any depth requires `**/`. The semantics look like gitignore but differ subtly, which invites mistakes.
5. **`ignore` crate layering** (ripgrep/fd: `.gitignore` → `.ignore` → `.rgignore`)
   - *Fits:* It is a working example of several sources sharing one gitignore syntax with a defined precedence. That is the model you need for package defaults plus operator additions.
   - *Breaks:* It is a Rust library, and its precedence is per directory, not per source.

**Recommendation:** Use gitignore semantics. Concatenate the package-supplied defaults first and the operator file last, so an operator's `!` can override a package default. In Python, `pathspec.GitIgnoreSpec` implements this; it is a third-party dependency.

# C2: Activating (group, name) handlers from installed packages

1. **Python entry points** (packaging "Entry points specification", `importlib.metadata`)
   - *Fits:* Packages already register handlers under exactly a (group, name) pair, and discovery comes from the standard library.
   - *Breaks:* It only covers discovery, not activation. An entry-point group is normally a whole plugin type, so your "group" either becomes a dotted group like `myprog.handlers.<group>` or is encoded in the name.
2. **Ruff/Flake8 rule selection** (`select`, `ignore`, `extend-select`, `extend-ignore`)
   - *Fits:* It is the same model: you select whole groups or single rules, start from a default set, and make exceptions in both directions in a TOML config. Many developers already know it.
   - *Breaks:* Its codes are opaque prefixes like `E501`, not readable (group, name) pairs. The precedence rule (the more specific selector wins) has to be stated explicitly.
3. **systemd preset files**
   - *Fits:* Packages ship defaults (`enable foo.*`, `disable *`), and administrator files in `/etc` override them. This mirrors "packages propose, installation decides".
   - *Breaks:* Names have only one level. First match wins across lexically ordered files, which is not obvious when you read a single file.
4. **pytest plugin control** (`-p name`, `-p no:name`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD`)
   - *Fits:* Plugins load automatically from entry points, and each installation can opt out of single ones.
   - *Breaks:* There is no group level, and putting it in an `addopts` string is not self-explanatory.
5. **stevedore** (OpenStack)
   - *Fits:* It is a library on top of entry points (`NamedExtensionManager`, `EnabledExtensionManager`) built for config-driven enabling.
   - *Breaks:* It is a third-party dependency, and you still have to design the config syntax yourself.

**Recommendation:** Use entry points for discovery. In the config, follow the Ruff pattern with explicit names:

```toml
[handlers]
enable  = ["imaging", "io.legacy_dm3"]
disable = ["io"]
```

The rule would be "the most specific entry wins; at equal specificity, `disable` wins". Write that rule into a comment in the shipped default config.

# C3: Searching millions of files in place, including natural language

Nothing existing covers all of this with zero operational work. You have to choose between running a search index yourself and sending your index to a cloud service. Whatever you choose, two points matter:
- **Permission trimming:** results must respect file ACLs.
- **Electron microscopy formats:** `.dm4`, `.emd`, `.mrc` and similar formats are not parsed by generic extractors like Apache Tika, so searching by content means extracting metadata first (for example with RosettaSciIO).

1. **Microsoft Graph file-share connector → Microsoft Search / Copilot**
   - *Fits:* It indexes on-prem SMB shares while the files stay in place. It trims results by ACL, returns links, and supports natural-language queries through Copilot, with no index for you to operate.
   - *Breaks:* Index content goes to M365, so data-protection approval is needed. It only makes sense if the institute already licenses M365 and Copilot. EM binary formats stay opaque.
2. **Elastic Network Drive connector or FSCrawler + Elasticsearch/OpenSearch**
   - *Fits:* It crawls the file share in place, extracts text with Tika, supports document-level security and faceting by owner, type and date, and offers optional semantic or natural-language search.
   - *Breaks:* Someone has to operate a cluster sized for millions of documents, which comes close to "our own search system". Some features require a paid license.
3. **SciCat**
   - *Fits:* It is a scientific-data catalog from the PSI/ESS community. Files stay where they are; datasets carry owner, instrument, date and domain metadata, and it has a web UI and API.
   - *Breaks:* It is organised around datasets, not individual files, has no full-text search, and needs an ingestion pipeline per group.
4. **GUFI** (Grand Unified File Index, LANL)
   - *Fits:* It runs fast, permission-aware queries over file metadata (owner, type, date) across very large trees.
   - *Breaks:* It searches metadata only, with no content and no natural language, and its audience is admins and power users.
5. **Nextcloud with external storage + Full Text Search app**
   - *Fits:* Files stay on the share, it combines a web UI, links and login, and its Assistant can sit on top for natural language.
   - *Breaks:* The full-text add-on runs on Elasticsearch anyway, and it is heavy and fragile at the scale of millions of files.

**Recommendation:** Clarify first whether a cloud index is acceptable. If yes, start with option 1. If no, use option 2 for content and option 3 or 4 for structured metadata, with natural-language search as a layer on top rather than the foundation.

# C4: Cross-platform network file access with institute accounts

The proposed custom web upload interface with a client program is essentially a re-implementation of options 1 and 2 below.

1. **SMB** (Windows Server or Samba joined to the institute AD/Kerberos)
   - *Fits:* Windows Explorer, macOS Finder and the Linux file managers (GNOME Files, Dolphin) support it natively, login uses institute accounts, and the institute's IT probably already runs it.
   - *Breaks:* It works poorly from outside the network or VPN, where port 445 is blocked and latency hurts. Kerberos setup on unmanaged Linux machines is fiddly.
2. **Nextcloud / ownCloud / Seafile**
   - *Fits:* They are a ready-made "web upload + small client": a browser UI, desktop sync clients on all three platforms, WebDAV, and LDAP/SAML/OIDC login. Nextcloud can also front an existing SMB store as external storage.
   - *Breaks:* It is one more service to operate. Sync clients copy data locally, which is a poor fit for very large EM datasets.
3. **WebDAV directly** (e.g. Apache `mod_dav` with LDAP auth)
   - *Fits:* It runs over HTTPS, so it passes firewalls, and it can be mounted from Finder, Linux file managers and Windows.
   - *Breaks:* The Windows WebClient is flaky, limits file size by default, and Microsoft has announced its deprecation. macOS Finder's WebDAV support is slow.
4. **SFTP** (SSH with LDAP/Kerberos accounts)
   - *Fits:* It is simple, secure, scriptable, and Linux file managers support it natively.
   - *Breaks:* Windows Explorer and macOS Finder cannot use it without third-party tools such as WinSCP or Cyberduck.
5. **NFSv4 with Kerberos**
   - *Fits:* It is native and fast on Linux and macOS, with identity-based access.
   - *Breaks:* The Windows NFS client is limited to some editions and practically has no Kerberos support, so it fails the Windows requirement.

**Recommendation:** Use SMB on site. If off-site or browser access is needed, add Nextcloud, or the IT department's existing equivalent, in front of the same store. A custom upload interface would only be justified for something these cannot do, such as validating metadata at upload time.