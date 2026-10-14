# Dataset recognition: requirements

Status: draft for review. Reviewers: @weber, @clausen, @shanker.

This is step 2 of the crawler plan (see `../AGENTS.md`): turn the file tree into datasets. Step 3, metadata extraction, is covered only as far as it constrains the architecture.

How to review: edit this file directly, commit and push on the `crawler` branch. Comments go inline as quotes starting with your handle, for example:

> **@clausen:** R6 is too strong, order independence only matters within a directory.

Resolved comments are removed and the outcome goes into the decision log in `architecture.md`.

Earlier notes by @weber and @clausen on MR !106 (June to August 2026) are folded in and marked (MR). They were wishes and ideas, not settled requirements: they are listed as *candidates* without a priority, with a proposal per item in the table at the end, and the technical solutions mentioned there appear under "options on the table", not as requirements.

## Vocabulary

Proposed definitions. Several are open, see the questions at the end.

- **File:** an entry in the file tree as seen by the crawl: regular file, directory or symlink, with path, size, mtime and owner.
- **Dataset:** the unit that gets one OAI-PMH record. A single file or a collection of files that belong together, for example an EMPAD XML with its raw file, a Zarr directory, or a Python environment collapsed into one unit.
- **Member:** a file that belongs to a dataset.
- **Anchor:** the member whose path identifies the dataset: the entry point, what one would pass to an `open()` function (MR). It defines the identifier and the browse URL, so it has to be stable.
- **Dataset type:** what kind of dataset it is (see R26 for how types are named).
- **Handler:** the code and rules that recognise one kind of dataset and, later, extract its metadata.
- **Handler collection:** a set of handlers shipped together, for example as a Python package, possibly from a separate repository.
- **Deployment:** one installation of the crawler with a chosen set of handler collections and per-handler settings.
- **Recognition:** deciding which files form which datasets and which handler is responsible for each.

## Requirements

Priorities: **must** for the first working version, **should** for soon after, **later** for anything we only keep in mind now.

### Composition and independence

- **R1 (must)** Handlers can be enabled and disabled per deployment, individually. Example: EMPAD raw files are needed at ER-C, Panasonic raw images are not, until someone buys such a camera. A deployment can also keep specific files or paths away from specific handlers, for example files known to crash one of them (MR; wrapping handlers with pre-filters is one way to do it).
- **R2 (must)** Handlers can be developed in separate repositories by separate teams without getting in each other's way. The crawler core defines the interface, and a handler collection is an installable package.
- **R3 (must)** A handler can be tested on its own, per file or per test tree, and unrelated handlers upstream don't change the result of its tests.
- **R4 (must)** A deployment can be tested as a whole: a real-world file tree against the assembled handlers, with general rules (for example "no contention", "every file classified") and specific expectations ("this path is an EMPAD dataset"), producing a works/doesn't-work verdict.
- **R21 (candidate)** A core collection of common formats (JPEG, PNG, plain text, generic HDF5, …) ships with the framework and is the baseline for ensemble tests (MR).

### Correctness

- **R5 (must)** Cross-talk between handlers is detected: ambiguous name matching, wrong priorities, ambiguous content matching, and contention, where two handlers claim the same file. Detection happens in tests of the composed deployment, and at crawl time with logging.
- **R6 (must)** The result is independent of the order in which files are crawled.
- **R7 (must)** The file system is read-write and in use. Files can be missing, incomplete or inconsistent at any time. Recognition handles this gracefully and reaches a consistent state once the files are complete.
- **R8 (must)** Errors and warnings are logged with enough context to reproduce the case as a test. The path from a real-world failure to a test case and a fix is short.
- **R9 (should)** Recognition is explainable: for every dataset, which handler claimed it and on what basis, and for every unclaimed or contested file, why.
- **R22 (candidate)** Where the format allows it, recognition started from any member file finds the same dataset (MR). Where it doesn't, for example HDF5 with external links, the handler declares the limitation.
- **R23 (candidate)** Stray files, those next to or inside a dataset that no handler claims, are reported rather than silently absorbed or silently skipped (MR).

### Scale

- **R10 (must)** Millions of files, petabytes, hundreds to thousands of new files per day. A full crawl stays feasible, and a re-crawl only does work for what changed.
- **R11 (should)** Large uninteresting trees (`node_modules`, Python and conda environments, large source trees, large Zarr arrays) are recognised early and not visited file by file. The contents of a multi-file dataset are not crawled individually; there is no point in indexing the chunks of a Zarr array (MR).
- **R12 (must)** Recognition has a bounded cost per file: reading file names and metadata is free, reading a bounded amount of content within a time budget is allowed, reading whole files is not. This rules out trying every handler on every file (MR).

### Development and testing

- **R13 (must)** Test data comes in several kinds: generated on the fly, small files in git, large files outside git, and files from public sources. A composed deployment can run the tests of all its handlers on all their data without manual setup.
- **R14 (should)** Developing a handler, including finding or generating test data and writing unit and integration tests, is easy for humans and for AI agents. Skills or templates for agents are part of the deliverable.

### Security (MR)

Handlers are code of varying quality and origin, run on inputs that users control, by a process that opens every file in the repository on a schedule. File readers are rarely hardened against malicious input; one HDF5 file that segfaults its decoder has already been seen, and a data file that is effectively executed by its reader is a known pattern. A weird file isn't suspicious in a research file system, so the crawler is an attractive delivery vehicle for an exploit.

- **R24 (candidate)** A crashing, hanging or misbehaving handler doesn't take the crawl down. Failures are isolated per file and handler, reported (R8), and the crawl continues.
- **R25 (candidate)** A compromised handler can't modify data, reach the network, or gain a permanent foothold on the host.

