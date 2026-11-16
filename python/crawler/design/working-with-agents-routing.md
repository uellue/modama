# Routing the working-with-agents material

Status: draft by Claude, 2026-11-16 (10:03 UTC), options only, nothing decided. Asked for by @weber the same day: "what would fit into the kaizen plugin …, what is specific to e.g. modama, what is reusable as a separate project/repo on GitHub, and what is for me personally. … let's play with options, and also let's look at requirements and walkthrough to understand this better. Here I want to decide on the routing. The detailed work goes into their specific places once we have split it up."

This file decides *where each piece goes*, not what it says. It builds on O26 (sort every piece into its layer) and W12 in `working-with-agents.md`.

## What there is to route

`working-with-agents.md` (about 15,000 words, options O1 to O39, questions W1 to W19) with `working-with-agents/` (five research reports, two scout experiments); `equivalences.md`; the ledger notes of 2026-11-12 to 11-16 in `kaizen.md`; the two kaizen issue drafts in `/.claude/drafts/`; `/docs/working-with-claude.md` (goal 3, about 5,000 words); 24 files of @weber's agent memory.

## The destinations, and what each one's record already says

| | Destination | Readers | Constraints found in its record |
|---|---|---|---|
| K | kaizen plugin, `uellue/skills` | the manager, colleagues, anyone who installs it (its `requirements.md` 1.4: the principal first, close colleagues next, others invited but not catered to yet) | public; "no details of other projects"; skills are Claude Code's, Codex reads only `AGENTS.md`; has `design/` (its own stakeholders, requirements, research) and `benchmarks/`; its README already has a section "Working with agents: lessons learned" |
| M | modama: this repository (crawler, top level), the private working repository after the demo (379) | contributors' people and agents | the top level is settled with the colleagues; the crawler's `AGENTS.md` is ours; public on GitHub except the private working repository |
| S | a separate repository on GitHub | to be found out: people outside a plugin, other tools, code that is not a skill | does not exist; one more home to keep alive |
| P | @weber personally | @weber and the agents working for him | agent memory (per user, per machine), the open-items page, a private board or repository; private |

Found while sorting: section 8's layers have a fifth that none of the four holds, **the ER-C team across projects** (know-how shared by modama, LiberTEM and later projects, internal findings: O11's record, W7). It is not modama-specific, not public, not personal. Question R1 below.

## First sort (the agent's lean, to be tested by the walks)

| Piece | Lean | Why; where it could go instead |
|---|---|---|
| O1 rules re-added after a summary, O39 push back and the debrief's signals, O14 measures | K | method for any project; a hook and a standing instruction kaizen already ships the frame for |
| O2 a session per area with a notes file, O3 one writer, O5 independence, O7 pause-point checklists | K | playbook and briefs; the area *list* and the notes files themselves are M |
| O9 roles defined by their preparation, O38 compose roles at load time, W19's words | K | agent definitions and `words.md`; the reading lists of modama's roles are M |
| O33, O35, O37 the analogy step, the library of known things, O36's scout as a benchmark | K (draft issue exists) | the library could become S if it grows a life of its own (other tools, other people adding entries) |
| O12 lessons become checks, O24 kaizen for teams, O22's board | K | the open-items page feature belongs here (ledger, 11-12) |
| Research and comparison (sections 2 to 4, 9, the five reports) | K's `design/research/`, or S as a handbook | the open question R2 |
| Section 1's numbers, section 5's diagnosis, the scout runs' raw answers | M | evidence about this project; K gets them abstracted ("a crawler project, five days, 8 summaries"), as its README already does |
| O32 `equivalences.md`, O34 reuse in review | M | the catalogue is the project's slice of K's library |
| O8 curated upstream series, O20 to O23 identity, memory review, shared coordination, working upstream; W1, W10 | M | rules for modama's contributors, settled with the colleagues |
| O31 the authorised officer (gatekeeper) | S, a repository of its own (@weber, 2026-11-16) | see "The authorised officer" below |
| O4 issues as briefs, O13 events, O29 assistant, O30 identity and credentials | M first (private GitLab), the method in K | |
| O10, O19, O25 the tree of agents, O15 liaison, O17, O18 crossings | K as method, P as @weber's instance of it | |
| O16 portfolio map, priorities, digest, decision queue, the open-items page's content | P | the portfolio layer of section 8 |
| How @weber likes to work (message length, when to ask) | P | stays in memory; O21 sorts the 24 files |
| O11 shared know-how record across projects | the fifth layer (R1) | internal findings, so not public |

## Separate repositories: which, and where

