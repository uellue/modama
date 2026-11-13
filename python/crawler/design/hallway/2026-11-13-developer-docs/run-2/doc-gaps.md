# Doc gaps (times UTC)

- 08:24 G1 Paths: docs say `/workspaces/data-management-system`, `~/.venv`, worktree from `crawler`;
  clone has only branch `hallway`. Brief resolves it; noted once.
- 08:24 G2 README says the Merlin Latin-1 fix and fixture `not_utf8` exist (README "worked example",
  BACKLOG "Sync with upstream": worked around here); code in clone: `open(path)` without encoding, no
  `not_utf8` fixture. Docs vs code drift (README itself warns about this). Task (b) input.
- 08:24 G3 BACKLOG.md line 47 talks about `em/mrc` (priority 60) and "the em/mrc agent", and
  TEMPLATE.md mentions `mrcfile.new` and "MRC's mode 0 is int8", but no em/mrc exists in the tree.
  A new developer cannot tell whether MRC exists, existed, or is planned.
- 08:24 G4 SKILL.md step 1 says "Write down what you heard" but not where (a file? the proposal?).
- 08:25 G5 MIME type lookup: TEMPLATE says look in /etc/mime.types and freedesktop.org.xml (both: no cryo-EM
  MRC; .mrc = application/marc, as TEMPLATE warns), but does not say where else to look for an
  "established unofficial" type (Tika? IANA? community?). One web search, nothing -> application/x.mrc.
- 08:25 G6 The per-directory read budget: TEMPLATE says "d.read ... counted against the budget" but not
  its size (BYTE_BUDGET = 1 MiB per format call, formats/__init__.py:304) nor what happens when it
  runs out (the format is skipped for the whole directory with a warning, :326). For a per-file
  content check of 212 bytes that caps a folder at ~4,900 files; folders of 67,600 files of one type
  exist (README). Found in the code.
- 08:25 G7 TEMPLATE: hand the reader a handle or BytesIO, never let it open the file. mrcfile's
  header_only=True still reads the whole extended header (909 kB for EPU 2.9): the doc's two
  options don't cover "the reader's bounded mode isn't bounded". Found by reading mrcfile source.
- 08:25 G8 openspec/config.yaml context: "Synthetic files only in the core's rule-processing tests";
  TEMPLATE allows generated fixtures written by the format's software. Conflict; I follow TEMPLATE.
- 08:25 G9 The step-1 answers: where to keep them (SKILL "write down") -> I put them in the proposal.
- 08:29 G10 `Extracted(...)` requires `subjects` (TypeError without it); TEMPLATE's example passes
  it but never says it is required. Found by the failing test. Belongs: TEMPLATE "Extracting metadata".
- 08:30 G11 TEMPLATE "Testing a format": `modama-crawler records --verbose src/<pkg>/<area>/tests/fixtures`
  shows only fixtures on disk; generated ones (most of mine) are not there. Nothing says how to look
  at a generated fixture by hand (materialise it somewhere first). Guess: ran it on the one on disk.
- 08:27 G12 `openspec validate <name> --strict` (AGENTS.md) reports "has issues" for requirements over
  500 characters; the model change common-structured fails the same way (4 warnings). Docs do not
  say whether warnings are acceptable. Followed the model.
- 08:32 G13 Lint: ruff's isort treats modama_crawler as third-party in a format package (no blank line
  before it), first-party is the package itself. Found by the hook's message; copying merlin's test
  imports would have shown it.
- 08:33 G14 README step 3 sends to design/testing.md "Deriving small files" for recipes per format; it
  has no Merlin (or MRC) recipe. The worked example in README itself was the recipe I used.
- 08:33 G15 README step 2 says check the library version that runs (worker image), but the bug depends
  on the locale's encoding too (UTF-8 here, C.UTF-8; Python 3.14 is not in UTF-8 mode by default);
  nothing tells you to check LANG/locale of the worker. Found by checking myself.
- 08:34 G16 Where a hand-over goes is not said for a coding agent without a main session (SKILL step 6,
  README step 7: "hand over"): a message? a file? `.claude/drafts/` is for drafts @weber asks for.
  Brief says: the final message.
- 08:35 G17 README step 5 "Fix, merge, run all suites": merge what into what in a single-branch
  clone; and browse reload not possible here, by rule. Brief: commit on hallway.
- 08:35 G18 Order "tests from the scenarios first, then the code" for a NEW format: the docs don't say
  how to show a red run when the module doesn't exist (import error counts?). I wrote code first.
- 08:36 G19 The task (a) docs never mention BACKLOG/README updates for a new format explicitly (only
  the standing rule "changes to behaviour update spec, test, README, backlog"); the crawler README's
  list of em formats and BACKLOG had to be found by grepping.
