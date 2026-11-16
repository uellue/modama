# Humans and LLM agents: cognitive similarities and differences for organising agent work

Research note, 2026-11-16. I fetched and read every source cited below in this run. For most papers that means the abstract page only; where I read only the abstract, the text says so. Quotes are marked and kept short.

## Summary for people

- Long contexts hurt LLMs as overload hurts people, but in a different way. A model has no fixed number of slots. Accuracy drops as the input grows, and drops further when the relevant fact sits in the middle, uses different words from the question, or has similar distractors around it. Many benchmarks show this.
- Compaction (summarising the session) mostly works when the goal is fixed and the state is on disk. It silently drops constraints, though: rules on how to work and what not to do. Two 2026 studies measure this directly, and it matches the mistakes you see after many summaries.
- LLMs, like people, go along with what they are handed (sycophancy, anchoring) and rate their own work too highly. Without outside feedback, self-correction is unreliable. Independent critics, tests and tools do help.
- Multi-agent setups help on tasks that split into independent parts and hurt on sequential, tightly coupled work. Most of the gain comes from separate clean context windows and more tokens, not from personas.
- Persona prompts ("you are an expert …") do not reliably improve accuracy. Specialist agents are worth having to narrow context, tools and responsibility, not for the label.
- Human practices that carry over: written handovers, knowing who knows what, independent review, small tasks with clear boundaries, checks outside the worker. What is new: agents can be copied, forked and restarted cheaply, so fresh eyes cost almost nothing, but agents build up no tacit experience.

## 1. Working memory and attention

