# Dataset recognition: architecture

Status: second iteration, after @weber's review of the requirements on 2026-10-14. Several axes are decided now and shown with their consequences; the rest shows options. Everything is still provisional, and pushback on decided items is welcome in the next round. References R*n* and Q*n* from `requirements.md`; evidence is in `prior-art.md`.

## How to read this

Seven decisions, mostly independent of each other. A decided axis shows the decision, what follows from it, and the risk we accept. An open axis shows options, a provisional recommendation, the strongest argument against it, and what would change it. The decision log at the end is the authoritative record.

## A. Flow of recognition (revised 2026-10-16 after the critique)

Decision: a post-order walk with a pre-order check.

1. **Pre-order check, before descending.** From a directory's listing alone (names, sizes, no content), the walker asks the collapse formats whether this directory is a dataset as a whole, for example a Python environment, `node_modules`, a Zarr store or a Quantum Espresso run. If so it is recorded as one dataset and not entered: nothing below it is listed, classified or extracted (R11). This must stay cheap because such trees can hold a million files from well-known public packages, one `npm install` away. Which markers identify a kind of folder and which metadata it yields (for an environment, say, the Python version and the installed packages) is decided per format, case by case.
2. **Descend, then recognise on the way back up.** Each file gets its MIME type from the XDG rules (`mime.py`). When a directory's children are done, its recognizers run with the directory's entries, their types, and the *results* of its subdirectories (the datasets they became, or that they were collapsed). A TENSOR export sees a `DiffractionPatterns/` child that is already a frame series; a nested Zarr is the outer marker swallowing an inner result.
3. **Store.** Results go to the index, which is what the server reads and what incremental runs compare against. The index is not what recognition reads.

Consequences: order independence holds per subtree by construction, so there is no cleanup step; re-recognition after a format upgrade is per subtree from stored listings; a dataset spanning sibling directories or reaching across the tree (an HDF5 external link to `../other/`) is out of reach and would need a declared exception, as it would under any directory-local model. The earlier "index first, then reduce" design was dropped because a directory group cannot see its children, which the survey's dominant cases need, and because the cleanup step it required was never defined.

Turn-around (walk-through, 2026-10-16): a full crawl of a large tree takes hours, while the survey takes minutes because it reads only listings. Re-running recognition with a different rule set, for a path subset, or only for previously unclaimed or failed items must stay possible without a re-walk, like `pytest --lf` or running one test file. The index already holds every listing with types and both timestamps, so stage 3 can run from the index alone and stage 2 needs the file system only for probes; the design must keep it that way. Output comes after the walk (H); with post-order recognition the result of a finished subtree is final, so per-subtree output would be possible if ever wanted. Speed itself is a later concern.

Open (Q16): the exact recognizer interface. Settled by the revision: its input is plain data, a directory's entries with types plus the results of its subdirectories, and it reads file contents itself within a budget; it holds no database connection, so it can run in a worker later (G).

Incomplete datasets (Q3): for now, a handler that can't complete a dataset reports it (a warning with the reason); the files stay what stage 2 made of them. A "revisit later" stash with a deadline, after which the dataset is reported as broken, is in the backlog.

## B. How rules are expressed (decided)

Decision: valid, compatible XDG MIME rules (shared-mime-info XML) are the rule language. Python code is allowed only where a proven problem can't be solved with XDG MIME, and it should extend an XDG rule rather than replace one. Directory and sibling rules are the expected case for Python, since XDG MIME works on single files only.

Also decided (Q12): the crawler uses only its own curated definitions and nothing from the host system. `freedesktop.org.xml` from shared-mime-info (GPL-2.0-or-later) is vendored into the core collection as its own file with its licence notice, the package being MIT apart from that file (decided 2026-10-16; copying it from the distribution package at build or run time was judged messier). Curating it, and adding definitions of our own, is the backlog item for an AI agent.

Consequences:
- A handler collection is an XDG-style package: a `<name>.xml` with MIME types, globs and magic, plus an optional Python module for what the XML can't say. The core builds its private MIME database from the enabled packages (`XDG_DATA_HOME` and `XDG_DATA_DIRS` pointed at a directory it controls, then `update-mime-database`).
- Conflict analysis, skeleton fixtures and candidate selection work on the XML, which is exactly what the prior art says a declarative layer buys.
- The Python part needs a small, fixed interface (Q16, open): the MIME types it reacts to, its priority, and a function from a directory group to datasets. The expected spike count is one Python handler for EMPAD (XML plus raw), one for Zarr and one for Python environments (directory markers); DM4, notebooks and plain files are XML only.

