# Cold critique of the design (2026-10-16)

Written by a fresh agent with no conversation context, from the repository alone, briefed to poke holes. Unedited. The assistant's response follows at the end; decisions go to the decision log in `architecture.md`.


Scope: requirements.md (R/Q), architecture.md (A–H, decision log), testing.md (T), survey.md, prior-art.md, AGENTS.md, BACKLOG.md, openspec/config.yaml, and the PoC in `src/modama_crawler/` and `tests/`. No files modified.

## 1. Contradictions and inconsistencies

1. **Two definitions of the OAI datestamp.** AGENTS.md ("Records") and `records.py` define it as the time the record last changed, explicitly not the mtime, with a reason (a file copied with an old mtime must still be harvested). architecture.md H makes the `records` CLI use the newest member mtime "as a first crawl would produce" (it doesn't) and filters `from`/`until` on it. H also makes that CLI the oracle for fixture tests (T4), so oracle and product disagree on a protocol field.
2. **Which stage owns series?** A puts directory-as-dataset in stage 1 (pruned, R11); survey.md "Rule sketch" says "stage 1, on the listing"; but the rule groups "by name template *and MIME type*" (stage 2 output), and D says members are matched individually and may be datasets (stage 3). The flagship format is in all three stages, and R11's pruning is silently dropped for it.
3. **"From the index alone" vs. "a function from a tree to records".** A: stage 3 "can run from the index alone"; H: the pipeline "runs without PostgreSQL". Those are two architectures (index-backed vs. in-memory). The sketch's `group.sibling(xml.raw_file_attribute())` reads content in stage 3, so stage 3 needs the file system anyway.
4. **Exclusive membership vs. the series handler.** C/log (Q1, Q2): "Everything else is exclusive membership". D: a suspected series "is matched as a series *and* its files are matched individually". The first collection type is the exception to the rule decided beside it.
5. **Collapsed trees are empty vs. Zarr nests.** D: "Collapsed trees (environments, Zarr) have no datasets inside." survey.md item 4: `.zarr` inside `.zarr` "must stop at the outer marker or produce nested datasets"; spike table: "Zarr (v3, nested)".
6. **R12 is a must; G defers the only mechanism.** A hard per-probe time limit on `h5py`/C code in-process is not implementable without signals or subprocesses (LiberTEM #440 in prior-art). Either R12 is not a must or G is wrong.
7. **Two configuration schemas.** E: `[formats] select/ignore`, `[formats.per-path-ignores]`, `[crawl] exclude`. Sketch: `[collections] enabled`, `[exclude]`, `[expect]`, "as it would look under E-c", which was not chosen.
8. **Vocabulary drift.** "Format" is decided (Vocabulary, 2026-10-16) but R1–R23, the sketch, testing.md and BACKLOG say "handler"; "collection" is both a pip package (E) and a dataset type (D); "skeleton" is a synthetic rule-generated file banned from collections (T-A) *and* a captured production listing used for deployment tests (T-D).
9. **prior-art.md Q5 "For us"** recommends computed specificity, hierarchy, first-class ambiguity; C rejects computed specificity. The rejected recommendation still stands as the document's conclusion.
10. **R10 vs. survey.** R10: millions of files, hundreds to thousands new per day. Survey: 525k files, 58 modified in 7 days. Not reconciled.
11. **R9 (must) vs. H.** `explain` is removed; basis goes to stderr, unstructured, only with `--verbose`.
12. **T-A** says "our own code mimicking a format does not count", then accepts DM4 "masks" from "a format-specific rewriter", which is our code.

## 2. Gaps

- **Q16, the recognizer interface, is the design**, and it is open. The sketch's `group` has methods (`of_type`, `sibling`, `warn`) — callbacks, not the "plain data" G requires for later subprocess isolation.
- **A-a cannot express the survey's own top cases.** TENSOR export (parent dir with `DiffractionPatterns/`, `.hspy`, maps), Dr. Probe (`img/`, `cel/`, `prm/`), QE `*.save`, nested Zarr all need *children's* content. "Declared number of parent levels" looks up; nothing looks down.
- **The cleanup step is undefined.** It is the reason streaming is forbidden (H), yet no document says what it does. Under A-a, order within a group is irrelevant by construction; what does it fix?
- **Dataset identity across crawls.** Anchor is a path. No rule for members disappearing, directory renames, or a format version change (re-run what: datasets it claimed, files it might now claim, files a lower-priority format claimed?). `handler (name, version)` is stored; nothing uses it.
- **Priority across stages.** XDG weights and magic priorities are stage-2 quantities; Python priority orders stage 3. C treats both as one "0..100" scale. What does recognizer 60 mean against glob 80?
- **Series rule parameters** g, N, c, f, r are unset; the "fit step" has no definition; the schema stores `max(mtime, ctime)` while the rule needs both at sub-second resolution.
- **Record content for collections.** What text does a 67,600-frame series or a sweep record carry? Title = path, creator = uid, format, plus 3,600 `dc:relation` URLs? R30 is about search quality and nothing says what is searchable.
- **Access.** A quarter of the tree is visible. R18 as written means "index a quarter". No decision.
- **`update-mime-database`** is an external C binary (pyxdg `install_mime_info`), undocumented; the pyxdg fork depends on an unmerged MR.
- **Licence** of importing freedesktop.org.xml (GPL-2.0-or-later, verify) into `modama-formats-core` is not mentioned.
- **Schema**: no parent key, `files_in_datasets` never populated, no migrations, int4 keys.
- **Report and expectation-file formats** (E, T-D): unspecified, yet the report is "the primary output".

## 3. Risky or questionable decisions

**XDG MIME XML + Python.** By file count XDG handles the small part: 371k of 525k visible files are series members, 74k collapsed trees, Zarr is directory-marked — all Python. XML-only spike formats: plain, DM4, ipynb. "Right for the 90%" (architecture, strongest arguments 1) counts types, not files or difficulty. The PoC already abuses the declarative layer (`*.xml` glob on EMPAD forcing sniffs of all 22k XML files). Evidence: write TENSOR, Dr. Probe, series and Zarr against XDG+A-a on paper first.

**0..100 priorities across contributors.** XDG works because one file has one maintainer. With `.dat`, `.bin`, `.raw`, `.h5`, `.tif`, `.xml` each meaning several things (survey item 3), equal-weight ties are certain, and C resolves ties to `application/octet-stream`: two good formats cancel to nothing. `select = ["gatan"]` auto-enables formats added by an upgrade (E), so `pip install -U` can create ties in production. Evidence: write the HDF5 family (h5, emd, nxs, hspy, Matlab 7.3) and the `.dat`/`.bin` cases as XDG rules; see whether weights or `sub-class-of` refinement (prior-art Q5, "what worked") resolve them.

**Index first, then reduce.** The previous attempt failed (architecture 3); A-a cannot look into child directories; the "complete picture" requirement kills streaming and incrementality. Evidence: a post-order walk prototype (§5.1) on the visible tree.

**Nesting + series as collection type.** Introduced for the least-understood case (sweeps: "need a decision"), as "the handler decides per kind" — three behaviours in one format. It bakes a search heuristic (R31, 10/100) into the data model and emits records with thousands of `dc:relation` entries. Evidence: feed the local EOSC snapshot a record with 3,600 relations and 10^6 records total; see what it renders and whether ingestion survives (BACKLOG: one failed record blocks a run).

**Exclusive membership.** A session README, a shared calibration file, an `.emi` with `_1`, `_2` `.ser` are normal; Bio-Formats needed 25 exemptions. Probably fine for search (R30), but say so instead of making the series handler the exception. Evidence: count directories with one text/markdown file beside more than one dataset candidate.

**Datestamp model.** Two definitions (§1, item 1); no migrations means a schema change resets every datestamp and triggers a full re-harvest; a live frame series republishes its collection record every crawl. Evidence: harvester behaviour on changed records in the snapshot.

**Fixture layout and two-purpose files.** Direct hit: the series rule depends on mtime regularity, size spread and ctime. **Git does not preserve mtime; ctime cannot be set.** Shipped representative fixtures for the series format are impossible under T-A/T-B, and listing-based synthetic fixtures are banned from collections (R29). Further: 100 KB compressed for N≥10–50 frames; the coverage rule over thousands of imported freedesktop types demands thousands of representative files in the core; recorded outcomes containing a format version churn every release. Evidence: try to write the first series fixture.

**`records` CLI as oracle.** `oai_dc` is the lowest-information representation: members, basis, warnings, unclaimed files are absent (stderr), so `expected/*.yaml` ("recognition output", T4) is a second oracle anyway; mtime datestamps make output checkout-dependent. Make the recognition result document the oracle and `oai_dc` a renderer of it.

**pip/entry points/ruff selection.** Mostly sound. But: `collection/format` has two levels, so ruff's prefix precedence is overkill; implicit enabling on upgrade contradicts R1's intent and the expectation file's purpose of detecting system changes (RuboCop's pending state fits better); `importlib.metadata` does not detect duplicates (prior-art), so "rejected at load time" is ours to write; a PyPI-prefix-generated list will list squatters.

**Survey-derived series rule.** One listing, a quarter of the tree, five example rows, thresholds by eye. Its flagship (67,600 TIFFs) has mtime span 0.0 h from `cp`, i.e. fails "one session without pauses"; the fallback ctime records the copy. Digit templating conflates indices with dates and versions. Size spread breaks for compressed formats (LZW TIFF, gzip HDF5). Evidence: label `series-candidates.tsv`, report precision/recall, validate on the invisible three quarters.

**Deployment expectation file.** "Optional, may start empty" means T7's single mechanism has nothing to run; a frozen snapshot of a petabyte tree is either copied real files (ownership deferred, T3) or a skeleton that can't exercise probes (admitted in T-D).

**Deferred security.** This is an operational must, not a nicety: one segfaulting HDF5 file (already seen) kills an uncheckpointed multi-hour crawl, and R12 needs the same process boundary. The boundary shapes the interface (plain data, no DB connection or callbacks in the recognizer). Defer hardening, not the interface decision. Evidence: open every `.h5`/`.emd`/`.nxs` in the visible tree with h5py; count crashes and opens over 3 s.

**PostgreSQL only.** Fine at 10^8 rows. The risk is the schema (absolute text paths, no parent key, so directory-group queries scan) and the parallel in-memory path demanded by H (§5.3).

**One record per dataset for search.** The warehouse's DC→DataCite XSLT drops `dc:format` (BACKLOG), so the one thing recognition produces, the type, is not searchable downstream. Nothing specifies searchable text beyond path and owner. Evidence: ask the warehouse what it indexes before investing in types.

## 4. Scale and operations

- **Walk.** Single-threaded `os.walk` plus a second `stat` per entry over NFS, no checkpoint. At 5–10k stat RPCs/s, 10^8 files is 3–6 h per crawl, restarted from zero on failure. `scandir` caching and parallel subtree walkers are not discussed.
- **Stage 2.** 5 ms plus an 18 KB NFS read per sniff. With 20% sniffed (no extension, all `.xml`, `.dat`, `.bin`) at 10^8 files: 2×10^7 sniffs, ~28 h CPU, ~360 GB read, single-threaded. Every XML rule change re-runs this.
- **Index.** A 10^8-row temp table rebuilt per crawl, then an anti-join delete (BACKLOG). No parent key: directory groups need a full sort or `LIKE` scan.
- **Incremental.** "Stage 3 for directories whose listing changed" is unworkable while datasets look across directories or depend on an undefined cleanup step. Directory mtime as a listing-changed signal is unused.
- **Re-recognition after a format upgrade.** No invalidation rule; realistically a full stage 3 and, for XML changes, a full stage 2; every changed record gets a new datestamp and is re-harvested.
- **Cleanup.** Needs the complete result; at 10^8 files that is 10^7–10^8 datasets, in memory on H's pure-function path.
- **Nested datasets.** A sweep record with 3,600 relation URLs is ~400 KB of XML; a 100-record page is 40 MB. Member→parent back-references mean touching 3,600 member records when the collection changes. Cascade on parent deletion is unspecified.
- **Live file system.** A series written over 1.3 h is republished every crawl; files vanishing between walk and probe leave stale `crawl` rows in the PoC.
- **All numbers are extrapolated from a quarter of the tree.**

## 5. Alternatives not considered or dismissed too quickly

1. **Post-order walk with per-directory recognition.** Rejected (log, Q11) as "during the walk only", but a bottom-up walk hands each directory its children's *results*: exactly what TENSOR, Dr. Probe, QE and nested Zarr need; order-independent per subtree; streams; incremental by subtree; no cleanup step. Boring-tree pruning still works with a pre-order peek. Wins whenever datasets are directory-local, which the survey says is nearly always.
2. **Type hierarchy (`sub-class-of`) for container formats** instead of weights: HDF5 → Velox/NeXus/hspy/Matlab, ZIP → office/npz, XML → EMPAD. Prior-art calls it the thing that worked everywhere. Wins for the "immediately after" HDF5 batch.
3. **SQLite/DuckDB as the index for the CLI and fixture tests**, keeping one index-backed code path instead of an in-memory fork. Wins the moment stage 3 needs a query the group object can't answer.
4. **Snapshot diff or change notification** (the repo has `python/PyInotify`; NetApp/GPFS/Lustre offer policy or snapdiff APIs). Wins when a full walk exceeds the crawl interval.
5. **Members as a template, not a list**: (anchor, name template, count, size range) instead of 67,600 `files_in_datasets` rows. Wins at scale and makes series fixtures tractable.
6. **A trivial series rule** (one template, one type, ≥N files, nothing else in the directory) without timing features; producer-specific formats for the rest. Wins when copies destroy mtimes, as the survey already shows.
7. **OAI-PMH sets** per project directory or type. Wins when one bad record must not block the whole harvest, or the warehouse wants subsets.
8. **RuboCop-style pending state** for formats added by upgrade. Wins for every deployment with whole-collection `select`.

## 6. Questions before sign-off, by design impact

1. Full read access (group-member user or `CAP_DAC_READ_SEARCH`), or is a quarter of the tree the product?
2. What does the EOSC warehouse index, render and survive: 10^6 records, 3,600 relations in one record, `dc:format` dropped? If types are not searchable downstream, recognition's value is grouping only and the priority apparatus shrinks.
3. Recognizer interface (Q16): directory group, subtree with children's results, or queries?
4. Out-of-process probes from day one (R12, R23)? Decides plain-data interface and checkpointing.
5. Dataset identity across crawls, and what invalidates stage-3 results on member change or format upgrade?
6. One datestamp definition: which code path is wrong?
7. Who labels the series candidates, on which data, and is mtime trustworthy on this storage after typical copies?
8. What storage serves `/er-c-data`; does it offer change notification or snapshot diff?
9. Licence of importing freedesktop.org.xml.
10. Why does the measured change rate differ from R10 by two orders of magnitude?

## 7. Plain bad ideas

- Two definitions of the OAI datestamp, one in the test oracle (H vs. AGENTS.md).
- Git-shipped fixtures for a rule that depends on mtime/ctime regularity (T-A/T-B vs. the survey rule).
- Forbidding streaming and incremental processing because of a cleanup step nobody has defined (H, A).
- Making the first collection type the exception to exclusive membership (C vs. D).
- Resolving a tie between two legitimate formats to `application/octet-stream` (C).
- Auto-enabling new formats on `pip install -U` for whole-collection `select` (E).
- Keeping the `*.xml` glob trick that forces sniffing of every XML file (B, BACKLOG).
- Using `oai_dc`, which lacks members, basis and warnings, as the recognition oracle (H).
- Deferring the process boundary when one already-observed segfault loses an uncheckpointed multi-hour crawl (G, BACKLOG).

## Response (assistant, 2026-10-16)

Where the critique is right and the design should change:

1. **Datestamp (§1.1, §7):** a real contradiction. The recognition result, not `oai_dc`, must be the oracle (§3 "records CLI"); `oai_dc` is one renderer of it. The `records` command then prints the rendering, and the recorded fixture outcome is the result document. The CLI's `from`/`until` stays a convenience on member mtime and is documented as not the server's datestamp.
2. **Series fixtures versus git (§3 fixtures, §7):** a direct hit. Git keeps no mtime and ctime cannot be set. Fix without breaking "wild files only": the manifest carries the timestamps observed in the wild, and the test plugin applies them with `utime` before recognition; ctime is excluded from fixture tests. Or the series rule uses timing only to split groups (§5.6), not to recognise.
3. **Post-order walk (§5.1):** the strongest point. Bottom-up recognition hands each directory its children's results, which TENSOR, Dr. Probe, Quantum Espresso and nested Zarr need and A-a cannot see; it makes order independence hold per subtree by construction, which removes the undefined cleanup step; and it allows incremental re-recognition by subtree. Pruning of boring trees keeps a pre-order peek. This revisits Q11; the earlier reason for "index first" was anchor consistency, which post-order gives for free within a subtree.
4. **Ties resolve to `application/octet-stream` (§3 priorities, §7):** bad. Resolve ties by the XDG `sub-class-of` hierarchy first (two HDF5 subtypes tie to `application/x-hdf5`, not to nothing), report the tie, and keep the common ancestor.
5. **Process boundary (§3 security, §6.4):** agree on the interface, not on the schedule: the recognizer takes plain data (a directory's entries plus children's results) and reads files itself, holds no database connection, so it can run in a worker later; checkpointing of the walk is needed at multi-hour crawls regardless of isolation.
6. **Members as a template (§5.5)** for series: (anchor, template, count, size range) instead of 67,600 rows; the record carries the template, not thousands of `dc:relation` URLs. Relations only for members that are datasets (R31 keeps those under 100).
7. **The `*.xml` glob trick (§7):** drop it; the EMPAD magic rule exists.
8. **New formats on upgrade (§3 selection):** make it policy, as RuboCop does: `new-formats = "pending"` (reported, not enabled) by default, `"enable"` as opt-in.
9. **Vocabulary drift, two config schemas, R10 versus survey, prior-art Q5 conclusion (§1.7–1.10):** editorial, to be fixed in one pass.
10. **Downstream searchability (§3 one record, §6.2):** `dc:format` is dropped by the warehouse's XSLT; what reaches the search index is title, description, subjects, dates. The value of recognition for EOSC search is grouping and the text we put in title and description; the type matters for our own index and browse. Worth confirming with the warehouse team before investing in type detail.

Where I'd push back or qualify:

- **Streaming (§1.3, §7):** the ban came from experience that order invariance and complex matching need the complete picture. With a post-order walk the picture is complete per subtree, so output per finished subtree is possible; whether it is wanted is a separate question. The two-phase `records` command stands either way.
- **Series as the exception to exclusive membership (§1.4, §7):** it is the declared-collection exception that the rule itself provides, decided with a reason (sweeps). The valid point is that the first collection type is also the least understood one; the fix is to label the candidates before designing further, not to drop nesting.
- **XDG handles "the small part" (§3 XDG):** by file count, yes; by number of formats, no: the survey shows a few shapes (series, collapse, directory markers) covering most files, and hundreds of single-file types covering the rest. XDG is the right tool for the hundreds; the few shapes are Python either way.
- **PostgreSQL in-memory fork (§3 PostgreSQL, §5.3):** the pipeline as a function over a tree does not need two code paths if the recognizer's input is a directory's entries plus children's results; the index is where results are stored, not what recognition reads. SQLite for the CLI would add a second store for no gain.
- **Collapsed Zarr versus nested Zarr (§1.5):** not a contradiction, an open choice recorded as such in the survey.

Questions for the lead, from §6, in the critic's order: full read access or a quarter of the tree; what the EOSC warehouse indexes and survives; post-order walk instead of index-first (Q11 revisited); plain-data recognizer interface now; dataset identity and invalidation across crawls; the storage system behind `/er-c-data` and whether mtime survives typical copies; the freedesktop.org.xml licence; the change-rate mismatch with R10.
