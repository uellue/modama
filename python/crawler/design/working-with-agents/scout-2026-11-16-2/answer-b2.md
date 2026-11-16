Short method notes come first for each problem, then the candidates. Labels used in "Via":
**R1/R2** = synonym restatements, **R3** = generalised restatement, **I** = inversion, **G/S** = generalise/specialise, **C** = compose, **O** = other side.

---

## C1 – Path exclusion file for a tree walker

**Method notes**
- R1: A crawler traverses a huge folder hierarchy and ignores paths listed in a config file.
- R2: A scanner visits a filesystem and prunes subtrees that match patterns.
- R3: A process enumerates items and filters them by ordered, layered rules.
- I: "skip" → "include". "Operator excludes" → "package proposes, operator overrides".
- G: Ordered glob rules where the last match wins. S: `.gitignore`.
- C: Pattern syntax + layered config sources.
- O: How tools that walk trees, such as VCS, search and backup tools, let users declare ignores.

**Candidates**
1. **gitignore pattern syntax and git's layered sources**
   - Fits: Every feature is there. A leading or middle `/` anchors a pattern, a pattern without `/` matches at any depth, `**` works, a trailing `/` matches directories only, `!` re-includes, and the last match wins. Sources are layered: per-directory file, `info/exclude`, `core.excludesFile`.
   - Breaks: A path can't be re-included if a parent directory is excluded. For "skip entirely" that is consistent behaviour, but it must be documented. Git has no notion of "package defaults".
   - Via: R1, G
2. **ripgrep/fd `ignore` crate, or Python `pathspec` (GitIgnoreSpec)**
   - Fits: These are ready-made gitignore matchers built for tree walkers. ripgrep already layers `.gitignore`, `.ignore`, `--ignore-file` with defined precedence.
   - Breaks: Each is a third-party dependency, and the layering semantics are those tools' own choices, not yours.
   - Via: O, C
3. **rsync filter rules (`--filter`, `--exclude-from`, `+`/`-`, merge files)**
   - Fits: Include and exclude rules work in both directions, a leading `/` anchors, `***` is available, and merge files give layering.
   - Breaks: The first match wins, which is the opposite of your "a later entry brings it back". That is a real source of operator confusion.
   - Via: I
4. **Drop-in directory convention (systemd `*.d/`, `/usr/lib` vs `/etc`)**
   - Fits: It covers the layering part. Packages ship defaults, operators add files that are read in lexical order, and an admin can mask a package file.
   - Breaks: It only defines file layering, not the pattern language. You must decide whether concatenation order equals precedence.
   - Via: O, C
5. **Backup exclude files (borg patterns, restic `--exclude-file`)**
   - Fits: The domain is the same: skipping subtrees of a large tree during traversal. borg even distinguishes "exclude" from "don't recurse" (`!`).
   - Breaks: borg uses first-match-wins and has multiple pattern styles (`sh:`, `fm:`, `re:`), which adds complexity you don't need.
   - Via: R3, S

**Recommendation:** Use gitignore semantics (via 2) for the syntax and drop-ins (4) for package defaults plus operator files. Concatenate the files in a defined order, so that operator entries come last and win.

---

## C2 – Enabling or disabling plugin handlers `(group, name)`

**Method notes**
- R1: Many small rules from installed plugins, with configuration selecting which are on.
- R2: Pluggable checks with namespaced IDs, enabled by family or individually.
- R3: Items in a two-level namespace with a default selection and overrides.
- I: "activate" → "deactivate". "Program discovers" → "package announces".
- G: Hierarchical feature toggles. S: Linter rule selection.
- C: Plugin discovery + selection syntax.
- O: The package author's view of how to register a handler.

**Candidates**
1. **flake8 plugins + `select`/`extend-select`/`ignore`/`extend-ignore`** (Ruff uses the same vocabulary)
   - Fits: Plugins are separate packages contributing coded checks. A prefix selects a whole group, a full code selects one check, and there are defaults plus exceptions both ways. It is all in an INI/TOML file that most Python developers already read fluently.
   - Breaks: The "group" is implicit as a code prefix, not an explicit `(group, name)`. Precedence between conflicting selectors needs to be stated (Ruff: the more specific selector wins).
   - Via: G, R3
2. **ESLint plugins and rules (`plugin/rule`, shared "recommended" configs)**
   - Fits: The identifier is literally two-part, plugins are separately installed, presets act as the default set, and per-rule overrides go in both directions.
   - Breaks: The config is JavaScript and uses severity levels rather than on/off. Turning off a whole group is indirect: you don't load the plugin or preset.
   - Via: R1, O
3. **Python entry points (`importlib.metadata`, packaging entry-points spec)**
   - Fits: This is the standard way separately installed packages announce `(group, name)` objects.
   - Breaks: It handles discovery only, not selection. The entry-point "group" usually means plugin type, so your group may need a naming scheme such as `myprog.handlers` with `group.name`, or one entry-point group per handler group.
   - Via: O, C
4. **systemd preset files (`enable`/`disable` with globs; vendor vs admin files)**
   - Fits: Packages ship default activation, admins override, globs cover groups, and both directions are supported.
   - Breaks: The first match wins, names are flat, and presets apply only at install/preset time.
   - Via: I, G
