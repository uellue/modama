Brief: `2026-11-13-developer-docs/brief.md`. Usage: tester 27 min, 155 tool calls, 71,000 output tokens (Opus 5.5); blind grader 8 min (Sonnet 5.5).

# Hallway test of the developer docs, 2026-11-13 (run 1)

**For people.** A fresh coding agent with only a clean clone (no history) did both tasks the way the
docs say, in 27 minutes: (a) a new format for MRC files (`em/mrc`: spec first, MIME rules with a
content check, the header read alone and measured, every header field minus a skip list, an entry
nobody has seen, a credential test, public EMDB fixture with licence, all suites green), and (b) the
seeded Merlin bug from a symptom report: found in our code, reproducer composed, test failing first
with the staging error, fix, spec scenario restored. The blind grader, against a key written before
the run: (a) 13 of 15 items met, 2 partly (the summary line lists 11 values plus a label, more than
"a few"; the hand-over in the commit lacks example lines and numbered questions); (b) 9 of 9. The
docs carried a newcomer through; what slowed it down are the gaps below, the first two of which
could lock a bug in or hide one.

## What held up

- "Start here", TEMPLATE.md and the skill `format-collection`: the tester asked the person first
  (seven questions about the files), wrote the spec before the code, and followed the checklist
  (bytes-read test, skip list, unseen entry, shared checks, TZ run, fixtures with provenance).
- `not_of_type` worked as documented on the first try (a linker map named `.map` fell back to
  `text/plain`, with the reason in its basis); `records --verbose` showed the new format.
- For (b), the docs' worked example led straight to the cause: four documents describe the Latin-1
  read and the `not_utf8` reproducer, so the tester saw that the code disagreed with them and
  checked that RosettaSciIO 0.15.0 fails the same way. (This also means (b) measured the way to a
  reproducer more than a search from scratch.)

## Gaps, ranked (the tester's G-numbers; full list in `run-1/doc-gaps.md`), each with what would catch it

1. **G15 A red first run records the bug as expected.** The fixture plugin records an extraction
   error as the expected result on purpose (fixtures meant to be invalid), so a newcomer's first,
   red run on a bug writes `{"error": "UnicodeDecodeError"}` and asks for a review; TEMPLATE's "read
   them, then run again" would lock the bug in. Checked in `testing.py` (lines ~195–230).
   *Catch:* the plugin's message names it ("recorded an ERROR as the expected result; intended only
   for a fixture whose purpose is invalid-by-design"), refusing it for `purpose = "reproducer"`
   fixtures; README "Finding and fixing", step 4: delete the recorded file after the red run.
2. **G16 Docs claim a fix the code lacks** (seeded here, but it can happen with a revert or a
   merge). *Catch:* README step 2: "check the code you run against what the docs and BACKLOG
   claim"; the reproducer test itself is the real guard (the seed removed it).
3. **G10 The documented lint misses new files.** `uvx pre-commit run --all-files` checks only files
   Git tracks; untracked new files passed unchecked, TEMPLATE's `uvx ruff …` found 2 problems.
   Checked. *Catch:* the README says `git add` first (or gives the ruff commands); one lint command
   in all docs.
4. **G3 OpenSpec without skills.** No CLI line for coding agents without the `/opsx` skills; found
   in the skill file. *Catch:* one line in AGENTS.md "OpenSpec" (`openspec new change <name>`,
   which change to copy).
5. **G8 Generated fixtures must be deterministic** (`mrcfile` stamps the time into a label).
   *Catch:* TEMPLATE "Fixtures": a line, and the plugin could run each generator twice and compare.
6. **G14 Where a fix's spec scenario goes:** format specs sit in unarchived changes. *Catch:* a
   pointer in README step 4; archiving the format changes (sync to `openspec/specs/`).
7. **G4 How to look up a MIME type** (Debian's list, what to do when none exists), **G6** reading
   with a field reader on bytes we read, **G9** "0 placeholders left out" vs codes where 0 is a
   value, **G7** float32 widening: lines in TEMPLATE.
8. **G13** search-chain's DataCite test fails silently without the submodules; **G12** stale test
   counts in the README; **G17** no hand-over shape for an issue fix; **G11** caches outside
   scratch; **G5** which library a format belongs to; **G1/G2** leading-slash paths, Start here
   needs the stack.
9. **A10/A15 (grader)**: the summary-line rule "a few chosen entries" left room for 11; the
   skill's hand-over shape was not followed in the commit message. *Catch:* an example summary
   line of the right length in TEMPLATE; the skill's step 6 template.

## Distortions

- No history in the clone (`setup.sh`), no stack, browse or Docker (one stack per VM).
- The tester ran as a sub-agent of the session that wrote the docs: the harness attached that
  session's instruction files, memory index and edit hook (the tester named them). The README of
  the harness now says how to run it as a session of its own.

## Answers given

`run-1/answers-given.md`: three rounds, all from the key's stock answers; two points the key did
not cover (program versions; the extended header) answered "decide, write it down as an
assumption".

## TODO for @weber (each with my lean)

- Fix gaps 1–6 and the TEMPLATE lines of 7 now, small and in one change? [lean: yes; G15 as a
  change to the plugin's message with a test]
- Keep the tester's MRC format (it passed the key)? [lean: not from this clone; MRC files from
  processing exist on staging, so a real `em/mrc` deserves the person-first step with real files,
  the clone's work as the starting point]
- Run 2 after the fixes, as a session of its own in the clone? [lean: yes, then compare]