Risk accepted: XDG XML can't express "this XML file is EMPAD only if its `raw_file` attribute names a sibling that exists". The proof of concept's `*.xml` glob for EMPAD, which forces a sniff of every XML file, is an implementation detail, not a requirement; whatever works best and is easiest to maintain replaces it.

## C. Priority and ambiguity (decided)

Decision: the XDG MIME model, numeric 0..100 weights on globs and priorities on magic, battle-proven on Linux desktops and easy to understand. Python handlers carry a 0..100 priority too and run in that order in stage 3.

Rejected: computed specificity (apples and oranges across evidence kinds) and declared "wins over" relations (a handler would have to know the other side).

Risk accepted, from the prior art: hand-negotiated numbers across contributors (Tika) and unlisted rules landing in the wrong place (Galaxy). Mitigations that stay: all definitions are curated packages that we assemble, so collisions are visible in one place; the core reports glob and magic collisions between unrelated types at load time; the skeleton suite (F) fails on files claimed by more than one type; ties are reported as ambiguous rather than resolved silently. A tie between two legitimate types resolves to their common ancestor in the `sub-class-of` hierarchy (two HDF5 subtypes tie to HDF5), and only to `application/octet-stream` when they share nothing else (after the critique, 2026-10-16).

Nesting and shared membership (Q1, Q2): a single file can be a dataset, so "a file in two datasets" and "a dataset inside a dataset" are the same question. Decision: the data model and the server allow nesting, but it is reported as a warning unless the outer handler is positively declared as a collection type. Everything else is exclusive membership.

## D. The dataset model (decided)

Per dataset: `type` (R25), `anchor` (a path), `members` (sorted paths, including the anchor), `handler` (name and version), `basis` (text), `warnings` (list), and later metadata (R15). Nesting is a `parent` reference, used only by declared collection types, and a collection's record references its member datasets (in `oai_dc`, `dc:relation` entries with the members' browse URLs).

**Series as the first collection type.** The series handler uses nesting to resolve the sweep ambiguity from `survey.md`: a suspected series is matched as a series *and* its files are matched individually. The handler decides per kind what the members are: plain files for a frame series, where 67,600 TIFF records would be noise, or datasets in their own right for a parameter sweep of DM4 files or a numbered set of acquisitions, each with its own record that the collection record references. Whether a sweep is one dataset or many then needs no global answer, and the grouping guideline R31 (under 10 always individually, over 100 only as the group unless members are clearly distinct) is the default the handler applies. A series record also carries, where the handler can tell, the script or program that produced it (R32). Collapsed trees (environments, Zarr) have no datasets inside.

Anchor (Q4): the handler's decision; it can't be predicted across dataset types. What the handler chooses must be the same whichever member is seen first (R6), which the cleanup step in stage 3 enforces.

What is indexed inside a collapsed tree (Q9): the handler's decision.

**Identity across crawls (decided 2026-10-16, after the critique).** A dataset's identity is its anchor path, kept actionable (something the user can `open()`) and understandable on a repository that is in use. We deliberately drop the idea that an identifier points at something immutable: when members change, the same record is updated and the change is indicated (the record's datestamp, the newest member mtime in `dc:date`). If the anchor path disappears but members remain, the orphaned members are re-recognised, after a short grace period in case the user is deleting the whole thing and happened to start with the anchor. A rename is a disappearance plus a new dataset; what happens to the old record is the deleted-records item in the backlog. After a format changes (an upgrade, an edited rule) we re-crawl rather than invalidate selectively: datasets are navigation aids, not important entities, a newer format is assumed better, and if it isn't, that is what the issue-reporting and fixing workflow is for (R8, R27). Selective re-recognition per subtree stays possible but is an optimisation for later.

## E. Packaging, registration and deployment (partly decided)

