# Dataset recognition: architecture options

Status: draft, first iteration, for review. Everything here is provisional: as the requirements get refined, the solution space changes. References R*n* and Q*n* from `requirements.md`; evidence is in `prior-art.md`.

## How to read this

The design splits into seven decisions that are mostly independent of each other. Each section lists options, a provisional recommendation, the strongest argument against it, and what would change it. A combined sketch near the end shows what a handler would look like if all recommendations held. The decision log at the end records what is settled; sections A to G are not.

## A. When and where recognition runs (Q11, R6, R7, R10, R11)

Today recognition sees one file at a time, during the walk. Multi-file datasets need the directory listing, and collapsing a tree needs a decision before descending into it.

**A1. Per directory, during the walk.** The walker reads a directory (names and `stat`), sorts it, and hands it to the recogniser, which returns datasets, unclaimed files, and the subdirectories not to enter. Results go to the database as now.
- For: one pass. The directory listing is exactly what header+data and marker formats need. Pruning (R11) falls out naturally. Order independence (R6) holds if the result is a function of the sorted listing plus bounded content. An incremental crawl re-runs recognition only for directories whose listing or mtimes changed (R10).
- Against: datasets that span directories (HDF5 external links to `../`, a raw file in a subfolder) aren't visible from one listing. A handler change needs a re-walk to take effect, although listings are cheap compared to probes.

**A2. Second pass over the index.** The walk stores everything, as now; recognition is a separate stage over the database: per-handler passes with priorities (an MR idea), SQL for grouping, the file system only for probes.
- For: handler changes re-run without walking; global questions ("all `.raw` without an `.xml` next to them") are one statement; the walk stays trivial.
- Against: this is what `mime_sql.py` was, and it failed on the basics: anchoring, weights, and O(handlers × files) scans. Handlers written as SQL are hard to test and hard to write by the hundred. Pruning can't happen because the walk has already visited the tree, so R11 needs a separate pre-pass with its own rules. Two places hold the truth about a directory.

**A3. A1 plus stored listings.** The walk stores listings anyway (the `files` table), so a handler change can re-run recognition from the database for directories that need no new probes, and from the file system otherwise. This is A1 with an optimisation, not needed for the spike.

