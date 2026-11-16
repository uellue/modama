## Summary

- **Communities of practice and guilds** are well documented for moving know-how between teams. The Spotify version is a weak precedent: one of the original authors' colleagues said it was never run as described.
- **Galbraith's lateral mechanisms** form a ladder, from cheap informal networks up to expensive integrator roles and a full matrix. Tushman showed that information crossing team boundaries tends to get biased and distorted.
- **Lessons-learned databases** have a poor record. NASA's own Inspector General found its system rarely consulted or fed (no time, outdated, not relevant). Lessons need to be tied to a next action, not just stored.
- **Blackboard and event-log designs** are being applied to LLM agents again (arXiv 2025–2026). The results are early and come from the authors themselves.
- **Agent-specific coordination tools** exist (Beads, Claude Code agent teams, GitHub Copilot coding agent). A2A connects agents to agents; MCP connects an agent to tools.
- **Programme management:** I found no fetchable PMI or MSP text. The UK government standard GovS 002 does require a record of dependencies and says to keep them to a minimum.
- **Monorepo vs polyrepo:** there is no neutral evidence. The pro-monorepo case for agents comes from a vendor (Nx). The critiques mostly say a monorepo needs discipline and tooling.
- **Release trains** (Linux, Chromium, Firefox, SAFe) share one rule: work that misses the cut waits for the next train.

---

### 1. Communities of practice; guilds and chapters

**What it is.** Lave and Wenger introduced the concept in *Situated Learning* (1991). Their cases were apprenticeships such as midwives and tailors. Wenger developed it further in 1998. A community of practice is a group that, quoted, "share[s] a concern or a passion for something they do and learn how to do it better as they interact regularly". It has three elements: domain, community and practice. Organisations cultivate these groups for onboarding, less rework and spreading tacit know-how; the Wikipedia article cites Wenger, McDermott & Snyder (2002), *Cultivating Communities of Practice*.

The Spotify paper (Kniberg & Ivarsson, Oct 2012) uses the idea directly:
- **Chapter:** people with similar skills within one tribe. Its lead is the members' line manager.
- **Guild:** a "community of interest" that cuts across the whole organisation. Each guild has a coordinator.
- The paper calls chapters and guilds "the glue that keeps the company together". It names the motivation: "The tester in squad A may be wrestling with a problem that the tester in squad B solved last week."
- It admits, quoted, "isn't this just a matrix org? Yes. Well, sort of."
- Its own disclaimer: "This article is only a snapshot of our current way of working".

**Evidence and failure modes.**
- Jeremiah Lee (April 2020) argues the model was "only ever aspirational and never fully implemented".
- Lee quotes the Spotify coach Joakim Sundén: "Even at the time we wrote it, we weren't doing it". Sundén on chapter leads: "They don't have really any accountability for the delivery". I saw this only as cited by Lee.
- Lee also reports that product managers had no engineering counterpart to negotiate with.
- In 2013 Kniberg acknowledged the chapter-lead concerns and said "the advantages of this model seem to outweigh the disadvantages".
- Barriers cited on Wikipedia: "egos and personal attacks, large overwhelming CoPs, and time constraints".

**Fits agents and humans?** For agents, the practical form is a shared skills or know-how repository that every agent loads, so it is cheap and needs no meetings. Someone still has to tend it, and agents will agree with whatever it says. A human "guild coordinator" role competes for the principal's attention.

Sources:
- https://en.wikipedia.org/wiki/Community_of_practice
- https://holub.com/goodies/SpotifyScaling.pdf (third-party copy of the 2012 paper; text extracted)
- https://blog.crisp.se/2012/11/14/henrikkniberg/scaling-agile-at-spotify
- https://www.jeremiahlee.com/posts/failed-squad-goals/

### 2. Boundary spanners and Galbraith's lateral relations

**What it is.** Tushman (1977, *ASQ* 22(4)) described roles that link a unit's internal network to outside information. Cross-boundary communication is, in Wikipedia's paraphrase of Tushman, "inefficient and prone to bias and distortion". A 2002 MIT course deck summarises the paper as boundary roles, internal "communication stars" and a "two-step process": staff talk to the stars, who talk outside. The same deck lists the caveat "When are boundary roles counter-productive?".

Galbraith's information-processing view (Interfaces, 1974; I saw only the abstract): more task uncertainty requires more processing capacity. The design options are self-contained tasks, vertical information systems and lateral networks. A Corporate Research Forum paper, adapting Galbraith (2002), lists five lateral capabilities on a continuum of rising "Cost, Management Time, and Difficulty":
1. networks
2. management processes
3. teams
4. integrator roles
5. matrix structures

