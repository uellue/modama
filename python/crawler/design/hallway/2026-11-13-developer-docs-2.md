Brief: `2026-11-13-developer-docs/brief.md` (setup at `REF=06ee8f55`). Usage: tester 29 min, ~80 tool calls, 77,000 output tokens (Opus 5.5, its own Claude Code session in the clone, started by @weber); blind grader 8 min (Opus 5.5, sub-agent). Material: `2026-11-13-developer-docs/run-2/`.

# Hallway test of the developer docs, 2026-11-13 (run 2, after the fixes of 292)

**For people.** Same tasks, same key, the docs after the fixes of run 1 (06ee8f55), and this
time the tester ran as a Claude Code session of its own rather than a sub-agent. Result: (a) the
MRC format, 13 of 15 met, 1 partly (A11: the broken file is built inside a test instead of being
a fixture), 1 not visible in the clone (A15: the hand-over is in the tester's report, with an
example summary line, example `original_metadata` lines and numbered questions with leans, so it
is met there); (b) the Merlin bug, 9 of 9 again. Run 1 had (a) 13 met, 2 partly; the summary
line (A10) is now met. The fixes of run 1 held where the tester met them. The new top gaps are
the read budget (undocumented, and a format silently loses a whole folder past it) and readers
whose "header only" mode isn't.

## Run 1's fixes: did they hold?

| Run 1 gap | Fix (06ee8f55) | Run 2 |
|---|---|---|
| G15 a red first run records the bug | plugin names a recorded error, refuses it for a reproducer | held: "fix the code first", nothing recorded for `not_utf8` |
| G10 lint misses new files | one lint command, `git add` first | held: pre-commit found an import-order problem, then passed |
| G3 OpenSpec without skills | CLI line in AGENTS.md | held: `openspec new change em-mrc` in 0.9 s |
| G13 search-chain fails silently | submodule guard | held: "submodule not checked out … git submodule update --init" |
| A10 summary line too long | TEMPLATE example | held: 5 entries, met |
| G16 docs claim a fix the code lacks | README step 2 | held: the tester checked the code against the docs first |

## Gaps, ranked (the tester's G-numbers; full list in `run-2/tester-report.md` §5), each with what would catch it

1. **G6 The read budget is undocumented, and running out drops the format for the whole folder.**
   Checked: `formats/__init__.py` `BYTE_BUDGET = 1 << 20` per format call per directory; past it,
   `BudgetExceeded` → `"<format> skipped: …"` warning and no datasets from that format in that
   folder (`_call`, lines 362–385). Neither README nor TEMPLATE names it. For MRC (4 bytes at
   offset 208 per file, plus the name) the tester estimates the cap at about 4,900 files per
   folder; EPU movie folders can be larger. *Catch:* TEMPLATE "Rules first" and the checklist
   name the budget and its failure; a design question for @weber whether a folder past the
   budget should lose the format (item on the page).
2. **G7 A reader's bounded mode may not be bounded** (mrcfile's `header_only` reads the whole
   extended header, 909 kB for EPU files). Caught here only because TEMPLATE asks for the
   `rchar` test. *Catch:* TEMPLATE "Extracting metadata": measure the reader's own bounded mode
   too, or decode the header with the reader's definitions on bytes we read.
3. **G3 Docs cite things not in the tree** (at 06ee8f55: BACKLOG's em/de item "found by the
   em/mrc agent", TEMPLATE examples from MRC, a "hallway G8" reference). em/mrc is merged now
   (b49adf35), so only the hallway references remain (BACKLOG line 43). *Catch:* docs don't
   cite test-run gap numbers; a test run's task must not be named in the docs it tests.
4. **G12 `openspec validate --strict` fails on the model change** (`common-structured`: four
   "over 500 characters" warnings). *Catch:* fix the model change, or AGENTS.md "OpenSpec" says
   which warnings are acceptable.
5. **G10 `Extracted.subjects` is required** but TEMPLATE's example doesn't show it (found from a
   TypeError). *Catch:* the example.
6. **G15 The worker's locale** is not among the checks of README step 2. *Catch:* one line.
7. **A11 (grader) A broken file as a fixture**: built inline in a test. *Catch:* TEMPLATE
   "Fixtures": a broken file is a fixture with `purpose = "invalid-by-design"`.
8. **Grader finding: provenance hash.** `fixtures.toml` puts the map's sha256 next to the
   tarball's name. *Catch:* TEMPLATE: the hash is of the fixture file itself, said so.
9. **Smaller:** G11 how to look at a generated fixture by hand; G16/G17 where a lone agent's
   hand-over and merge go; G5 MIME lookup beyond Debian/freedesktop; G14 no Merlin recipe in
   `design/testing.md`; G19 which other docs to update (found by grep); G4/G9 where the person's
   answers go; G8 `openspec/config.yaml` "synthetic files only in the core's tests" vs
   TEMPLATE's generated fixtures; G18 a red run for a new format; the README's test times and
   sizes (crawler 7–9 min, 466 MB measured under load; README says 5–7 min, 390 MB).
10. **Bug, not docs:** `records --verbose` gave no basis comment for an unclaimed
    `application/octet-stream` file (not yet checked against the code).

## Distortions

- The clone's docs (06ee8f55) mentioned em/mrc and the Direct Electron grouping, so the task
  leaked into the docs (`answers-given.md`). em/mrc is merged now: **a run 3 needs a new format
  task** and a new seed.
- The tester sent its step-1 questions to the main session by cross-session message instead of
  asking @weber in its chat; the main session answered from the key's stock answers, as in run 1.
- Timings were measured while other suites ran on the VM.
- As its own session it got this project's skills and its own (empty) memory, not the main
  session's memory or context: closer to a newcomer than run 1.

## Answers given

`run-2/answers-given.md`: one round, all stock answers; two points not in the key (program
versions; files without the stamp) answered "decide, write it down as an assumption".

## TODO for @weber (each with my lean)

- Fix gaps 1–8 (docs) in one small change, as after run 1? [lean: yes]
- The read budget (gap 1): should a folder past the budget lose the format, or should the
  format keep what it recognised within the budget and warn? [lean: a design question of its own
  on the page, with the MRC numbers; decide before em/mrc meets an EPU folder on staging]
- Run 3? [lean: only with a new task format, not mentioned in the docs; not now]
