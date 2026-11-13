# Expectations (tester's own reading of the docs; no written requirements)

Written 2026-11-13T07:04:39Z (date -u), after reading: clone AGENTS.md, python/crawler/AGENTS.md,
python/crawler/README.md, formats/TEMPLATE.md, .claude/skills/format-collection/{SKILL,builder-brief,review-brief}.md,
and a first look at modama_formats_em/merlin (layout, __init__.py, fixtures.toml).

## Setup (both tasks)

- E0.1 Venv: `uv venv --python 3.14 /var/tmp/hallway/scratch/venv`, then from the clone root
  `uv pip install --python .../venv/bin/python -e "python/crawler[test]" -e "python/modama-formats-common[test]" -e python/modama-formats-em -e "python/search-chain[browse]"`.
  Promise (AGENTS.md "Parallel coding agents"): this works, no pip in venv. Time: a minute or two (downloads).
- E0.2 PostgreSQL server binaries and `update-mime-database` (shared-mime-info) must be on the machine
  (README "Getting started"). I expect them present, since this is the VM. Doc does not say how to check.
- E0.3 Worktree rule: one worktree per agent branched from `crawler`. Here: the clone on branch `hallway`, no `crawler`
  branch. I expect to just work on `hallway`.
- E0.4 Submodules for search-chain tests: EOSC submodules missing in the clone; search-chain suite will fail/err. Expect
  to skip that suite and log it.
- E0.5 `pytest --basetemp /var/tmp/hallway/scratch/pytest`, `TMPDIR=/var/tmp/hallway/scratch/tmp`.

## Task (a): MRC format (TEMPLATE.md "Step by step (a)" + skill steps 1-7)

- Ea.1 Talk with the person: ask (one round at a time) what files, which program/version, what belongs together,
  which reader, summary line entries, UI/private entries, lying names. Answer from the main session.
  `modama-chain browse` not possible here, by rule. `records --verbose` on a folder the person names: no real folder.
- Ea.2 Decide where it lives: MRC is cryo-EM -> I expect `python/modama-formats-em`, area `mrc`
  (`src/modama_formats_em/mrc/`), collection `em`, format id `em/mrc`. (TEMPLATE (a) "a new EM format").
- Ea.3 Spec: an OpenSpec change in `python/crawler/openspec/changes/<name>/` with proposal (person's answers, leans as
  assumptions, user-visible behaviour change), delta spec `formats/mrc/spec.md`, tasks. Expect existing changes
  (e.g. merlin, common-*) to show the shape. Person agrees to leans before code. The openspec CLI may not be installed;
  docs say the VM provisions it. Expect to write files by hand if CLI missing.
- Ea.4 Copy skeleton/ to src/modama_formats_em/mrc/, rename collection to `em`, types, class, fixtures; add import
  and PARTS entry in modama_formats_em/__init__.py.
- Ea.5 MIME: check core freedesktop.org.xml / er-c.xml for an existing MRC type; else `application/x.…`
  (README: check Debian, LiberTEM, HyperSpy). Single-file -> XML rules (glob *.mrc, *.map, *.mrcs; magic "MAP " at
  offset 208). `.map` clashes with other programs' .map -> content check (tie / magic).
- Ea.6 Fixtures: mrcfile's own test data (check licence: I believe BSD-3) or written by mrcfile at test time via a
  generator in tests/generate.py; manifest entry each in fixtures.toml; LICENSE.fixtures if another licence.
- Ea.7 Reader `mrcfile` pinned exactly in modama-formats-em pyproject.toml with comment; current release looked up on
  PyPI; wheels for 3.14 (mrcfile is pure Python, expect fine). Ask before adding the dependency (standing rule).
