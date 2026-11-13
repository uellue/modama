# Doc gaps log (times UTC)

- 07:05 G1 Paths: docs say "/workspaces/data-management-system", "the repository root", "your worktree"; brief maps them
  to the clone. Leading-slash paths (`/.claude/skills/...`, `/prototypes/...`) mean repo-relative, not file-system
  root; README never says so. Mild.
- 07:05 G2 The README "Start here" step 2/3 needs the VM, Docker and the search stack (not allowed here); no path for a
  newcomer without the stack is offered, other than `records --verbose`.
- 07:08 G3 OpenSpec: TEMPLATE (a) step 2 and the skill step 2 say "an OpenSpec change" and point to AGENTS.md
  "OpenSpec", which names the /opsx:* slash commands only. No CLI command is given for agents without skills
  (`openspec new change <name>`). Found it in the clone's `python/crawler/.claude/skills/openspec-propose/SKILL.md`.
  Belongs in AGENTS.md "OpenSpec" or TEMPLATE step 2: `openspec new change <name>` from python/crawler, then
  proposal.md, specs/formats/<area>/spec.md, tasks.md; `common-structured` as the model. Also no word on design.md
  (optional?) or on what a change's name should be (`em-mrc`? `common-*` pattern suggests `<domain>-<area>`).
- 07:09 G4 Which MIME type: README says "look at freedesktop.org, Debian's package list, or reader libraries such as
  LiberTEM and HyperSpy". No link or command for Debian's list (found salsa.debian.org media-types mime.types by
  guess), nor how to search "LiberTEM/HyperSpy" for a MIME type (they have none that I know of). Cost: a web search.
- 07:10 G5 Where an MRC format belongs: TEMPLATE's (a) example is "a new EM format in python/modama-formats-em"; MRC is
  cryo-EM -> em. Defensible, but nothing says which domain counts as EM vs a new library (b). Guess.
- 07:11 G6 Reading a file's header "as the field's reader does" without letting the reader open the file: TEMPLATE says
  extract may open members itself unbuffered, and the readers should be used. How to combine (read 1024 bytes
  unbuffered, hand the reader a BytesIO) is shown nowhere generic; I found MrcInterpreter in mrcfile's code. A short
  pattern ("open yourself, give the reader a buffer or a handle") in TEMPLATE "Extracting metadata" would help; dm
  passes its own 64 KiB handle (README pitfalls) - the closest hint.
- 07:12 G7 Float values: "no rounding" + "as found" vs float32 header fields: `.item()` gives 11.399999618530273 for a
  stored 11.4. The em README's "Values and units" shows `18.325349807739258` as the accepted form; so widened float32
  is the convention. Took me a decision; one line in the checklist ("float32 as Python float, unrounded, as dm does")
  would settle it.
- 07:12 G8 Generators with writers that stamp the time: mrcfile.new writes a label "Created by mrcfile.py <time>".
  The recorded expected JSON then changes every run. TEMPLATE "Fixtures" says "generated at test time by the program
  that writes the format" but does not warn that generated fixtures must be deterministic (times, random ids).
  Found by the failing test. Belongs in TEMPLATE "Fixtures".
- 07:13 G9 "0 placeholders left out" in the summary line vs codes where 0 is a value (MRC ispg 0 = image stack,
  mode 0 = int8). The skeleton's phrase() drops every 0. TEMPLATE checklist says "0 placeholders left out" without
  saying how to tell a placeholder 0. Decided per field, written in the spec.
- 07:14 G10 Lint: README table says `uvx pre-commit run --all-files`, "as CI runs it". It runs on tracked files only:
  my new, untracked files were not checked and it said "Passed". TEMPLATE says `uvx ruff format --check --diff` and
  `uvx ruff check`, which did find 2 problems in my files. Docs disagree on the command and neither warns that
  pre-commit skips untracked files (git add first). Cost: one false "clean".
- 07:16 G12 The crawler suite: README says 451 tests, 5 to 7 min; it ran 497 passed in 6:43 (with mrc). Count in the
  README is stale (before my change it would be 497 - mrc's ... the crawler suite runs only its own tests; so the
  451 is simply outdated). Mild.
- 07:16 G13 search-chain suite without the EOSC submodules: 1 failed, 75 passed (README: 74 tests). The failure is an
  assertion on empty text (`test_a_file_the_crawler_has_not_seen`), not a message that the submodule is missing:
  against the team rule "Fail, don't skip ... says what is missing". The README table names the need; the failure
  does not.
- 07:21 G14 (b) Where the spec scenario goes: README step 4 says "a test named after the spec scenario you add". The
  Merlin spec is not in `openspec/specs/formats/` (only collapse, core, empad, zarr there) but in the unarchived
  change `openspec/changes/em-formats-and-extraction/specs/formats/merlin/spec.md`; the code cites "spec
  formats/merlin". Nothing says whether a fix adds a scenario to an open change's delta, a new change, or the main
  spec. Guessed: the open change's delta.
- 07:22 G15 (b) The fixture recorder records a failure as the expected result: on the old code, `test_fixture`
  wrote `expected/not_utf8.json` with `"extractions": {"/acq.hdr": {"error": "UnicodeDecodeError"}}` and asked to
  "review it and run again". TEMPLATE step 5 says "The first run records expected/*.json and fails: read them, then
  run again". For a reproducer recorded before the fix, "run again" locks the bug in. Neither README step 4 ("show
  the test failing on the old code") nor TEMPLATE warns: delete the recorded JSON after the red run, or record only
  after the fix. Found by reading the JSON.
- 07:22 G16 (b) README step 2 "check which version of the library actually runs (the worker's image, not your venv)":
  no command for how, and agents have no shell on staging (AGENTS.md). Here the question was moot (the error is in
  our code), but the docs (README worked example, em README, BACKLOG, TEMPLATE checklist) all describe a Latin-1
  fix that the code did not have. No doc says "check that the code matches the docs' claim" - the cheapest first
  check here.
- 07:23 G17 (b) Hand-over for an issue fix: the README section ends at "Fix, merge, run all suites, reload browse";
  no hand-over shape (the skill's step 6 is for formats and its when_to_use excludes this case). Used the standing
  rule (people first, then agents).
- 07:14 G11 pre-commit used the shared cache in ~/.cache/pre-commit (outside my scratch; ran in 0.5 s, so cached).
  The docs' "temporary files" advice covers pytest only, not pre-commit/uv caches. Minor.
