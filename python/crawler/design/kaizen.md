# Kaizen ledger

What leaves a debrief: proposals with decisions, the fate of earlier ones, what did not fit in the plugin's skills, and notes for the next debrief. The full reports are private, in `../.claude/debriefs/`. For the crawler only; earlier records stay where they are: the debrief of 2026-11-03 in `/docs/debriefs/2026-11-03.md`, lessons in `/docs/working-with-claude.md`, walk-throughs in `walkthroughs/`, reviews and play tests in `review.md`, `critique.md`, `playtest.md`.

Public: yes, asked 2026-11-10.
Message size: comfortable, asked 2026-11-10.

## Proposals

## Skill friction
- 2026-11-10, update: the skill assumes one instruction file and one `design/` per repository; here kaizen is rolled out for one subproject (`python/crawler/`) while the top level is shared with colleagues, so every record's place had to be asked.
- 2026-11-10, sync: step 2 assumes `git fetch` from the tracker's remote; here `origin` is the legacy iffgit and GitHub is no remote yet, so it fetched the GitHub URL directly into `github/*`; `gh` is not installed, the public API stood in.

## Notes for the next debrief
- 2026-11-10: modama-rdm/modama#10 (`CONTEXT.md`, the glossary) → the rule on ambiguous words in `../AGENTS.md` points at it since the rebase; moving the crawler's terms there → `../BACKLOG.md`, "Move to GitHub".
- 2026-11-10: modama-rdm/modama#11 (GitLab CI removed) → dropped: GitHub Actions runs the same `uvx ruff` commands, so the rule on "clean" holds; the ruff failure on `prototypes/` → `../BACKLOG.md`.
- 2026-11-10 (inbox): Matt Pocock's skills installed (`mattpocock-skills` 1.3.2, user scope). Its `domain-modeling` keeps `GLOSSARY.md` (or `GLOSSARY-MAP.md` for several contexts), the top level has `CONTEXT.md`: which name, settle with the colleagues before moving the crawler's terms. The VM's provisioning reinstalls only kaizen (`/docs/working-with-claude.md`, devvm move).
- 2026-11-10: sync; read up to modama-rdm/modama#30, the next sync starts there. Issues and pull requests left undecided by @weber for now.