**Failure modes.** The CRF paper says "Lateral connections and networks can be over-used". It adds that lateral connections "don't spontaneously occur" and must be designed.

**Fits agents and humans?** A liaison agent per project pair is cheap. But a summary passed from one agent to another has exactly the bias-and-distortion problem, and agents will not push back on whoever briefed them. Use the cheapest rung (a shared document or process) before adding integrator roles; the principal should not become the matrix.

Sources:
- https://en.wikipedia.org/wiki/Boundary_spanning
- https://ocw.mit.edu/courses/15-351-managing-the-innovation-process-fall-2002/2b1b482d920a030ef23c8cace0d3f6f2_lecture67.pdf
- https://jaygalbraith.com/?p=57
- https://www.crforum.co.uk/wp-content/uploads/2019/03/The-Lateral-Organisation.pdf

### 3. SECI; lessons-learned systems and AARs

**What it is.** Nonaka and Takeuchi's SECI model has four modes of turning knowledge between tacit and explicit:
- socialization (tacit to tacit)
- externalization (tacit to explicit)
- combination (explicit to explicit)
- internalization (explicit to tacit)

These form a spiral. "Ba" is the shared context in which knowledge is created (Nonaka & Konno 1998).

Criticisms: it was built on Japanese firms with long tenure, its linear order is questioned (Gourlay 2006), and, quoted, "The model does not explain at all how new ideas and solutions are developed in practice."

**Lessons-learned evidence.**
- **GAO-02-195 (Jan 2002):** NASA lessons were "not routinely identified, collected, or shared". Barriers were lack of time and "a perception of intolerance for mistakes". GAO recommended mentoring and "storytelling".
- **NASA OIG IG-12-012 (6 March 2012), main finding:** project managers "do not routinely use LLIS to search for lessons identified by other projects or routinely contribute new information".
- **Same report, contributions:** apart from JPL, no NASA centre contributed consistently in 2005–2010.
- **Same report, reasons managers gave:** the system is "outdated, is not user friendly, and does not contain information relevant to their projects", and their time is taken by competing demands.
- **Same report, verdict:** LLIS is "of diminishing and questionable value".
- **US Army:** its 2025 after-action review circular (TC 7-0.1) puts follow-up (retraining, revising SOPs, sharing lessons) in a chapter of its own. That is, the review is not the end of the work.

**Fits agents and humans?** Agents externalize cheaply: they write everything down. Retrieval and use is where these systems fail, and that is exactly the agent weakness too. A lesson should become a changed instruction, check or test that is loaded automatically, not a database entry.

Sources:
- https://en.wikipedia.org/wiki/SECI_model_of_knowledge_dimensions
- https://www.gao.gov/products/GAO-02-195
- https://www.oversight.gov/sites/default/files/oig-reports/IG-12-012.pdf
- https://www.army.mil/article/283214/tmd_publishes_training_circular_to_augment_fm_and_adp_7_0
- https://en.wikipedia.org/wiki/After-action_review

### 4. Blackboard architecture; event sourcing; LLM applications

**What it is.** A blackboard system has three parts:
- a shared blackboard holding partial solutions
- specialist knowledge sources that contribute when their conditions match the board
- a control component that decides who acts

Hearsay-II (Erman et al. 1980) is the classic example. I could fetch neither Nii's 1986 AI Magazine articles nor the Hearsay-II paper.

Event sourcing (Fowler, 2005): "Capture all changes to an application state as a sequence of events." This gives audit, temporal queries and replay. Fowler's caveats:
- replays must not re-trigger external systems
- external queries make replay non-deterministic
- it is "very hard to retrofit"
- readers "are liable to be out of sync with the master"

