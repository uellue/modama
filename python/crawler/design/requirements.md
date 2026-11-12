# Dataset recognition: requirements

Status: second draft, after @weber's review of 2026-10-14 (comments on MR !106). Reviewers: @weber, @clausen, @shanker.

This is step 2 of the crawler plan (1: the OAI-PMH server, 2: dataset recognition, 3: metadata extraction): turn the file tree into datasets. Step 3, metadata extraction, is covered only as far as it constrains the architecture.

How to review: edit this file directly, commit and push on the `crawler` branch. Comments go inline as quotes starting with your handle, for example:

> **@clausen:** R6 is too strong, order independence only matters within a directory.

Resolved comments are removed and the outcome goes into the decision log in `architecture.md`.

Earlier notes by @weber and @clausen on MR !106 (June to August 2026) are folded in and marked (MR). They were wishes and ideas, not settled requirements: after @weber's review, the ones kept carry a priority like the others, and the technical solutions mentioned there appear under "options on the table", not as requirements.

## Vocabulary

Proposed definitions. Several are open, see the questions at the end.

- **File:** an entry in the file tree as seen by the crawl: regular file, directory or symlink, with path, size, mtime and owner.
- **Dataset:** the unit that gets one OAI-PMH record. A single file or a collection of files that belong together, for example an EMPAD XML with its raw file, a Zarr directory, or a Python environment collapsed into one unit.
- **Member:** a file that belongs to a dataset.
- **Anchor:** the member whose path identifies the dataset: the entry point, what one would pass to an `open()` function (MR). It defines the identifier and the browse URL, so it has to be stable.
- **Dataset type:** what kind of dataset it is, named by a MIME-type string (R25).
- **Format** (decided 2026-10-16, previously "handler"): the definition of one kind of dataset: its identifier and description (R25), the rules that recognise it (XDG MIME XML, plus a Python *recognizer* where needed), and later its metadata *extractor* and relations. The admin-facing unit, selected by id `collection/format`, for example `gatan/dm4`. "Format" is used loosely, as people do: a Python environment or a TENSOR export is a format in this sense. Older text in these documents says "handler" for the same thing.
- **Collection:** a set of formats shipped together as a Python package (`modama-formats-*`, entry-point group `modama.formats`), possibly from a separate repository.
- **Deployment:** one installation of the crawler with a chosen set of handler collections and per-handler settings.
- **Recognition:** deciding which files form which datasets and which handler is responsible for each.

## Requirements

Priorities: **must** for the first working version, **should** for soon after, **later** for anything we only keep in mind now.

### Composition and independence

- **R1 (must)** Handlers can be enabled and disabled per deployment, individually. Example: EMPAD raw files are needed at ER-C, Panasonic raw images are not, until someone buys such a camera. A deployment can also exclude paths from the crawl entirely, with gitignore-like defaults proposed by the collections (for example `__pycache__`, `.ipynb_checkpoints`) and the actual list per deployment (@weber, 2026-10-27, play test), and exclude paths from individual handlers: a directory of files known to crash one reader is still crawled and classified by name, but that reader never opens them (MR; wrapping handlers with pre-filters is one way to do it).
- **R33 (must, decided 2026-10-27)** An id in `select`, `ignore` or a per-path ignore that names no installed collection or format is an error naming the id and the installed ids, before anything is crawled; a typo never silently changes what runs. Example: `--ignore collapse/vnev` used to run everything, `--select nosuch` disabled every format with exit 0. Several ids in one argument separated by commas are a list, as in ruff (`--ignore collapse,zarr`; @weber, 2026-10-27).
- **R2 (must)** Handlers can be developed in separate repositories by separate teams without getting in each other's way. The crawler core defines the interface, and a handler collection is an installable package.
- **R3 (must)** A handler can be tested on its own, per file or per test tree, and unrelated handlers upstream don't change the result of its tests.
- **R4 (must)** A deployment can be tested as a whole: a real-world file tree against the assembled handlers, with general rules (for example "no contention", "every file classified") and specific expectations ("this path is an EMPAD dataset"), producing a works/doesn't-work verdict.
- **R21 (should)** A core collection of common formats (JPEG, PNG, plain text, generic HDF5, …) ships with the framework and is the baseline for ensemble tests (MR). These are the common cases of normal files and generic scientific work; this intersects with selecting handlers by topic (Q7).
- **R34 (must, @weber 2026-10-27)** Generic definitions can be overridden: generic overrides especially for the core collection (curating vendored rules that are wrong for us, for example `*.raw` as a Panasonic image), and fixes and overrides per deployment (data repository). The first mechanism is `core/er-c.xml`: a tie that forces a content check, without editing the vendored file.

