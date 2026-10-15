# Dataset recognition: requirements

Status: second draft, after @weber's review of 2026-10-14 (comments on MR !106). Reviewers: @weber, @clausen, @shanker.

This is step 2 of the crawler plan (see `../AGENTS.md`): turn the file tree into datasets. Step 3, metadata extraction, is covered only as far as it constrains the architecture.

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
- **Handler:** the code and rules that recognise one kind of dataset and, later, extract its metadata.
- **Handler collection:** a set of handlers shipped together, for example as a Python package, possibly from a separate repository.
- **Deployment:** one installation of the crawler with a chosen set of handler collections and per-handler settings.
- **Recognition:** deciding which files form which datasets and which handler is responsible for each.

## Requirements

Priorities: **must** for the first working version, **should** for soon after, **later** for anything we only keep in mind now.

### Composition and independence

- **R1 (must)** Handlers can be enabled and disabled per deployment, individually. Example: EMPAD raw files are needed at ER-C, Panasonic raw images are not, until someone buys such a camera. A deployment can also exclude paths from the crawl entirely, and exclude paths from individual handlers: a directory of files known to crash one reader is still crawled and classified by name, but that reader never opens them (MR; wrapping handlers with pre-filters is one way to do it).
- **R2 (must)** Handlers can be developed in separate repositories by separate teams without getting in each other's way. The crawler core defines the interface, and a handler collection is an installable package.
- **R3 (must)** A handler can be tested on its own, per file or per test tree, and unrelated handlers upstream don't change the result of its tests.
- **R4 (must)** A deployment can be tested as a whole: a real-world file tree against the assembled handlers, with general rules (for example "no contention", "every file classified") and specific expectations ("this path is an EMPAD dataset"), producing a works/doesn't-work verdict.
- **R21 (should)** A core collection of common formats (JPEG, PNG, plain text, generic HDF5, …) ships with the framework and is the baseline for ensemble tests (MR). These are the common cases of normal files and generic scientific work; this intersects with selecting handlers by topic (Q7).

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

### Scale

- **R10 (must)** Millions of files, petabytes, hundreds to thousands of new files per day. A full crawl stays feasible, and a re-crawl only does work for what changed.
- **R11 (should)** Large uninteresting trees (`node_modules`, Python and conda environments, large source trees, large Zarr arrays) are recognised early and not visited file by file. The contents of a multi-file dataset are not crawled individually; there is no point in indexing the chunks of a Zarr array (MR).
- **R12 (must)** Every probe has a hard time limit. **(should)** Recognition is as fast and light as possible: reading file names and metadata is free, reading a bounded amount of content is allowed, reading whole files is not, and trying every handler on every file is out (MR). The crawl reports the slowest handlers, like pytest's `--durations`, so the impact of changes is visible.

### Development and testing

Test data has to be collected and improved continuously: new format variants, issues that show up in the real world, and proof that a deployment keeps working. This project indexes metadata, not bulk data, so unlike LiberTEM most of it can be tested on very small or even mocked files, and the real world is caught by dedicated pipelines on real data.

- **R13 (must)** Two kinds of tests. *Per-handler tests* are universal and self-contained: they run after installation without network access or external data, on small or generated files. *Per-deployment tests* run the assembled handlers against real data in a dedicated pipeline, regularly in CI, in the spirit of LiberTEM's data pipeline, and catch what small files can't. A composed deployment can run the per-handler tests of all its collections without manual setup. How test data is best defined and provided, with guidance for the preferred way and flexibility for complex formats, is a core design question (Q8).
- **R27 (must)** Every issue found on real data becomes a small reproducer in the responsible handler's tests. A workflow for agents (R14) helps derive a small file from a large real-world case. Reproducers derived from production data are scrubbed and reviewed before they are committed. Reproducers that may only be valid for our software and not for the originating application are labelled as such.
- **R28 (should)** A shipped fixture is bound to its expected outcome (type, anchor, members, warnings, selected metadata, or the error it must raise), so that file content and expectations don't drift apart. Generated fixtures carry this in code; shipped files need a companion record that a test fixture picks up.
- **R29 (must, decided)** Test files have two purposes that are kept apart. *Representative files* are realistic files as found in the wild, written by the instrument, the application, or the library that writes the format in practice; every file-specific rule (glob, magic, Python handler) has at least one representative file that matches it. *Reproducers* for crashes or wrong results caused by invalid or incomplete files are the only exception from realism. Synthetic and skeleton files test the rule engine and live in the core, not in handler collections (`testing.md`).
- **R14 (must)** Developing a handler, including finding or generating test data and writing unit and integration tests, is easy for humans and for AI agents. Skills or templates for agents are part of the deliverable.

### Security (MR)

Handlers are code of varying quality and origin, run on inputs that users control, by a process that opens every file in the repository on a schedule. File readers are rarely hardened against malicious input; one HDF5 file that segfaults its decoder has already been seen, and a data file that is effectively executed by its reader is a known pattern. A weird file isn't suspicious in a research file system, so the crawler is an attractive delivery vehicle for an exploit.

