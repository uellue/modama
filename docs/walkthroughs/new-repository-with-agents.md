# Walk-through: a colleague starts a new repository for development with agents

Persona: a research software engineer at ER-C, comfortable with git, Python and Docker, who has watched the modama crawler work from a distance and wants the same setup for a new tool of their own: Claude Code (a Codex user is the variant), in a devcontainer, on iffgit, with the lessons from `docs/working-with-claude.md` applied from day one. Confidence: simulated, by Claude on 2026-11-03; the questions below are for @weber and for the first colleague who actually does this.
What exists: modama's root `CLAUDE.md`, `python/crawler/CLAUDE.md` and `AGENTS.md`, `.devcontainer/` (Dockerfile, compose, `post-create.sh`), `.gitignore`, `docs/working-with-claude.md`, `python/crawler/design/` and `openspec/`, the kaizen plugin at github.com/uellue/skills, Claude Code's plugin and settings documentation.

## Steps

1. **Create the repository on iffgit and clone it.** Does: new project, default branch, clone. Needs to know: nothing agent-specific yet. Goes wrong: nothing. Would ask: "Is there a template?" (There is not; modama is the example, and it is a monorepo with seven services.)
2. **Set up isolation.** Does: copies modama's `.devcontainer/`. Needs to know: which parts are modama-specific: the PostgreSQL service and its five environment variables, the pyxdg sibling mount, the read-only data mount, the forwarded port, the editable installs in `post-create.sh`. Which parts are general: the `claude-home` named volume so sessions and memory survive a rebuild, the `chown` of that volume, the backup-and-restore of `~/.claude` into the repository's ignored `.claude/home-backup/`, the Node feature for OpenSpec, the X packages for the visual check. Goes wrong: the general parts are not marked as such, so they copy the database too, or drop the volume and lose their agent's memory at the first rebuild. Would ask: "Which lines of this are the agent setup, and which are the crawler's?"
3. **Decide how the agent persists.** Does: nothing, because they do not know there is a decision. Needs to know: memory and sessions live in `~/.claude`, per user and per checkout path; a devcontainer without the volume loses them at every rebuild; the `.claude/` folder in the repository is ignored by git and holds a token and a full copy of the home directory, including the login credential, as a local backup only. Goes wrong: a backup folder with a credential in it inside a repository checkout is one `git add -f` or one shared folder away from a leak. Would ask: "Why is my login credential in a folder inside the repository?"
4. **Write the instruction file.** Does: runs `/init`, gets a `CLAUDE.md` describing the empty repository. Needs to know: modama's convention is `AGENTS.md` with the content and `CLAUDE.md` as a one-line import, so that Codex reads the same file; what the sections are (goal and status, principles, decisions so far, commands, architecture, gotchas, tests, standing rules for agents); that the root of modama itself does not follow its own convention yet (`CLAUDE.md` with content, no `AGENTS.md`). Goes wrong: `/init` writes a `CLAUDE.md`; the colleague does not know about `AGENTS.md`; a Codex-using colleague of theirs gets nothing. Would ask: "Which file do I write, and what has to be in it before the first session?"
5. **Choose the design record.** Does: looks at `python/crawler/design/` (six documents, 150 KB) and `openspec/` and feels discouraged. Needs to know: which of these a new, small project needs on day one. The review found the spread costly even for the crawler. Goes wrong: either copies everything (and maintains six documents for a 500-line tool) or nothing (and the decision log that refuted eleven refactorings never exists). Would ask: "What is the minimum: a decision log and a backlog? When does OpenSpec pay off?"
6. **Install the shared tooling.** Does: `claude plugin marketplace add uellue/skills`, `claude plugin install kaizen@uellue`. Needs to know: that the marketplace exists, what it contains, that project scope would enable it for everyone who clones. Goes wrong: nothing, once they know; but nothing in a new repository tells them. Would ask: "Should the repository enable it for everyone, and where is that written down?" (It is `.claude/settings.json` with `enabledPlugins`, which modama does not have either.)
7. **Give the agent access to iffgit.** Does: wants the agent to read merge-request comments as the crawler's does. Needs to know: a read-only project token with `read_api`, kept at a gitignored path, used only at call time, never copied into files or chat; the token's expiry; that the agent commits under the colleague's identity with a co-author line. Goes wrong: the procedure exists only in Claude's memory for @weber's checkout and in one backlog line; a colleague either skips it or makes a token with more rights than needed. Would ask: "What rights does the token need, where do I put it, and who is the agent on git?"
8. **Set permissions.** Does: starts in auto mode, approves things one by one. Needs to know: which commands the project wants pre-allowed, and which must never run (`docker compose down -v` for the volume; pushes; the production data mount). Goes wrong: either a prompt on every test run, or a blanket allow. Would ask: "Is there an allowlist to start from?" (There is a skill for it, `/fewer-permission-prompts`; nothing project-level is committed.)
9. **The first piece of work.** Does: describes the tool and asks the agent to build it. Needs to know: the leadership habits in the notes: principles once, options with counter-arguments, outcome not solution, examples labelled, numbered answers, judge the behaviour; and the standing rules the agent should carry (which scenario asks for this, library before custom code, evidence). Goes wrong: the habits are in a notes file inside modama; the standing rules are in the crawler's `AGENTS.md`. The colleague starts from `/init` and from habit. Would ask: "Is there a one-page version of this?"
10. **The first review and the first debrief.** Does: finishes the change, asks the agent whether it is done. Needs to know: `/code-review` for correctness, the review dimensions for the owner's rules, `/kaizen:debrief` at the end of the stretch, `docs/debriefs/` as history. Goes wrong: "all tests pass" is accepted as done; the lessons stay in chat. Would ask: "What does 'done' mean here?"
11. **A Codex-using colleague joins.** Does: opens the repository with Codex. Needs to know: `AGENTS.md` is read; skills, plugins, hooks and settings are not; the debrief and the hallway test have no Codex form. Goes wrong: two agents with different standing rules on one repository. Would ask: "Which of this works for me?"