Decided (2026-10-16, deployment walk-through): "Modama" means modular data management, so the search feature (indexer plus OAI-PMH endpoint, with the EOSC warehouse or a matchmaker behind it) is deployable on its own, like every other component. A `survey` command is the entry point of a deployment: it runs the listing-only analysis from `survey.md` with the default collection, suggests collections for what it sees, flags ambiguous matches, generic-only matches that probably follow a specific schema, and unmatched or odd files, and asks the admin which application domains the deployment should cover. Handlers describe themselves (a docstring an agent can relate to a survey) and must be findable by web search; an overview page of external collections exists but is expected to be incomplete and needs a process to stay current. Weird files lead to the dataset-type workflow for deployment-specific handlers, with encouragement to publish them and to report issues with existing ones (R8, R14, R22). Installation follows pip conventions, including local paths and editable installs from requirements files, so a collection under development and a published one are installed the same way; no mechanism of our own. The primary output of survey and crawl is a report (unclaimed, ambiguous and generic-only files by extension and location, collisions, slow handlers, failures, incomplete datasets); the expectation file of T-D is optional, for CI and alerting, and may start empty. Helping with the per-deployment configuration is its own later story about making Modama easier to deploy elsewhere.

Decided (Q7): collections are cut per application domain (office documents, source code per language, photography, music, video, electron microscopy, cryo-EM, neutron scattering, X-ray diffraction, …) and per software package, the way Linux distributions ship `gwyddion.xml` with the software that reads those formats. The core ships the common formats (R21).

Open (Q17): how a collection is packaged and found.
- **E-a. Python packages with entry points.** Each collection is a pip package exposing an entry point that names its XML file(s) and optional Python module. Discovery without import; the deployment config lists what is enabled; load failures are collected, not fatal; duplicate type definitions are rejected. Fits R2 (separate repositories) directly.
- **E-b. A directory of XML files plus a Python path.** The deployment points at a directory; packages are copied in. Simplest; no packaging; versioning and tests of a collection become the deployment's problem.
- **E-c. Both**: E-a for distribution, E-b as what E-a resolves to at runtime.

Resolved by the walk-through: E-a, with E-b being nothing more than pip's own local-path and editable installs (`-e ./collections/xyz-detector` in a requirements file), so there is one mechanism. The selection syntax follows ruff, which copied flake8, because it is the model Python developers already know and its semantics fit in one sentence (prior art in `prior-art.md`, "Rule selection"):

```toml
[formats]
select = ["core", "collapse", "series", "gatan", "merlin/mib"]   # a collection, or collection/format
ignore = ["gatan/dm3-legacy"]
# "more specific prefixes override less specific prefixes";
# "ignore takes precedence over select if the same prefix appears in both" (ruff's rule, verbatim)

[formats.per-path-ignores]                  # gitignore-style globs, additive only
"/legacy/**" = ["empad"]                    # crawled and classified, but this handler never opens them
"/scratch/**" = ["ALL"]

[crawl]
exclude = ["/tmp/**", "**/.Trash/**"]       # not crawled at all
```

Format ids are `collection/format` (ESLint and RuboCop namespacing) instead of opaque codes, so the ids read like the file system they describe. Per-path entries only subtract, which ruff adopted after trying to let negated patterns re-enable rules and reverting it as "too confusing". Selecting a whole collection implicitly enables formats added by an upgrade, as ruff's `ALL` does, deliberately: new formats are field-tested that way, a newer format is assumed better, and bug reports and fixes follow (confirmed after the critique, 2026-10-16). The crawl report lists formats enabled for the first time, and deployments that don't want this pin versions in their requirements file. Versions are pinned where Python versions are pinned, in the requirements file, with no mechanism of our own.

Discovery and distribution follow pytest and flake8: collections are packages named `modama-formats-*` exposing an entry point in the group `modama.formats`, with unique names (duplicates are rejected at load time, as flake8 requires unique plugin prefixes), a package-name prefix so they can be searched on PyPI and the web, and an overview page in the documentation in two parts: a list generated from PyPI by the name prefix, like pytest's plugin list, so it is never stale, and above it a short curated section that we maintain by pull request with stated criteria (a published package, passing tests, a licence, a maintainer contact), like pre-commit's hooks page. A PyPI classifier would need to be requested upstream.

Enabling (R1): an explicit list in the deployment configuration, with wildcards per collection, plus path exclusions per handler and for the crawl as a whole.

## F. Testing and test data (open: Q8, Q10, Q18)

Moved to `testing.md`: what other projects do, how reproducers are derived from real-world cases, the options for fixtures, expected outcomes, external data, deployment tests and monitoring, validity checks, size and licence policy, and the reusable collections. Decided so far (Q10): an ensemble test passes on no crash, no timeout, known-bad reported, known-good present, with expectations owned by the deployment.

