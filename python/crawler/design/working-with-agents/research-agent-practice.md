# Organising software work across many coding agents and a few humans: current practice, 2025–2026

Research note, 2026-11-16. Every source cited below was fetched and read in this run. Quotes are short and marked. Anything I could not fetch is listed under "Not verified".

## Summary for people (main lessons)

1. Use several agents for reading, research and review. Keep writing to one agent per piece of code. Anthropic, Cognition (in its 2026 follow-up) and CooperBench reach the same conclusion from different directions.
2. Each extra agent costs a lot of tokens: about 15× chat for Anthropic's research system, and about 7× a single session for Claude Code agent teams in plan mode. Coding work also parallelises less than research does.
3. The human doing the reviewing is the limit. Running more agents than one person can review just makes the queue longer (Osmani, Willison, Faros telemetry). Set a work-in-progress limit and let agents prove routine correctness themselves.
4. Don't rely on compaction to carry the work. Keep state in files that outlive the session: progress notes, feature lists, git history, issues. Start a fresh session per task or area rather than one session that never ends.
5. A reviewer that never saw how the code was written helps. LLM reviewers also flag correct code, though, so tell them what to skip ("skip style").
6. Writing a spec first helps review, because code built from your own spec is easier to check. Heavy spec frameworks add review overhead and can be too much for small changes (Böckeler).
7. Open-source policies converge on the same points: a human understands and answers for every line, AI use is disclosed, changes are small with one scope each, and no unsupervised agents. A few projects (Gentoo, NetBSD, QEMU) ban AI-generated code outright.
8. The productivity evidence is weak and mixed. METR measured a 19% slowdown in early 2025. Its late-2025 follow-up points to a speedup but can no longer measure it reliably, partly because developers now run several agents at once.

---

## 1. Anthropic: documentation and engineering posts