@weber, 2026-11-16: "we are evaluating here which ones we should create, and where. I like the idea of having the 'authorized officer' in a separate repo entirely since that will be an important safety gate that we need to keep small and tight."

When a piece earns a repository of its own (the agent's proposal, to be tested on the candidates below): it needs a **different permission boundary** (who may change it differs from who may change its neighbours), a **different audience** that K, M or P cannot reach, a **different life** (its own contributors, releases or pace), or it is **code that is not a skill**. One reason may be enough; "it is a topic of its own" is not one.

### The authorised officer (O31): its own repository

Settled in direction (@weber). Why it fits the criteria, beyond small and tight:
- **Permission boundary, enforced.** O31 says the officer's rules "live in git and only the person changes them". In a repository of its own that is a setting, not a sentence: the working agents get no write access to it at all, so no agent can widen the gate it has to pass (section 5, point 3: checks, not sentences).
- **Reviewable as a whole.** A safety gate is trusted only if it can be read in one sitting; a repository with nothing else in it keeps the review surface to the gate.
- **Reusable.** Any project with agents and credentials needs one; it is not modama's.

Found while placing it: the officer has **three parts with three homes**, and only one belongs in the repository:

| Part | What | Home |
|---|---|---|
| Mechanism | the code: takes a request, checks it against the policy and the artifacts, grants, rejects or escalates; the request and brief formats; its tests | the officer's repository (public?) |
| Policy | per deployment: the allow-list of acts, the tiers (O31), the filters (colleagues' names, internal host names), the receiving projects' rules | private, owned by the person whose authority it carries (P), or the team's (M) for a shared officer; changed only by that person |
| Credentials | the tokens it acts with | never in a repository; on the machine that runs it, revocable by the person |

Questions this raises: R5 to R7 below.

### Other candidates

- **S1 A handbook for people**, tool-neutral: the "what you do" of working with agents, the research and the comparison with human organisations, citeable, for colleagues and anyone (goal 2 of `/docs/working-with-claude.md`). Criterion: a different audience (people who install nothing, colleagues on Codex). Against: a second public text beside K's README section, and lessons registers fail at reuse (section 7, NASA): a handbook nobody loads is that register.
- **S3 The library of known things** (O37) as data others add to. Criterion: a different life, once others contribute; until then a reference file of K's analogy skill.
- **S4 The know-how record across ER-C projects** (R1). Criterion: a different audience and permission boundary (internal, several projects); on the institute's GitLab, not GitHub.
- **S5 Other infrastructure** (event-started agents, a token broker beside the officer, bot identities). Criterion: code that is not a skill; only once it exists, and kept out of the officer's repository so the gate stays small.

Lean: the officer now (as a design first, R5 to R7); S4 decided with R1; S1 by the walks; S3 and S5 when their content exists.

## Walks proposed

Personas from kaizen's stakeholder record (`uellue/skills`, `design/stakeholders.md`), to be confirmed before walking:

1. **The manager** (@weber, interviewed) starts agent work on a second project (for example LiberTEM) next week: which piece does each session need, and where does it find it? Tests K, P and the fifth layer.
2. **The colleague starting with agents** joins modama next to @weber's agents, maybe on Codex: what reaches them, from where, and what must not (P)? Tests M, K's reach without skills, and S1.
3. **The coding agent** starts a fresh session for one area: measured, since this session was one (it started from three files, one too long to read at once).
4. **The coding agent** asks the officer to open a merge request in the private repository, and once to do something outside its allow-list: tests the split into mechanism, policy and credentials, and what the request must carry. A persona for the officer itself, and one for whoever reads its log, are not in K's record yet.

## Open questions

- **R1** The fifth layer, ER-C across projects (O11's record, colleagues' shared conventions): a home of its own (a group on the institute's GitLab), or folded into M's private working repository until a second project needs it?
- **R2** Research and comparison: K's `design/research/` (with the plugin's own requirements), or S1?
- **R3** Does K take method that is not a skill (the tree of agents, layers, the gatekeeper's design) as documents, or only what a skill, hook or brief carries?
- **R5** Where does the officer's repository live: public on GitHub (under `uellue` or `modama-rdm`), or private on the institute's GitLab first? Lean: public on GitHub under `uellue` once it has code, since a safety gate gains from outside eyes and holds no secrets if policy and credentials stay out; designed in the private working repository until then.
- **R6** Is there one officer per person (it carries that person's authority, O31: "directly under my authority") or one per team with a policy per person? Lean: one per person to start, as the quote says; a team's officer when a second person needs one (O25).
- **R7** What does it run on, and with which model? Lean: a separate process with only the tools for its acts (O31), not a Claude Code session with a shell; the model a question for its design, preferably not the requesters' (section 4, copies share errors).