### Correctness

- **R5 (must)** Cross-talk between handlers is detected: ambiguous name matching, wrong priorities, ambiguous content matching, and contention, where two handlers claim the same file. Detection happens in tests of the composed deployment, and at crawl time with logging.
- **R6 (should)** The result is independent of the order in which files are crawled: best effort, not a hard gate. One part is a **must**: a dataset's anchor is the same whichever member is seen first. A cleanup step over the database is an acceptable way to get there.
- **R7 (must)** The file system is read-write and in use. Files can be missing, incomplete or inconsistent at any time. Recognition handles this gracefully and reaches a consistent state once the files are complete.
- **R8 (must)** Errors and warnings are logged with enough context to reproduce the case as a test. The path from a real-world failure to a test case and a fix is short.
- **R9 (must)** Recognition is explainable. The basic version is a must: run recognition on one file or directory and inspect the outcome. The full version is a should: for every dataset, which handler claimed it and on what basis, and for every unclaimed or contested file, why.
- **R22 (should)** Stray files, those next to or inside a dataset that no handler claims, are reported rather than silently absorbed or silently skipped (MR). Unclaimed files are normal, for example raw numeric data without an extension; they become `application/octet-stream` datasets. They must stay inspectable, grouped by extension and location, because of these scenarios:
  - A sudden jump in unclaimed files: a handler stopped matching them, or the system tombstoned them by mistake.
  - A new file type appears for which no handler is active: a distinctive extension that nobody claims is suspicious.
  - Routine maintenance: look at new unclaimed files and decide whether an existing handler's rules should be extended (an unknown variant of a known format) or a new handler is needed.
  Files claimed only by a generic type (XML, YAML, JSON, ZIP, …) are suspicious in the same way, since most of them follow a domain-specific schema (`docker-compose.yml`, Dublin Core XML) that a sub-handler could distinguish. Both reviews are candidates for agentic workflows (R14): inspect the likely candidates, then search for, activate or create a handler.
- **R35 (must, decided 2026-10-27)** What recognition sees: regular files and directories. Symlinks, special files (FIFOs, devices), files the crawl cannot read and directories it cannot list are skipped with a diagnostic naming the entry and the reason, and get no record; names that cannot be stored (not valid UTF-8) are reported. The one exception: the path the operator named on the command line being unreadable or missing is an error. A record for symlinks to files is an open question in the backlog.
- **R36 (should, @weber 2026-10-27)** Severity model, to serve operators and end users: *info* for diagnostics, as detailed as needed; *warning* for what the operator might want to review or act upon; *error* where action is likely required. Warning and error output must not be crowded with items that are not actionable or that repeat: similar items are summarised in one line, such as "123456 unreadable files encountered", so that an operator keeps an overview over millions of files. The concrete rules grow from examples and user stories (Q20); the exit status of a run with warnings is zero.
- **R42 (must for production, @weber 2026-11-12)** A schema change reaches an existing crawler database in place, without recreating it.
  - Datasets, extractions, records with their datestamps and the run history are kept, so a change costs no re-crawl, re-harvest or re-indexing (staging: about a night; `field-tests/search-stack-staging-findings.md`).
  - The change is applied by one explicit step before the crawler's services start, never by two processes at once and never during a crawl.
  - A crawler refuses a database whose schema is not the one its code expects, and names the step to take.
  - Example: staging's database, made by commit 3251cad, gains `crawl_runs.scope`, with its 1.45 million records and their datestamps unchanged.
  - Accepted when a database made by the code before this change migrates in a test and compares equal to a fresh one, and a copy of staging's database migrates before staging does.
  - Mechanism: the `database-schema` spec (change `schema-migrations`), with Alembic.

### Scale

