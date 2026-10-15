# Dataset recognition: architecture

Status: second iteration, after @weber's review of the requirements on 2026-10-14. Several axes are decided now and shown with their consequences; the rest shows options. Everything is still provisional, and pushback on decided items is welcome in the next round. References R*n* and Q*n* from `requirements.md`; evidence is in `prior-art.md`.

## How to read this

Seven decisions, mostly independent of each other. A decided axis shows the decision, what follows from it, and the risk we accept. An open axis shows options, a provisional recommendation, the strongest argument against it, and what would change it. The decision log at the end is the authoritative record.

## A. Flow of recognition (decided in outline, details open)

Decision: three stages.

1. **Walk with pruning.** Directories that are a dataset as a whole (`node_modules`, Python environments, Zarr arrays) are recognised from their listing during the walk, recorded as one dataset, and not entered (R11). What of their content is indexed is the handler's decision (Q9).
2. **Per-file classification** with the XDG MIME rules, as implemented today in `mime.py`. Every regular file gets a type; files nothing matches are `application/octet-stream` and remain inspectable (R22).
3. **Reduction.** Multi-file handlers run over the index in order of priority and claim their files, turning groups of files into datasets. A cleanup step ensures the anchor of a dataset is the same whichever member was seen first (R6).

Consequences: stage 1 needs a cheap rule on a directory listing, available before descending; stage 3 is where sibling and directory logic lives, with the index as input, not the file system walk. An incremental crawl re-runs stage 2 for changed files and stage 3 for directories whose listing changed.

Open, for the next round (Q16): what a reduction handler sees.
- **A-a. One directory group at a time.** The core hands the handler a directory's entries with their types from the index; the handler returns datasets. Testable with a listing, order-independent by construction, bounded cost. Can't see across directories, unless the core also passes a declared number of parent levels, as Bio-Formats' `getRequiredDirectories` does.
- **A-b. Free queries over the index.** The handler runs SQL. Global questions are one statement; handler changes re-run without a walk. This is what `mime_sql.py` was, which failed on anchoring, weights and O(handlers × files) scans, and SQL handlers are hard to test and to write by the hundred.
- **A-c. Both.** A-a as the normal interface, A-b as an escape hatch for the few handlers that need it.

Recommendation: A-a, with A-c if a spike handler can't be written against A-a. Against: cross-directory datasets (HDF5 external links to `../`) stay out of reach.

Incomplete datasets (Q3): for now, a handler that can't complete a dataset reports it (a warning with the reason); the files stay what stage 2 made of them. A "revisit later" stash with a deadline, after which the dataset is reported as broken, is in the backlog.

## B. How rules are expressed (decided)

Decision: valid, compatible XDG MIME rules (shared-mime-info XML) are the rule language. Python code is allowed only where a proven problem can't be solved with XDG MIME, and it should extend an XDG rule rather than replace one. Directory and sibling rules are the expected case for Python, since XDG MIME works on single files only.

Also decided (Q12): the crawler uses only its own curated definitions and nothing from the host system. The full range of existing freedesktop types is to be imported into curated packages soon; this is a well-defined, large work item for an AI agent (backlog).

Consequences:
- A handler collection is an XDG-style package: a `<name>.xml` with MIME types, globs and magic, plus an optional Python module for what the XML can't say. The core builds its private MIME database from the enabled packages (`XDG_DATA_HOME` and `XDG_DATA_DIRS` pointed at a directory it controls, then `update-mime-database`).
- Conflict analysis, skeleton fixtures and candidate selection work on the XML, which is exactly what the prior art says a declarative layer buys.
- The Python part needs a small, fixed interface (Q16, open): the MIME types it reacts to, its priority, and a function from a directory group to datasets. The expected spike count is one Python handler for EMPAD (XML plus raw), one for Zarr and one for Python environments (directory markers); DM4, notebooks and plain files are XML only.

Risk accepted: XDG XML can't express "this XML file is EMPAD only if its `raw_file` attribute names a sibling that exists". The current `*.xml` glob trick for EMPAD stays until the Python part exists.

## C. Priority and ambiguity (decided)

Decision: the XDG MIME model, numeric 0..100 weights on globs and priorities on magic, battle-proven on Linux desktops and easy to understand. Python handlers carry a 0..100 priority too and run in that order in stage 3.

Rejected: computed specificity (apples and oranges across evidence kinds) and declared "wins over" relations (a handler would have to know the other side).

Risk accepted, from the prior art: hand-negotiated numbers across contributors (Tika) and unlisted rules landing in the wrong place (Galaxy). Mitigations that stay: all definitions are curated packages that we assemble, so collisions are visible in one place; the core reports glob and magic collisions between unrelated types at load time; the skeleton suite (F) fails on files claimed by more than one type; ties are reported as ambiguous rather than resolved silently, and the file stays `application/octet-stream` with a warning.