**Multi-agent research system** (https://www.anthropic.com/engineering/multi-agent-research-system)
- Multi-agent setups suit breadth-first work with independent directions. Anthropic reports 90.2% better results than single-agent Opus 4 on its internal research eval.
- Costs: agents use "4× more tokens than chat interactions", and multi-agent systems use about "15× more tokens than chats". They only pay off where "the value of the task is high enough".
- Poor fits are tasks with shared context or many dependencies between agents. The post also says "most coding tasks involve fewer truly parallelizable tasks than research".
- Briefs: "Each subagent needs an objective, an output format, guidance on the tools and sources to use", plus clear task boundaries. Vague briefs led to duplicated work and gaps.
- Long tasks: the lead saves its plan to memory, because context gets truncated. Sub-agents write output to external storage and return references, which reduces information loss.
- Failure modes Anthropic saw: "50 subagents for simple queries", agents "distracting each other with excessive updates", and the whole system blocking while it waited on one slow sub-agent.
- Evaluation: start with about 20 real queries, judge the final state rather than the path, and keep human testing.

**Effective context engineering** (https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Context is "a finite resource with diminishing marginal returns".
- Compaction risk: "overly aggressive compaction can result in the loss of subtle but critical context".
- Structured note-taking means the agent "regularly writes notes persisted to memory outside of the context window".
- A sub-agent may use tens of thousands of tokens but returns "often 1,000-2,000 tokens".
- When to use each: compaction for long back-and-forth conversations, notes for "iterative development with clear milestones", sub-agents for parallel research.

**Building effective agents** (https://www.anthropic.com/engineering/building-effective-agents)
- "finding the simplest solution possible, and only increasing complexity when needed."
- Agents trade latency and cost for performance, and errors compound over steps.
- The orchestrator-worker and evaluator-optimizer patterns pay off only when there are clear evaluation criteria.
- Coding suits agents because tests verify the work, but humans still check fit with the wider system.

**Effective harnesses for long-running agents** (https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents, 26 Nov 2025)
- "compaction isn't sufficient" on its own.
- An initializer session creates `init.sh`, a progress file and a feature list in which every feature starts as failing. Each later session reads git log and the progress notes, runs a basic end-to-end test, works on one feature, commits, and updates the notes.
- Failure modes: declaring victory too early, leaving broken or undocumented state, and marking features done without testing.
- Whether one agent or a multi-agent setup (for example separate QA agents) does better is left as an open question.

**Claude Code best practices** (https://code.claude.com/docs/en/best-practices)
- Specs: write `SPEC.md`, then build in a fresh session "so the build begins with a clean context and a written definition of done".
- Review: `/code-review` runs in a fresh sub-agent that "isn't swayed by the reasoning that produced the code". A second session is "the easiest independent reviewer you can get".
- The docs warn: "A reviewer that's asked to find problems will always find *something*". If you fix every finding you end up with extra abstraction, so the review prompt should say "skip style".
- Delegation: "Handing the same task to a subagent doesn't make the answer any better", and a fresh sub-agent "can end up *slower*" because it first has to gather context.
- Run `/clear` between unrelated tasks, because a session holding several tasks re-reads all of them on every turn. Instructions given only in conversation "can get lost when the conversation compacts". Anything that matters belongs in a deny rule, a hook or CLAUDE.md.
- Parallel work: one worktree per session. Worktrees of sub-agents that make no changes are removed. Leftover sub-agent and background worktrees are swept after `cleanupPeriodDays` if they hold no work. `claude -p --worktree` runs must be cleaned up by hand.

**Agent teams** (https://code.claude.com/docs/en/agent-teams)
- Experimental and off by default.
- Teammates have their own context windows, share a task list and message each other. "The lead's conversation history does not carry over."
- Use them where parallel exploration adds value. "For sequential tasks, same-file edits, or work with many dependencies, a single session or subagents are more effective."
- Recommendations: "Start with 3-5 teammates", "5-6 tasks per teammate", "Two teammates editing the same file leads to overwrites", and start with research and review rather than implementation.
- Limitations: in-process teammates do not survive session resume, task status can lag, and only the lead can manage the team.

**Costs** (https://code.claude.com/docs/en/costs)
- "Agent teams use approximately 7x more tokens than standard sessions when teammates run in plan mode."
- Advice: keep teams small, keep spawn prompts focused, and shut teammates down when they are done.

**Memory and compaction** (https://code.claude.com/docs/en/memory, https://code.claude.com/docs/en/context-window)
- Keep each CLAUDE.md under 200 lines. Imports don't reduce context cost.
- Auto memory is shared across all worktrees of a repo, and only the first 200 lines or 25 KB load. It is not loaded into sub-agents, except forks.
- After compaction, the root CLAUDE.md, auto memory and the plan-mode plan are re-injected from disk. Path-scoped rules, nested CLAUDE.md files and instructions given only in conversation are summarised away.

**Sub-agents** (https://code.claude.com/docs/en/sub-agents)
- Each starts with "a fresh, isolated context window", unless it is a fork.
- Optional `isolation: worktree`, with automatic cleanup if nothing changed.
- Optional persistent per-agent `memory` (project scope recommended). Agents can be resumed by name or ID with SendMessage.

*Implication for a mix of agents and humans:* Anthropic's own guidance supports short, focused sessions that keep their state in files (plan, progress notes, a short CLAUDE.md, issues) over one long main session. Use parallel agents mainly for research and review, and give each writer its own files. A long-lived "area agent" is fine as long as its memory lives on disk and is re-read, not carried in the transcript.

## 2. The opposite view: Cognition

**"Don't Build Multi-Agents"**, Walden Yan, 12 June 2025 (https://cognition.com/blog/dont-build-multi-agents)
- Principles: share context, meaning "full agent traces, not just individual messages"; and every action carries implicit decisions.
- Flappy Bird example: two sub-agents built a background and a bird in mismatched styles, which then had to be reconciled.
- Recommendation: a single-threaded linear agent, with a compression model for long histories. They call compression "hard to get right".
- On Claude Code at the time, they describe its sub-agents as a "purposefully simple approach": the sub-agent answers a question but doesn't write code in parallel.

**"Multi-Agents: What's Actually Working"**, Walden Yan, 22 April 2026 (https://cognition.com/blog/multi-agents-working)
- What works: setups where "writes stay single-threaded" while several agents contribute analysis; clean-context review loops, where the reviewer catches bugs the coder misses, partly because it avoids context rot; escalating hard cases to a stronger model; and manager/child "map-reduce-and-manage" delegation.
- What doesn't: parallel-writer swarms with conflicting implicit decisions, and unstructured swarms ("mostly a distraction"). Child agents assume shared state, and managers trained on small tasks over-prescribe.
- The goal is "a coordinated system that scales human taste", not "a swarm of autonomous actors".
- Company-reported figure: Devin Review finds about 2 bugs per PR, about 58% of them severe.

*Implication for a mix of agents and humans:* "One agent per area" fits Cognition's rule only if each area has a single writer and areas rarely touch the same files. Cross-area decisions must be written down where every agent reads them (decision log, issues). Otherwise the agents make conflicting implicit decisions.

## 3. Practitioners

**Simon Willison, "Embracing the parallel coding agent lifestyle"**, 5 Oct 2025 (https://simonwillison.net/2025/Oct/5/parallel-coding-agents/)
- Parallel agents work for research and proofs of concept, codebase explanations, small maintenance, and directed work he has specified himself.
- "Code that started from your own specification is a lot less effort to review."
- "the natural bottleneck on all of this is how fast I can review the results". He can land "one significant change at a time".
- He uses fresh checkouts rather than worktrees, and wants agents in containers.

**Simon Willison, "Vibe engineering"**, 7 Oct 2025 (https://simonwillison.net/2025/Oct/7/vibe-engineering/)
- Agents amplify existing engineering practice: a stable test suite, planning in advance, documentation, version control habits, CI and linting, a culture of code review, management skills (clear instructions and feedback), manual QA, preview environments, and judgement about what to hand to an agent.

**Mitchell Hashimoto, "My AI Adoption Journey"**, 5 Feb 2026 (https://mitchellh.com/writing/my-ai-adoption-journey)
- He runs one agent at a time: "I'm not [yet?] running multiple agents". Parallel runs happen only in the last 30 minutes of the day, on research, vague ideas and issue triage, and those agents write reports only.
- "Harness engineering": after each agent mistake, add an AGENTS.md line or a tool "such that the agent never makes that mistake again".
- He turns off agent notifications so he decides when to look, and he reviews everything.

**Armin Ronacher, "Agentic Coding Recommendations"**, 12 June 2025 (https://lucumr.pocoo.org/2025/6/12/agentic-coding/)
- Fast, observable tools ("Crashes are tolerable; hangs are problematic"), logs written to files, simple explicit code, and conservative upgrades.
- Parallelism raises throughput, but shared state (database, file system) is the unsolved obstacle.

**Kent Beck, "Augmented Coding: Beyond the Vibes"**, 25 June 2025 (https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes)
- TDD, a `plan.md` the agent follows test by test, and structural and behavioural commits kept separate.
- Warning signs: loops, unrequested functionality, and cheating such as disabling or deleting tests.
- When it stalled under accumulated complexity, he intervened in the design himself.

**Addy Osmani, "The Orchestration Tax"**, 24 May 2026 (https://addyosmani.com/blog/orchestration-tax/)
- "running multiple agents does not mean there is more of you."
- Human review is the serial step. The parallel agent limit is "for most of us … a low single digit".
- Practices: sort isolated tasks (background agents, final check only) from judgement-heavy ones (don't parallelise), batch reviews, let agents prove routine correctness, and "Only spend the lock on judgement".

**Spec-first tooling**
- GitHub Spec Kit (https://github.com/github/spec-kit): constitution → specify → plan → tasks → implement, with each step reviewed.
- OpenSpec (https://github.com/Fission-AI/OpenSpec): a change folder per proposal (`proposal.md`, `design.md`, `tasks.md`, spec deltas), archived after apply. It describes itself as "built for brownfield". The README recommends clearing context before implementation.
- Birgitta Böckeler, "Understanding Spec-Driven-Development: Kiro, spec-kit, and Tessl", 15 Oct 2025 (https://www.martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html):
  - "I'd rather review code than all these markdown files". Kiro turned a small bug into 16 acceptance criteria, "like using a sledgehammer to crack a nut".
  - Agents still ignored the spec, for example duplicating existing classes. Specs can give a false sense of control.
  - She favours spec-first with small iterative steps, and warns that spec-as-source might combine the downsides of model-driven development and LLMs.

*Implication for a mix of agents and humans:* Cap parallelism at the human's review capacity, not at the number of open topics. Give agents work that is specified and verifiable. Feed every mistake back into AGENTS.md or tooling. Keep specs as short as the change allows.

## 4. Other vendors: OpenAI Codex, GitHub Copilot, Devin

**OpenAI Codex best practices** (https://learn.chatgpt.com/guides/best-practices, redirected from developers.openai.com/codex/learn/best-practices)
- Prompts state goal, context, constraints and "done-when".
- Use "one chat per coherent unit of work", not "one chat for an entire project".
- Keep AGENTS.md short and add rules when mistakes repeat.
- Avoid "Running live tasks on the same files without using Git worktrees".
- Use sub-agents for "exploration, tests, or triage" while the main agent stays focused.

**GitHub Copilot cloud agent** (https://docs.github.com/en/copilot/tutorials/coding-agent/get-the-best-results)
- The issue is the prompt: problem, "Complete acceptance criteria", and the files involved.
- Start with bugs, UI tweaks, tests and docs. Keep complex cross-cutting, sensitive, ambiguous and learning tasks for humans.
- Iterate through batched PR review comments.

**Devin** (https://docs.devin.ai/essential-guidelines/when-to-use-devin)
- "if a task would take you three hours or less, Devin can most likely do it"; split larger work into sessions.
- Clear success criteria (tests, CI). Run independent tasks in parallel. Use automated review before human review.

*Implication for a mix of agents and humans:* All three vendors converge on one task (or issue) per thread, tasks of a few hours at most with written acceptance criteria, and an issue as the hand-off format. That supports moving coordination to GitLab issues: an issue is a brief that does not depend on any session's memory.

## 5. Open-source policies on AI contributions

- **EOSC Data Commons** (https://github.com/EOSC-Data-Commons/ai-policy)
  - AI is allowed for generation and review. Contributors "MUST disclose" the model, version and prompt in the PR.
  - "You MUST be able to explain what your changes do"; "You accept full responsibility".
  - One clear scope per PR, with soft limits of 2,000 changed lines or 10 files.
  - "Fully unsupervised agentic tools" are not allowed.
  - Agent-generated plans don't go in the code PR; they may go in a separate plan-only PR.
- **LLVM** (https://llvm.org/docs/AIToolPolicy.html)
  - "there must be a human in the loop", and contributors read and review all LLM output before asking others to.
  - "a contribution should be worth more to the project than the time it takes to review it". Maintainers can label a PR `extractive`.
  - An `Assisted-by:` trailer is suggested. Agents acting in project spaces without human approval are banned. AI must not be used on "good first issue" tickets.
- **Linux kernel**
  - https://docs.kernel.org/process/coding-assistants.html: "AI agents MUST NOT add Signed-off-by tags". The human takes full responsibility. Bug reports must state what could not be built or tested.
  - The same document says fixes written "in the same session as used to find the bug will generally lead to better and more accurate fixes".
  - Source of generated-content.rst read via https://docs.kernel.org/_sources/process/generated-content.rst.txt: disclose tools, prompts (or a summary of them for long sessions), affected portions and testing; "expect additional scrutiny in proportion to how much of it was generated"; if you cannot defend it, "do not submit".
- **curl** (https://curl.se/dev/contribute.html)
  - AI-assisted code is accepted under the same standards. AI-assisted bug finding must be disclosed.
  - Fabricated security reports lead to an immediate ban. "if someone can spot that the contribution was made with the help of AI, you have more work to do."
- **QEMU** (https://www.qemu.org/docs/master/devel/code-provenance.html): declines AI-generated content because its copyright and licence status is unsettled. Research and debugging uses are allowed.
- **Gentoo** (https://wiki.gentoo.org/wiki/Project:Council/AI_policy): council vote of 14 April 2024 forbids NLP-AI-assisted contributions, on copyright, quality and ethics grounds.
- **NetBSD** (https://www.netbsd.org/developers/commit-guidelines.html): LLM-generated code "is presumed to be tainted code" and needs prior written approval from core.

*Implication for a mix of agents and humans:* A curated upstream series should consist of small, single-scope commits that a human has read and can defend. Each disclosed (Assisted-by or similar, plus a prompt summary) and states how it was tested. Agent plans go into a separate design MR, if anywhere. A private GitLab with agent-driven issues is compatible with this only if the upstream series is rebuilt and owned by a human. QEMU, Gentoo and NetBSD will not take it at all.

## 6. Empirical evidence

**METR, early 2025** (https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)
- 16 experienced developers, 246 real issues in large repositories they knew.
- Allowing AI made tasks take 19% longer. Developers expected a 24% speedup beforehand and afterwards still believed in 20%.

**METR, late 2025 follow-up** (https://metr.org/blog/2026-02-24-uplift-update/)
- 57 developers, 800+ tasks.
- Estimates: −18% (CI −38% to +9%) for returning developers, −4% (CI −15% to +9%) for new ones. Negative means a speedup.
- METR calls this very weak evidence because of selection effects: 30–50% of developers withheld tasks they didn't want to do without AI. Time tracking also breaks down for developers who run several agents at once.

**Faros AI telemetry, 2025** (https://www.faros.ai/blog/ai-productivity-paradox-report-2025)
- More than 10,000 developers in 1,255 teams; correlational data.
- High-adoption teams complete 21% more tasks and merge 98% more PRs, but PR review time rose 91% and PR size 154%, with 9% more bugs per developer.
- "no significant correlation between AI adoption and improvements at the company level."

**Failed agentic PRs** (https://arxiv.org/abs/2601.15195, MSR 2026, 33k PRs)
- Docs, CI and build PRs merge best; performance and bug-fix PRs merge worst. Unmerged PRs are larger and touch more files.
- Reasons for rejection: lack of reviewer engagement, duplicate PRs, unwanted features, and agent misalignment.

**Multi-agent coordination**
- CooperBench (https://arxiv.org/abs/2601.13295): two coding agents implementing compatible features achieve "on average 30% lower success rates" than one agent doing both. Causes are jammed, vague communication, broken commitments and wrong expectations about the other agent.
- "Do More Agents Help?" (https://arxiv.org/abs/2606.05670): on ten benchmarks with GPT-4.1, five of six multi-agent workflows trailed a single-agent baseline by 1.7–8.8 points, often at higher token cost.
- MAST, "Why Do Multi-Agent LLM Systems Fail?" (https://arxiv.org/abs/2503.13657): 14 failure modes in 3 groups (system design or specification, inter-agent misalignment, task verification), from 1,600+ traces of 7 frameworks.

**Self-review vs independent review**
- Huang et al., ICLR 2024 (https://arxiv.org/abs/2310.01798): "LLMs struggle to self-correct their responses without external feedback", and sometimes get worse.
- Panickssery et al. 2024 (https://arxiv.org/abs/2404.13076): LLM evaluators recognise and favour their own output.
- Guey & Bougault 2026 (https://arxiv.org/abs/2606.20093): with a deterministic checker, authors rejected valid fixes no more often than fresh models (−5.1 pp, CI −12.9 to +2.7). Self-preference was weak or absent.
- Jin & Chen 2026 (https://arxiv.org/abs/2603.00539): LLM reviewers "frequently misclassify correct code implementation as non-compliant". Asking for explanations and fixes raises false positives. The proposed mitigation is to run the proposed fix against tests.

*Implication for a mix of agents and humans:* Use multi-agent setups for exploration and review, not for writers coordinating with each other. Treat an independent review as a filter that needs tests or a human to confirm it, not as a verdict. Measure your own throughput as merged and reviewed changes, not as agent-hours.

---

## Disagreements and open questions

- **Multi-agent: helps or hurts?** Anthropic reports large gains for research, and Claude Code ships agent teams. Cognition (2025), CooperBench and the "Do More Agents Help?" paper find that coordination between writers costs accuracy. Everyone agrees on the narrower point: parallel readers and reviewers, a single writer per piece of code.
- **Fresh reviewer vs same context.** Anthropic's docs and Cognition (2026) favour a clean-context reviewer. The kernel document says fixes written in the same session that found the bug are better. Guey & Bougault find little self-preference in authors when a checker decides. A plausible reconciliation, not proven: keep finding and fixing in one context, and review in another.
- **How much to trust LLM review.** Cognition reports about 2 real bugs per PR from Devin Review (vendor figure). Jin & Chen find systematic over-flagging of correct code, and Anthropic warns that a reviewer "will always find *something*". No source gives a precision figure for in-house agent review.
- **Specs.** Willison, Copilot and Anthropic say specs make review cheaper. Böckeler finds heavy spec frameworks costly to review and sometimes ignored. Nobody has measured where the break-even lies.
- **Context windows.** Anthropic's 2026 docs say running out of context is "rare" with 1M windows. Its own context-engineering post, Cognition and Osmani stress context rot and loss of detail when context is summarised. Bigger windows reduce compaction but not the accumulation of unrelated tasks; the docs themselves recommend `/clear` between tasks.
- **Long-lived area agents.** No source evaluates persistent per-area agents directly. Closest are Anthropic's long-running harness (state in files, one feature per session), sub-agent persistent memory, and the agent-teams limitation that teammates do not survive resume. All of this suggests "area" should mean a memory file plus an issue label, not one session that never ends.
- **Productivity.** METR's early-2025 RCT showed a slowdown; its late-2025 data suggest a speedup that METR cannot measure reliably. Faros finds team-level output up and company-level delivery flat. There is no controlled evidence on many agents per human.
- **Policy split.** Most projects allow AI with disclosure and human accountability. QEMU, Gentoo and NetBSD reject it on copyright grounds, which is still legally unsettled.

## Not verified

These were seen only in search results or could not be fetched, so they are not cited above.

- Steve Yegge, "Welcome to Gas Town" (Medium, steve-yegge.medium.com/welcome-to-gas-town-4f25ee16dd04): fetch returned HTTP 403. The roles (Mayor, Polecats, Refinery, …), the Beads issue tracker, agent counts and cost figures are known only from secondary coverage.
- Addy Osmani, "Your AI coding agents need a manager" (addyosmani.com/blog/coding-agents-manager/) and "The Code Agent Orchestra" ("One File, One Owner"): not fetched.
- Faros AI 2026 "Acceleration Whiplash": figures such as PR review time +441% and 31% of PRs merged without review appeared only in search snippets.
- DORA 2025 "State of AI-assisted Software Development" report (services.google.com PDF): not fetched. Secondary sources say AI improves throughput but increases instability.
- Linux kernel `Assisted-by: AGENT_NAME:MODEL_VERSION` tag: search results attributed it to some docs.kernel.org versions (7.x), but the current `coding-assistants.rst` I fetched contains no such tag. Check the target kernel version.
- The 14 MAST failure-mode names, for example "Fail to Ask for Clarification": the abstract page I read does not list them.
- Other AIDev-based acceptance-rate papers (arXiv 2602.08915, 2602.02345, 2602.12144, 2601.18749): snippets only.
- The Stanford paper on single-agent vs multi-agent under matched compute: not located.
- OpenInfra AI policy ("Assisted-By" label) and the 2026 arXiv surveys of OSS AI policies (2609.07542, 2609.07919): snippets only.