5. **Python `logging` logger hierarchy (`group.name`)**
   - Fits: Every Python developer knows "set it on the parent, override on the child".
   - Breaks: It uses levels and propagation, not booleans, so the analogy is only for explaining semantics.
   - Via: S, R2

**Recommendation:** Use entry points (3) for discovery and a flake8/Ruff-style selection (1). For example: `select = ["io", "fft.wiener"]`, `ignore = ["io.legacy_dm3"]`, with "more specific wins" documented.

---

## C3 – Search over a shared file tree, files left in place

**Method notes**
- R1: Find documents in a shared drive by content, owner, type and date.
- R2: Index a group file server and make it queryable with deep links.
- R3: Make a large collection of items discoverable without moving them.
- I: "find" → "publish so others can find". "Users search" → "store announces".
- G: Enterprise search / federated index. S: Metadata-only catalogue.
- C: Crawler + extractor + index + UI/LLM.
- O: The file server's view: it could answer queries itself.

**Candidates**
1. **Microsoft Search / Copilot with the Graph file-share connector** (only if the institute already runs M365)
   - Fits: Files are indexed in place, natural-language queries work, results link back, and ACLs are honoured. It is fully operated by someone else.
   - Breaks: The index lives in the cloud, which needs data-protection and IT approval plus licences. Linux and Mac clients get only a browser experience.
   - Via: R3, O
2. **Elasticsearch/OpenSearch + FSCrawler or Elastic connectors (+ semantic/vector search)**
   - Fits: This is the mature standard for in-place crawling, full text plus metadata facets, and file links.
   - Breaks: You operate a cluster, which is exactly the "own search system" you want to avoid, unless central IT already runs one.
   - Via: C, G
3. **Open-source RAG enterprise search (e.g. Onyx, formerly Danswer)**
   - Fits: Natural-language questions with source links on top of connectors.
   - Breaks: These are young projects that need LLM hosting. Support for in-place network-drive crawling and permission sync is weaker; verify this before choosing.
   - Via: R2, I
4. **Server-side search exposed to native clients: Windows Search on the file server, Samba Spotlight with Elasticsearch backend**
   - Fits: Users search from Explorer or Finder, and the "link" is the file itself.
   - Breaks: There is no natural language, behaviour differs per OS, and Linux clients get nothing.
   - Via: O
5. **Metadata-only catalogues (Robinhood Policy Engine, Starfish, `plocate`)**
   - Fits: Owner, type, date and path at millions of files with little effort.
   - Breaks: No content search at all.
   - Via: S

**Cross-cutting break:** For microscopy formats (`.dm4`, `.emd`, `.mrc`, …), "what is in them" means embedded metadata. Generic extractors such as Apache Tika won't read it, so every option needs a custom extractor (e.g. based on RosettaSciIO). Respecting per-group permissions in results is the hard part of any option.

**Near-miss:** CKAN and Dataverse do find-and-link well, but they require ingesting the files, which violates "files stay".

**Recommendation:** Ask central IT first what they already operate (1 or 2). If they run nothing suitable, use 5 for metadata now and add content search later.

---

## C4 – Cross-platform network file access with institute login

**Method notes**
- R1: Users on three OSes read and write a central repository with institutional credentials.
- R2: Mount a network share in the native file browser with single sign-on.
- R3: Authenticated remote access to a shared store.
- I: "custom upload client" → "use what the file manager already speaks".
- G: Network filesystem protocol. S: Web upload portal.
- C: File protocol + directory authentication.
- O: The server operator's view: which protocols are standard to run.

**Candidates**
1. **SMB (Windows file server or Samba) with AD/Kerberos**
   - Fits: Explorer, Finder and Nautilus/Dolphin support it natively, users log in with the institute account, and it is the default answer.
   - Breaks: It is not usable off-campus without VPN. Kerberos SSO on Linux and Mac clients needs setup.
   - Via: R2, O
2. **Nextcloud / ownCloud Infinite Scale / Seafile with LDAP/SAML/OIDC**
   - Fits: This is the "web upload interface + small client" proposal, already built and maintained. It adds web UI, sync clients, sharing, and works off-campus.
   - Breaks: It is another service to run, and its storage model can conflict with an existing tree. Nextcloud external storage mitigates this.
   - Via: S, I
3. **WebDAV (standalone or via 2)**
   - Fits: HTTP-based, firewall-friendly, and mountable in all three file managers.
   - Breaks: The Windows WebClient is flaky with large files and auth, and performance on big trees is poor.
   - Via: R3, G
4. **NFSv4 with Kerberos**
   - Fits: Native and fast on Linux and macOS, with proper identity.
   - Breaks: The Windows client is limited and needs identity mapping, and it is unsuitable off-campus.
   - Via: G
5. **SFTP with directory accounts (OpenSSH + SSSD/LDAP)**
   - Fits: Simple and secure; Linux file managers handle `sftp://` natively.
   - Breaks: Windows and macOS need extra tools (WinSCP, Cyberduck), so it fails "the file managers they already use".
   - Via: R3

**Recommendation:** Use SMB with AD/Kerberos on campus and add 2 if off-campus or web access is needed. A custom web uploader plus client would reimplement 2 with less functionality.