# Analogy scout, second series: with a library of known things (O36, O37), 2026-11-16

Asked by @weber after the first run ("run the next scout with the library of known things"). Same four cases and key as the first run (`../scout-2026-11-16/`); the key's addendum, written before any run (08:26:25 UTC), sharpens the grade for C3 and records the expectation. Arms: A = cases only; B = @weber's fuzzing method plus the cases; C = the fuzzing method, a library of 22 known things in neutral structural words (`library.md`, OAI-PMH among decoys such as RSS, sitemaps, LDAP, DNS zone transfers, CKAN) plus the cases. Three runs per arm, nine headless sessions in parallel (`run.sh`), each in its own empty folder outside the repository, no tools, default model; 08:26:32 to 08:28:44 UTC. Answers unedited in `answer-<arm><run>.md`. The organisation's instructions (domain hints, no project analogies) loaded into every session, as in the first run.

## Result

| Case | A (neutral) | B (fuzzing) | C (fuzzing + library) |
|---|---|---|---|
| C1 skip rules: gitignore | 2, 2, 2 | 2, 2, 2 | 2, 2, 2 |
| C2 enabling handlers: ruff/flake8 selection | 2, 2, 2 | 2, 2, 2 | 2, 2, 2 |
| C3 finding files: the tree's descriptions over OAI-PMH into an existing aggregator | 1, 1, 1 | 1, 1, 1 | 1, 1, 1 |
| C3: OAI-PMH or harvesting named at all | 0 of 3 | 0 of 3 | **3 of 3**, at ranks 4, 4, 5 |
| C4 file access: SMB, WebDAV, NFS | 2, 2, 2 | 2, 2, 2 | 2, 2, 2 |
| Time, cost per run | 71 to 81 s, $0.15 to 0.18 | 94 to 131 s, $0.20 to 0.26 | 95 to 122 s, $0.21 to 0.27 |

The expectation written before the run (C reaches 2 on C3 in at least two of three runs) did not hold under the strict key: the library made every C run find the idea, and every C run ranked it below enterprise search, file-system metadata engines and iRODS. In C's own words, run 2: "OAI-PMH with Dublin Core, harvested into CKAN or another aggregator. Fits: A provider exposes records while the items stay at the provider. Existing harvesters and aggregators handle the search, so you build less on the searcher side."

## Reading

- Near analogies need no help; the far one needs the library. Without it, 0 of 6 runs named the idea; with it, 3 of 3. That is the intersection @weber proposed (O37): the fuzzed problem ("find" → "publish so others can find", in all C runs) met the neutral description of OAI-PMH.
- Finding is not ranking. The runs put the familiar product category first, although the case said the team wants to avoid running a search system of its own, which favours a harvest into an existing aggregator. This matches the research on familiarity over suitability (section 8b). Three runs per arm, one model: a direction, not a measurement.
- Caveat: the library's line for OAI-PMH mentions that aggregators "offer search over all of them", a real property but also a strong cue; and the library is ours, so it contains what we know the answer is. A fair library comes from outside the project and is much larger.

## Next (proposed, not run)

- Arm D: arm C plus a step that scores each candidate against the case's stated constraints (here: files stay, no own search system) before ranking, to separate finding from ranking.
- A library not written by us: for example generated from a public catalogue of standards and protocols, with hundreds of entries, to see whether the intersection still surfaces the idea among many more decoys.
