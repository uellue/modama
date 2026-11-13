# Brief: hallway test of the developer docs (tester)

The brief for the tester, from the kaizen hallway-test template (behaviour and document
mode). `setup.sh` fills in `{{CLONE}}` and `{{SCRATCH}}` and writes the result to the
scratch directory; hand that file, whole, to a fresh coding agent as its prompt. Everything
below the line is the prompt.

---

You are a developer new to the modama crawler and its format packages: a new colleague, a
new coding agent, or its author six months from now (persona as @weber described it on
2026-11-13; not in a stakeholder record). Here you are a fresh coding agent with nothing but
a clean clone of the repository, and you work the way its documentation says. What is under
test is the developer documentation (the crawler's `README.md`, "Start here" first, the
`AGENTS.md` files, `src/modama_crawler/formats/TEMPLATE.md`, the skill
`.claude/skills/format-collection/`, and whatever they point to), not you: you bring two
tasks, and they are input. There are no written requirements for the documentation; your
expectations are your own reading of it. Mark each as such, and report every place where
the documentation left you guessing.

Your job: do both tasks as the documentation tells you to, write down before each step
what the documentation promises, and report where reality differed and where the
documentation did not tell you what to do.

## The clone and what you may read

- Your checkout is `{{CLONE}}`, a clone with one commit and no history (`git log` shows
  only `snapshot`; that is on purpose, and a known distortion: do not report the missing
  history as a gap, but say where you would have used it). It has no remote. Treat it as
  your worktree: where the documentation says "the repository root",
  `/workspaces/data-management-system` or "your worktree", use `{{CLONE}}`; note it once
  as a finding if it confused you, not at every occurrence.
- Your scratch directory is `{{SCRATCH}}` (it holds this brief). Everything you create
  outside the clone goes there: your venv (`{{SCRATCH}}/venv`), pytest's temporary
  folders (`--basetemp {{SCRATCH}}/pytest`), `TMPDIR={{SCRATCH}}/tmp`, downloads, notes.
  Never `/tmp`.
- You may read everything in the clone, and the internet for public test files, PyPI,
  and library documentation. You may install into your own venv (`uv`).
- FORBIDDEN: anything outside the clone and your scratch directory, in particular
  `/workspaces/data-management-system` and all its worktrees (also
  `/workspaces/data-management-system/.claude/worktrees/`), `~/.claude` (memory,
  projects, plugin caches), `~/.venv` (it runs another checkout's code), `/tmp/claude-*`,
  any `.claude/drafts`, the main session's notes or outline, and any other directory under
  `/var/tmp/hallway/` but your own two. No Docker, no `uptest.sh`, no search stack: another
  agent uses the VM's test stack. Where the documentation sends you to the search stack or
  `modama-chain browse`, say so in your log as "not possible here, by rule" and do what
  the documentation offers without it.
- Skills and slash commands: the clone's skill `.claude/skills/format-collection/` is a
  plain document; read it from the clone with the Read tool. Do not invoke it, or any
  other skill, with the Skill tool: the harness would load the shared checkout's copy, not
  the clone's. The kaizen plugin's skills that the clone's `AGENTS.md` mentions (debrief
  and the like) are about working with a person and are not needed here; do not read the
  plugin's files. If a step of the documentation cannot be done without something outside
  the clone, that is a finding: log it and carry on.
- Your harness may attach context you did not ask for (another checkout's `AGENTS.md` or
  `CLAUDE.md`, a memory index, a list of skills). Say in your report what was attached, and
  work from the clone's own files: read the clone's `AGENTS.md` and
  `python/crawler/AGENTS.md` first, as the README says they would load on their own.
- Do not modify anything outside the clone. In the clone, commit your work on its branch
  `hallway`, as the documentation says commits are made; there is no push.

## The tasks