- Ea.8 Tests from scenarios first; `pytest src` in the package: first run records expected/*.json and fails; read them,
  run again -> pass. Also `TZ=Europe/Berlin pytest src`. Tests named after scenarios.
- Ea.9 Checklist tests: bytes read (rchar on large file; mrcfile header_only / permissive), entry nobody has seen
  (MRC header has fixed fields + extended header + labels; "entry nobody has seen" maps to... unclear), name lies
  (text file named x.mrc -> not_of_type or magic), time-zone (MRC has no date except maybe in labels).
- Ea.10 README row in modama-formats-em/README.md; dependency in pyproject.
- Ea.11 `modama-crawler records --verbose src/modama_formats_em/mrc/tests/fixtures` shows em/mrc datasets.
- Ea.12 Crawler suite `pytest` in python/crawler: 451 tests, 5-7 min, 390 MB. Lint: `uvx pre-commit run --all-files`
  from repo root (README table) or `uvx ruff format --check --diff` + `uvx ruff check` (TEMPLATE). Expect both pass
  for my files.
- Ea.13 Independent review: review-brief.md, a reviewer agent that did not write it. I am a subagent; I expect I
  cannot/should not spawn one without asking (cost rule). Ask the main session.
- Ea.14 Hand-over: for people first (formats, example summary line, original_metadata lines, skip list, deps with
  versions, numbered open questions with leans), then for agents (commits, commands, not verified).
- Ea.15 BACKLOG/README/spec updated in the same change (standing rule). Commit path-limited on `hallway`, message via
  file + `git commit -F`.
- Ea.16 Time: TEMPLATE gives none for a format. Night of 2026-11-12: five builders in parallel; I guess 1-2 h for one.

## Task (b): Merlin UnicodeDecodeError (README "Finding and fixing an issue on real data")

- Eb.1 See it: browse snapshot -> not possible here, by rule. I have the error text and the header shape from the brief.
- Eb.2 Ours or upstream's: read the error where it is raised. README's worked example says the cause was upstream
  (rsciio parse_hdr_file reads UTF-8) and that our fix reads Latin-1 in `read_header`. First look: the clone's
  `read_header` uses `open(path)` (locale encoding) -> I expect the error to be raised in OUR code here, not upstream.
  Check the version of rsciio that runs (staging worker image: not visible to me).
- Eb.3 Cut a reproducer: no real file; compose a header with the lines of the public test header plus the quoted lines
  (README: `merlin/tests/generate.py`, fixture `not_utf8` in fixtures.toml). The clone has no `not_utf8` entry; I
  expect to add it, with a generator; recipes in `design/testing.md`, "Deriving small files from real-world cases".
- Eb.4 Show the test failing on the old code, test named after a spec scenario I add (spec formats/merlin in
  openspec/specs/).
- Eb.5 Fix (Latin-1 decode), run all suites; reload browse -> not possible here.
- Eb.6 Upstream bug -> BACKLOG.md "Sync with upstream" as worked around here (README says already there; check).
- Eb.7 Hand-over: like the format hand-over? README section names no hand-over format for issues; I expect the
  standing rule "split: people first, agents second".

## Additions

(Correction: the three entries marked 07:10Z were written at 07:07Z; I guessed the time instead of reading it.)

- 07:10Z Ea.0 Baseline before changing: `pytest src` in python/modama-formats-em with my venv: README table says
  135 tests, 25 s, 130 MB; all pass. (Expect pass: the seeded Merlin issue has no fixture in the clone.)
- 07:10Z Ea.5b From reading: no MRC type in core, Debian maps *.mrc to application/marc (library records). So per
  README rule: unofficial `application/x.mrc`, globs *.mrc *.mrcs *.map, magic "MAP " at 208; content check by
  d.not_of_type for files without it (TEMPLATE "A file that is not of its name's type").
- 07:10Z Ea.6b Fixture: EMD-3197.map (33 kB) from mrcfile's tests (fetched from EMDB; EMDB data CC0 per wwPDB/EBI),
  plus generator-written .mrcs (stack) and .mrc (volume) written by mrcfile at test time. Expect fixtures.toml to
  accept "generator" entries with an empty fixture dir (as merlin's frame_series).
- 07:14Z Ea.12b Crawler suite with my venv: `pytest --basetemp ... ` in python/crawler, README: 451 tests, 5-7 min,
  390 MB; with the mrc area added, the crawler's tests "use every installed package" -> I expect pass, maybe a count
  that moves (test_runs counts). Lint: `uvx pre-commit run --all-files` from the clone root; expect pass for my files,
  and that pre-commit needs network to fetch the pinned ruff (first run).
- 07:15Z Eb.2b Read (b) so far: our `merlin.read_header` opens the header with `open(path)` (locale encoding, UTF-8
  here), so the UnicodeDecodeError is raised in our code; the docs (README worked example, em README, BACKLOG
  "Sync with upstream" RosettaSciIO entry, TEMPLATE checklist) all say we already read it in Latin-1 and that a
  fixture `not_utf8` exists. Expect: the docs describe a fix the code lacks. Plan: generator `not_utf8` from the
  public single_frame header with the Sensor Bias line `Sensor Bias (V, \xb5A)\t120 V` and Software Version
  0.67.0.1; a test named after a new scenario in the merlin spec (which lives only in the unarchived change
  `em-formats-and-extraction`, not in `openspec/specs/formats/`); it must fail with UnicodeDecodeError on the old
  code (`pytest src/modama_formats_em/merlin`, seconds), pass after `open(path, encoding="latin-1", newline=...)`.
  Expect the fixture test to record expected/not_utf8.json on first run and fail once.
- 07:15Z Eb.5b "Fix, merge, run all suites": no merge here (one branch); "all suites" = em, em under TZ, common,
  crawler, search-chain (search-chain needs EOSC submodules: expect failure/unavailable in the clone).
