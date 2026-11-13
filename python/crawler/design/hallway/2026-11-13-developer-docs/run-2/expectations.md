# Expectations (hallway test of the crawler developer docs)

Written 2026-11-13 between 08:21:45Z and 08:22:22Z (the two date -u reads around it; I first
wrote "08:24" from a guess, corrected), before any command other than reading.
All expectations are my own reading of the docs; there are no written requirements for them.

Read so far: /AGENTS.md, python/crawler/AGENTS.md, python/crawler/README.md (all),
formats/TEMPLATE.md (all), .claude/skills/format-collection/{SKILL,builder-brief,review-brief}.md,
merlin/__init__.py, merlin/tests/{fixtures.toml,generate.py}, BACKLOG.md (grep).

## Setup (README "Getting started", AGENTS.md "Parallel coding agents")

- E0.1 `uv venv --python 3.14 /var/tmp/hallway/run2/scratch/venv`, then
  `uv pip install --python …/venv/bin/python -e "python/crawler[test]" -e "python/modama-formats-common[test]" -e python/modama-formats-em -e "python/search-chain[browse]"`
  from the repo root. Promise: works in one line, a minute or two. Needs PostgreSQL server
  binaries and shared-mime-info on the machine (provision.sh); I expect those may be missing here
  (not the devvm VM) -> the crawler suite may fail. Docs say "On another Debian 13 machine do what
  provision.sh does by hand".
- E0.2 `modama-crawler records --verbose tests/` from python/crawler: prints oai_dc XML records with
  XML comments saying why each dataset was recognised. Seconds.
- E0.3 Worktree: docs say branch from `crawler` in a worktree; the clone has only `hallway` and the
  brief says commit on `hallway`. I'll work in the clone directly (brief overrides).

## Task (a): MRC format (SKILL.md steps 1-7, TEMPLATE.md "Step by step (a)")

- E1 Step 1, talk with the person: ask what the files are, program/version, which belong together,
  reader, what the summary line should show, what is private, which names lie. Promise: SKILL.md
  lists the questions; I send them to the main session (one topic per message). Look at real files
  with `records --verbose` / browse: browse not possible here, by rule; no real files.
  Write down the answers in the person's words (where? SKILL.md does not say a file; I expect the
  proposal).
- E2 Step 2, the spec: OpenSpec change in python/crawler/openspec/changes/<name>/, shape copied from
  `common-structured` (proposal, specs/formats/<area>/spec.md, tasks). `openspec` CLI: not in README
  setup; may not be installed here -> I copy the shape by hand. `openspec validate <name> --strict`
  if available. Person agrees to the leans before code -> I send the leans and wait (continue with
  fixtures meanwhile).
- E3 MIME type: TEMPLATE "Rules first": look up `.mrc` in /etc/mime.types (expect application/marc, the
  trap the doc warns about) and in core/freedesktop.org.xml; `records --verbose` on a sample shows the
  type today. If none, `application/x.mrc` or similar of our own (R25). MRC has magic? MRC2014 has
  "MAP " at byte 208 -> a magic rule. Expect a tie with application/marc glob -> curation via
  er-c.xml or a tie forcing a content check (Pitfalls).
- E4 Step 3, build: copy skeleton/ to python/modama-formats-em/src/modama_formats_em/mrc/, rename
  collection to `em`, import in package __init__ and add to PARTS; entry point already exists for em.
- E5 Fixtures: mrcfile's own test data (licence BSD-3?) recorded in fixtures.toml + LICENSE.fixtures,
  or generated with mrcfile at test time (deterministic: overwrite the time label, TEMPLATE says so).
- E6 Dependency: mrcfile pinned exactly with a comment, current release looked up on PyPI, py3.14
  wheel (pure Python, expect fine). Must ask before adding the dependency (AGENTS standing rule).