- **R10 (must)** Millions of files, petabytes, hundreds to thousands of new files per day. A full crawl stays feasible, and a re-crawl only does work for what changed. The survey of 2026-10-15 saw a quarter of the tree (525k files, 18 TB) and 58 files changed in a week; the rest is behind permissions. The gap is not a contradiction: `/er-c-data` and its user base are growing, and the design targets the situation two or more years out, not today's. The figures here are the planning assumption.
- **R11 (should)** Large uninteresting trees (`node_modules`, Python and conda environments, large source trees, large Zarr arrays) are recognised early and not visited file by file. The contents of a multi-file dataset are not crawled individually; there is no point in indexing the chunks of a Zarr array (MR).
- **R12 (must)** Every probe has a time limit; until hang isolation exists (worker subprocesses, R23) it is checked after the call and a slow result is discarded, so a hanging format can still stall a crawl (review 2026-11-03, B14). **(should)** Recognition is as fast and light as possible: reading file names and metadata is free, reading a bounded amount of content is allowed, reading whole files is not, and trying every handler on every file is out (MR). The crawl reports the slowest handlers, like pytest's `--durations`, so the impact of changes is visible.

### Development and testing

Test data has to be collected and improved continuously: new format variants, issues that show up in the real world, and proof that a deployment keeps working. This project indexes metadata, not bulk data, so unlike LiberTEM most of it can be tested on very small or even mocked files, and the real world is caught by dedicated pipelines on real data.

- **R13 (must)** Two kinds of tests. *Per-handler tests* are universal and self-contained: they run after installation without network access or external data, on small or generated files. *Per-deployment tests* run the assembled handlers against real data in a dedicated pipeline, regularly in CI, in the spirit of LiberTEM's data pipeline, and catch what small files can't. A composed deployment can run the per-handler tests of all its collections without manual setup. How test data is best defined and provided, with guidance for the preferred way and flexibility for complex formats, is a core design question (Q8).
- **R27 (must)** Every issue found on real data becomes a small reproducer in the responsible handler's tests. A workflow for agents (R14) helps derive a small file from a large real-world case. Reproducers derived from production data are scrubbed and reviewed before they are committed. Reproducers that may only be valid for our software and not for the originating application are labelled as such.
- **R28 (should)** A shipped fixture is bound to its expected outcome (type, anchor, members, warnings, selected metadata, or the error it must raise), so that file content and expectations don't drift apart. Generated fixtures carry this in code; shipped files need a companion record that a test fixture picks up.
- **R29 (must, decided)** Test files have two purposes that are kept apart. *Representative files* are realistic files as found in the wild, written by the instrument, the application, or the library that writes the format in practice; every file-specific rule (glob, magic, Python handler) has at least one representative file that matches it. *Reproducers* for crashes or wrong results caused by invalid or incomplete files are the only exception from realism. Synthetic and skeleton files test the rule engine and live in the core, not in handler collections (`testing.md`).
- **R40 (must, @weber 2026-10-27)** The oracle is usable without shell tricks: `records --verbose | less` shows the records together with their diagnostics, associated per record so that the two can be matched even on a large tree; the user is not expected to redirect or merge streams. The stdout/stderr split holds for machine use without `--verbose`. Mechanism in the `records-cli` spec: diagnostics as XML comments in path order, the document stays valid. Judged in a real terminal, by eye (`design/playtest.md`, visual check); repeat after changes to the output.
- **R14 (must)** Developing a handler, including finding or generating test data and writing unit and integration tests, is easy for humans and for AI agents. Skills or templates for agents are part of the deliverable. The central one is a workflow for defining a dataset type: an agent looks at sample files or directories, figures out what they are and how they group, works it out with the user in questions and answers, and develops the matching rules, the metadata extractor and the relation extractor ("produced by this script") together with their fixtures. This conversation, which found the TENSOR export and the series kinds in the survey, is the prototype of that workflow.

### Security (MR)

Handlers are code of varying quality and origin, run on inputs that users control, by a process that opens every file in the repository on a schedule. File readers are rarely hardened against malicious input; one HDF5 file that segfaults its decoder has already been seen, and a data file that is effectively executed by its reader is a known pattern. A weird file isn't suspicious in a research file system, so the crawler is an attractive delivery vehicle for an exploit.

- **R23 (must for production)** A crashing, hanging or misbehaving handler doesn't take the crawl down. Failures are isolated per file and handler, reported (R8), and the crawl continues. May be deferred during the initial design to keep it simple.
- **R24 (should)** A compromised handler can't modify data, reach the network, or gain a permanent foothold on the host. The architecture enables this; the actual hardening comes later, and the options are evaluated in `architecture.md` G.