## G. Execution and isolation (decided for now)

Decided (Q13): isolation per crawl for now. The whole crawler runs in a container with a read-only data mount and no network; nothing finer. R23 (a crashing handler doesn't stop the crawl) is deferred during the initial design.

What the architecture keeps open for later hardening (R24): the handler interface takes a directory group and returns datasets, both plain data, so handlers can later run in worker subprocesses with timeouts (crash and hang isolation) without changing them. Per-handler sandboxes (gVisor, micro-VMs) stay an option, unjustified so far.

## H. The development loop (decided 2026-10-16)

`modama-crawler records [PATH]` runs the whole pipeline on a path (default: the current directory) with the installed collections (default: all, with `--select`/`--ignore` to try another selection) and prints the OAI-PMH `ListRecords` response for it, without pagination or sets, `oai_dc` by default, `from`/`until` as in the protocol. Its purpose is to observe every part of the stack in one go without the database or the server, to shorten the iterative loop when setting up a deployment, and to give humans and agents the same evidence to look at; it replaces the single-path `explain` command.

Consequences:
- The pipeline (walk, classify, recognise, build records, render) is a function from a tree to a *recognition result* (datasets with type, anchor, members, basis, warnings, plus unclaimed files) that runs without PostgreSQL. That result is the oracle for fixture tests (T4) and what the database stores; `oai_dc` is one renderer of it, which this command prints and the server serves. The renderer is tested once in the core.
- Two phases, not streaming: progress and diagnostics go to stderr as the walk proceeds; the records are printed after the walk, because a directory's result is final only once its subtree is done and because complex multi-file matching needs the complete picture. `--verbose` adds, per record, the format and recognizer that claimed it, the basis, warnings, unclaimed files and timings, on stderr, so stdout stays valid OAI-PMH that can be piped to `less`, `xmllint --schema`, `diff`, or the EOSC harvester's XSLT.
- Without a database there is no "when the record last changed", so the command's datestamp is the newest mtime of the members, which since the identity decision (D) is also what moves the server's datestamp when members change; `from`/`until` filter on that, documented in `--help`.
- Later, the basis may travel in-band in the OAI-PMH `<about>` container, which the protocol provides for provenance; that needs a schema and is not part of the spike.

## Sketch

A collection, as it would look under B, C and E. Illustration, not an API proposal (the recognizer interface follows the revised section A: entries, types, children's results in; datasets out):

```
empad/
├── empad.xml          # XDG MIME: application/x.empad+xml (magic), application/x.empad-raw (globs, weight 80)
├── empad.py           # reduction handler: XML + raw -> one dataset, anchor = the XML
└── tests/             # fixtures/, fixtures.toml, expected/; see testing.md
```

```python
# empad.py, interface still open in detail (Q16)
PRIORITY = 60
REACTS_TO = ["application/x.empad+xml"]


def recognize(group):
    """group: one directory's entries with their types and its subdirectories' results. Returns datasets."""
    for xml in group.of_type("application/x.empad+xml"):
        raw = group.sibling(xml.raw_file_attribute())  # bounded read
        if raw is None:
            group.warn(xml, "raw file missing")  # incomplete (Q3)
            continue
        yield Dataset(
            type="application/x.empad",
            anchor=xml,
            members=[xml, raw],
            basis=f"raw_file points to {raw.name}",
        )
```

A deployment configuration:

```toml
[formats]                                # see E for the selection rules
select = ["core", "collapse", "series", "empad", "zarr", "gatan/dm4", "ipynb"]

[formats.per-path-ignores]
"/adhoc/legacy/**" = ["empad"]           # crawled and classified by name, never opened by this recognizer

[crawl]
exclude = ["/scratch/**"]
```

The expectation file (T-D) is separate and optional.

## Strongest arguments against the current state

1. XDG MIME as the rule language fixes the single-file part and leaves the hard part, multi-file datasets, to Python with an interface we haven't designed (Q16). The decision is right for the 90% and says nothing yet about the 10% where the difficulty is.
2. The 0..100 model works on desktops because one organisation curates one file. With collections per domain and per software package from several teams, the same numbers are chosen by people who don't talk to each other. The mitigations are reports and tests, not a mechanism.
3. Stage 3 over the index is an A2-shaped design, and the previous attempt at that (`mime_sql.py`) failed. The difference is that handlers would be Python over directory groups, not SQL; whether that holds up is a spike question.

## Decision log

| Date | Decision | Why | Alternatives |
|---|---|---|---|
| 2026-10-14 | `oai_dc` is the only output format | DataCite requires a DOI; the EOSC warehouse converts DC itself | DataCite with a URL identifier |
| 2026-10-14 | The server reads only the `records` table; recognition and metadata happen at crawl time | No file system access while serving; bounded and testable | Request-time handlers, as in the proof of concept |
| 2026-10-14 | Single-file MIME detection follows the shared-mime-info checking order, in Python | Spec compliance; the SQL version had anchoring and weight bugs | SQL prefilter, removed |
| 2026-10-14 (@weber review) | Rules are valid XDG MIME XML; Python only for proven cases XDG can't express, extending rather than replacing a rule (Q6) | Battle-proven, analysable, one language for the common case | Own declaration schema; code only |
| 2026-10-14 (@weber review) | Only our own curated MIME definitions, nothing from the host (Q12) | Cross-talk with system packages seen in June; reproducible deployments | Host database plus overrides |
| 2026-10-14 (@weber review) | Priorities are the XDG 0..100 model, also for Python handlers (Q5) | Proven on Linux desktops, easy to understand; "wins over" needs to see the other side | Computed specificity; pairwise relations |
| 2026-10-14 (@weber review) | Type identifiers are valid MIME strings: official, then established as in XDG, then our own; no hierarchy of our own (Q14, R25) | Could become official one day; interoperable | MIME plus own hierarchy path |
| 2026-10-14 (@weber review) | Nesting is allowed by the data model but warned unless the outer handler is a declared collection type; otherwise membership is exclusive (Q1, Q2) | Avoid unless there is a clear rationale, without making the core reject it | Flat only; free multi-membership |
| 2026-10-14 (@weber review) | The handler decides the anchor (Q4) and what is indexed inside a collapsed tree (Q9) | Can't be predicted across dataset types | Core-defined rules |
| 2026-10-14 (@weber review) | Flow: prune collapsible directories during the walk, classify files, then multi-file handlers reduce over the index in priority order with a cleanup step for anchor consistency (Q11) | Large boring folders must be skipped early; everything else indexed first, then grouped | Per-directory recognition during the walk only |
| 2026-10-14 (@weber review) | Incomplete datasets are reported for now; a revisit-later stash with a deadline is deferred (Q3) | Keep the initial design simple | Emit nothing until complete; provisional flag |
| 2026-10-14 (@weber review) | Collections per application domain and per software package (Q7) | Mirrors how Linux distributions ship format definitions | Per team; per instrument |
| 2026-10-14 (@weber review) | Ensemble test passes on: no crash, no timeout, known-bad reported, known-good present; expectations owned by the deployment (Q10) | Checks that the deployment's rules and handlers work together | Coverage thresholds |
| 2026-10-14 (@weber review) | Isolation per crawl for now; the architecture must allow finer isolation later (Q13, R23, R24) | Keep it simple; hardening is for production | Worker subprocesses now; per-handler sandboxes |
| 2026-10-15 (@weber) | Per-handler tests never download; external data only in the opt-in tier and deployment tests (T1) | Self-contained test suites | Download and cache on first run |
| 2026-10-15 (@weber) | Size policy: 100 KB compressed per fixture, a few MB per collection, enforced by an overridable pre-commit check with the override justified at review (T2) | Keeps collection repositories small without blocking exceptions | No policy, as in most projects |
| 2026-10-15 (@weber) | Expected outcomes are recorded on first run and reviewed, bound to the fixture's file stem (T4) | As LiberTEM does with notebooks; hand-written asserts drift | Hand-written companion records only |
| 2026-10-15 (@weber) | One expectation file per deployment serves both CI tests on a snapshot and monitoring after each production crawl (T7) | The monitoring mechanism is tested in the same go | Separate mechanisms |
| 2026-10-15 (@weber) | Deferred: where the deployment pipeline runs and who owns ER-C's known-good list; run by hand first (T3) | Automate once something exists to automate | Decide now |
| 2026-10-15 (@weber) | Optional validator step per format in CI; required validity field per fixture, `parser-only` where no independent check exists (T5) | Makes "only our parser accepts this" visible | Trust fixtures implicitly |
| 2026-10-15 (@weber) | Reproducers from production are always scrubbed (allow-list) and reviewed; they go into the handler's repository by default; an internal store is deferred (T6) | A scrubbed, reviewed file has no reason to stay internal yet | Internal store by default |
| 2026-10-15 (@weber) | Two purposes of test files: representative files (realistic, from the wild or a real-world producer, at least one per file-specific rule) and reproducers for invalid or incomplete files; synthetic and skeleton files only in the core's rule-processing tests (T-A, R29) | Synthetic files pass name rules and keep passing after content rules change, hiding the gap; skeletons test the engine, not the format | Skeletons generated from every rule; synthetic `.fake` files in handler tests |
| 2026-10-15 (@weber) | A suspected series is matched as a series and its files individually: the series handler is a declared collection type whose members are plain files (frame series) or datasets with their own records (sweeps, numbered acquisitions), referenced from the collection record | Resolves per kind whether a sweep is one dataset or many; the first real case for nested datasets with references | Decide per instrument by labels only |
| 2026-10-16 (@weber) | Search is a standalone Modama component; a `survey` command is the entry point of a deployment; the crawl report is the primary output and the expectation file is optional, recorded once the admin is happy and evaluated on a frozen sample to detect system changes (walk-through, T-D refined) | Modular data management; survey was the most useful step; expectations separate system from data changes | Expectation file as a required setup step |
| 2026-10-16 (@weber) | Collections are pip packages installed with pip's own mechanisms including local paths; selection follows ruff's `select`/`ignore` model with `collection/format` ids and additive-only gitignore-style per-path ignores; discovery via entry points, the `modama-formats-*` prefix and a curated page maintained by pull request (Q17) | Familiar to Python developers; one sentence of precedence; no mechanism of our own | Config-pointed directories; positional glob lists; a central registry |
| 2026-10-16 (@weber) | The unit is called a *format* (admin-facing, id `collection/format`); its code parts are a *recognizer* and an *extractor*; packages are `modama-formats-*`, entry-point group `modama.formats` | What people search for; "handler" named the code, not the thing | datatype (Galaxy), handler, type |
| 2026-10-16 (@weber) | The collections overview page is generated from PyPI by name prefix, with a short curated section above it maintained by pull request with stated criteria (Q17 closed) | Never stale, with a quality signal on top; pytest's and pre-commit's models stacked | Curated only; per-domain maintainers; generated only |
| 2026-10-16 (@weber) | `records [PATH]` prints the polished OAI-PMH ListRecords for a path without database or server, diagnostics on stderr, output only after the cleanup step, no streaming (H) | One observable for the whole stack; order invariance and multi-file matching need the complete picture | Streaming output; a separate explain command |
| 2026-10-16 (@weber, after the critique) | Q11 revised: post-order walk, each directory's recognizers see its entries, their types and its subdirectories' results; a pre-order check on the listing collapses boring trees before anything below is visited; no cleanup step. An accidental split beats an accidental grouping (R30) | Dominant cases are a directory plus what its children are; the cleanup step was never defined; a million files from public packages must not be visited | Index first, then reduce over directory groups or queries |
| 2026-10-16 (@weber, after the critique) | Identity is the anchor path, mutable: changes update the record and its datestamp; orphaned members are re-recognised after a short grace period when the anchor disappears | Identifiers stay actionable with `open()` and understandable on a live repository | Immutable identifiers (hash, UUID) |
| 2026-10-16 (@weber) | After a format change, re-crawl; no selective invalidation. A newer format is assumed better; if not, the issue workflow applies | Datasets are navigation aids, not important entities; keeps the system simple | Invalidation rules per format version |
| 2026-10-16 (@weber) | Our records follow the spirit of Dublin Core (or another schema later) as well as we can; what the warehouse, itself work in progress, makes of them is theirs. We only avoid what actively breaks it (identifier length) and, once our side is clean, suggest changes aligned with their plans | Keep responsibilities separate; don't design around a moving target | Shape records to the warehouse's current indexing |
| 2026-10-16 (@weber) | Timestamps on `/er-c-data` are best effort: transfers are a mess, so timing features in the series rule degrade gracefully (identical mtimes mean no information) and issues are fixed as they appear; no reliance on storage features for incremental crawls | Only bad outcome is a user missing a result in a query that the data would have justified | Require preserved mtimes; snapshot-diff or notification based crawling |
| 2026-10-16 (@weber) | Vendor `freedesktop.org.xml` (GPL-2.0-or-later) into the core collection with its licence notice | Fair, and simpler than extracting from a distribution package at build or run time | Build-time copy; own definitions only |
| 2026-10-16 (@weber, after the critique) | Ties between legitimate types resolve to their common `sub-class-of` ancestor and are reported | Two good formats must not cancel to nothing | Fall to `application/octet-stream` |
| 2026-10-16 (@weber, after the critique) | Formats added by an upgrade are auto-enabled under a whole-collection `select`, to field-test them; the report lists them; version pins for those who don't want it | A newer format is assumed better; bug reports and fixes follow | Pending state until acknowledged |
| 2026-10-16 (@weber, after the critique) | The recognition result is the oracle and the stored form; `oai_dc` is a renderer; `records` prints the rendering (H) | One oracle, with members, basis and warnings in it | `oai_dc` output as oracle |
| 2026-10-16 (@weber, explore recognition-core) | The `survey` command is its own change after `recognition-core` | Change 1 stays one intent | Survey inside change 1 |
| 2026-10-16 (@weber, explore) | The recognition result: datasets (type, anchor, members, format and version, basis, warnings, parent, collapsed) plus tree-level warnings; unclaimed and generic-only are queries over types, not a second structure | One structure for store, renderer, fixtures and report | Separate unclaimed list |
| 2026-10-16 (@weber, explore) | Every file gets a record by default; an ignore format or a higher-level collection is the remedy if search results flood | Avoid the "missing result" outcome (R30); collapse removes the bulk | Records only for recognised types |
| 2026-10-16 (@weber, explore) | A format is a class with `type`, `priority`, `reacts_to`, `collection` and `recognize(directory)`, called pre-order (names and sizes; collapse formats may stop the descent) and post-order (entries, types, children's results, budgeted `read`); plain data in, no database, nothing outside the directory | One interface for both calls; runnable in a worker later (G) | Two interfaces; module-level functions |
| 2026-10-16 (@weber, explore) | A recognizer claims its own directory's entries and whole child datasets, which it re-parents; reach-down into subdirectories only as a declared exception decided by real cases | Exclusive membership holds by construction | Reach-down with contention rules |
| 2026-10-16 (@weber, explore) | Change-1 fixtures: collapse and Zarr generated at test time by their real producers; EMPAD as a generated cheat (real XML header, 2×2 scan, zero-filled raw) validated once with LiberTEM's reader (`second-reader`); synthetic trees only in the core engine's tests | Real producers count as representative (R29); LiberTEM stays out of test dependencies (T1) | Shipped real EMPAD pair now |
| 2026-10-16 (@weber, explore) | The coverage rule applies to our own rules; vendored `freedesktop.org.xml` is exempt, a curated override counts as ours | Upstream tests its own definitions; hundreds of fixtures would block the first format | Coverage over all vendored types |
| 2026-10-16 (@weber, explore) | Collections live inside the crawler package with the standard layout and the entry-point group from day one; separate distributions as soon as more formats come | Get the core right first; the split is a move, not a redesign | Separate distributions now |
| 2026-10-16 (@weber, explore) | Structure for a swarm of cheap agents implementing formats autonomously: one template, one interface, one test plugin, everything a format needs visible from its own directory | Scaling goal for hundreds of formats | Bespoke per-format setups |
| 2026-10-15 (@weber) | Preliminary, to be revisited after the spike: fixture layout with a fixture as a directory containing only wild files, provenance in one manifest per collection (purpose, validity, licence, source), expected outcomes recorded in a parallel `expected/` tree bound by name, and checks, skills and workflows around the trees (T-B layout) | Sidecars would be seen by sibling and directory rules; the hand-written part stays four keys | Sidecar record per fixture |
| 2026-10-27 (play test) | A tie that resolves to one of the tied candidates (the parent of the others) is not reported as ambiguous | Every `*.json` and every declaration-less `*.xml` tied with a subtype and produced a warning; the parent is exactly what a name match without the subtype would give | Report every tie |
| 2026-10-27 (play test) | An unknown id in `select`, `ignore` or a per-path ignore is an error naming the installed ids | A typo (`collapse/vnev`, `collapse,zarr`, `nosuch`) silently changed what ran; ruff rejects unknown codes too | Warn and continue |
| 2026-10-27 (play test) | Warnings carried by a dataset are logged and counted like the walk's own warnings | A store with an unparsable `zarr.json` showed "0 warnings" without `--verbose` | Dataset warnings only in `--verbose` |
| 2026-10-27 (@weber, play test) | Symlinks, special files, unreadable files and unlistable directories are skipped with an info line and get no record; an unreadable root is an error | They would not make useful records; the path the user asked for is different | Records with a warning; silent skip (the state before) |
| 2026-10-27 (@weber, play test) | A collection id in `select`/`ignore` covers the collection's MIME definitions too; ignoring a single format keeps them | Makes `--select core` mean "the common files only" and `--ignore empad` complete; the generic single-file path is the handler those definitions need | Definitions always from all installed collections (the state before) |
| 2026-10-27 (@weber, play test) | Vendored definitions are curated in `core/er-c.xml` by forcing a content check with a tie (`*.raw` on `application/octet-stream` against Panasonic) rather than by editing `freedesktop.org.xml` | Keeps the vendored file pristine for updates; the tie trick is already the EMPAD pattern | Edit the vendored XML; a demotion list in the configuration |
| 2026-10-27 (@weber, play test) | The datestamp of a collapsed dataset is the directory mtime as a baseline; a format may override it | Collapse does not descend by design; a format that reads the store knows better | Walk members for the newest mtime |
| 2026-10-27 (@weber, play test) | A collapsed dataset contains everything below by default; a format may hand back entries that are not its own (warning or separate datasets, decided on wild examples); a top-level README is the dataset's description | R22 wants strays seen, but stores legitimately hold extra files | Report every non-format entry |
| 2026-10-27 (@weber, play test) | New formats take an existing MIME type used in the wild if one exists, else an unofficial `application/x.…` type; never a misleading generic type | `text/plain` for MIB would mislabel data in the index | Generic types until a format exists |
| 2026-10-27 (@weber) | `--select`/`--ignore` take comma-separated lists and may be repeated, as ruff's rule options do | No reason to differ from the model users know | One id per option, lists an error (the state before) |
| 2026-10-27 (@weber) | `records --verbose` embeds diagnostics as XML comments next to the records instead of printing them on stderr | `records --verbose \| less` hid the diagnostics; users should not have to merge streams; comments keep the document valid | Separate streams (before); a text rendering option |
| 2026-10-27 (@weber, play test) | Paths to ignore entirely: gitignore-like, defaults proposed by collections, the actual list per deployment | `__pycache__` and the like are not worth a record (R30) | Records for everything (the state before) |
| 2026-11-03 (review) | gitignore patterns are matched by `pathspec` (new dependency, MPL-2.0) | The hand-written matcher deviated from gitignore in the corners users copy from real files; `!` negation came for free | Keep `PurePosixPath.full_match` and document the deviations |
| 2026-11-03 (review) | The OAI-PMH server stays hand-written over werkzeug and lxml | `oaipmh`/pyoai and `oai_repo` paginate by offset over a re-run query and have no real-client tests; keyset pagination is an outcome we need. Revisit with tombstones or sets | Adopt a library server |
| 2026-11-03 (review) | Detection without an active MIME database raises; `mimedb.activate` sets pyxdg's module attributes instead of the environment | Silent fallback to the host's definitions contradicted Q12 and returned plausible wrong types | Keep the environment writes and reload |
| 2026-11-03 (review) | A collection's fixture tests run with its definitions plus the core's only | Recorded results must not depend on what else is installed (R2, R3) | The full installed set, documented |
| 2026-11-03 (review) | The time limit stays checked after the call, named honestly; enforcement waits for worker subprocesses | A second mechanism (signals) beside the planned one is churn; R12 and the docs now say what is guaranteed | SIGALRM-based enforcement now |
| 2026-11-04 (@weber) | The metadata warehouse (harvester, warehouse, search) is deployed inside the institute, alongside the other services in `deploy/` | Keeps the records, owners' names and paths among them, internal, so the "Mapping" decision (owner in `dc:creator`) holds; the e2e stack in `prototypes/crawler-e2e/` is the starting point | Harvesting by the central EOSC warehouse |
| 2026-10-14 | The crawler stays independent of the other modama services for now (recorded here 2026-11-04, moved from `AGENTS.md`) | Develop and test it on its own; integration with the permission APIs and the management interface comes with per-user access (backlog) | Building on `modama-common` and the services from the start |

Open for the next round: Q16 (the recognizer interface, sections A and B) and Q15 (generic extractors on subtypes, later). Q17 is closed.