- E7 Tests: one per spec scenario named after it; bytes-read test (rchar) on a large sparse file;
  entry nobody has seen in original_metadata; name lies (text file named .mrc; renamed copy found by
  magic); TZ=Europe/Berlin run. `pytest src` in modama-formats-em: first run records expected/*.json and
  fails; review; run again green. ~25 s.
- E8 README row in modama-formats-em/README.md; pyproject dependency.
- E9 Testing: `pytest src`, `TZ=Europe/Berlin pytest src`, `pytest -s src/.../mrc`,
  `modama-crawler records --verbose src/.../mrc/tests/fixtures`; then crawler suite (5-7 min, 390 MB,
  needs PostgreSQL binaries), then `uvx pre-commit run --all-files` from repo root after git add.
- E10 Step 5, independent review: a reviewer agent with review-brief.md filled in. I am a sub-agent;
  I expect to either spawn one (cost check first) or hand the brief to the main session. The docs
  do not say what a single agent without a main session does -> probably ask.
- E11 Step 6 hand-over: people part first (formats, example summary line, original_metadata lines,
  skip list, deps, numbered questions), then agent part. Commit on branch, path-limited,
  `git diff --cached --stat`, `git commit -F file` (hook refuses heredocs / sed -i in messages).
- E12 Step 7 merge and look: main session's job; not mine.

## Task (b): Merlin UnicodeDecodeError (README "Finding and fixing an issue on real data")

- E13 See it: snapshot from @weber; browse not possible here, by rule.
- E14 Ours or upstream's: read the error where it is raised. README worked example says it is
  upstream (rsciio parse_hdr_file) and already worked around in merlin.read_header (Latin-1). In
  the clone read_header uses `open(path)` (locale encoding): the documented fix is not in the code.
  README warns exactly this: "a revert or a merge can undo a documented fix". Check the rsciio version
  that runs (worker image: not possible here; my venv's).
- E15 Cut a reproducer: no real file -> compose; recipes in design/testing.md "Deriving small files
  from real-world cases"; record in fixtures.toml. Expect a fixture `not_utf8` (README names it) or
  fix the date_order generator, which writes "uA" instead of "µA".
- E16 Show the test failing on old code; scenario added to the spec of formats/merlin, which lives in
  an unarchived change (`find openspec/changes -path '*specs/formats/merlin/spec.md'`). On the red run
  the plugin records nothing for a reproducer whose extraction fails.
- E17 Fix (Latin-1 read), run all suites; reload browse (not possible here).
- E18 Upstream bug: BACKLOG "Sync with upstream" already lists it as worked around -> keep/verify.
- E19 Hand over: people first, then agents, with commits, commands, suites and skipped counts.

## Additions 08:25Z (before building)

- E4' openspec CLI 1.16.0 is installed here (~/.local/bin). `openspec new change em-mrc` should make
  openspec/changes/em-mrc/ with a skeleton; `openspec instructions proposal --change em-mrc` prints
  the template; `openspec validate em-mrc --strict` passes when the delta spec has
  "## ADDED Requirements" with "#### Scenario:" blocks. Seconds each.
- E7' First `pytest src/modama_formats_em/mrc` records expected/*.json and FAILS asking for review;
  second run passes. Coverage test fails if any glob (*.mrc, *.map, *.mrcs) or the magic rule never
  fires on a representative fixture -> I need a representative fixture per glob plus a renamed one.

## Additions 08:34Z (task b, before the reproducer)

- E15' Reproducer: a generator `not_utf8` beside `date_order` in merlin/tests/generate.py, the brief's
  key order, "Sensor Bias (V, µA)\t120 V" with µ as the byte 0xB5, CRLF, padded with spaces; a
  manifest entry purpose=reproducer, validity=parser-only (composed). Expect the plugin to record
  nothing on the red run (README step 4) and test_fixture to fail with the extraction error.
- E16' Spec scenario "A header in Latin-1" into em-formats-and-extraction/specs/formats/merlin/spec.md,
  requirement "Every header entry is kept"; test `test_a_header_in_latin_1` fails red with
  UnicodeDecodeError, passes after reading the header in Latin-1 (unbuffered, README Pitfalls).
- E17' After the fix: pytest src (em), TZ run, crawler suite, lint; README/BACKLOG already describe the
  fix, so no doc change expected except where they name things that don't exist (`not_utf8`).