**Applications to LLM agents** (arXiv preprints; results are the authors' own claims):
- **Han & Zhang, 2507.01701 (July 2025):** agents are chosen "based on the current content of the blackboard", and the loop runs until consensus. They report competitive accuracy with fewer tokens.
- **Salemi et al., 2510.01285 (Sept 2025, v2 Jan 2026):** a central agent posts requests and agents volunteer to answer, so no controller needs to know each agent's expertise. They report "13%-57% relative improvements in end-to-end success".
- **Nakajima, 2605.21997 (May 2026), "The Log is the Agent":** "The append-only event log is the source of truth". Components coordinate only through the shared graph, with deterministic replay and "cheap forking".

**Fits agents and humans?** This fits forgetful, forkable agents well: a file-based log or board is the memory, and a new agent catches up by reading it. The control component (who acts, who arbitrates conflicting writes) remains the hard part. A human can read the log only if it is summarised.

Sources:
- https://en.wikipedia.org/wiki/Blackboard_system
- https://martinfowler.com/eaaDev/EventSourcing.html
- https://arxiv.org/abs/2507.01701
- https://arxiv.org/abs/2510.01285
- https://arxiv.org/abs/2605.21997

### 5. Coordination tools for coding agents; A2A and MCP

**Beads (Yegge).** A "Distributed graph issue tracker for AI agents, powered by Dolt". Git is only the transport, and `issues.jsonl` is an export, "not the source of truth".
- Tasks have blocking and parent-child dependencies.
- `bd ready` lists tasks with "no open blockers"; claiming is atomic.
- Hash IDs avoid merge collisions.
- `bd remember` and `bd prime` store and re-inject project facts.

**Claude Code agent teams** (experimental, off by default). A lead, teammates, a shared task list (pending, in progress, completed, with dependencies) and per-agent JSON mailboxes. Claiming uses file locking. Documented limitations:
- no resumption of in-process teammates
- "Task status can lag"
- one team per session, no nested teams

The docs also warn: "Letting a team run unattended for too long increases the risk of wasted effort."

**GitHub Copilot coding agent.** Works in a cloud environment and opens one pull request per task. Sessions on Actions are limited to one repository; cloud-sandbox sessions can span repositories. The docs say "Logs do not replace your own review and testing."

**A2A and MCP.** A2A is "An open protocol enabling communication and interoperability between opaque agentic applications", under Linux Foundation governance. In its own words: "MCP connects an agent to tools, APIs, and data. A2A connects it to other agents." MCP is "an open-source standard for connecting AI applications to external systems".

**Fits agents and humans?** These are designed for exactly the stated constraints: a persistent file or database instead of memory, plus atomic claims. Cross-project use needs one tracker that all projects share. A2A matters only if agents run as remote services; local agents share files.

Sources:
- https://github.com/steveyegge/beads
- https://code.claude.com/docs/en/agent-teams
- https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent
- https://a2a-protocol.org/latest/
- https://modelcontextprotocol.io/docs/getting-started/intro

### 6. Programme and portfolio management: dependency registers

**What it is.** A programme coordinates related projects towards shared outcomes; a portfolio is the organisation's set of investments. Because I could not fetch PMI or MSP text, the citable source is the UK GovS 002 (v2.1, Sept 2025). Its clauses:
- **Portfolio (3.3):** "comprises part or all of an organisation's investment required to achieve its objectives"
- **5.2:** the record of work components includes "interdependencies between components under different senior responsible owners"
- **5.3.3:** plans are collated "with interdependencies identified between components within and outside the portfolio"
- **5.3.6:** risk monitoring covers interdependencies
- **7.2.4:** "Dependencies between work components should be minimised to make each component as self-contained as possible", and remaining dependencies "should be defined"

**Failure modes.** None stated in what I read. GovS 002's "minimise first, then record" is itself the lesson.

**Fits agents and humans?** A machine-readable dependency record across projects (shared pins, interfaces between projects) suits agents, which can check it on every change. Keeping it current needs an owner. For the scarce human, it is a place to look rather than a ritual.

Sources:
- https://projectdelivery.gov.uk/library-products/government-functional-standard-govs-002-project-delivery/
- https://www.gov.uk/government/publications/project-delivery-functional-standard
- https://en.wikipedia.org/wiki/Program_management (tagged as poorly cited)

### 7. Monorepo vs polyrepo

**What it is.** Potvin & Levenberg (CACM 2016): Google's monolithic repository "provides a common source of truth for tens of thousands of developers". It depends on custom "systems and workflows that make managing and working productively with a large repository feasible". I could read only the abstract.

**Critiques.**
- **Kreinin (July 2019):** "Monorepo is great if you're really good, but absolutely terrible if you're not that good." In a monorepo, modularity is only an ideal, and branches and forks hurt everyone. Standard tools assume small working trees.
- **Merino (Aug 2023):** a monorepo makes maintenance costs visible. Multirepos spread the same costs across teams, where they "fly under the radar", for example side repos "stuck with an old version of the compiler".

**Agent-specific.** Savkin (Nx, July 2026; vendor material) argues that agents in polyrepos see "one project at a time" and that "Every repo boundary wipes the agent's context". Nx's own "synthetic monorepo" links repos into one dependency graph, but Savkin concedes cross-repo writes are only "eventually consistent".

**Fits agents and humans?** Cross-repo context and atomic changes favour a monorepo or a meta-repo for agents. Upstream and third-party projects (the EOSC stack, LiberTEM) cannot be merged in anyway. A shared graph of pins plus coordinated pull requests is the realistic middle ground.

Sources:
- https://research.google/pubs/why-google-stores-billions-of-lines-of-code-in-a-single-repository/
- https://www.yosefk.com/blog/dont-ask-if-a-monorepo-is-good-for-you-ask-if-youre-good-enough-for-a-monorepo.html
- https://jmmv.dev/2023/08/costs-exposed-monorepo-multirepo.html
- https://nx.dev/blog/the-effect-of-monorepos-on-the-effectiveness-of-ai-agents
- https://monorepo.tools/synthetic-monorepos

### 8. Release trains

**What it is.** A fixed schedule where work that misses the cut waits for the next train.

- **Linux:**
  - The merge window "lasts for approximately two weeks", followed by weekly -rc releases.
  - Releases come "every two or three months".
  - After -rc1, only fixes are accepted.
  - linux-next is "a snapshot of what the mainline is expected to look like after the next merge window closes".
- **Chromium** (current docs): a new milestone ships to stable "every two weeks". The rule for late work: "Features which are not code complete by branch point should be punted to the following milestone."
- **Firefox** (current wiki): "The standard release interval of Firefox is two weeks". Every two weeks the main branch merges to beta, which then takes only stabilising patches. Search results showed a 2019 move to four weeks, but I did not fetch that announcement.
- **SAFe Agile Release Train:** "a long-lived team of Agile teams", "generally made up of 50 -125 people". PI planning is "typically a 2-day event" every 8–12 weeks, and its planning board shows delivery dates and dependencies.

**Critique.** Schwaber (2013) objected that "SAFe tries to control risk through predictability" and that "Values and principles scale, but practices are context sensitive."

**Fits agents and humans?** A shared cadence for bumping pinned versions across projects lets agents integrate continuously while the human reviews in batches at known times. That helps with attention. A SAFe-sized ceremony does not fit a team with one principal.

Sources:
- https://docs.kernel.org/process/2.Process.html
- https://chromium.googlesource.com/chromium/src/+/HEAD/docs/process/release_cycle.md
- https://wiki.mozilla.org/Release_Management/Release_Process
- https://framework.scaledagile.com/agile-release-train
- https://framework.scaledagile.com/pi-planning
- https://kenschwaber.wordpress.com/2013/08/06/unsafe-at-any-speed/

---

### Not verified

These looked relevant but I could not fetch them, or saw them only cited by someone else:
- **Primary works I did not read:**
  - Lave & Wenger (1991) and Wenger (1998), the books themselves
  - the Wenger-Trayner site (403)
  - Wenger, McDermott & Snyder (2002)
  - Roberts (2006), "Limits to Communities of Practice"
  - Tushman (1977), full text
  - Galbraith, *Designing Complex Organizations* (1973), the 1974 Interfaces full text, and the 2002 source behind the CRF summary
  - Nonaka (1991, HBR) and Gourlay (2006)
- **Seen only as cited by Lee:** Sundén's 2017 talk.
- **Army and HBR:** TC 25-20 and TC 7-0.1 texts; Darling, Parry & Moore, "Learning in the Thick of It" (HBR 2005).
- **Blackboard:** Nii, AI Magazine 7(2) and 7(3), 1986 (bot-blocked); Erman et al. (1980), Hearsay-II.
- **Monorepo:** the Potvin & Levenberg full text (only the abstract read); Matt Klein, "Monorepos: Please don't!" and Adam Jacob's reply (403 or not found).
- **Programme management:** PMI *The Standard for Program Management*; AXELOS MSP (no fetchable text; I found no confirmation that MSP names a "dependency register").
- **Release trains:** Mozilla's 2019 four-week announcement.
- **Arxiv:** "ESAA-Conversational", arXiv 2606.23752 (seen only on Emergent Mind).
- **Nx's cited evidence:** the Airbnb migration figure and the "20% of commits" claim.

There was one minor conflict in sources I did read: the OIG report says GAO-02-195 had seven recommendations, while my fetch of the GAO page reported ten.