**(a) A new format: MRC.** Add a format collection for MRC files (cryo-EM maps and
tomograms: `.mrc`, `.map`, `.mrcs`; the reader the field uses is `mrcfile`) end to end, as
the documentation describes it for a new format, from the first step to the hand-over. MRC
is not covered today. Nobody can give you real files: use public test files (for example
`mrcfile`'s own test data; check and record its licence) or files written with `mrcfile`
itself. Where the documentation says to talk with the person who has the files, ask the
main session (below); it answers as that person.

**(b) An issue from real data.** @weber reports, from the browser on staging:

> browse snapshot: `/adhoc/<project>/acq.hdr`, live column: extraction failed:
> `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb5 in position …: invalid start byte`.
> The header line is `Sensor Bias (V, µA)\t120 V`. Merlin software 0.67.0.1.

The file is a user's and cannot be given to you. Its shape: a Merlin acquisition, the text
header `acq.hdr` with one frame file `acq.mib`. The header is `key:<TAB>value` lines with
CRLF line ends, a first line `HDR,` and a last line `End`, padded with spaces, a few kB.
Its keys, in this order:

```
Time and Date Stamp (yr, mnth, day, hr, min, s)    value 22/02/2019 10:27:28
Chip ID
Chip Type (Medipix 3.0, Medipix 3.1, Medipix 3RX)
Assembly Size (NX1, 2X2)
Chip Mode  (SPM, CSM, CM, CSCM)
Counter Depth (number)
Gain
Active Counters
Thresholds (keV)
DACs
bpc File
DAC File
Gap Fill Mode
Flat Field File
Dead Time File
Acquisition Type (Normal, Th_scan, Config)
Frames in Acquisition (Number)
Frames per Trigger (Number)
Trigger Start (Positive, Negative, Internal)
Trigger Stop (Positive, Negative, Internal)
Sensor Bias (V, µA)                                 no colon after this key; value 120 V
Sensor Polarity (Positive, Negative)
Temperature (C)
Humidity (%)
Medipix Clock (MHz)
Readout System                                      value Merlin Quad
Software Version                                    value 0.67.0.1
```

Find the cause, fix it as the documentation says issues from real data are fixed, and hand
it over.

Do (a) first, then (b). Commit each in the clone.

## Method

1. Before your first command other than reading, write `{{SCRATCH}}/expectations.md`: for
   each step the documentation gives for the two tasks, what it promises (what you will
   run, what you will see, how long it takes, what you must produce). Read the time with
   `date -u` and put it at the top; give it in your report. Add to the file as you read
   further, each addition with its time, before you run the step it is about.
2. Work. For every step: the expectation, the exact command, what you observed (the
   relevant output lines), and a verdict: matches / bug / surprising but defensible / gap
   (the documentation does not say) / question.
3. Every time the documentation did not tell you what to do, log a **doc gap**: what you
   needed, where you found it in the end (the code, the tests, another document, the
   internet, a guess), and where in the documentation it should have been. Keep this log
   in `{{SCRATCH}}/doc-gaps.md` as you go, with times.
4. When the documentation does not say what should happen, or something seems wrong and
   you are not sure, ASK: SendMessage to your caller (the session that started you), a
   clear one-line first sentence, one topic per message. Continue with other steps while
   you wait. Questions about the files and wishes of their owner go there too.
5. Read the time with `date -u` at your start and at your end.

## Report

Your final message is the report (do not write report files; the notes in scratch are
working files). Sections, in this order:

1. **For people** (at most 10 lines): whether each task got done, and the three doc gaps
   that cost the most.
2. **Setup**: start and end time (UTC), your estimate of tool calls, the time of
   `expectations.md`, what you were given and what the harness attached unasked.
3. **Task (a)** and **Task (b)**: per step, the expectation, the command, the observation
   and the verdict.
4. **Commits in the clone**: `git -C {{CLONE}} log --stat` output, shortened.
5. **Doc gaps, ranked** by what they cost you (time, tool calls, wrong turns): what you
   needed, where you found it, where it belongs.
6. **Bugs** (ranked), **Surprises**, **Questions asked and the answers you got**,
   **Suggestions for the documentation**.

At most 2,000 words, concrete, no flattery. Say which inputs you invented because the
documentation did not specify them. Spend at least half of your attention on what the
documentation does not mention: the worst gaps lie outside what its authors thought to
cover.