## Product hat

The colleague wanted one thing: to start the way modama now works, in an afternoon, without reading three weeks of history. "Done" for them is a repository where the first agent session already knows the rules, keeps its memory across rebuilds, can read the merge request, and ends with a debrief. What they would complain about: the setup is scattered across a monorepo's devcontainer, one subproject's instruction file, a notes file, Claude's private memory, and a plugin they have to be told about.

## Developer hat

Feasible, nothing exotic. Fragile: the credential copy in `.claude/home-backup/` (step 3) and the token procedure living in memory rather than in a file (step 7). Slow: steps 4 and 5 without a template cost a day each the first time. Insecure if done wrong: a token with write rights, a backup folder that stops being ignored.

## Questions for the owner

- Which parts of modama's devcontainer are the agent setup, and should they be a separate, copyable piece? (step 2)
- Should the home-directory backup exclude the credential file, or move out of the repository tree altogether? (step 3)
- Does modama's root follow the `AGENTS.md` convention, so that Codex users get the project instructions? (step 4)
- What is the minimum design record for a new repository, and at what size does OpenSpec pay off? (step 5)
- Should the kaizen plugin be enabled at project scope in modama, and in a new repository's template? (step 6)
- What is the written procedure for an agent's iffgit access, and is the agent a persona with its own token or the developer? (step 7)
- Is there a project-level permission allowlist worth committing? (step 8)
- Where does the one-page guide live, so that it is found from a new repository and not only from modama? (step 9)

## Gaps

- A template or a short "new repository" checklist that carries the general parts of the setup: devcontainer fragment with the `claude-home` volume, `AGENTS.md` skeleton with the standing rules, `CLAUDE.md` import, `.gitignore` entries for `.claude/`, `.claude/settings.json` enabling kaizen, `docs/debriefs/`, a minimal design record.
- A written token procedure (rights, path, expiry, use at call time), today only in Claude's memory and a backlog line.
- ~~The home-backup includes `.credentials.json`; nothing says it must stay ignored, and nothing excludes it.~~ Done 2026-11-03: `.devcontainer/backup-claude-home.sh` copies the home directory without the credential; the copy on disk was cleaned.
- ~~`AGENTS.md` at modama's root, so the repository follows its own convention.~~ Done 2026-11-03: the root instructions moved to `AGENTS.md`, `CLAUDE.md` is the one-line import.
- A Codex counterpart, or at least a statement of what Codex users get and what they do not.
- A definition of "done" for a change (tests, review by an agent that did not write it, spec scenario, debrief) in the instruction file skeleton.

## Acceptance examples

- When a colleague copies the new-repository checklist into an empty iffgit project and opens it in a devcontainer, then the first Claude Code session starts with the standing rules loaded, `/kaizen:debrief` available, and memory that survives a container rebuild.
- When the same repository is opened with Codex, then the project instructions are read from `AGENTS.md` and the README says which kaizen skills have no Codex form.
- When the agent reads a merge-request comment, then it does so with a token that has read rights only, stored at a gitignored path, and the procedure that created the token is in the repository's documentation.
- When `git add -A` is run in a checkout with the home-directory backup present, then no credential and no token is staged.
- When a developer asks "is it done", then the answer names the tests run, the review by a second agent, the spec scenario, and the debrief entry.