Recommendation: A1, later A3. For datasets that reach beyond their directory, a handler declares how many parent levels it may look at (Bio-Formats' `getRequiredDirectories`) and the walker provides that context; anything beyond is out of scope for now.

Would change it: if Q2 or Q4 require datasets that group arbitrary subtrees ("session folder" datasets), recognition needs children before parents, which is a post-order walk; A1 survives, the walker changes.

**Incomplete datasets (Q3, R7) under A1.** Recognition re-runs for a directory whenever its listing changes. What to emit in between:
- A-i: emit what is recognisable now. An EMPAD XML without its raw becomes a single-file XML dataset; when the raw arrives, the dataset is re-emitted under the same anchor with more members. If the raw arrived first, it had its own record, which must disappear later (deleted records, backlog).
- A-ii: emit nothing for files a handler marks as "part of something incomplete", until complete or until a grace period passes. Files stay invisible for days; the grace period is state.
- A-iii: emit provisional datasets marked incomplete. Harvesters index incomplete things; needs a flag in the metadata.

Recommendation: A-i. It needs no state and converges by itself; the price is records that disappear, which we have to handle anyway.

## B. How a handler expresses recognition (Q6, R3, R5, R12, R14)

**B1. Code only.** `recognise(listing, probe) -> claims`, as in the current `FileHandler`, LiberTEM and Bio-Formats.
- For: anything is expressible; one thing to learn; easy for AI agents to write.
- Against: nothing can be checked without running it: no static conflict analysis (R5), no generated skeleton tests, and candidate selection means running every handler on every directory (R12), unless handlers also declare hints, which is B3.

**B2. Data only.** A handler is a declaration (type, parent, name patterns, magic, sibling rules, directory markers) interpreted by the core, as in PRONOM.
- For: fully analysable; conflict detection and skeleton generation are exact; contributors can't write slow or dangerous code.
- Against: no precedent for sibling and directory rules as data. Every system that tried pure data grew a DSL or an escape hatch (PRONOM #292, libmagic's `use` and `indirect`). EMPAD already needs "parse the XML, read the `raw_file` attribute, check that the file exists and has a plausible size".

**B3. Declaration plus optional probe.** A handler is a declaration the core can analyse (type and parent, name patterns with a case flag, magic with offset, sibling patterns, directory markers, scope, probe budget) plus an optional `probe(context)` function for what the declaration can't say. The declaration selects candidates and decides the cheap cases; the probe confirms, finds members and gives the basis.
- For: the analysable part covers conflict detection, skeleton tests and candidate selection; the probe keeps rare cases fixable; the declaration stays a schema rather than becoming a language.
- Against: two things to learn; pressure to grow the declaration into a DSL; if most handlers need a probe anyway, this is B1 with ceremony. Mitigation: keep the declaration minimal and count in the spike how many of the six handlers need a probe. Expected: EMPAD yes, Zarr no, Python environment no, plain files no, DM4 no, notebook maybe.

Recommendation: B3.

Would change it: deciding that only a small fixed core of handlers will ever exist (dropping R2) makes B1 fine.

## C. Priority, ambiguity and contention (Q1, Q5, R5, R9)

Covers several handlers claiming the same file, and several rules of one handler matching.

**C1. One global order or integer priority.** As in shared-mime-info and in `mime.py` today: weights on globs, priorities on magic, the core sorts.
- For: simple, and already implemented for single files.
- Against: numbers negotiated across independent repositories (Tika's comment negotiations), and unlisted handlers silently last (Galaxy).

**C2. Computed specificity, hierarchy, explicit ambiguity.** The core orders candidates by evidence class (directory marker, then sibling structure, then magic, then name, then fallback), within a class by specificity (longer pattern, more bytes, more siblings), then by depth in the type hierarchy. A more specific type refines a more generic one on the same files (hspy refines HDF5) instead of conflicting with it. What remains is a tie and is reported as ambiguous. A deployment may add overrides ("empad-raw wins over panasonic-raw") for proven cases, as data.
- For: contributors declare facts, not ranks; the ensemble test surfaces every tie; overrides are local to a deployment and reviewable.
- Against: specificity across evidence kinds is apples and oranges and will give surprising orders; libmagic's experience says overrides accumulate; the type hierarchy must be shared across repositories, and someone has to own `application/x-hdf5`'s children.

**C3. Declared "wins over" relations.** PRONOM style: a handler declares which types it beats.
- For: explicit and exact.
- Against: a handler must know the other one, across repositories; cycles and inconsistencies need a registry, which we would then be.

Recommendation: C2, with C3-style relations allowed only as deployment overrides.

**Contention and exclusivity (Q1).** Recommendation: exclusive membership by default (a file belongs to at most one dataset), with one declared exception class for metadata-only companions that may be shared, such as a README referenced from two places. Ambiguous or contested files get a plain single-file record, so they remain findable, plus a logged contention that the ensemble test treats as a failure unless the deployment's exemption data lists it. Bio-Formats shows the exemption list is unavoidable; keeping it as deployment data rather than test code keeps it reviewable.

Would change it: if Q1 allows multi-membership freely, contention mostly disappears and C2 only decides the type name. If the reviewers prefer predictability over "no coordination", C1 with a core-curated priority file is simpler.

## D. The dataset model and its anchor (Q2, Q4, R17, R22)

Proposed per dataset: `type`, `anchor` (a path), `members` (sorted paths, including the anchor), `handler` (name and version), `basis` (text), `warnings` (list). Metadata comes later (R15).

**Anchor (Q4).** The handler names it; the default is the file whose evidence triggered the claim: the header for header+data pairs (EMPAD XML, MIB `.hdr`), the directory for marker formats (Zarr, `node_modules`, an environment), the file itself for single files. This is what `open()` would take (MR) and it stays stable while members arrive (A-i).

**Nesting (Q2).** D1 flat: members are files, and a collapsed directory swallows everything beneath it, with no datasets inside. D2 nested: a directory dataset may contain child datasets, each with its own record, and membership exclusivity applies per level. D1 is enough for the spike, since Zarr, environments and `node_modules` all want "swallow everything". D2 becomes necessary once "session folder" or "project" datasets exist that contain real datasets.

Recommendation: D1 now; the record format keeps room for D2 (a `parent` field, unused).

Would change it: Q2 answered "yes, now".

## E. Packaging, registration and deployment configuration (R1, R2, R21, Q7)

- Discovery: Python entry points in a group such as `modama_crawler.handlers`, each naming a handler. Any installed package can contribute; nothing is imported until enabled.
- Enabling (R1): E1, an explicit list in the deployment config (`enabled = ["core.*", "empad", "zarr"]`); E2, everything installed minus a denylist. E1 makes a deployment self-describing; E2 is convenient in development. Recommendation: E1 with wildcards per collection.
- Loading: failures are collected and reported, not fatal (stevedore style); duplicate handler names and duplicate type identifiers are rejected at load time. Overrides (C2), exemptions (C) and path exclusions (R1) live in the same configuration file.
- Collections (Q7): one package per maintaining team or repository is the natural boundary; inside it, teams group as they like. The core ships `core.*` with common formats (R21) so a deployment has a baseline and the ensemble tests have something to run against. Handlers that share code (several HDF5-based types) belong together regardless of team.
- Versioning: each handler declares a version; records store handler name and version (R9), so a handler update can later trigger re-recognition of its datasets (A3).

Would change it: dropping R2 (one repository forever) makes the configuration a Python list; entry points would still be cheap.

## F. Testing and test data (R3, R4, R5, R8, R13, R14, Q8, Q10)

**Per handler (R3):**
- Skeleton fixtures generated from the declaration: minimal files and directories that satisfy its name, magic, sibling and marker rules (PRONOM's idea). Free, always available, and they expose declaration conflicts.
- Small real fixtures shipped in the handler package next to expected results (one JSON per fixture: type, anchor, members, warnings); fetched through a hash registry when too large for git; large files on Zenodo or an institute store, with a licence note per file (the RosettaSciIO pattern, Q8).
- A pytest plugin from the core provides the fixtures (`recognise(path)`, tree builders, the registry fetcher), so every handler package's tests look the same and an AI agent has one template to follow (R14).

**Per deployment (R4, R5):**
- Static: at load time, the core checks the enabled declarations for conflicts (identical globs for unrelated types, overlapping magic, duplicate markers) and reports them; the ensemble test fails on conflicts that aren't exempted.
- Skeleton suite: all enabled handlers' skeleton fixtures in one tree; every file must be claimed by exactly one handler (the Bio-Formats invariant), unless the deployment's exemption data says otherwise.
- Corpus: a real tree against the enabled handlers, with expectations ("this path is EMPAD", "no unclaimed files under X", "zero contention") and a report of every unclaimed, contested or failed file. Two corpus formats: F1, a subset of real files copied; F2, a "skeleton tree": the listing (paths, sizes, mtimes, modes) plus the first N KB of each file. F2 reproduces every name, magic, sibling and marker decision at a fraction of the size and can be captured from production with one command; probes that need more than N KB are the exception and get real fixtures. Recommendation: F2 as the main corpus format.

**From failure to test case (R8, R9):** every log line carries path, handler and basis. `modama-crawler explain PATH` prints the full decision for a path, and `modama-crawler capture DIR` writes a skeleton tree of a directory into a fixture, so a production failure becomes a test with one command plus an expectation file.

Would change it: if real data can't leave the institute even as prefixes, F2 fixtures stay internal and only skeletons and synthetic data go into public handler repositories.

## G. Execution and isolation (R24, R25, Q13)

- G1, in process: fastest and simplest to test; a segfault kills the crawl, which violates R24.
- G2, worker subprocesses with timeouts: a crash or hang costs one worker, which is restarted, and the crawl continues; the time budget (R12) is enforceable by killing. Works inside any container.
- G3, the whole crawler in a locked-down container (read-only data mount, no network, seccomp) with G2 inside: isolates the host from a compromised handler at deployment level, with no per-handler cost.
- G4, per-handler or per-file sandboxes (gVisor, micro-VMs): the strongest isolation, a large cost per file at millions of files, and complex.

Recommendation: G2 for the spike (it also forces the handler interface to be serialisable, which keeps it clean), G3 at deployment, G4 only if a concrete threat justifies it.

Against: subprocess pools complicate database access and debugging, and a process stuck in uninterruptible I/O on a network file system can't be killed, so the pool also needs a way to give up on a path.

## Combined sketch

If all recommendations held, a handler would be a declaration plus an optional probe, in a package that registers it through an entry point. Illustration only, not an API proposal:

```python
from modama_crawler.handlers import Declaration, Context, Claim

EMPAD = Declaration(
    type="application/x.empad",          # naming scheme: Q14
    parent="application/xml",            # refines generic XML
    version="1",
    names=["*.xml"],                     # candidate by name; weak evidence
    magic=[(0, b"<root name=")],         # candidate by content
    siblings=["*.raw"],                  # needs a raw file in the same directory
    probe_budget=(64 * 1024, 2.0),       # bytes, seconds
)

def probe(ctx: Context) -> Claim | None:
    raw_name = ctx.xml_attribute("raw_file", "filename")   # bounded parse
    raw = ctx.sibling(raw_name)
    if raw is None:
        return None                      # not EMPAD, or not complete yet (A-i)
    return Claim(anchor=ctx.path, members=[ctx.path, raw], basis=f"raw_file points to {raw.name}")


ZARR = Declaration(
    type="application/x.zarr",
    directory_markers=["zarr.json", ".zarray", ".zgroup"],
    collapse=True,                       # the directory is the dataset; don't descend
    version="1",
)
```

A deployment configuration lists enabled handlers, overrides and exemptions:

```toml
[handlers]
enabled = ["core.*", "empad", "zarr", "python-env", "dm4", "ipynb"]

[overrides]
"application/x.empad-raw" = { wins_over = ["image/x-panasonic-rw"] }

[exemptions]
"/adhoc/legacy/*.raw" = "two cameras wrote .raw here; sorted out by hand"
```

## Strongest arguments against the combination

1. It is a framework. R20 says YAGNI and the spike has six handlers; everything above could be six Python functions and a list. The counter-argument is R2 and the thousand-handler horizon. The honest answer: the spike implements only what six handlers and one deployment need, and this document is a direction, not a backlog.
2. Declarations, probes and specificity rules are three concepts where Bio-Formats has one, a reader class with `isThisType`. Bio-Formats also has a hand-ordered list and 25 exemptions. Which is worse is partly an empirical question the spike can answer.
3. Per-directory recognition can't see across directories. Formats that need that will appear; the question is whether they're common enough to design for now.

## Decision log

| Date | Decision | Why | Alternatives |
|---|---|---|---|
| 2026-10-14 | `oai_dc` is the only output format | DataCite requires a DOI; the EOSC warehouse converts DC itself | DataCite with a URL identifier |
| 2026-10-14 | The server reads only the `records` table; recognition and metadata happen at crawl time | No file system access while serving; bounded and testable | Request-time handlers, as in the proof of concept |
| 2026-10-14 | Single-file MIME detection follows the shared-mime-info checking order, in Python | Spec compliance; the SQL version had anchoring and weight bugs | SQL prefilter, removed |

Sections A to G are open.