Options on the table, to be weighed against cost and complexity, not requirements: read-only mounts, no network, subprocess workers with timeouts, container seccomp profiles, gVisor or Kata, short-lived micro-VMs, and `CAP_DAC_READ_SEARCH` to read everything once isolation exists (until then R18 applies).

### Identifiers and metadata (MR)

- **R25 (must, decided)** Dataset types are named by MIME-type strings with valid MIME syntax, so that a custom type could become official one day: official types where they exist, then established unofficial ones as XDG MIME uses them (`application/x-ipynb+json`, `application/x-npy`, `application/x-dm4-tem`), then our own. No hierarchy of our own beyond what MIME offers. Every non-standard identifier carries a description, a link to its source, and a mapping to the closest official type.
- **R37 (must, decided 2026-10-27)** The datestamp of a multi-file dataset is the newest of its members' and parts' modification times; for a collapsed directory, whose contents are not visited by design, it is the directory's own modification time as a baseline, and the format may override it when it reads the store. Consequence for incremental harvesting (R10): a rewritten store whose directory mtime did not move is not seen by a `from` query until its record changes.
- **R38 (must, details TBD)** The member files of every dataset are known in the result, and a format can represent them in the record as it sees fit, for example by overriding methods of its parent handler class. The default representation is open (Q21): the user stories so far are "what is inside this dataset" and "which dataset does this file belong to"; @weber's lean is `dc:description` entries, top-down for nested structures, cut at about 100 entries. To be settled in end-to-end tests of the search with real users.
- **R39 (must, decided)** Identifier limits: the local part of the OAI identifier after the last `:` is at most 255 characters, because the EOSC warehouse cuts there and stores `VARCHAR(255)`; longer local parts are shortened with a hash suffix (@weber, 2026-10-14). Characters that XML 1.0 cannot carry (control characters) are replaced in `dc:title` and percent-encoded in the identifier and browse URL; non-UTF-8 names are reported and skipped (R35).
- **R15 (later)** Handlers extract metadata from tags and content, for example the code cells of a Jupyter notebook or the tags of a DM4 file. The recognition design must not stand in the way of this, but it isn't designed in detail yet.
- **R26 (later)** Metadata from several extractors per dataset can be combined into one record, with generic extractors (an HDF5 dump, `stat()` results) applied only where a subtype wants them, so a notebook isn't also dumped as generic JSON. How that works for subtypes (a notebook is JSON, an office document is a ZIP) is Q15. The MR notes suggest merging partial results into one human-readable document with the file system authoritative for conflicts such as dates and owners; that is an option, not a requirement.
- **R16 (later)** Vision-language models or similar for metadata extraction.

Keeping guessing (cheap candidates), recognition (authoritative) and metadata extraction as separate stages, as the MR notes propose, is an architecture option discussed in `architecture.md`.

### Search goals (decided 2026-10-16)

- **R30 (must)** The index serves search: it helps people find things that match a query, and once they have an anchor they make sense of the data themselves. Misgrouping is therefore not a disaster. Two outcomes are bad: flooding the results with hundreds or thousands of similar, related files, which should have been found as one collection; and not finding something although the file tree and file contents held enough information to match the query. When in doubt, an accidental split beats an accidental grouping, because a grouping can hide distinctive items.
- **R31 (should)** Grouping guideline, derived from R30: fewer than 10 files in a suspected series are always indexed individually as well; 10 to 100 depending on the case; more than 100 only as the group, unless some members are clearly distinct (one overview plus hundreds of detail images). Complex program outputs (a Quantum Espresso run, a TENSOR export, a Dr. Probe run) are one unit. To make this testable when series are implemented, the thresholds and the "clearly distinct" exception are settled on examples: 200 `frame_NNNN.tif` → one group; 5 → five records; 150 frames plus `overview.png` and `log.txt` → the group and the two distinct files (play test E06, 2026-10-27).
- **R32 (should)** Where a handler can tell, a dataset records its relations: part of a collection, produced by a script or program (with the parameter file where there is one), belongs to a specimen or session. In `oai_dc` these go into `dc:relation` and `dc:source` with a documented convention; richer vocabularies are a later format.

### Carried over from earlier decisions