- **R23 (must for production)** A crashing, hanging or misbehaving handler doesn't take the crawl down. Failures are isolated per file and handler, reported (R8), and the crawl continues. May be deferred during the initial design to keep it simple.
- **R24 (should)** A compromised handler can't modify data, reach the network, or gain a permanent foothold on the host. The architecture enables this; the actual hardening comes later, and the options are evaluated in `architecture.md` G.

Options on the table, to be weighed against cost and complexity, not requirements: read-only mounts, no network, subprocess workers with timeouts, container seccomp profiles, gVisor or Kata, short-lived micro-VMs, and `CAP_DAC_READ_SEARCH` to read everything once isolation exists (until then R18 applies).

### Identifiers and metadata (MR)

- **R25 (must, decided)** Dataset types are named by MIME-type strings with valid MIME syntax, so that a custom type could become official one day: official types where they exist, then established unofficial ones as XDG MIME uses them (`application/x-ipynb+json`, `application/x-npy`, `application/x-dm4-tem`), then our own. No hierarchy of our own beyond what MIME offers. Every non-standard identifier carries a description, a link to its source, and a mapping to the closest official type.
- **R15 (later)** Handlers extract metadata from tags and content, for example the code cells of a Jupyter notebook or the tags of a DM4 file. The recognition design must not stand in the way of this, but it isn't designed in detail yet.
- **R26 (later)** Metadata from several extractors per dataset can be combined into one record, with generic extractors (an HDF5 dump, `stat()` results) applied only where a subtype wants them, so a notebook isn't also dumped as generic JSON. How that works for subtypes (a notebook is JSON, an office document is a ZIP) is Q15. The MR notes suggest merging partial results into one human-readable document with the file system authoritative for conflicts such as dates and owners; that is an option, not a requirement.
- **R16 (later)** Vision-language models or similar for metadata extraction.

Keeping guessing (cheap candidates), recognition (authoritative) and metadata extraction as separate stages, as the MR notes propose, is an architecture option discussed in `architecture.md`.

### Carried over from earlier decisions

- **R17** One OAI-PMH record per dataset. A dataset can be a single file.
- **R18** Whatever the crawl process can read is in scope. No per-user access checks at crawl time; per-user views are a deferred requirement.
- **R19** PostgreSQL stays, unless something non-relational turns out clearly better.
- **R20** YAGNI: solve the ER-C case first, keep the core small, and add generality when a concrete need appears.

## Non-goals for now

Deleted records, per-user access checks, DataCite output, deployment packaging, metadata extraction beyond what the spike needs. All in `../BACKLOG.md`.

## Spike

The architecture is validated with a prototype before it is final. Handlers for the spike, chosen to be different from each other:

| Handler | Why |
|---|---|
| Plain single files (text, PNG, …) | The default case |
| EMPAD | Two files, XML plus raw, linked by content |
| Zarr | A directory tree with marker files; potentially huge |
| Python environment | A large tree to collapse into one dataset |
| DM4 | Single file with many interesting tags, for the metadata path |
| Jupyter notebook | Single file whose content (code cells) matters for indexing |

Immediately after: HDF5, in particular datasets split over several files, and as an earmarked test case, HDF5 files with overly complex tag structures as generated by Matlab.

## Open questions

Questions answered in @weber's review are in the decision log of `architecture.md`. Still open:

- **Q8** How test data is defined, provided and shared. Generated fixtures bind content to expectations and make round-trip checks easy, but miss the quirks of files written by other software, and generating invalid or arcane files can turn into confusing, complex code. Shipped real files capture quirks and can be inspected with external tools, but disconnect content from expectations and may enshrine reproducers that only our parser accepts. Where large or external files are still needed, how they are provided (hash registry, institute store, Zenodo, skeleton trees captured from production) and licensed. Guidance for the preferred way per kind of format, and flexibility for complex cases. Other projects' accessible test-data collections may be reused rather than rebuilt: LiberTEM's collection for a deployment pipeline on self-hosted runners, as LiberTEM does; public collections (RosettaSciIO, Bio-Formats samples, …) where the licence allows. This is one of the core design questions; options and the decisions T1 to T7 are in `testing.md`. Still unconfirmed there: the mix of fixture kinds (T-A).
- **Q18** Where is the line between per-deployment tests and monitoring of a deployment? If the same expectations (known-good present, known-bad reported, unclaimed counts within bounds) can be evaluated on a snapshot in CI and on the live index after each production crawl, the two may be one mechanism. See `testing.md` T-D.
- **Q15** How generic extractors apply to subtypes, for example a notebook that is JSON or an office document that is a ZIP (R26). Later.
- **Q16** How Python extensions and XDG MIME rules compose: how a multi-file handler declares what it reacts to (the MIME types of candidate files?), what context it gets (a directory group from the index, free queries, both), and how its priority relates to XDG weights. `architecture.md` A and B.
- **Q17** How a handler collection is packaged and registered: XML definitions plus an optional Python module per collection, discovered how, enabled how. `architecture.md` E.