Options on the table, to be weighed against cost and complexity, not requirements: read-only mounts, no network, subprocess workers with timeouts, container seccomp profiles, gVisor or Kata, short-lived micro-VMs, and `CAP_DAC_READ_SEARCH` to read everything once isolation exists (until then R18 applies).

### Identifiers and metadata (MR)

- **R26 (candidate)** Dataset types have stable, documented identifiers that outside systems understand, support an is-a relation (an hspy file is an HDF5 file), and cover formats without an official name. Every non-standard identifier carries a description, a link to its source, and a mapping to the closest official type. The MR notes propose MIME-type strings, official where they exist and otherwise established unofficial ones (`application/x-ipynb+json`, `application/x-npy`, `application/x-dm4-tem` from the Debian MIME list); see Q14.
- **R15 (later)** Handlers extract metadata from tags and content, for example the code cells of a Jupyter notebook or the tags of a DM4 file. The recognition design must not stand in the way of this, but it isn't designed in detail yet.
- **R27 (candidate)** Metadata from several extractors per dataset can be combined into one record, with generic extractors (an HDF5 dump, `stat()` results) applied only where a subtype wants them, so a notebook isn't also dumped as generic JSON. The MR notes suggest merging partial results into one human-readable document with the file system authoritative for conflicts such as dates and owners; that is an option, not a requirement.
- **R16 (later)** Vision-language models or similar for metadata extraction.

Keeping guessing (cheap candidates), recognition (authoritative) and metadata extraction as separate stages, as the MR notes propose, is an architecture option discussed in `architecture.md`.

### Carried over from earlier decisions

- **R17** One OAI-PMH record per dataset. A dataset can be a single file.
- **R18** Whatever the crawl process can read is in scope. No per-user access checks.
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

## Candidates from the MR notes: keep, and with what weight?

| Item | Proposal | Why | Against |
|---|---|---|---|
| R1 addition: keep paths away from specific handlers | keep, should | Also the mechanism for exemptions in ensemble tests; cheap | None strong |
| R11 addition: don't crawl inside collapsed datasets | keep, as part of R11 | It is what collapsing means | None |
| R12 addition: no brute force over all handlers | keep, as explanation of R12 | A consequence of bounded cost, not a separate requirement | None |
| R21 core format collection | keep, should | We have it already: single-file MIME detection is the core; ensemble tests need a baseline | None strong |
| R22 recognition from any member | drop as a requirement | Under per-directory recognition (architecture A1) it holds automatically; as a requirement it would push towards per-file recognition | Keep if recognition ends up per file |
| R23 stray files reported | keep, should | Costs one log line; it is how we learn what the handlers miss | Noise in messy trees; aggregate per directory |
| R24 handler crash doesn't stop the crawl | keep, must | A segfaulting HDF5 file has been seen; without this a full crawl never finishes | Costs a process boundary (architecture G2) |
| R25 compromise containment | keep, should, at deployment level only | Read-only mount, no network and a container are nearly free; the data is internal | Anything beyond that (gVisor, micro-VMs) is expensive and unjustified so far |
| R26 identifiers | keep, must | Identifiers go outside (EOSC); changing them later means re-harvesting everything | Partly decided already: `dc:format` carries MIME strings today |
| R27 composable metadata | keep, later, as "don't preclude" | Real need, but nothing to design now | Designing it now would shape recognition prematurely |

## Open questions

- **Q1** Can a file belong to more than one dataset? Example: a notebook inside a directory that is itself a dataset. If not, contention needs a rule for who wins.
- **Q2** Can datasets nest? If a session folder is a dataset and contains a Zarr array, is the Zarr a member, a child dataset, or both?
- **Q3** What happens when a handler can't decide yet, for example an EMPAD XML whose raw file hasn't been copied? Emit nothing, emit a provisional single-file dataset, or emit and regroup later? This decides what "eventual consistency" means in practice (R7).
- **Q4** What is the anchor of a multi-file dataset: the header file, the directory, the first file? It must be stable across re-crawls and partial states (Q3).
- **Q5** Priority model. Numeric priorities like today's 0 to 100, explicit "wins over" relations between handlers as in the PRONOM registry, specificity-based ordering, or something else. Who resolves conflicts between handlers from independent repositories?
- **Q6** Should recognition rules be declarative data (like shared-mime-info XML, checkable for conflicts without running code), Python code (flexible, hard to analyse), or data with a code escape hatch?
- **Q7** How are handler collections cut: per format family, per team, per instrument, per vendor?
- **Q8** Where do large test files live: an institute server, Zenodo, git LFS on iffgit? What about licensing of files found online?
- **Q9** What of a collapsed tree is indexed: nothing, a summary, or a bounded subset of files?
- **Q10** What exactly makes the real-world test (R4) pass: coverage thresholds, zero contention, a list of known-bad paths that must be reported?
- **Q11** Recognition today runs during the crawl and reads only the file being classified. Multi-file datasets need neighbours. Is recognition a second pass over the crawled index (the MR notes suggest per-handler database passes with priorities), or does it run per directory during the walk? The MR notes also raise the continuation problem: a listing can only be considered complete once every dataset in it is filled, and a dataset that claims a very early and a very late file in crawl order would keep a chunk open.
- **Q12** Should the crawler use only its own curated MIME definitions, with `XDG_DATA_DIRS` pointed at them, instead of whatever the host has installed? The MR notes found cross-talk with system packages, DM3/DM4 defined by extension only (gwyddion), and `*.raw` claimed by Panasonic raw images, which a custom `application/octet-stream` glob entry can override to force content matching.
- **Q13** What is the unit of isolation for R25: one sandbox per crawl, per handler collection, or per file? Cost against safety.
- **Q14** Is the identifier a MIME string alone, or MIME plus our own hierarchy path, for example to distinguish hspy with and without the pyxem extension?