- **R17** One OAI-PMH record per dataset. A dataset can be a single file.
- **R18** Whatever the crawl process can read is in scope. No per-user access checks at crawl time; per-user views are a deferred requirement.
- **R19** PostgreSQL stays, unless something non-relational turns out clearly better.
- **R20** YAGNI: solve the ER-C case first, keep the core small, and add generality when a concrete need appears.

## Non-goals for now

Deleted records, per-user access checks, DataCite output, deployment packaging, metadata extraction beyond what the spike needs. All in `../BACKLOG.md`.

## Spike

The architecture is validated with a prototype before it is final. Handlers for the spike, ranked by payoff on the visible part of the ER-C tree (`survey.md`, 2026-10-15) while staying different from each other:

| Handler | Why | In the visible tree |
|---|---|---|
| Plain single files (text, PNG, …) | The default case | everything else |
| Collapsed trees: Python and conda environments, `site-packages`, `__pycache__`, `.ipynb_checkpoints`, `.git`, Quantum Espresso `*.save` | Large trees to collapse into one dataset, or to ignore | 74k files, 14% of all |
| Series directories: numbered frames of one type, optionally with a header (`.tif`, `.npy`, `.bin`, MIB `.hdr` + `.mib`) | The dominant dataset shape; a rule derived from examples | 371k files in numbered groups; 67k `.tif` in one directory |
| DM3/DM4 | The largest single-file population, with many tags for the metadata path | 28k files, 3.2 TB |
| Zarr (v2 and v3, nested) | A directory tree with marker files; nests in practice | 132 `.zarr` directories |
| Jupyter notebook | Single file whose content (code cells) matters for indexing | 1.5k files |
| Pairs: TIA `.emi` + `.ser`, EMPAD XML + raw | Two files linked by name or content; EMPAD code exists already | 324 TIA pairs, 52 EMPAD pairs |

Immediately after: HDF5 (7.6k `.h5`, 4.4k Velox `.emd`, 1.2k `.nxs`), in particular datasets split over several files, and as an earmarked test case, HDF5 files with overly complex tag structures as generated by Matlab.

## Questionnaire check (2026-11-03, `/kaizen:requirements` in document mode)

This document, `../AGENTS.md`, `architecture.md`, `survey.md` and `../BACKLOG.md` read against the sections of ER-C's demand and requirements form (the software-adapted questionnaire in the kaizen plugin). Deferred by @weber: the open questions are recorded here and taken up later.

| Section | State | What the record says, and what it does not |
|---|---|---|
| 1.1 Problem and context | answered | Make the ER-C file system searchable through the EOSC metadata warehouse; petabytes, millions of files, a messy tree. Not stated: what it costs today that data is not findable. |
| 1.2 Current solutions | partly | The proof of concept and its defects, `prior-art.md` for libraries. Not stated: how people find data today (folder names, asking colleagues, the ELN), and whether a data catalogue product was considered instead of a crawler. |
| 1.3 Benefits | assumed | Search over the data, FAIR findability, the EOSC connection. No figure for time saved or for which projects wait for it. |
| 1.4 Users | partly | Internal to the institute, growing over two years (R10). Not quantified: how many people would search, how often, with what skills; who is explicitly not a user. |
| 2.1 Use scenarios | partly | The operator installing it (Q17 walk-through), the format author (TEMPLATE.md), the critical first user of the oracle (play test). Missing: the scientist searching the index, the operator reading the log after a night run, and frequencies. |
| 2.2 Demand uncertainties | answered | The open questions below, growth of the tree and user base, the warehouse's quirks. |
| 2.3 Interfaces | answered | EOSC metadata warehouse (oaipmh-scythe, DC→DataCite XSLT, 255-character identifiers), the modama browse URL, pyxdg and shared-mime-info, PostgreSQL. |
| 2.4 Operating conditions | partly | A container behind the gateway with a read-only data mount (backlog). Not stated: the production host, the user the crawl runs as and what it can read, the schedule. |
| 2.5 Availability and reliability | partly | A failing format does not stop the crawl (R23); monitoring is Q18. Not stated: the consequence of a stale or wrong index, and who notices it. |
| 2.6 Performance | answered | Millions of files, hundreds to thousands of new files a day (R10); measured: two hours for 428,000 files, a full harvest in 58 s. Not stated: how stale the index may be (a day?), and a target crawl duration. |
| 2.7 Testing, installation, service | partly | Real-client tests, fixtures and the plugin, CI pending. Not stated: who operates it after the project and with how much time. |
| 2.8 Portability and distribution | partly | Collections as pip packages, a container for the service. Nothing else needed so far. |
| 2.9 Jurisdictions | unknown | Licences of what we ship and vendor (GPL-2.0-or-later freedesktop.org.xml, MPL-2.0 pathspec, MIT) are not summarised; personal data (file owners as `dc:creator`) was accepted for an internal service, but the harvester is external: what may leave the institute is not written down. |
| 2.10 Lifetime and decommissioning | unknown | Identifiers are browse URLs that must stay stable; nothing says for how long, or what happens to harvested records when the service is retired. |
| 2.11 Safety and risks | partly | Read-only mount, a compromised handler (R24), flooding the search (R30), the data tree as untrusted input. Not stated: the I/O load of a crawl on the storage that instruments write to, and data-protection sign-off for the records that leave. |
| 2.12 Standards | answered | OAI-PMH 2.0, `oai_dc`, shared-mime-info, FAIR by intent. |
| Release | unknown | Who decides, builds, pays and signs off is not in the record; the merge request names reviewers, not a principal. |

