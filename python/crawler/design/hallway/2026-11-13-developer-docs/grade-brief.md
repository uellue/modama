# Brief: grading the hallway test of the developer docs (grader)

For a blind grader: a fresh agent that did not write the answer key and does not see the
tester's report. Make a new, empty scratch directory `{{GRADE}}` and copy this folder's
`answer-key.md` into it (`{{KEY}}` is that copy, so that the grader needs nothing from the
repository); fill in `{{CLONE}}` (the tester's clone, in its final state), `{{KEY}}` and
`{{GRADE}}` by hand, and hand everything below the line to the grader as its prompt.

---

You grade the work of a coding agent that was given a clean clone of a repository and two
tasks: (a) add a format collection for MRC files (cryo-EM maps and tomograms, reader
`mrcfile`) to the modama crawler's EM format package, following the repository's
developer documentation; (b) find and fix the cause of a reported
`UnicodeDecodeError` in the Merlin header extraction, as the documentation says issues
from real data are fixed. Its clone, in its final state, is `{{CLONE}}`; it committed its
work there. The answer key is `{{KEY}}`: read it whole first, including its first section
on what was seeded.

Your job: for each item of the answer key (A1 to A15, B1 to B9), a verdict, met / partly /
not met / not visible in the clone, with the evidence: the file and line, or the exact
command and the relevant lines of its output. You judge the clone, not the agent's
intentions: what is not in the clone does not count, and where the key says evidence may
live only in the agent's report (A15, B3's second half), say "not visible in the clone".

Rules:

- Read anything in `{{CLONE}}` and `{{KEY}}`. Do not read the agent's report, the main
  session's notes, `/workspaces/data-management-system` or its worktrees, or `~/.claude`.
  The internet is allowed for PyPI and the licences of public test data.
- Do not modify `{{CLONE}}`. For checks that change code (B3, B4), copy the clone first
  (`cp -a {{CLONE}} {{GRADE}}/copy`) and change the copy.
- Everything you create goes under `{{GRADE}}`: a venv of your own
  (`uv venv --python 3.14 {{GRADE}}/venv`, then the install line of the clone's
  `python/crawler/AGENTS.md`, "Parallel coding agents", with `uv pip install --python
  {{GRADE}}/venv/bin/python`, from the clone), `pytest --basetemp {{GRADE}}/pytest`,
  `TMPDIR={{GRADE}}/tmp`. Never `/tmp`. No Docker.
- Run the suites the key names, each once, and give passed, failed and skipped counts.
  The crawler's suite takes 5 to 7 minutes.
- Where the key's "met" is a judgement (a reason good enough, a summary line that follows
  the rules), quote what you judged and say why.
- Note anything the agent did beyond the key that looks wrong (a file outside its area
  changed, a real-looking file committed, a large fixture, a secret), as findings after
  the verdicts.

Your final message is the grade: first a table, one row per item (item, verdict, evidence
in one line); then the counts per verdict for (a) and for (b); then the details for every
item that is not met or partly, and your findings. At most 1,500 words. Read the time with
`date -u` at the start and at the end and give both.
