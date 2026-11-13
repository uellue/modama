# Hallway test: the developer docs (2026-11-13)

A fresh coding agent with only a clean clone of the repository does two tasks the way the
docs say: (a) a new format collection for MRC files, (b) a seeded issue from real data (a
Merlin header that is not UTF-8). It reports where the docs did not tell it what to do. A
blind grader then scores its clone against an answer key written before the first run.
Approved by @weber on 2026-11-13 (items 274 to 279).

| File | What |
|---|---|
| `setup.sh` | makes the clone and the tester's scratch directory |
| `seed.patch` | puts the Merlin header reading back to before its fix, and removes its reproducer (made at `crawler` 0fced7aa) |
| `brief.md` | the tester's prompt (`setup.sh` fills in the paths) |
| `answer-key.md` | the checklist for the grader; the answers the main session gives the tester |
| `grade-brief.md` | the grader's prompt |

## To run it again

1. `python/crawler/design/hallway/2026-11-13-developer-docs/setup.sh /workspaces/data-management-system`
   (from anywhere; optional: the clone's and the scratch directory's paths, default
   `/var/tmp/hallway/clone` and `/var/tmp/hallway/scratch`; both must not exist). It
   prints what it did and writes the filled brief to `<scratch>/brief.md`. If the seed no
   longer applies to `crawler`'s head, run it with `REF=0fced7aa` (the docs of that
   commit are then what is tested), or make the seed again. It warns when files in the
   clone mention this test.
2. Give `<scratch>/brief.md`, whole, as the prompt to a fresh coding agent (the session's
   model), in the background. Answer its questions from `answer-key.md`, "Answers the
   main session gives during the run"; never pass it the answer key.
3. When it reports, copy `answer-key.md` into a new scratch directory and give
   `grade-brief.md` (filled in by hand) to another fresh agent, without the tester's
   report.
4. Write the record beside this folder, as the kaizen hallway-test skill says (usage from
   its usage script, the ranked doc gaps, the grade): `2026-11-13-developer-docs.md`, a
   re-run's `2026-11-13-developer-docs-<date>.md`, so that `setup.sh` removes them from
   later clones.
5. Remove the clone and the scratch directories afterwards
   (`rm -rf -- "${dir:?}"`).

The seed relies on a UTF-8 locale (the VM's `C.UTF-8`; Python treats `C` as UTF-8 too).
Under a Latin-1 locale the seeded bug would not show.

Distortions, by design: the clone has no history (`git log` shows one commit); no search
stack, no Docker and no `browse`, since one stack serves the VM; the tester's harness may
attach the shared checkout's `AGENTS.md` and a memory index, which it must name.

## What it costs

To be filled in after the first run: minutes, output tokens and tool calls of the tester
and of the grader, from the usage script.