## Open questions

Questions answered in @weber's review are in the decision log of `architecture.md`. Still open:

- **Q8** How test data is defined, provided and shared. Generated fixtures bind content to expectations and make round-trip checks easy, but miss the quirks of files written by other software, and generating invalid or arcane files can turn into confusing, complex code. Shipped real files capture quirks and can be inspected with external tools, but disconnect content from expectations and may enshrine reproducers that only our parser accepts. Where large or external files are still needed, how they are provided (hash registry, institute store, Zenodo, skeleton trees captured from production) and licensed. Guidance for the preferred way per kind of format, and flexibility for complex cases. Other projects' accessible test-data collections may be reused rather than rebuilt: LiberTEM's collection for a deployment pipeline on self-hosted runners, as LiberTEM does; public collections (RosettaSciIO, Bio-Formats samples, …) where the licence allows. This is one of the core design questions; options and the decisions T1 to T7 are in `testing.md`. Still unconfirmed there: the mix of fixture kinds (T-A).
- **Q18** Where is the line between per-deployment tests and monitoring of a deployment? If the same expectations (known-good present, known-bad reported, unclaimed counts within bounds) can be evaluated on a snapshot in CI and on the live index after each production crawl, the two may be one mechanism. See `testing.md` T-D.
- **Q15** How generic extractors apply to subtypes, for example a notebook that is JSON or an office document that is a ZIP (R26). Later.
- **Q16** How Python extensions and XDG MIME rules compose: how a multi-file handler declares what it reacts to (the MIME types of candidate files?), what context it gets (a directory group from the index, free queries, both), and how its priority relates to XDG weights. `architecture.md` A and B.
- **Q20** The severity model (R36) in detail: which diagnostics are summarised, what the summary lines say, what the crawl's own summary counts. Grown from examples and user stories; meta-requirement: ask operators and users whether the output was helpful, as part of user testing (TODO).
- **Q21** How members of a dataset show in a record (R38): collect user stories, decide in end-to-end search tests with real users (TODO).
- **Q22** (questionnaire 2.9, 2.11) What may leave the institute through the harvester: file owners' names, full paths, anything else in the records; who signs that off (data protection), and which licence notice ships with the vendored and third-party parts. Narrowed 2026-11-04: the warehouse runs inside the institute (`architecture.md` decision log), so the question is whether anything is passed on beyond it, for example to EOSC's central services, and the licence notice.
- **Q23** (2.5, 2.7) Who operates the service after the project, with how much time; what the consequence of a stale or wrong index is, and how they would notice. Feeds Q18 and the severity model Q20.
- **Q24** (2.6) How stale the index may be, and the target duration of a crawl at the stated scale; decides parallelisation and the Rust question in the backlog.
- **Q25** (2.10) For how long identifiers and harvested records must stay valid, and what decommissioning looks like for a repository that others have harvested.
- **Q26** (1.3, 1.4, 2.1) The scientist's search scenario with figures: who searches, how often, for what, and what "found" means to them; the end-to-end search test with real users (Q21) is where it is settled.
- **Q27** (release) Who the principal is, who pays, and who signs off that the requirements are complete.
- **Q17** How a handler collection is packaged and registered: XML definitions plus an optional Python module per collection, discovered how, enabled how. `architecture.md` E.
