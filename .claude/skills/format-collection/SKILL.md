---
name: format-collection
description: Develop a format or a format library for the modama crawler with the person who has the files, from sample files to a reviewed, merged change; with the briefs for builder and reviewer coding agents when several formats are built at once.
when_to_use: A new file format, a new kind of dataset (files that belong together, a folder that is one dataset) or a new library of formats for the crawler; extending a format for a variant found in real data; reviewing a format change. Not for a bug in an existing format found on real data (python/crawler/README.md, "Finding and fixing an issue on real data").
---

# A format for the crawler, from sample files to a merged change

This is the workflow. The rules a format must follow live in
`python/crawler/src/modama_crawler/formats/TEMPLATE.md` ("Core requirements", the
checklist at its end) and are not repeated here. This file is plain Markdown: a coding
agent without skills, or a person, follows it as it is.

## 1. Look at sample files with the person (before any code)

A format is the person's knowledge of their files put into rules (R14). Ask, one round
at a time, with the files in front of you:

- What are these files, which program or instrument wrote them, which version?
- Which files belong together (a header and its data files, a series, a whole
  folder)? What happens when one is missing?
- Which reader does the field use (the reader of LiberTEM, HyperSpy/RosettaSciIO,
  h5py, tifffile, Pillow, …)? Is there public test data for it?
- What does the person look at in such a file, and what should a search find
  (the summary line's few entries)? What in it is a user-interface setting or
  private?
- Which file names lie: other programs that use the same extension?

Where to see real files: `modama-crawler records --verbose PATH` on a folder the person
names, and `modama-chain browse` in the search stack, which shows what each stage makes
of one file (`python/search-chain/README.md`, "browse"). Counts across the whole tree
(how many files of an extension, how large, in which folders) come from the private
listing in `.claude/survey/` of @weber's checkout only
(`python/crawler/benchmark/README.md`, "Making a listing"); without it, ask the person.
Never copy a real file into the repository without its owner's agreement; a fixture
from real data is cut to what the rules and the extractor read (`k2is/tests/cut-capture.sh`,
`blockfile/tests/cut-header.sh` in `python/modama-formats-em`).

Write down what you heard, in the person's words, with your reading of each answer.
Where an answer is an example ("the DM files from the Titan"), say whether you read it
as the whole case or as an example of a rule.

## 2. The spec

An OpenSpec change in `python/crawler/openspec/changes/<name>/` (`python/crawler/AGENTS.md`,
"OpenSpec"): the proposal with the person's answers and your leans as assumptions, the
behaviour towards the user that changes (new records, new summary lines), delta specs
`formats/<area>/spec.md` with a scenario per rule (a representative file, a broken one,
a misnamed one, an entry nobody has seen), tasks. The person agrees to the leans before
the code, not after.

## 3. Build

In a worktree of your own, branched from `crawler`, with a venv of your own
(`python/crawler/AGENTS.md`, "Parallel coding agents"). Start from the skeleton
collection and follow TEMPLATE.md, "Step by step". Tests from the scenarios first, then
the code; one test per scenario, named after it.

## 4. Test

TEMPLATE.md, "Testing a format", all of it, then the crawler's suite and CI's ruff from
the repository root. Show the commands with their output in the hand-over.

## 5. Independent review

A reviewer that did not write the code, read-only, given the code and the rules, not your
conclusions: `review-brief.md` beside this file, with the change's name and range filled
in. Verify each finding before acting on it; answer each one (applied, or not and why).

## 6. Hand-over

For people first, plain words, at most a screen: the formats covered, for each one
example summary line and a few `original_metadata` lines, what is left out (the skip
list), new dependencies with versions, open questions numbered with your lean and the
strongest argument against. Then for agents: commits, commands with output, what was
not verified.

## 7. Merge and look

The person (or the main session) merges into `crawler`, runs every suite (README,
"Running tests") and the search stack's e2e, and looks at real files in browse before
and after. Every merge changes the extractor identity: the next crawl extracts every
dataset again (TEMPLATE.md, "No version to raise").

## Several formats at once

The night of 2026-11-12 built five areas of `modama-formats-common` this way, and it is
the reference: a foundation step by one coding agent (the empty package with its entry
point, the shared checks), then one builder per area from one brief
(`builder-brief.md`), each in its own worktree, one independent reviewer per area
(`review-brief.md`), and merges one at a time by the main session with all suites after
each. Step 1 above happens before the night, with the person, for all areas; the briefs
carry its answers. Plan the machine: each builder runs its own suites
(`python/crawler/README.md`, "Running tests", for times and space).
