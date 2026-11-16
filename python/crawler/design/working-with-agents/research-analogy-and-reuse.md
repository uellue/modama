## Summary for people

**Is the impression true?** Partly. The weak step is noticing that a distant analogy applies. Once the analogy is pointed out, mapping one domain onto the other works fairly well. Humans show the same weakness, and a hint helps both.

- **Strongest evidence for:** in Gick & Holyoak's classic setup, about 30% of people used a distant analog without a hint and about 80% with one (as summarised by Pedone et al. 2001). GPT-3 lost the analogous solution once distractor stories were added, and found it again only when told to consider the earlier stories (Webb et al. 2023). Without a hint, GPT-4 named the correct source story in 0 of its runs; with a hint it recalled it every time, but it also over-applied analogies (Puranam et al. 2025). LLMs do clearly worse on far analogies than near ones (ARN benchmark).
- **Strongest evidence against:**
  - "Excellent within an established ontology" overstates it. LLMs are also brittle on variants of tasks within one domain (Lewis & Mitchell; Hodel & West), although Webb et al. dispute this.
  - The gitignore case is better described as a reuse failure than an analogy failure, because the analogy had already been named. For reuse, the evidence goes both ways. Agent PRs duplicate existing code more than human PRs do (one MSR 2026 study). But LLMs in general over-use popular libraries rather than avoid them. NIH, as a measured attitude bias in humans, has not been shown in LLMs.

## 1. Analogical reasoning in LLMs

