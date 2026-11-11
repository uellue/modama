# Kaizen ledger

What leaves a debrief: proposals with decisions, the fate of earlier ones, what did not fit in the plugin's skills, and notes for the next debrief. The full reports are private, in `../.claude/debriefs/`. For the crawler only; earlier records stay where they are: the debrief of 2026-11-03 in `/docs/debriefs/2026-11-03.md`, lessons in `/docs/working-with-claude.md`, walk-throughs in `walkthroughs/`, reviews and play tests in `review.md`, `critique.md`, `playtest.md`.

Public: yes, asked 2026-11-10.
Message size: comfortable, asked 2026-11-10.

## Proposals

## Skill friction
- 2026-11-10, update: the skill assumes one instruction file and one `design/` per repository; here kaizen is rolled out for one subproject (`python/crawler/`) while the top level is shared with colleagues, so every record's place had to be asked.
- 2026-11-10, sync: step 2 assumes `git fetch` from the tracker's remote; here `origin` is the legacy iffgit and GitHub is no remote yet, so it fetched the GitHub URL directly into `github/*`; `gh` is not installed, the public API stood in.
- 2026-11-11, requirements: the skill writes `design/requirements.md`, but the crawler keeps one requirements document per topic (`requirements.md`, `-pipeline.md`, `-benchmark.md`); and the hand-over's "quote every open item in full" does not fit the fifteen-line message limit once a document has twenty items.

## Notes for the next debrief
- 2026-11-10: modama-rdm/modama#10 (`CONTEXT.md`, the glossary) → the rule on ambiguous words in `../AGENTS.md` points at it since the rebase; moving the crawler's terms there → `../BACKLOG.md`, "Move to GitHub".
- 2026-11-10: modama-rdm/modama#11 (GitLab CI removed) → dropped: GitHub Actions runs the same `uvx ruff` commands, so the rule on "clean" holds; the ruff failure on `prototypes/` → `../BACKLOG.md`.
- 2026-11-10 (inbox): Matt Pocock's skills installed (`mattpocock-skills` 1.3.2, user scope). Its `domain-modeling` keeps `GLOSSARY.md` (or `GLOSSARY-MAP.md` for several contexts), the top level has `CONTEXT.md`: which name, settle with the colleagues before moving the crawler's terms. The VM's provisioning reinstalls only kaizen (`/docs/working-with-claude.md`, devvm move).
- 2026-11-10 (note for the debrief, @weber, field test of the search stack, at the question "one shot on real work or repeated from a fixed state"): "Plugin language needs adjustment here."
- 2026-11-10 (note for the debrief, @weber, on the plugin; field test, after the runbook was rewritten from tables to code blocks): "The runbook format will be a friction in many cases, also if a user wants to extract their own shell scripts from that." The field-test skill's runbook ("one command per line, each with what it does") came out as a Markdown table, unreadable as raw text and with `|` escaped inside commands.
- 2026-11-10 (note for upstream, kaizen, @weber, field test): "diverging instructions from your responses here and the runbook". The channel probe (`# probe` at the prompt) was asked for only in the chat, not in the runbook, so @weber, following the runbook, did not do it; the skill's step 4 (check each channel) and step 5 (the runbook) are separate, and the probe never made it into the runbook.- 2026-11-10 (note for upstream, kaizen, @weber, field test): no clear "GO!" point in the sequence. The agent asked for the probe together with open questions, then looked for the recording before @weber had started it, and read the missing folder as a fault (a delay on the share, which there was not). The skill needs an explicit hand-over moment: the agent says "go", the person starts, the person says when it is started, and only then the agent looks.
- 2026-11-10: sync; read up to modama-rdm/modama#30, the next sync starts there. Issues and pull requests left undecided by @weber for now.
