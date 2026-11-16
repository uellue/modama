# How human organisations structure work, and what transfers to a mix of coding agents and humans

Research note, 2026-11-16. Every source below was fetched in this run. Most are encyclopaedic overviews (Wikipedia). Where I could read them, I also used primary documents: IIA, WHO, the Google SRE book, kernel.org, GitHub docs, PEP 13, teamtopologies.com and Martin Fowler. Quotes are short and marked. Caveat: I read the pages through a summarising fetch tool, so check a quoted phrase against its URL before reusing it in print. The exception is the IIA PDF, whose text I extracted directly.

## Summary for people

- **Structure:** every structure trades specialisation against coordination cost. Matrix structures add a second line of authority, and the overviews name two failure modes: "accountability without control" and slow decisions.
- **Cognitive load:** Conway's law and Team Topologies agree that system boundaries follow communication boundaries and that cognitive load caps what a team can own. For an agent, the context window is that cognitive load, literally. One long main session over many areas hits this limit.
- **Coordination cost:** Brooks' law and span of control both say coordination cost grows faster than headcount. Cheap agent copies don't remove that cost. They move it to whoever integrates the work and decides, which here is the one human.
- **Checks:** separation of duties, maker-checker and the three lines model transfer well, because a second check by a fresh agent is cheap. The open problem is independence: the checker must not be briefed by the maker.
- **Briefs and handovers:** the closest fits are mission command (intent plus freedom of method), SBAR-style structured handovers, checklists, and the andon cord that lets any agent stop the work.
- **Memory:** transactive memory ("who knows what") and institutional memory exist for agents only as files. So the decision log, the issues and a maintainers file are the memory itself, not overhead.
- **Open source:** it shows a working model with a scarce top decider. Subsystem maintainers own areas, the top person directly picks about 1% of patches, and decisions are pushed down. Python's steering council is told to use its powers "as little as possible".

---

## 1. Organisational structures

**Idea.**
- Functional structures group people by specialism.
- Divisional (product) structures give each division one product or market, end to end.
- A matrix groups people by function and by product or project at once, so some people report to two managers.
- Project management texts place matrices on a scale of project-manager authority: weak (the PM coordinates), balanced, strong (the PM controls most resources), and finally projectized (the PM controls the budget; Wikibooks). The Wikipedia overview lists the weak, balanced and strong variants.

**Evidence and failure modes.**
- Functional specialisation gives "operational efficiency" but can make an organisation "slow and inflexible".
- Divisions can "support unhealthy rivalries" and duplicate resources.
- Matrices spread information across task boundaries faster but "increase the complexity of the chain of command", which leads to power struggles (Organizational structure).
- The matrix management article cites the case of DEC. The matrix was credited with DEC's innovation, then abandoned for having "sapped energy and efficiency" from product development.
- The same article cites Hall: "accountability without control" and influence without authority are the norm in matrix roles, and more cross-silo cooperation can bring bureaucracy and too many people in each decision.
- It also cites Galbraith: structures don't fail, management fails at implementing them.
- These claims rest on cited NYT articles and books that I did not verify.

**Transfers to agents?** Partly.
- A matrix in which an "area agent" and a "task agent" both direct the same work reproduces dual reporting. Agents tend to follow the latest or most forceful brief, so unclear authority turns into silent contradictions in the code rather than open conflict.
- What doesn't transfer is the cost of standing up a project team. Agents can be created per task (projectized) for almost nothing, so the "functional home" becomes files (area notes, conventions), not a standing agent.

## 2. Division of labour and specialisation