- **Webb, Holyoak & Lu, "Emergent analogical reasoning in large language models"**, Nature Human Behaviour 2023 (https://arxiv.org/abs/2212.09196; full text read at https://ar5iv.labs.arxiv.org/html/2212.09196).
  - GPT-3 matched or beat humans "in most settings" on letter strings, verbal analogies and text matrices.
  - Story analogies:
    - Near analogies: GPT-3 chose the causally matching story above chance (p=0.0039).
    - Far analogies: not significant for GPT-3 (p=0.065), but strongly significant for humans.
    - Humans clearly outperformed GPT-3 (OR=0.37). Preliminary GPT-4 runs did better.
  - Radiation problem:
    - Without a source story, GPT-3 proposed a non-convergence solution.
    - After the fortress story, it found convergence.
    - With two distractor stories, it "no longer identified the convergence solution" until it was prompted to consider the earlier stories.
  - The authors list as a limitation that it is "limited in its ability to evaluate analogies based on causal relations".
  - Strength: one paper; widely cited and contested.
- **Hodel & West, "Response: Emergent analogical reasoning in large language models"**, arXiv 2023/24 (https://arxiv.org/abs/2308.16118).
  - GPT-3 fails simple variants of the letter-string tasks while humans stay high.
  - Quote: "Zero-shot reasoning is an extraordinary claim that requires extraordinary evidence".
- **Lewis & Mitchell**, arXiv 2402.08955 (https://arxiv.org/abs/2402.08955) and arXiv 2411.14215 (https://arxiv.org/abs/2411.14215).
  - On counterfactual letter strings (permuted alphabets, symbols), GPT performance "declines sharply"; humans do not decline.
  - The 2024 follow-up covers letter strings, digit matrices and stories. GPT models are sensitive to answer order and paraphrasing; they "often lack the robustness of zero-shot human analogy-making".
- **Webb et al. reply**, arXiv 2404.13070 (https://arxiv.org/abs/2404.13070).
  - Argues the counterfactual drop comes from difficulty with counting, not from analogy. Webb et al. report that GPT-4 solved the counterfactual tasks when it could run code to count; this is from search snippets, not checked against the paper.
  - Status: an unresolved dispute between the two groups, not a replication.
- **Musker, Duchnowski, Millière & Pavlick, "LLMs as Models for Analogical Reasoning"**, J. Memory and Language 145 (2025) 104676 (https://arxiv.org/abs/2406.13803).
  - Advanced LLMs match humans in several semantic structure-mapping conditions.
  - They respond differently from humans to semantic distractors and to task variations.
- **Sourati et al., "ARN: Analogical Reasoning on Narratives"** (https://arxiv.org/abs/2310.00996).
  - LLMs largely recognise near analogies; "even the largest ones struggle with far analogies", and GPT-4 zero-shot scored below random.
  - Few-shot plus chain-of-thought gets the best model only about halfway to human performance.
- **SCAR (Yuan et al.)**, EMNLP Findings 2023 (https://arxiv.org/abs/2305.12660).
  - 400 scientific analogies from 13 fields; "LLMs often overlook the structures" underlying an analogy. GPT-4 struggles.
  - E-KAR (https://arxiv.org/abs/2203.08480) appeared only in search results; I did not read it.
- **Johnson et al., "Do large language models solve verbal analogies like children do?"**, CoNLL 2025 (https://aclanthology.org/2025.conll-1.40.pdf).
  - Eight LLMs scored at or above the level of children on 872 A:B::C:? items. Most items can be solved by association from C alone.
  - Conclusion: LLMs "rely heavily on association like young children do".
- **Newer models (2025–2026)**:
  - Camposampiero et al., NeSy 2025 (https://arxiv.org/abs/2503.11207): o3-mini fell from 86.6% to 17.0% and DeepSeek R1 from 80.6% to 23.2% when moving from I-RAVEN to I-RAVEN-X with perceptual noise, while a neuro-symbolic model kept 88%.
  - Lee et al., "The Curious Case of Analogies", AAAI 2026 (https://arxiv.org/abs/2511.20344): models encode relations but often fail to apply them to new entities; "emerging but limited capabilities".
  - Khojasteh et al. 2026 (https://arxiv.org/abs/2603.29997): LLMs are sensitive to how similar the stories look on the surface; making the abstraction an explicit step improves narrative mapping.
  - I found no peer-reviewed far-analogy evaluation of the current frontier coding models (GPT-5-class, Claude 4-class).
- **Strength:** far analogies being harder than near ones is consistent across several benchmarks. The size of the "LLMs can't analogise" claim is contested.
- **Implication for working with coding agents:** expect an agent to map a domain correctly once you name the analogy. Don't expect it to bring up an analogy from a different vocabulary by itself, especially when similar-looking but irrelevant material is in its context.

## 2. Humans: spontaneous transfer and the hint effect

- **Gick & Holyoak 1980/1983**, as summarised in Pedone, Hummel & Holyoak, Memory & Cognition 29(2) 2001, 214–221 (https://sites.lifesci.ucla.edu/psych-reasoninglab/wp-content/uploads/sites/273/2021/04/Pedone_etal.MC_.2001.pdf). I read the full text.
  - Control group: about 10% found the convergence solution.
  - With the fortress story: about 30% used it spontaneously, and about 80% in total after the hint "to use the source".
  - With diagrams as the source: no rise above baseline before the hint, and about 70% after it.
  - Conclusion: "retrieval and noticing were major blocks". Adding a verbal statement of the principle, or animation, raised spontaneous access (Pedone et al.).
  - I could not read the 1980/1983 originals (see Not verified).
- **Gentner, Rattermann & Forbus 1993**, as summarised in Morita & Miwa, CogSci 2004 (https://escholarship.org/content/qt8b46r9w3/qt8b46r9w3.pdf).
  - People recalled more stories that looked similar on the surface than ones with the same structure.
  - Yet they rated the structurally similar ones as the more sound analogies.
  - Retrieval follows the surface; evaluation follows the structure.
- **Challenge to that:** Trench et al., CogSci 2020 (https://escholarship.org/content/qt63p1b8j4/qt63p1b8j4.pdf).
  - Raynal et al. argued the surface advantage came from flawed materials.
  - Trench et al. find it holds only against some kinds of surface match: it disappeared when the surface similarity was only similar objects.
  - So the "surface beats structure in retrieval" finding is replicated but under debate.
- **Hint effect in LLMs:** Puranam, Sen & Workiewicz, arXiv 2505.00603 (https://arxiv.org/abs/2505.00603; I read the PDF).
  - Gick & Holyoak protocol: two source stories, two strategic problems, 199 humans and 60 GPT-4 runs.
  - Without a hint, GPT-4 named the correct source story in 0% of runs: "Without a hint, AI fails to recognize or apply analogies". Humans: precision high, recall 6–22%.
  - With a hint, GPT-4 recall reached 1.0, but there were many false positives (over-applying analogies). Abstract: AI "errors arise from surface level matching".
  - Strength: one preprint, n=15 GPT-4 runs per cell, and the paper's own figures are partly inconsistent (14 of 15 runs "used an analogy" without a hint on one problem). Webb et al. 2023 shows the same pattern qualitatively.
- **Implication for working with coding agents:** your hint is the main lever, as it is for humans. A hint also invites over-mapping, so ask the agent to say where the analogy breaks.

## 3. What helps

- **Analogical prompting**, Yasunaga et al., ICLR 2024 (https://arxiv.org/abs/2310.01714): the model first generates its own relevant examples or knowledge, then solves the problem. It beats 0-shot and few-shot chain-of-thought on GSM8K, MATH, Codeforces and BIG-Bench. The examples it generates are near analogies within the same domain, not cross-domain ones.
- **Step-back prompting**, Zheng et al., ICLR 2024 (https://arxiv.org/abs/2310.06117): ask the higher-level principle first. PaLM-2L gains: +7% MMLU Physics, +11% Chemistry, +27% TimeQA.
- **Abstraction before mapping**: the 2026 narrative-mapping work above (Khojasteh et al.) shows that an explicit abstraction step "consistently improve[s]" performance. In humans, stating the principle verbally raised spontaneous access (Pedone et al. 2001).
- **Comparison of cases**: Gentner, Loewenstein & Thompson, J. Educational Psychology 2003, 393–408 (abstract via https://www.kellogg.northwestern.edu/academics-research/research/detail/2003/learning-and-transfer-a-general-role-for-analogical-encoding). Quote: "a marked advantage for comparing two cases over studying the 2 cases separately".
- **Repository- and library-aware generation**: A^3-CodGen (https://arxiv.org/abs/2312.05772) targets "code redundancy" by feeding local, global and third-party library information into context, and reports a higher reuse rate. It is a preprint, and the abstract gives no numbers.
- **Implication for working with coding agents:** make "what is this an instance of, and who already solved it?" an explicit step before implementation. Put two concrete cases side by side (for example "crawler ignore rules ≈ .gitignore") and require a library search before any hand-written parser or matcher.

## 4. Not-invented-here, the inner-platform effect, and agent reimplementation

- **NIH, human evidence**:
  - Hannen, Antons, Piller et al., Research Policy 48(9) 2019 (https://eprints.whiterose.ac.uk/id/eprint/147964/). NIH defined as "a persistent decision-making error arising from an attitude-based bias against external knowledge".
  - Evidence: 32 interviews and a survey of 565 R&D projects. NIH lowers project success through lower uptake of external knowledge; perspective taking reduces it.
  - Katz & Allen 1982 (R&D group performance declining after about 5 years) I know only through Wikipedia (https://en.wikipedia.org/wiki/Not_invented_here).
  - NIH is an attitude or identity bias. Nothing I found shows LLMs have such an attitude, so calling it "NIH" is itself an analogy.
- **Inner-platform effect**: Wikipedia (https://en.wikipedia.org/wiki/Inner-platform_effect) defines it as "the tendency of software architects to create a system so customizable as to become a replica" of the platform. It is anti-pattern folklore (origin linked to The Daily WTF). I found no empirical studies.
- **Agent reimplementation, evidence for**: Huang et al., "More Code, Less Reuse", MSR 2026 (https://arxiv.org/abs/2601.21276; I read the HTML).
  - Agent PRs "frequently disregard code reuse opportunities".
  - Redundancy score for new functions against existing ones (semantic clones by embedding similarity): 0.287 for agent PRs vs 0.153 for human PRs, p<0.001.
  - Weaknesses: one repository (crewAI, 617 PRs), embedding similarity, and only 10 samples checked by hand.
  - GitClear duplication figures appear only in press coverage, which I did not use.
- **Evidence against a general reimplementation bias**:
  - Twist et al., ACL Findings 2026 (https://arxiv.org/abs/2503.17181): LLMs over-use popular libraries such as NumPy, unnecessarily in "up to 45% of cases". They chose Python in 58% of tasks where it was a poor fit, and never Rust. They favour familiarity over suitability.
  - Latendresse et al. 2025 (https://arxiv.org/abs/2507.10818): LLMs "predominantly favour third-party libraries over standard ones".
- **My reading (a hypothesis, not a finding)**: the bias is toward what is familiar and popular. The agent reuses what it strongly associates with the task's own vocabulary ("glob", "fnmatch"). It misses libraries named in another domain's vocabulary ("pathspec", "gitwildmatch") and code already in the repository. That fits the pattern in section 2: retrieval by surface, not structure. Humans show the same, so the NIH and inner-platform labels describe outcomes rather than prove a shared cause.
- **Implication for working with coding agents:** treat "duplicates existing code or a well-known library" as a review item (or an automated check with clone detection and a dependency search). Don't expect a named analogy to turn into library use automatically; name the library too.

## 5. Structured methods for finding cross-domain equivalences

- **TRIZ** (https://en.wikipedia.org/wiki/TRIZ):
  - Altshuller derived recurring problems and solutions from patents, which led to the 40 inventive principles and the contradiction matrix.
  - The statistical basis is marked "citation needed", and effectiveness claims rest on weak sources.
  - LLM automation: AutoTRIZ, Advanced Engineering Informatics 65 (2025) 103312 (https://arxiv.org/abs/2403.13002). It is a demonstration, not a controlled test.
- **Design patterns**: GoF 1994 (https://en.wikipedia.org/wiki/Design_Patterns), 23 patterns.
  - Same page: Norvig showed 16 of the 23 become simpler or disappear in Lisp/Dylan; the patterns are criticised as workarounds for missing language features.
  - A catalogue gives the abstraction a shared name, which is exactly the retrieval cue that section 2 says is missing.
- **Generic parts technique**: McCaffrey, Psychological Science 2012, known only through the APS press release (https://www.psychologicalscience.org/?p=65585).
  - Break objects into parts and describe each part without implying a use. Trained participants solved problems "67 percent more often".
  - Based on 1,001 inventions, McCaffrey claims each innovator found "an obscure feature or an obscure function".
  - One small study; I did not read the paper.
- **Strength**: the methods are plausible and match the abstraction and comparison findings above, but rigorous evidence for TRIZ or for pattern catalogues is weak to absent in what I read.
- **Implication for working with coding agents:** a project "equivalence catalogue" (our problem → established format, protocol or library, for example "ignore rules → gitignore/pathspec", "rule selection → ruff select/ignore", "file access protocol → WebDAV/NFS") in AGENTS.md gives agents the retrieval cue they lack. Describing a requirement without its domain words ("match path patterns with negation and directory anchoring") before searching is the generic parts technique applied to code.

## Not verified

- Gick & Holyoak 1980 and 1983 originals: 403 errors or scanned PDFs. The figures come from Pedone et al. 2001.
- Gentner, Rattermann & Forbus 1993 and Forbus/Gentner MAC/FAC: scanned PDFs, so I used Morita & Miwa's summary.
- Gentner, Loewenstein & Thompson 2003: abstract only. "Inert knowledge" (term and origin) not verified.
- Katz & Allen 1982: Wikipedia only. Antons & Piller 2015: search snippets only.
- E-KAR, the ANALOGICAL benchmark, Raven/Sternberg-style text benchmarks: not read.
- Lewis & Mitchell 2411.14215: TMLR 2025 publication not confirmed from a primary page.
- Webb et al. "GPT-4 with code execution solves the counterfactuals": search snippet only.
- GitClear/GitKraken duplication statistics, Popescu et al. MSR 2026 (110k PRs), Spracklen et al. package hallucinations (USENIX Security 2025): seen in search results only, not read.
- McCaffrey 2012 paper itself: sample size (14 vs 14 per secondary coverage) not verified.
- The IJCAI 2026 Khojasteh doctoral paper: read, but adds nothing beyond the 2026 arXiv paper.
- No study found that tests agents on recognising an existing protocol (WebDAV, NFS) or library from a description in another domain's vocabulary.
