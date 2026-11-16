# Routing the working-with-agents material

Status: draft by Claude, 2026-11-16 (10:03 UTC), options only, nothing decided. Asked for by @weber the same day: "what would fit into the kaizen plugin …, what is specific to e.g. modama, what is reusable as a separate project/repo on GitHub, and what is for me personally. … let's play with options, and also let's look at requirements and walkthrough to understand this better. Here I want to decide on the routing. The detailed work goes into their specific places once we have split it up."

This file decides *where each piece goes*, not what it says. It builds on O26 (sort every piece into its layer) and W12 in `working-with-agents.md`.

## Decided so far

- **The rule decides, not a list** (@weber, 2026-11-16: "I like your reasoning on how to split it up, a nice meta answer (rule to decide instead of decision outright). Let's run with that!"): a piece gets a repository of its own by the criteria in "Separate repositories" below; everything else goes to the layer whose readers need it.
- **R5** The authorised officer: designed in the private working repository, then public on GitHub under `uellue` once it has code (@weber: "I like it!").
- **R7** What the officer runs on and with which model: kept as a question for the officer's own design, not settled here (@weber: "Let's keep the question and work on that in the appropriate place").
- **R8** A private portfolio repository of @weber's (@weber, 2026-11-16: "yes agree, I need my own private portfolio repo. Also associated communication and signaling channels."). It holds what follows him across projects and machines: how he works (`~/.claude/CLAUDE.md`, provisioned by devvm), the portfolio map (O16), priorities, the decision queue and digest, ledgers of projects he does not own alone (R10). Its channels: R14; the officer's policy: R15.
- **R15** The officer's policy gets a small repository of its own, written by the person only, and public for now (@weber, 2026-11-16: "yes exactly. I think that one can be public for now, let's see how that will evolve. The portfolio makes no sense public, and contains a lot of more private 'noise'."). So three repositories for the officer's world: the mechanism (public), the policy (public), the portfolio (private). What a public policy must not hold: R16.
- **R16** The lean taken "for now" (@weber, 2026-11-16): public rules and tiers with hosts and projects by alias; the filter list and the alias mapping private; the officer fails to start without them.
- **R2** The research and comparison go to the kaizen repository, referenced from its README (@weber, 2026-11-16).
- **R3** The embodiment of the agent organisation (roles, the tree, events, housekeeping) goes to a repository of its own; kaizen takes "the rationale and research so far" (@weber).
- **R6** One officer per person, clone-and-own, with the selective membrane as read above (@weber: "yes exactly!").
- **R13** The vault is kept as a tool and an option, not decided. The underlying requirement (@weber): "make key management, authentication and authorization safe, predictable, understandable and convenient in practice", to be worked on in its own place.
- **R9** Yes (@weber: "Important instructions slipping out of sight was a recurring theme here, I think. A bit like posting a note 'remember to empty the dishwasher'").
- **R10** Yes, and more generally the debrief routes between ledgers; in the portfolio repository, ledger entries are probably work items (issues), routed on from there (@weber).
- **R11** Yes.
- **R12** Yes; where, see the packages below (@weber: "at least some part of that needs to go to the contributor docs of every project, or where else?").
- **R14** Worked out there, with kaizen; the portfolio repository becomes the headquarters from which things are routed to places of their own (@weber).
- **Walks 3 and 4** are not needed for the routing (walk 3 tests O2's notes files, walk 4 the officer's design); they go as notes with the packages they test (@weber).
- **R4** Walks 1 and 2 first, "only as a test to see where they should go" (@weber); done on the small path, results below.

## The packages (draft, 2026-11-16, from the decisions below)

Each package goes to its place and is worked out there; O, W and R numbers refer to `working-with-agents.md` and this file.