Nesting and shared membership (Q1, Q2): a single file can be a dataset, so "a file in two datasets" and "a dataset inside a dataset" are the same question. Decision: the data model and the server allow nesting, but it is reported as a warning unless the outer handler is positively declared as a collection type. Everything else is exclusive membership.

## D. The dataset model (decided)

Per dataset: `type` (R25), `anchor` (a path), `members` (sorted paths, including the anchor), `handler` (name and version), `basis` (text), `warnings` (list), and later metadata (R15). Nesting is a `parent` reference, used only by declared collection types.

Anchor (Q4): the handler's decision; it can't be predicted across dataset types. What the handler chooses must be the same whichever member is seen first (R6), which the cleanup step in stage 3 enforces.

What is indexed inside a collapsed tree (Q9): the handler's decision.

## E. Packaging, registration and deployment (partly decided)

Decided (Q7): collections are cut per application domain (office documents, source code per language, photography, music, video, electron microscopy, cryo-EM, neutron scattering, X-ray diffraction, …) and per software package, the way Linux distributions ship `gwyddion.xml` with the software that reads those formats. The core ships the common formats (R21).

Open (Q17): how a collection is packaged and found.
- **E-a. Python packages with entry points.** Each collection is a pip package exposing an entry point that names its XML file(s) and optional Python module. Discovery without import; the deployment config lists what is enabled; load failures are collected, not fatal; duplicate type definitions are rejected. Fits R2 (separate repositories) directly.
- **E-b. A directory of XML files plus a Python path.** The deployment points at a directory; packages are copied in. Simplest; no packaging; versioning and tests of a collection become the deployment's problem.
- **E-c. Both**: E-a for distribution, E-b as what E-a resolves to at runtime.

Recommendation: E-c. Against: two mechanisms to document.

Enabling (R1): an explicit list in the deployment configuration, with wildcards per collection, plus path exclusions per handler and for the crawl as a whole.

## F. Testing and test data (open: Q8, Q10, Q18)

Moved to `testing.md`: what other projects do, how reproducers are derived from real-world cases, the options for fixtures, expected outcomes, external data, deployment tests and monitoring, validity checks, size and licence policy, and the reusable collections. Decided so far (Q10): an ensemble test passes on no crash, no timeout, known-bad reported, known-good present, with expectations owned by the deployment.

## G. Execution and isolation (decided for now)

Decided (Q13): isolation per crawl for now. The whole crawler runs in a container with a read-only data mount and no network; nothing finer. R23 (a crashing handler doesn't stop the crawl) is deferred during the initial design.

What the architecture keeps open for later hardening (R24): the handler interface takes a directory group and returns datasets, both plain data, so handlers can later run in worker subprocesses with timeouts (crash and hang isolation) without changing them. Per-handler sandboxes (gVisor, micro-VMs) stay an option, unjustified so far.

## Sketch

A collection, as it would look under B, C and E-c. Illustration, not an API proposal:

```
empad/
├── empad.xml          # XDG MIME: application/x.empad+xml (magic), application/x.empad-raw (globs, weight 80)
├── empad.py           # reduction handler: XML + raw -> one dataset, anchor = the XML
└── tests/             # fixtures/, fixtures.toml, expected/; see testing.md
```

```python
# empad.py, interface still open (Q16)
PRIORITY = 60
REACTS_TO = ["application/x.empad+xml"]

def reduce(group):
    """group: one directory's entries with their types. Returns datasets."""
    for xml in group.of_type("application/x.empad+xml"):
        raw = group.sibling(xml.raw_file_attribute())   # bounded read
        if raw is None:
            group.warn(xml, "raw file missing")           # incomplete (Q3)
            continue
        yield Dataset(type="application/x.empad", anchor=xml, members=[xml, raw],
                      basis=f"raw_file points to {raw.name}")
```

A deployment configuration:

```toml
[collections]
enabled = ["core", "empad", "zarr", "python-env", "dm4", "ipynb"]

[exclude]
crawl = ["/scratch/*"]
"some-reader" = ["/adhoc/legacy/*"]     # crawled and classified by name, never opened by this handler

[expect]                                 # ensemble test, Q10
known_good = ["/adhoc/empad/scan_001.xml", "/adhoc/zarr/sample.zarr"]
known_bad = { "/adhoc/legacy/broken.xml" = "raw file missing" }
```

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
| 2026-10-15 (@weber) | Preliminary, to be revisited after the spike: fixture layout with a fixture as a directory containing only wild files, provenance in one manifest per collection (purpose, validity, licence, source), expected outcomes recorded in a parallel `expected/` tree bound by name, and checks, skills and workflows around the trees (T-B layout) | Sidecars would be seen by sibling and directory rules; the hand-written part stays four keys | Sidecar record per fixture |

Open for the next round: Q16 (the Python handler interface, sections A and B), Q17 (packaging and discovery, section E), and Q15 (generic extractors on subtypes, later).