**Adam Smith and Taylor.**
- Smith's pin factory split pin making into "about eighteen distinct operations". Ten workers made about 48,000 pins a day, against fewer than twenty for one unspecialised worker.
- Smith also warned that repetitive work makes a worker "as stupid and ignorant as it is possible for a human creature to become" (Division of labour).
- Taylor's scientific management separated planning (managers) from doing (workers), standardised the "one best method", and used time studies.
- Critics cite the "destruction of craft skill" and workers reduced to an "automaton". Later schools (human relations, Toyota's "respect for people") brought worker judgement and suggestions back (Scientific management).

**Transfers to agents?**
- Taylor's split between planning and doing maps onto "the main session plans, the sub-agent executes".
- Deskilling and alienation don't apply to agents.
- The Taylorist failure that does apply is losing the doer's improvement suggestions. An agent working to a narrow brief won't report "this whole approach is wrong" unless the brief asks it to.

**Conway's law and the inverse Conway manoeuvre.**
- Conway (Datamation 1968, "How do Committees Invent?") wrote that organisations "are constrained to produce designs which are copies of the communication structures of these organizations".
- Wikipedia cites MacCormack, Rusnak and Baldwin: "strong evidence to support the mirroring hypothesis". It also cites a Microsoft case study and a FreeBSD study.
- Fowler (2022) describes the inverse manoeuvre as changing "the communication patterns of the designers to encourage the desired software architecture". He warns it "isn't all-powerful" for rigid existing systems, and that "the modular decomposition of a system and the decomposition of the development organization must be done together".

**Team Topologies.** There are four team types:
- stream-aligned: "aligned to a flow of work from (usually) a segment of the business domain"
- platform: provides "a compelling internal product to accelerate delivery by Stream-aligned teams"
- enabling: helps other teams past blockers
- complicated-subsystem: for "significant mathematics/calculation/technical expertise"

There are three interaction modes: collaboration (time-boxed), X-as-a-Service, and facilitation. Cognitive load is the design limit: "overloaded teams make poor decisions and move slowly" (teamtopologies.com key concepts). Fowler (2023) calls the platform idea "the bright insight": "The key benefit of a platform is that it reduces this cognitive load". He adds that the model is "designed explicitly recognizing the influence of Conways Law".

**Transfers to agents?** Strongly.
- An agent's context window is cognitive load in measurable form. A long session that spans many areas is the "overloaded team".
- Conway's law cuts both ways. If agents coordinate only through the main session, the architecture will tend to mirror one central hub. Area agents that communicate through issues and stable interfaces push the code towards modularity.
- For agents, the platform is tooling and docs that reduce what each agent must load. The enabling team is a skill or playbook, not a standing agent.

**Brooks' law.**
- "Adding manpower to a late software project makes it later." Brooks himself called it an "outrageous oversimplification".
- His reasons: ramp-up time, communication channels that grow combinatorially, and limited divisibility ("nine women can't make a baby in one month").
- Critiques: McConnell says adding people to late projects is common and he no longer believes the law holds in general. Berkun says labour isn't interchangeable.
- Named mitigations: modularity, and well-defined tasks such as QA or documentation (Brooks's law).

**Transfers to agents?**
- Ramp-up is cheap but not free: each agent must load context, and a bad brief gives it a bad start.
- Overhead between agents stays low only if they don't talk to each other freely and their areas are separate.
- The combinatorial cost moves to integration (merge conflicts, drifting conventions) and to the human who reads the results.

**Span of control.**
- Spans moved from about 1:4 to about 1:10 as hierarchies flattened. Davis (1951) suggested 3 to 8 reports for senior managers and up to 30 for first-line supervisors.
- Graicunas showed that possible relationships grow much faster than the number of reports.
- Wide spans work when tasks are similar and staff are capable. "information overload and span of control are positively correlated" (Span of control).

**Dunbar's number.**
- About 150 stable relationships (range 100 to 250), derived from primate brain-size regression.
- The 2021 re-analysis by Lindenfors et al. found "wildly different numbers", with confidence intervals of roughly 4 to 520, and concluded that no such limit can be derived this way.
- Field studies found a median network size around 231 (Dunbar's number).

**Transfers to agents?**
- The human's span of control is the binding limit: how many agent results one person can read, judge and decide on per day.
- The agent-to-agent limit is the briefing agent's context, not social bonds.
- Dunbar's number is about social grooming. It doesn't apply to agents, and its evidence is weak even for humans.

## 3. Checks and balances

**Separation of duties, four eyes, maker-checker.**
- Separation of duties means "having more than one person required to complete a task". Its aim is "the prevention of fraud and errors".
- Variants: sequential separation (two signatures), individual (four eyes), spatial, factorial.
- Four functions should be kept apart: authorization, custody, record keeping and reconciliation. For IT change control, that means separating requirements, authorization, development, review and deployment.
- Small organisations that can't separate duties fully use compensating controls: audit trails, exception reports, independent reviews (Separation of duties).
- The two-person rule appears in nuclear launch keys, bank vaults, cockpits and AWS multi-party approval. One limit: authentication isn't judgement (Two-person rule).
- Maker-checker is the banking form: "for each transaction, there must be at least two individuals necessary for its completion" (Maker-checker; a stub article).

**RACI and DACI.**
- The roles are Responsible, Accountable ("ultimately answerable"), Consulted (two-way communication) and Informed (one-way).
- Some theories require exactly one Accountable party per deliverable.
- DACI stands for Driver, Approvers, Contributors, Informed. Other variants include RASCI, RACIQ (adds quality review) and RACI-VSL (adds verifier and signatory).
- The article has no criticism section (Responsibility assignment matrix).

**COSO and the three lines model.**
- COSO gives "reasonable, not absolute, assurance" through five components: control environment, risk assessment, control activities, information and communication, monitoring.
- One named limit: management "may be in a position to override controls" (Internal control).
- The IIA Three Lines Model (2020) separates three roles. First line: management's delivery roles. Second line: risk, compliance and quality expertise, which provides "monitoring, and challenge". Third line: internal audit.
- Principle 5 reads: "Internal audit's independence from the responsibilities of management is critical to its objectivity, authority, and credibility". It rests on accountability to the governing body, "unfettered access", and freedom from interference.
- The model also says "independence does not imply isolation", and that the lines must coordinate to avoid "duplication, overlap, or gaps" (IIA PDF).

**Audit trails.** An audit trail is a chronological record serving as "documentary evidence of the sequence of activities". Ordinary users should not be able to reach or alter the logging (Audit trail).

**Transfers to agents?**
- Maker-checker transfers best, because the checker is cheap.
- The real risk is the one the IIA's Principle 5 names. A reviewer briefed by the maker, or by a main session that shares the maker's view, isn't independent, and agents tend to agree with whoever briefed them.
- In practice, independence means the reviewer gets the diff and the requirement, not the maker's reasoning, and reports to the human or the log, not to the maker.
- Management override applies too. The human or the main session can bypass review, so the bypass should be logged.
- Git history and the decision log are a ready-made audit trail, but only if agents cannot rewrite them.
- RACI carries over as "one accountable human per area". Agents can be Responsible but cannot be accountable.

## 4. Coordination under uncertainty

**Mission command (Auftragstaktik).**
- Orders give intent, constraints and the objective. Subordinates choose the method. Moltke: "A favourable situation will never be exploited if commanders wait for orders."
- Preconditions: trust (earned, with tolerance for mistakes), mutual understanding, shared doctrine.
- Documented problems: little tolerance for failure in practice, bureaucratic demands, and doctrine read differently by each commander. A 2025 study of NATO officers concluded that orders must be concise (Mission command).

**Transfers to agents?**
- A brief with the goal, why it matters, the constraints and what "done" means is commander's intent. It lets a sub-agent decide sensibly when the plan meets reality.
- "Trust earned over time" doesn't transfer. A fresh agent has no track record, so trust has to rest on checks (tests, review), not on the individual agent.

**Crew resource management (CRM).**
- CRM grew out of accidents such as United 173 (1978), where the crew ran out of fuel while troubleshooting, and out of a NASA workshop.
- It keeps the hierarchy but encourages juniors to challenge the captain. It trains decision making, assertiveness, communication and situational awareness.
- The evidence is mostly correlational, and success is "difficult to measure". TeamSTEPPS, its healthcare adaptation, is "not universally effective" (Crew resource management).

**Transfers to agents?**
- CRM targets everyone fixating on one problem while a critical variable runs out. For agents that is chasing a bug while the budget or scope drifts.
- The deference CRM fights shows up in agents as agreeing with whoever briefed them.
- What carries over is explicitly asking an agent to challenge the brief, or adding a separate devil's-advocate agent.

**WHO Surgical Safety Checklist.**
- 19 items at three pauses: before anaesthesia, before incision, and before the patient leaves the theatre. The team confirms items aloud against a written tool, not from memory. Local adaptation is encouraged (WHO safe surgery page).
- Wikipedia reports Haynes et al. 2009 (eight hospitals): complications fell from 11.0% to 7.0% and deaths from 1.5% to 0.8%.
- It also notes that some studies found no improvement. Rollouts failed where the checklist "just appeared" or staff understood "neither why nor how" to use it (WHO Surgical Safety Checklist).

**Transfers to agents?**
- Checklists at fixed pause points (before starting, before merging, before handing back) fit agents well, and agents run them faithfully every time.
- The implementation lesson transfers too: a checklist imposed without its reason gets ticked mechanically. Agents tick even more readily, so each item should be checkable (a command that passes), not an attestation.

**High-reliability organisations (Weick and Sutcliffe).**
- Five principles: preoccupation with failure, reluctance to simplify, sensitivity to operations, commitment to resilience, and deference to expertise (in a crisis, authority moves to whoever has the expertise).
- The counter-position is Perrow's Normal Accident Theory: in tightly coupled, complex systems, accidents are inevitable.
- The Wikipedia article is tagged as reading like an essay (High reliability organization).

**Toyota Production System, kaizen, andon.**
- The TPS principles are jidoka ("automation with a human touch": stop when a problem occurs), just-in-time, genchi genbutsu ("go to the source to find the facts"), and respect for people.
- "Standardized tasks are the foundation for continuous improvement". Copying the visible practices, such as low inventory, without the underlying concept is cited as a reason adoptions failed (Toyota Production System).
- Kaizen means small improvements by everyone, run in Plan-Do-Check-Act cycles (Kaizen).
- The andon gives "a non-management (production line) worker the authority to stop the production line". At Toyota the first pull calls the team leader, and the line stops only if the problem isn't solved. Alerts are logged for later improvement (Andon).

**Blameless postmortems.**
- Google SRE book: focus on "contributing causes ... without indicting any individual or team", and assume people "had good intentions and did the right thing with the information they had".
- Triggers are set in advance (downtime, data loss, manual intervention).
- Senior engineers review each postmortem, because "an unreviewed postmortem might as well never have existed" (Google SRE book, ch. 15).

**Transfers to agents?**
- The andon transfers directly: any agent may and should stop and raise a blocker instead of working around it.
- Toyota's two-pull version suits a scarce human: ask for help first, stop only if the problem stays unresolved.
- "Blameless" is moot for agents, but the systems focus is still right: fix the brief, the tool or the check, not "the agent".
- Kaizen's input is the logged stops and postmortems, which agents produce cheaply. Choosing which improvements to adopt still needs the human.
- Genchi genbutsu is "check the real system, not the summary".

## 5. Knowledge and memory in organisations

**Transactive memory.**
- Wegner (1985): "a mechanism through which groups collectively encode, store, and retrieve knowledge". Each member knows their own field and who knows what.
- Groups trained together, or given feedback on each other's skills, performed better.
- People who expect to look information up later remember where it is better than the information itself (Sparrow et al. 2011, as reported) (Transactive memory).

**Handover: SBAR and WHO.**
- SBAR stands for Situation, Background, Assessment, Recommendation. It came from military submarines and was adopted at Kaiser Permanente in 2002.
- A 2013 review found the commonest handover problem was "the omission of detailed patient information".
- Limits: SBAR needs training, the receiver may not know the format, and juniors hold back on the Recommendation step (SBAR).
- WHO listed "communication during patient hand-overs" as one of nine patient safety solutions in 2007 (news release only).

**Institutional memory and turnover.**
- Organisational memory is "the accumulated body of data, information, and knowledge created in the course of an organization's existence".
- Flexible labour markets have "imposed an Alzheimer's-like corporate amnesia". Undocumented decisions are a particular gap, and memory "can only be applied if it can be accessed" (Organizational memory).
- The bus factor is "the minimum number of team members that have to suddenly disappear from a project before the project stalls". An analysis of 133 popular GitHub projects found "65% have bus factor ≤ 2". The named mitigations are documentation and cross-training (Bus factor).

**Transfers to agents?** This is where agents differ most.
- Every session end is total turnover. Anything held only in a session has a bus factor of zero once the session ends.
- The "who knows what" directory has to be a file: which notes, issues and human owners cover which area.
- SBAR is a good template for an agent's handback, and "omission of detail" is exactly the handoff pain the brief describes.
- Agents can dump their full state, so a handover can attach raw logs as well as the summary. The limit is the reader's attention.
- The Recommendation weakness is inverted: agents recommend readily, and the risk is over-assertion.

## 6. Open-source governance

**The Linux kernel maintainer model.**
- Each subsystem maintainer is a gatekeeper with their own tree. Trees pull from each other in chains that "rarely exceed two or three links".
- "Linus trusts the subsystem maintainers to not send bad patches upstream." In 2.6.38, "only 112 (around 1.3%)" of more than 9,500 patches were chosen by Linus directly.
- Each cycle has a two-week merge window, then fixes only. linux-next previews the next merge so conflicts show up early. Andrew Morton's -mm tree is the "tree of last resort" (kernel.org development process).

**How patch series are reviewed** (kernel.org submitting patches).
- "Separate each logical change into a separate patch". Each patch must be "justifiable on its own merits" and the kernel must build after every patch. Send about 15 patches at a time.
- The commit message states the problem and why the change matters.
- Tags record roles: Signed-off-by (provenance), Reviewed-by (a technical review with no serious issues left), Acked-by (lighter acceptance), Tested-by. Tags are dropped if the patch changes substantially.
- "Ignoring reviewers is a good way to get ignored in return".

**CODEOWNERS.** Owners of a path are "automatically requested for review", and branch protection can require their approval. The last matching pattern wins (GitHub docs).

**BDFL vs. steering council.**
- A BDFL is a project founder who keeps the final say in disputes. Raymond argued that the threat of a fork keeps the dictator benevolent.
- Van Rossum stepped down in 2018 "without appointing a successor" (BDFL article).
- PEP 13 replaced him with a five-person elected steering council, the "court of final appeal". It "should look for ways to use these powers as little as possible", prefers consensus to voting, and delegates (PEP 13).

**Transfers to agents?**
- The kernel model is the strongest precedent for one scarce top decider. Area maintainers filter and integrate, and the top person handles about 1% of patches plus merge timing. Agent area owners can fill the maintainer role for routine changes.
- Reviewed-by and Tested-by map onto recording which independent agent reviewed or tried a change.
- What differs: a kernel maintainer is a long-lived person with judgement built over years. An agent area owner is rebuilt from files every session. So the area's MAINTAINERS entry, conventions and decision log must carry that judgement, and accountability stays with a human.
- CODEOWNERS can enforce "the area owner reviews" mechanically.
- PEP 13's restraint principle is a model for the human: decide principles and appeals, and delegate the rest explicitly.

---

## What does not transfer

- **Trust built over time.** Mission command, kernel maintainership and HRO deference to expertise all rest on a person's track record. A fresh agent has none, and a resumed agent has only what its files record. Trust has to rest on mechanical checks and on the written record.
- **Long-term memory in people.** Transactive memory, institutional memory and handover practice assume people remember beyond the handover. For agents, every handover is total turnover, and files are the only memory.
- **Social limits.** Dunbar's number, morale, alienation (Smith, Taylor's critics), blame and fear of reporting, and rank deference (CRM) are human problems. Agents show other biases: they agree with whoever briefed them and they over-assert. These need other countermeasures: independent briefs, and explicitly asking for evidence against the plan.
- **Cost structure.** Ramp-up, team setup and a second reviewer are expensive for humans and cheap for agents, tokens aside. Human attention is the scarce resource here. Any structure that adds decision points for the human, such as matrix approvals or a "Consulted" role, costs far more than it would among people.
- **Independence through separate people.** Two humans are independent by default. Two agents that share a briefing context or a model's habits are not. Independence has to be engineered: a different brief, no access to the maker's reasoning, perhaps a different model.
- **Collusion and fraud.** Separation of duties mainly targets fraud. Among agents the threat is correlated error. The control looks the same, but its purpose and how its failures show up are different.
- **Accountability.** RACI's "A", the three lines' governing body and a BDFL all need someone who can be held to account. Only humans can fill that role.

## Not verified

These look relevant but were not fetched or could not be read in this run. They are named only as cited by fetched pages or as seen in search results.
- Haynes et al., NEJM 2009 (surgical checklist): nejm.org returned 403 and PubMed required cookies. The figures above are as Wikipedia reports them.
- WHO Patient Safety Solution 3 document on hand-over communication (2007). Only the news release was read.
- The IIA's 2024 "Statement of Position on the Three Lines Model", which the IIA page says supersedes the 2020 paper. Only the 2020 PDF was read.
- PMBOK Guide definitions of weak, balanced and strong matrix. Only search snippets and a 2011 Wikibooks page were read; kirkwood.pressbooks.pub and spscc.pressbooks.pub returned 403.
- The Team Topologies book (Skelton and Pais), the InfoQ 2019 article on cognitive load (404), and the teamtopologies.com cognitive-load page (404). The intrinsic/extraneous/germane split came from search snippets only.
- Weick and Sutcliffe, *Managing the Unexpected* (only the Wikipedia summary was read).
- Sources cited by fetched pages but not read: Conway's 1968 Datamation paper; MacCormack, Rusnak and Baldwin (2011); Lindenfors et al. (2021); Avelino et al. (bus factor); Galbraith (1971); Hall, *Making the Matrix Work*; Gottlieb (2007); Raymond, "Homesteading the Noosphere".
- NATO AJP-01 and US Army mission command doctrine (not fetched).

## Sources fetched and read

- https://en.wikipedia.org/wiki/Organizational_structure
- https://en.wikipedia.org/wiki/Matrix_management
- https://en.wikibooks.org/wiki/Project_Management/Organization_structures
- https://en.wikipedia.org/wiki/Division_of_labour
- https://en.wikipedia.org/wiki/Scientific_management
- https://en.wikipedia.org/wiki/Conway%27s_law
- https://martinfowler.com/bliki/ConwaysLaw.html
- https://teamtopologies.com/key-concepts
- https://martinfowler.com/bliki/TeamTopologies.html
- https://en.wikipedia.org/wiki/Brooks%27s_law
- https://en.wikipedia.org/wiki/Span_of_control
- https://en.wikipedia.org/wiki/Dunbar%27s_number
- https://en.wikipedia.org/wiki/Separation_of_duties
- https://en.wikipedia.org/wiki/Two-person_rule
- https://en.wikipedia.org/wiki/Maker-checker
- https://en.wikipedia.org/wiki/Responsibility_assignment_matrix
- https://en.wikipedia.org/wiki/Internal_control
- https://www.theiia.org/globalassets/documents/resources/the-iias-three-lines-model-an-update-of-the-three-lines-of-defense-july-2020/three-lines-model-updated-english.pdf
- https://en.wikipedia.org/wiki/Audit_trail
- https://en.wikipedia.org/wiki/Mission_command
- https://en.wikipedia.org/wiki/Crew_resource_management
- https://www.who.int/teams/integrated-health-services/patient-safety/research/safe-surgery/tool-and-resources
- https://en.wikipedia.org/wiki/WHO_Surgical_Safety_Checklist
- https://en.wikipedia.org/wiki/High_reliability_organization
- https://en.wikipedia.org/wiki/Toyota_Production_System
- https://en.wikipedia.org/wiki/Kaizen
- https://en.wikipedia.org/wiki/Andon_(manufacturing)
- https://sre.google/sre-book/postmortem-culture/
- https://en.wikipedia.org/wiki/Transactive_memory
- https://en.wikipedia.org/wiki/SBAR
- https://www.who.int/news/item/02-05-2007-who-launches-nine-patient-safety-solutions
- https://en.wikipedia.org/wiki/Organizational_memory
- https://en.wikipedia.org/wiki/Bus_factor
- https://docs.kernel.org/process/2.Process.html
- https://docs.kernel.org/process/submitting-patches.html
- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- https://en.wikipedia.org/wiki/Benevolent_dictator_for_life
- https://peps.python.org/pep-0013/