**Humans.** Miller (1956) argued that the span of immediate memory is limited by the number of chunks, not by the information in them, and that recoding into larger chunks raises effective capacity. Quote: "The span of immediate memory seems to be almost independent of the number of bits per chunk" (https://psychclassics.yorku.ca/Miller/).

Cowan (2001, *Behavioral and Brain Sciences* 24) argued for a smaller limit. Abstract: "A single, central capacity limit averaging about four chunks is implicated". He calls Miller's seven "more as a rough estimate and a rhetorical device" (https://memory.psych.missouri.edu/assets/doc/articles/2001/cowan-bbs-2001.pdf; https://www.cambridge.org/core/journals/behavioral-and-brain-sciences/article/magical-number-4-in-shortterm-memory-a-reconsideration-of-mental-storage-capacity/44023F1147D4A1D44BDC0AD226838496).

Ericsson & Kintsch (1995) proposed long-term working memory. Experts encode into long-term memory using retrieval structures. This widens working memory within their domain and makes it robust to interruption. I read this only through a summary (https://www.jimdavies.org/summaries/ericsson1995.html), which cites one finding: interruptions while reading add reading time but do not reduce comprehension.

**LLMs.** Quality degrades with length and clutter:
- *Lost in the Middle* (Liu et al., TACL; https://arxiv.org/abs/2307.03172): performance is best when the relevant information is at the start or end of the context, and it falls when the information is in the middle, even for long-context models.
- *RULER* (Hsieh et al., COLM 2024; https://arxiv.org/abs/2404.06654): 17 models, 13 tasks. Plain needle-in-a-haystack is nearly perfect, yet "only half of them can maintain satisfactory performance at the length of 32K".
- *NoLiMa* (Modarressi et al., ICML 2025; https://arxiv.org/abs/2502.05167): the test uses needles with little word overlap with the question. "At 32K, for instance, 11 models drop below 50% of their strong short-length baselines". GPT-4o falls from 99.3% to 69.7%.
- Chroma, *Context Rot* (Hong, Troynikov, Huber, technical report, July 2025; https://www.trychroma.com/research/context-rot): 18 models. Performance falls faster when the needle is less similar to the question, and distractors hurt. On LongMemEval, every model did better with a focused prompt of about 300 tokens than with the full one of about 113k. Quote: "LLMs do not maintain consistent performance across input lengths."
- Laban et al. (https://arxiv.org/abs/2505.06120, preprint): over 200,000 simulated conversations. Splitting a task over several turns costs 39% on average, mostly as unreliability: models commit early and attempt a solution too soon. Quote: "when LLMs take a wrong turn in a conversation, they get lost and do not recover".

**Compaction.**
- Anthropic's guide (https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents, vendor) warns: "overly aggressive compaction can result in the loss of subtle but critical context".
- Salle et al., *Benchmarks Are Surprisingly Compaction-Friendly* (https://arxiv.org/abs/2610.31778, preprint, Oct 2026):
  - For two models with 1M-token contexts, the compaction threshold had no measurable effect on scores, and no method beat default self-summarisation.
  - However: "Compaction can, however, silently remove task constraints". On ProgramBench, the first summary already removed about a third of the anti-cheating rules, and losses grew with each further compaction.
  - In real sessions (SWE-chat), instructions on how to work or what to avoid were dropped about six times more often than specifications of what to build.
  - The authors' reason why benchmarks cope: the objective is fixed and progress is on disk.
- Wang et al., *Lost in Context Compaction* (https://arxiv.org/abs/2608.11242, preprint, 2026):
  - Compactors kept about 17% of injected side constraints on average.
  - An inbox agent deleted e-mails without approval in 30 of 100 sessions after compaction, and in 0 before.
  - Storing constraints separately and re-appending them after compaction raised retention above 90%.
- ACON (https://arxiv.org/abs/2510.00615, ICML 2026 per the arXiv page): compression guidelines tuned from failure analysis cut peak tokens by 26–54% and improved success.

**Strength.** Degradation with length is strong and replicated. Constraint loss under compaction comes from two independent 2026 preprints that agree with each other.

**Implication for organising work:** keep each agent's context short and on one topic. Keep constraints in files that agents re-read, not only in the conversation that the next summary rewrites.

## 2. Memory

**Humans.** Schacter (1999, *American Psychologist*; https://sites.harvard.edu/schacter-memory/files/2022/09/schacter1999.pdf) sorts memory errors into seven "sins": transience, absent-mindedness, blocking, misattribution, suggestibility, bias and persistence. He argues they are "by-products of otherwise adaptive features of memory". Recall is reconstructive: "Bias refers to the distorting influences of present knowledge, beliefs, and feelings on recollection of previous experiences."

**Agents.** Agents have no memory between sessions except files. The Claude Code docs (https://code.claude.com/docs/en/memory, vendor) say:
- "Each Claude Code session begins with a fresh context window."
- Auto memory loads "the first 200 lines of `MEMORY.md`, or the first 25KB".
- Instructions are "context, not enforced configuration".
- When instructions contradict each other, Claude may follow either one, arbitrarily.
- CLAUDE.md files over 200 lines reduce adherence, and rules that must always hold belong in hooks.

MemGPT (https://arxiv.org/abs/2310.08560) models agent memory on operating-system paging between memory tiers.

Evidence on memory files:
- Gloaguen et al., *Evaluating AGENTS.md* (https://arxiv.org/abs/2602.11988, preprint): "providing context files does not generally improve task success rates". Cost rises by "over 20%". Agents do follow the files. Repository overviews do not help; the files are useful for non-standard practices.
- Anthropic, *Effective harnesses for long-running agents* (https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents, vendor, Nov 2025):
  - Compaction alone was not enough for work spread over many sessions.
  - What worked: a progress file, git history, and a JSON feature list in which agents may only change a `passes` field. JSON was chosen because models are less likely to overwrite it than Markdown.
  - Each fresh session first reads the git log and progress notes and runs an end-to-end test.
  - Failure modes: trying too much at once, declaring victory early, and marking features done without testing.

**Strength.** Human memory research is well established. For agent memory files there is one preprint plus vendor experience, and the effects are small.

**Implication for organising work:** memory files serve as instructions and indexes, not as experience. Keep them short and free of contradictions, and put what matters in checkable artifacts (tests, feature lists, git).

## 3. Biases and self-correction

**Humans.** Nickerson (1998, *Review of General Psychology* 2; https://pages.ucsd.edu/~cmckenzie/nickersonConfirmationBias.pdf) defines confirmation bias as "the seeking or interpreting of evidence in ways that are partial to existing beliefs, expectations, or a hypothesis in hand".

**LLMs.**
- **Sycophancy.** Sharma et al. (Anthropic; https://arxiv.org/abs/2310.13548, preprint): "sycophancy is a general behavior of state-of-the-art AI assistants". Human preference data favours answers that match the user's view.
- **Anchoring.** Lou & Sun (https://arxiv.org/abs/2412.06593, preprint, abstract only): answers move with biased hints. Chain-of-thought, telling the model to ignore the anchor, and reflection were not enough; hints from several perspectives helped.
- **Self-preference.** Panickssery, Bowman & Feng (https://arxiv.org/abs/2404.13076, preprint): GPT-4 and Llama 2 recognise their own outputs better than chance, and the stronger the self-recognition, the stronger the self-preference (linear correlation).
- **Correlated errors.** Kim et al. (ICML 2025; https://arxiv.org/abs/2506.07962), over 350 LLMs: "models agree 60% of the time when both models err". Errors correlate more for models from the same developer or architecture, and for more accurate models.
- **Self-correction.** Huang et al. (ICLR 2024; https://arxiv.org/abs/2310.01798): "LLMs struggle to self-correct their responses without external feedback, and at times, their performance even degrades". Kamoi et al. (TACL 2024; https://arxiv.org/abs/2406.01297): "no prior work demonstrates successful self-correction with feedback from prompted LLMs". Self-correction does work with reliable external feedback or after fine-tuning.
- **What helps.** Self-Debugging (https://arxiv.org/abs/2304.05128): up to 12% gain with unit-test or execution feedback, against 2–3% without. CRITIC (ICLR 2024; https://arxiv.org/abs/2305.11738) stresses "the crucial importance of external feedback".

**Strength.** Sycophancy and the failure of self-correction without feedback are well supported. Self-preference, correlated errors and anchoring each rest on one study.

**Implication for organising work:** give reviewers the artifact and a question, not the author's hypothesis. Let tests and tools be the final judge. A reviewer on the same model catches errors that come from the author's context, but it shares the model's systematic errors.

## 4. Multi-agent evidence

- **Debate.** Du et al. (https://arxiv.org/abs/2305.14325): debate "significantly enhances mathematical and strategic reasoning". Smit et al. (https://arxiv.org/abs/2311.17371) disagree: debate systems "in their current form, do not reliably outperform other proposed prompting strategies". Results depend heavily on settings.
- **Failures.** Cemri et al. (https://arxiv.org/abs/2503.13657, preprint): over 1,600 traces from 7 frameworks, 14 failure modes in 3 categories (system design, inter-agent misalignment, task verification), with high annotator agreement (kappa 0.88). Gains over a single agent are often minimal.
- **When it helps.** Kim et al., *Towards a Science of Scaling Agent Systems* (https://arxiv.org/abs/2512.08296; blog https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/):
  - Results range from +80.8% on decomposable financial reasoning to −70.0% on sequential planning.
  - Quote: "architecture-task alignment determines collaborative success".
  - Per the blog, errors grow up to 17.2x with independent agents against 4.4x with a central orchestrator.
  - The blog and the abstract report different configuration counts and R².
- **Anthropic** (https://www.anthropic.com/engineering/multi-agent-research-system, vendor, internal eval):
  - The multi-agent system beat single-agent Opus 4 by 90.2%, at about 15x the tokens of a chat.
  - Token usage alone explained 80% of the variance in performance.
  - It fits poorly where agents must "share the same context", and "most coding tasks" have fewer parts that can run in parallel.
  - Vague briefs led to duplicated work.
- **Cognition** (https://cognition.com/blog/dont-build-multi-agents, vendor opinion): recommends a single-threaded agent by default, because "actions carry implicit decisions" and parallel subagents make conflicting ones.

**Strength.** Mixed but converging. Multi-agent helps on parallel, loosely coupled work and hurts on sequential work. The large gains come from vendor-internal evaluations.

**Implication for organising work:** split work by how independent the parts are, not by job title. Keep tightly coupled design and implementation in one thread, with one owner who integrates and verifies.

## 5. Specialisation

**Persona prompting.**
- Zheng et al. (Findings of EMNLP 2024; https://arxiv.org/abs/2311.10054): 162 roles and 2,410 questions. No improvement over no persona. Quote: "the effect of each persona can be largely random". Picking the best persona automatically was no better than random.
- Basil et al., *Playing Pretend* (https://arxiv.org/abs/2512.05858): "Across both benchmarks, persona prompts generally did not improve accuracy relative to a no-persona baseline." Low-knowledge personas hurt.
- Kong et al. (NAACL 2024; https://arxiv.org/abs/2308.07702) found the opposite for zero-shot reasoning with ChatGPT: AQuA rose from 53.5% to 63.8%. They frame role-play as an implicit chain-of-thought trigger.
- Dong et al., *Self-collaboration* (TOSEM; https://arxiv.org/abs/2304.07590): an analyst, coder and tester setup "relatively improves 29.9%-47.1% Pass@1" over a single agent. The design mixes roles with extra steps and test feedback, so it does not isolate the effect of the role.

**Human expertise.**
- Ericsson et al. (1993; https://stafforini.com/works/ericsson-1993-role-deliberate-practice/): expert performance is "the result of intense practice extended for a minimum of 10 yrs".
- Macnamara et al. (2014, meta-analysis; https://www.psychologie.uzh.ch/dam/jcr:658d39fe-2f4b-467f-9ae2-ffeb25caf2b6/McNamara.PsychSci.25.2014.pdf): deliberate practice explains 26% of performance differences in games, 21% in music, 18% in sports, 4% in education and "less than 1% for professions".
- Transactive memory: "This capacity for remembering who knows what is the key to transactive memory" (Wegner, https://dtg.sites.fas.harvard.edu/DANWEGNER/wjh/tm.htm).
- DeChurch & Mesmer-Magnus (2010, *J. Applied Psychology*, meta-analysis of 65 studies; https://atlas.northwestern.edu/papers/underpinningsTeamwork.pdf): team cognition, including transactive memory, relates strongly to team performance, and its value "manifests over time, in repeated interactions".

**Strength.** Two independent studies show that personas do not improve accuracy. I found no study that separates a narrow role from a smaller, relevant context, so that question remains open. In human teams, specialisation pays off through accumulated practice and repeated interaction, which agents do not have across sessions.

**Implication for organising work:** define specialist agents by what they load (area docs, constraints, tools, permissions) and what they are responsible for, not by a persona sentence. Keep an explicit map of which file or agent definition holds what.

## 6. What is new with agents

- **Fresh and forked agents.** Claude Code subagents "run in its own context window" and return "only the summary". A fresh one "doesn't see your conversation history". A fork "inherits the parent conversation instead of starting fresh". Worktree isolation gives each agent its own copy of the repository. The docs advise staying in the main conversation when phases share a lot of context (https://code.claude.com/docs/en/sub-agents).
- **Restarting from a brief.** The harness post above shows a project carried through many fresh sessions using a progress file and git. Each session is like a new hire with a perfect handover and no experience.
- **Tokens and parallelism.** About 15x the tokens of a chat, and tokens explain 80% of the variance (Anthropic). A subagent may use "tens of thousands of tokens" while working but returns "often 1,000-2,000 tokens" (context-engineering guide). Separate context windows also reduce path dependency.
- **Context engineering** is defined as "the set of strategies for curating and maintaining the optimal set of tokens" (Anthropic). Cognition's counterpoint: a brief never carries the full context, so splitting work loses implicit decisions.

**Strength.** Mostly vendor documentation and experience reports, consistent with the independent long-context and compaction studies.

**Implication for organising work:** fresh agents are cheap but start with little context. Invest in handover artifacts (brief template, progress file, constraint file), and use fresh instances for review and for any task whose context would otherwise rot.

## Similarities

- Limited effective attention: about four chunks for humans; degradation with length and distractors for LLMs.
- Confirmation-type biases: human confirmation bias and anchoring; LLM sycophancy, anchoring, and adopting the brief's framing.
- Lenient self-assessment in both. Independent review and external checks help both.
- Early commitment that is hard to undo, in people and in LLMs that get lost after a wrong turn in a conversation.
- Teams benefit from knowing who knows what, and suffer from misaligned assumptions.
- Memory is lossy and reconstructive: human recall is biased by present knowledge; compaction summaries are rewritten and selectively lose content.

## Differences

- Agents have no slot limit. Degradation is gradual and depends on position and similarity, and the context can be inspected and edited.
- No consolidation or learning between sessions: no long-term working memory and no deliberate practice. Expertise exists only in files and model weights.
- Compaction drops constraints about six times more often than goals.
- Copying, forking, restarting, running parallel instances and isolating them in worktrees are cheap, so fresh eyes are nearly free.
- Copies of the same model make correlated errors (60% agreement when both are wrong), so a team of copies is less diverse than a team of people.
- Role labels change little for agents, while human roles carry real, accumulated competence.
- Cost scales with tokens, not hours. The human's attention is the bottleneck, and every added agent draws on it.

## Not verified

- Ericsson & Kintsch (1995): I read only the jimdavies.org summary, not the original. Gobet's critique appeared only in search results.
- Wegner (1987) chapter and Lewis & Herndon (2011, *Organization Science*): the copy I found returned 404.
- Cowan (2010), "The Magical Mystery Four" on PMC: blocked by a captcha.
- Macnamara & Maitra (2019) replication of Ericsson et al.: search snippets only.
- The "~45% capability saturation" threshold in Kim et al. (2512.08296): only in secondary summaries, not in the abstract I read.
- arXiv 2601.20404 (effect of AGENTS.md files on efficiency), 2511.05766 (anchoring in LLMs), 2605.08580 (Slipstream), 2605.23296 (Parallel Context Compaction), and a "TRACE" compaction study: not fetched or snippets only.
- For most arXiv papers I read only the abstract page, so numbers beyond the abstracts were not checked.
