# Prior art for C1–C4

Variant labels used under "Via": **R1/R2** = synonym restatements, **R3** = generalised restatement, **I** = inversion, **G/S/C/O** = generalise / specialise / compose / other side.

---

## C1. Skip rules for a directory walker

**Variants**
- **R1:** A crawler traverses a huge folder hierarchy. Admins list, in a text config shipped with the deployment, which locations it leaves out.
- **R2:** A scanner descends a file system and prunes entries that match wildcard rules. Later rules override earlier ones.
- **R3:** A process enumerates items in a tree, and a layered, ordered rule list filters them.
- **I:** "Skip" becomes "include": rules that select what goes into an archive, backup or sync set. "Packages propose, operators add" becomes "vendor defaults vs. admin overrides".
- **G/C/O:** This is an ordered include/exclude path filter (G). It combines a pattern syntax with layered rule sources (C). From a plugin author's side, the question is "where do I ship my defaults file?" (O).

**Candidates**
1. **gitignore syntax** (also reused by `.dockerignore`, ripgrep's `.ignore`)
   - *Fits:* It covers every requirement: `*`, `?` and `[]` wildcards; a leading `/` anchors a pattern; `**` matches at any depth; `!` brings back an excluded path; the last match wins. Ops staff and developers already know it.
   - *Breaks:* A file can't be re-included if its parent directory is excluded. That is right for pruning but surprises people, so document it. Anchors are relative to where the ignore file sits, so you must define the base path for a deployment-level file. Libraries differ slightly in edge cases.
   - *Via:* R1, R2.
2. **rsync filter rules** (`+`/`-` rules, `merge` and `dir-merge` files)
   - *Fits:* Merge files are exactly "a package ships a rules file, the operator adds another".
   - *Breaks:* The first match wins, the opposite of your requirement. The modifier syntax is cryptic.
   - *Via:* I, C.
3. **Borg patterns files / restic `--exclude-file`**
   - *Fits:* Borg distinguishes `-` (exclude) from `!` (exclude and don't descend). You will need that same split between "hide this" and "skip the subtree".
   - *Breaks:* The first match wins. Pattern-style prefixes like `sh:` and `fm:` are specific to the tool.
   - *Via:* I.
4. **Drop-in / vendor-vs-admin layering** (systemd `/usr/lib` vs `/etc`, `conf.d/*.conf`, git's global → `info/exclude` → per-directory files)
   - *Fits:* It solves the "packages propose, operators add" half. Concatenate package files first and the operator file last, and the operator's `!` lines then win.
   - *Breaks:* It handles layering only, not matching. Pip-installed packages don't write to `/usr/lib`, so locate their defaults via package data or entry points (see C2).
   - *Via:* O, C.
5. **`find -prune` / `tar --exclude-from` / `fnmatch`**
   - *Fits:* It is the minimal baseline for the semantics of skipping a subtree.
   - *Breaks:* There is no negation and no anchoring convention, so you would rebuild gitignore yourself.
   - *Via:* S, R3.

**Suggestion:** Use gitignore syntax. Evaluate `[package defaults…, operator file]` in that order, let the last match win, and prune the walk when a directory matches. Library options: Python `pathspec` or the Rust `ignore` crate. *Either one is a new third-party dependency.*

---

## C2. Activating (group, name) handlers

**Variants**
- **R1:** An app has many small plugins keyed by (category, name), shipped by separately installed distributions. Each site enables a subset.
- **R2:** Components keyed by (namespace, id) are toggled per namespace or individually, relative to a default, with overrides either way.
- **R3:** A config file selects a subset of two-level keys.
- **I:** "Activate" becomes "suppress": linters ignoring rules, log filters muting targets. "The installation decides" becomes "the package proposes a default".
- **G/C/O:** This is hierarchical selection where the more specific rule wins (G). It combines a discovery registry with a selection syntax (C). From the plugin author's side, the question is "how do I register under a group?" (O).

**Candidates**
1. **Linter rule selection** (Ruff `select`/`ignore`/`extend-select`/`extend-ignore` in `pyproject.toml`; Flake8 similar)
   - *Fits:* It selects whole groups by prefix or single rules by full code, starts from a default set, and allows exceptions both ways. Python developers can read it without explanation.
   - *Breaks:* Codes are prefix strings, not pairs, so you need to map them to `group` and `group.name`. You must also state the precedence yourself: the more specific rule wins, and at equal specificity, disable wins.
   - *Via:* R2, I.
2. **Python entry points** (`importlib.metadata.entry_points(group=…)`)
   - *Fits:* The discovery half is literally (group, name) contributed by separately installed packages.
   - *Breaks:* It has no notion of enabled or disabled. Name collisions across packages are not resolved for you.
   - *Via:* O, C.
3. **Log-filter directives** (Rust `tracing` EnvFilter `info,crate::mod=off`; Python's logging hierarchy)
   - *Fits:* A default plus per-target overrides in both directions, where the most specific wins.
   - *Breaks:* It is built for levels, not on/off switches. A mini-language string is less readable than TOML lists.
   - *Via:* I, G.
4. **systemd presets** (`enable foo.*`, `disable *`)
   - *Fits:* Packages ship preset defaults, admins override them, and globs are allowed.
   - *Breaks:* The first match wins. Presets are applied at install time as state, not evaluated at runtime.
   - *Via:* I, O.
5. **pytest/pluggy blocking** (`-p no:name`, `set_blocked`)
   - *Fits:* A real plugin system where installed plugins auto-activate and can be blocked.
   - *Breaks:* It only subtracts, works on single names with no groups, and is mostly a CLI feature.
   - *Via:* R1.

**Suggestion:** Use entry points for discovery. For selection, use Ruff-style `enable` / `disable` lists (plus `extend-` variants) that accept `group` or `group.name`, with the precedence rule written down.

---

## C3. Searching a shared tree in place

**Variants**
- **R1:** Find documents on a group share by content, author, type and date, including natural-language questions, with clickable results.
- **R2:** Enterprise search over a network file share, indexed in place.
- **R3:** Index a large item collection, answer faceted and semantic queries, and resolve hits back to the originals.
- **I:** "Find" becomes "publish so that others can find": research data management catalogues. "Files stay" becomes "register in place".
- **G/S/C/O:** This is enterprise search (G). The special case is binary EM data with rich embedded metadata (S). It composes crawler + extractor + index with facets and vectors + LLM layer + link resolver (C). From the storage operator's side, inode scans already give owner, date and type (O).

**Candidates**
1. **OpenSearch/Elasticsearch + FSCrawler (Apache Tika)**
   - *Fits:* It crawls in place, extracts text and metadata, and offers facets plus hybrid/vector search in the engine.
   - *Breaks:* It is still a cluster you run. Natural-language Q&A needs an extra layer. File ACLs must be enforced at query time, or search leaks content across groups. Tika knows little about EM formats (dm4, emd, mrc…).
   - *Via:* R2, C.
2. **Nextcloud with External Storage + Full Text Search (+ its Assistant/Context Chat apps)**
   - *Fits:* Files stay on the share. Users log in with institute accounts. Results are links that open the files. It shares a layer with C4.
   - *Breaks:* Indexing millions of files through Nextcloud and detecting changes on external storage is slow. I haven't verified how mature the natural-language apps are at this scale, so test before committing.
   - *Via:* C, plus the C4 overlap.
3. **Microsoft Search with a file-share connector + Copilot** (only if the institute uses M365)
   - *Fits:* Nobody on your team has to operate it.
   - *Breaks:* Content gets indexed in a cloud tenant, which is likely a policy problem for research data. Licensing applies. Check that the connector is currently available.
   - *Via:* O.
4. **iRODS (`ireg` registers files in place; queries on attribute-value metadata) / OMERO in-place import for images**
   - *Fits:* Who, kind and date become reliable structured metadata, which works better than full-text search for binary data.
   - *Breaks:* It needs discipline in capturing metadata, has no natural-language search, and is another system to run.
   - *Via:* I, S.
5. **Filesystem metadata scanners** (Robinhood, IBM Storage Scale policy `LIST` rules) **+ `plocate`**
   - *Fits:* Owner, extension and date queries over millions of files come almost free from inode scans.
   - *Breaks:* No content search and no natural language.
   - *Via:* O.

**Note:** For scientific data, "content" mostly means embedded metadata. The hard part is the extractor (for example RosettaSciIO for EM formats, *which would be a new dependency*), not the search engine. Using DataCite or Dublin Core field names for who, kind and date avoids inventing your own schema.

---

## C4. Cross-platform network file access with institute login

**Variants**
- **R1:** Read from and write to a central repository from three operating systems, using institute credentials, in the native file browser.
- **R2:** Remote file access with single sign-on.
- **R3:** A network file protocol combined with central identity.
- **I:** "Read and add" becomes "serve and accept". The proposal inverted: expose a standard protocol on the server, and the clients already exist.
- **O:** Which protocols do Explorer, Finder and the Linux file managers speak natively?

**Candidates**
1. **SMB 3** (Windows server or Samba, AD/Kerberos)
   - *Fits:* It is the only protocol that all three native file managers handle with single sign-on, and the institute probably has AD already.
   - *Breaks:* Off-site access needs a VPN because of port 445. Kerberos on Linux takes setup. POSIX permissions and ACLs need mapping. (NFSv4 with `sec=krb5` is the Linux/macOS alternative, but weak on Windows.)
   - *Via:* O.
2. **WebDAV over HTTPS (RFC 4918)**
   - *Fits:* It passes firewalls and is native in Finder, Explorer (WebClient service) and GNOME/KDE. Apache `mod_dav` or Nextcloud can serve it.
   - *Breaks:* Windows WebClient has quirks, such as a default ~50 MB file size limit set in the registry. OIDC/SAML single sign-on doesn't work in native clients, so you end up with app passwords.
   - *Via:* R2, O.
3. **Nextcloud / ownCloud Infinite Scale / Seafile**
   - *Fits:* This is the proposed "web UI + small client", already built, with LDAP/SAML/OIDC logins and WebDAV included.
   - *Breaks:* These prefer to own the storage layout. Mounting an existing tree as external storage works but has performance caveats.
   - *Via:* I.
4. **SFTP (OpenSSH with LDAP/Kerberos)**
   - *Fits:* It is simple and secure, and native in Linux file managers.
   - *Breaks:* Explorer and Finder need extra software, which is what you wanted to avoid.
   - *Via:* R3.
5. **Globus Connect Server**
   - *Fits:* It handles very large datasets reliably (relevant for EM) and supports federated login.
   - *Breaks:* There is no file-manager integration, and some features need a licence.
   - *Via:* S, O.

**Verdict:** Nothing custom is needed. Use SMB on site, and WebDAV, possibly via Nextcloud, for off-site and browser access. The same serving layer gives C3 its "links that open files".