| Package | Destination | Contents |
|---|---|---|
| Method and rationale | kaizen, `uellue/skills` (public; abstracted, no other projects' details) | research and comparison (sections 2 to 4, 9, the five reports) in `design/research/`, linked from the README (R2, R3); for skills, hooks and briefs: the standing rules back after a summary (O1, R9), push back and the debrief's signals (O39, O14), a session per area with a notes file (O2), one writer, independent review, pause-point checklists (O3, O5, O7), roles by their preparation (O9, O38) and the words (W19), lessons become checks (O12), kaizen for teams and the board (O22, O24), routing between ledgers (R10), the analogy skill (O33, O35, O37, the scouts as a benchmark); notes: walk 3. Vehicles: the two drafted issues in `/.claude/drafts/`, to be brought up to date |
| The agent organisation | a new repository (R3) | its embodiment: roles and their definitions, the tree (O10, O19, O25), the assistant (O29), identity and limited credentials (O30), events and housekeeping (O13, O14), the layers (O26, O28); the credentials requirement of R13 is a candidate home |
| The officer's mechanism | a new repository, public under `uellue` once it has code, designed privately first (R5) | O31's gatekeeper, clone-and-own per person (R6), what it runs on (R7), where its keys live (R13); notes: walk 4 |
| The officer's policy | a new public repository, written by the person only (R15) | rules and tiers, hosts and projects by alias (R16) |
| Portfolio headquarters | @weber's private repository on the institute's GitLab (R8, R14) | how he works (`~/.claude/CLAUDE.md`, via devvm), the portfolio map (O16), priorities, the decision queue that replaces the open-items page, the digest, ledgers of shared projects as work items (R10), the officer's private filters and aliases (R16), the sorting of the 24 memory files (O21, W11); R1 until decided |
| modama | this repository, its private working repository (379), the top level with the colleagues | team rules out of personal form and kaizen's commands marked (R11), contributors' rules (O8, O20 to O23), `equivalences.md` (O32), the area list and notes files (O2, W5), the raw evidence (sections 1 and 5, the scouts' answers) |
| Working with agents, per project | every project's contributor docs (R12) | see below |

**R12, where else.** One home per fact: the general part (how to work with agents, tool-neutral) lives once, in kaizen's README and research, and every project's contributor docs link to it instead of copying it; what is specific to the project (which rules its agents follow, what is reviewed, how agent work is marked, O20) goes into its contributor docs (`CONTRIBUTING`, `AGENTS.md`). Kaizen could ship the template for that section and keep it in step, as `/kaizen:update` does for the standing instructions. Rules shared by every ER-C project, if there are any, would be R1's place.

## What there is to route

`working-with-agents.md` (about 15,000 words, options O1 to O39, questions W1 to W19) with `working-with-agents/` (five research reports, two scout experiments); `equivalences.md`; the ledger notes of 2026-11-12 to 11-16 in `kaizen.md`; the two kaizen issue drafts in `/.claude/drafts/`; `/docs/working-with-claude.md` (goal 3, about 5,000 words); 24 files of @weber's agent memory.

## The destinations, and what each one's record already says

| | Destination | Readers | Constraints found in its record |
|---|---|---|---|
| K | kaizen plugin, `uellue/skills` | the manager, colleagues, anyone who installs it (its `requirements.md` 1.4: the principal first, close colleagues next, others invited but not catered to yet) | public; "no details of other projects"; skills are Claude Code's, Codex reads only `AGENTS.md`; has `design/` (its own stakeholders, requirements, research) and `benchmarks/`; its README already has a section "Working with agents: lessons learned" |
| M | modama: this repository (crawler, top level), the private working repository after the demo (379) | contributors' people and agents | the top level is settled with the colleagues; the crawler's `AGENTS.md` is ours; public on GitHub except the private working repository |
| S | a separate repository on GitHub | to be found out: people outside a plugin, other tools, code that is not a skill | does not exist; one more home to keep alive |
| P | @weber personally | @weber and the agents working for him | agent memory (per checkout path, per machine), the open-items page, a private board or repository; private; splits in two (R8) |

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

**Where the credentials could live (R13, for the officer's design).** @weber, 2026-11-16: "Can sth like https://vault.fz-juelich.de help to manage credentials? I got really, really tired of juggling with env files that hold keys, and the agent organization will make that so much worse." Checked the same day from its public `/api/config`: the service is **Vaultwarden 1.37.5**, a Bitwarden-compatible password manager, not HashiCorp Vault; no single sign-on configured. Its README lists personal vaults, a personal API key, organisations with collections, member roles, groups and event logs; Bitwarden's Secrets Manager (machine accounts, project-scoped access tokens, `bws run`) is not in that list. So:
- **It helps with env files**: keys stored once, as items in a collection, and fetched at run time with Bitwarden's CLI (`bw get password <item>` after `bw unlock`) into the one command that needs them, instead of a file on disk.
- **It can approximate role-limited credentials** (O30): one account per bot role, seeing only its collection. Whether the institute allows accounts that are not people is a question for its operators.
- **It does not give** short-lived or dynamic credentials, rotation, or a second approval before use; those are what a secrets broker such as HashiCorp Vault or OpenBao offers (not checked whether the institute runs one).
- **The agent-specific risk**: whatever the agents' shell can read, an agent can read, and so can instructions injected into it. An unlocked `bw` session (`BW_SESSION`) in the VM where agents work opens everything that account sees. So the person's vault is never unlocked where agents run; only the officer, as a separate process or user (R7), holds a session, of its own bot account. That is O31's rule, "the credential is held by the system, not by the requesting agent", with an existing tool.

### Other candidates

- **S1 A handbook for people**, tool-neutral: the "what you do" of working with agents, the research and the comparison with human organisations, citeable, for colleagues and anyone (goal 2 of `/docs/working-with-claude.md`). Criterion: a different audience (people who install nothing, colleagues on Codex). Against: a second public text beside K's README section, and lessons registers fail at reuse (section 7, NASA): a handbook nobody loads is that register.
- **S3 The library of known things** (O37) as data others add to. Criterion: a different life, once others contribute; until then a reference file of K's analogy skill.
- **S4 The know-how record across ER-C projects** (R1). Criterion: a different audience and permission boundary (internal, several projects); on the institute's GitLab, not GitHub.
- **S5 Other infrastructure** (event-started agents, a token broker beside the officer, bot identities). Criterion: code that is not a skill; only once it exists, and kept out of the officer's repository so the gate stays small.

Lean: the officer now (as a design first, R5 to R7); S4 decided with R1; S1 by the walks; S3 and S5 when their content exists.

## Walks proposed

Personas from kaizen's stakeholder record (`uellue/skills`, `design/stakeholders.md`). Walks 1 and 2 done (2026-11-16, small path, simulated, results in R8 to R12 and RE1 to RE7); 3 and 4 not yet:

1. **The manager** (@weber, interviewed) starts agent work on a second project (for example LiberTEM) next week: which piece does each session need, and where does it find it? Tests K, P and the fifth layer.
2. **The colleague starting with agents** joins modama next to @weber's agents, maybe on Codex: what reaches them, from where, and what must not (P)? Tests M, K's reach without skills, and S1.
3. **The coding agent** starts a fresh session for one area: measured, since this session was one (it started from three files, one too long to read at once).
4. **The coding agent** asks the officer to open a merge request in the private repository, and once to do something outside its allow-list: tests the split into mechanism, policy and credentials, and what the request must carry. A persona for the officer itself, and one for whoever reads its log, are not in K's record yet.

## Open questions

- **R1** The fifth layer, ER-C across projects (O11's record, colleagues' shared conventions): a home of its own (a group on the institute's GitLab), or folded into M's private working repository until a second project needs it? New option since R14: start in the portfolio headquarters, which already spans the projects, and move out by the rule (a different audience) when the first colleague needs it. Lean: that.
- **R2** Research and comparison: K's `design/research/` (with the plugin's own requirements), or S1?
- **R3** Does K take method that is not a skill (the tree of agents, layers, the gatekeeper's design) as documents, or only what a skill, hook or brief carries?
- **R5** Where does the officer's repository live: public on GitHub (under `uellue` or `modama-rdm`), or private on the institute's GitLab first? Lean: public on GitHub under `uellue` once it has code, since a safety gate gains from outside eyes and holds no secrets if policy and credentials stay out; designed in the private working repository until then.
- **R6** Is there one officer per person (it carries that person's authority, O31: "directly under my authority") or one per team with a policy per person? Lean: one per person to start, as the quote says; a team's officer when a second person needs one (O25). @weber, 2026-11-16: "With agents it is now much easier to maintain sth like a 'quasi-fork', idk how to describe it, where new features are transferred through what humans may label 'osmosis', i.e. picking it up without a formal channel. Skills also work that way. A bit how bacteria handle gene transfer: Not with sexual procreation like in higher organisms, but by transferring gene snippets around, iirc even across species boundaries. People transfer useful sentences to their agents just like that." I read this as: one officer per person, each person's copy free to diverge, improvements travelling between copies by being picked up, not merged through one upstream. Software has a name for the pattern: **clone-and-own** (software product-line engineering: copy a variant, adapt it, carry changes between the copies by hand or with tool support); the biology is horizontal gene transfer. Not yet checked: the literature on how clone-and-own fares (sources to be read before this is cited). The strongest argument against, for the officer only: a snippet picked up into a safety gate is outside code entering the gate. So the membrane is selective: policy sentences and skills may travel freely between people, but anything entering an officer's mechanism passes the same review as any change to it, and only its person takes it in (O31: only the person changes its rules). The mechanism's public repository is then the common ancestor the copies pick from, not an upstream they must follow. Open: whether that answers R6 (one per person, clone-and-own), and whether "clone-and-own" is the word to use.
- **R7** What does it run on, and with which model? Deferred to the officer's design (above). The agent's lean, kept for that place: a separate process with only the tools for its acts (O31), not a Claude Code session with a shell; preferably not the requesters' model (section 4, copies share errors).

- **R13** The institute's Vaultwarden as the officer's credential store (see "Where the credentials could live")? Lean: yes for the person's own keys now (env files out of the way), and for the officer's bot account once the operators allow non-person accounts; ask them also whether the institute runs a secrets broker. For the officer's design, with R7.

- **R14** The portfolio repository's channels, in section 7's terms (git the memory, issues the work, messages the telephone, events the doorbell): its decision queue as issues in it (`needs-weber`), replacing the open-items page for him; signals to him by what the tracker already sends (its to-do list, mail); signals into it from the projects as cross-project issue links and mentions, and the officer's escalations (O31) as issues assigned to him; agents read it with a read token of their own (R13). Lean: all on the institute's GitLab first, since it exists, notifies and is where 379 and 380 already plan the team's; a chat channel or push notifications only if mail proves too slow. Open: which GitLab (iffgit or another instance of the institute).
- **R16** A public policy and its filters. The policy includes the filters the officer and the assistant share (O29, O31: colleagues' names, internal host names), and its allow-list names the hosts and projects the officer may act on. Published, the filter list would show exactly what it is meant to keep out, and the allow-list would be a map of what a stolen bot token reaches. Lean: the public policy holds the rules and the tiers, with hosts and projects by alias; the filter list and the alias-to-host mapping stay private, in the portfolio repository or as items in the vault (R13), and the officer loads them at start. Strongest argument against: two places to read the policy from; the officer's start must fail, not run without filters, when the private part is missing ("Fail, don't skip").
- **R15** (decided, see above) The officer's policy is P, but agents (the assistant, O29) will write to the portfolio repository, and only the person may change the policy (O31). So the policy cannot sit in a path agents can write to. Options: a protected path in the portfolio repository (code owners, the person's approval required; holds only if agents cannot approve), or a small repository of its own beside it, written by the person only. Lean: its own repository, for the same reason as the officer's code: a boundary that is a setting, not a rule.

From the walks (`walkthroughs/manager-second-project.md`, `walkthroughs/colleague-joins-agent-work.md`):

- **R8** (decided, see above) P is two layers, not one: what follows the person across projects and machines (how he works, the portfolio map, his ledger in shared projects) and what belongs to one checkout (auto memory). Today only the second exists, so nothing of the first reaches a LiberTEM session. The established pattern for the first is a **dotfiles repository**: a private personal repository that devvm provisions into every VM, holding a `~/.claude/CLAUDE.md` (or `~/.codex/AGENTS.md`) and the portfolio map. Lean: yes, a private personal repository on the institute's GitLab.
- **R9** kaizen's standing instructions reach a session only through the project's instruction file, which in LiberTEM belongs to other maintainers. A plugin can ship hooks: a kaizen `SessionStart` hook (on start and after a summary) that adds the standing instructions would bring them to any project without touching its files, and would also be O1 (rules back after a summary). Lean: propose it for kaizen, with the project file still able to override. To check first: what a plugin hook may inject, with the `claude-code-guide` agent, as kaizen's `CLAUDE.md` asks for claims about Claude Code.
- **R10** kaizen's debrief commits its ledger into the project; in a project the person does not own alone, it should go to the person's place (R8's repository). Lean: a ledger location setting in kaizen, default the project, as today.
- **R11** modama's `AGENTS.md` mixes rules every contributor's agent can follow with kaizen commands (`/kaizen:update`, offer `/kaizen:debrief`) and one person's provenance. Lean: as O26 says, team rules phrased as the team's (provenance in the decision log), kaizen's block marked "if you use kaizen".
- **R12** A colleague without Claude Code needs a short, tool-neutral guide to how the team works with agents. Lean: this is S1's case; whether it is a repository of its own or kaizen's README section made tool-neutral is R2.

## Acceptance examples (from the walks)

Kept here, not in `design/examples.md`, which holds the search's examples.

- **RE1** When @weber opens a session in a new checkout on a new VM, his way of working (numbered items, commands in the final message, check before claiming) is in effect from the first message, without copying memory files by hand. Walk 1, step 1.
- **RE2** When @weber works in a project whose instruction file belongs to others, kaizen's standing instructions hold in his sessions, also after a context summary, with no line added to that project's files. Walk 1, step 2.
- **RE3** When an agent in LiberTEM touches the CPU count in containers, one search in one place finds modama's finding and the drafted fix. Walk 1, step 3.
- **RE4** A debrief in a project @weber does not own alone commits nothing into that project unasked; its ledger lands in his place. Walk 1, step 6.
- **RE5** A colleague's Codex agent reading modama's `AGENTS.md` meets only rules it can follow without kaizen and that the team agreed to; kaizen's steps are marked as such. Walk 2, step 2.
- **RE6** A colleague asking what is open finds it in the team's tracker, not on one person's private page. Walk 2, step 3.
- **RE7** A colleague without Claude Code reaches a short, tool-neutral guide to how the team works with agents from the README in two clicks. Walk 2, step 4.
