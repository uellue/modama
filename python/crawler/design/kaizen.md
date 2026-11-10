# Kaizen ledger

What leaves a debrief: proposals with decisions, the fate of earlier ones, what did not fit in the plugin's skills, and notes for the next debrief. The full reports are private, in `../.claude/debriefs/`. For the crawler only; earlier records stay where they are: the debrief of 2026-11-03 in `/docs/debriefs/2026-11-03.md`, lessons in `/docs/working-with-claude.md`, walk-throughs in `walkthroughs/`, reviews and play tests in `review.md`, `critique.md`, `playtest.md`.

Public: yes, asked 2026-11-10.
Message size: comfortable, asked 2026-11-10.

## Proposals

## Skill friction
- 2026-11-10, update: the skill assumes one instruction file and one `design/` per repository; here kaizen is rolled out for one subproject (`python/crawler/`) while the top level is shared with colleagues, so every record's place had to be asked.

## Notes for the next debrief
- 2026-11-10 (inbox, from the first look at GitHub): modama-rdm/modama#10 added `CONTEXT.md`, a glossary of the domain language; the standing rule on ambiguous words should point at it once the crawler branch has it (it is 107 commits behind origin).
- 2026-11-10 (inbox): modama-rdm/modama#11 removed the GitLab CI; the top-level `AGENTS.md` ("mirrors `.gitlab-ci.yml`") and the crawler's rule on "clean only from the command CI runs" refer to what CI runs, now GitHub Actions; check after the rebase.
