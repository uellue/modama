# Review of recognition-checks-content, 2026-11-12

Scope: this change at cebdec4 (proposal with decisions 144 to 149 and 165 to 168, design D1 to D6 with the flows of events and the section "To fold into dm-containers-and-k2is", tasks, and the spec deltas for `recognition`, `records-cli` and `chain-trace`). It is a plan, with no code yet. Checked against the current code on branch `crawler` at 5e08245 in the main checkout, not this worktree's older base e35e4b4. Between the two, the crawler's `src/` differs only in `formats/TEMPLATE.md`. The DM and K2IS code (`python/modama-formats-em/src/modama_formats_em/dm/`, `k2is/`) is merged into `crawler` (merge a0e8ed2, then 09fabf9). Requirements used: @weber's words of 2026-11-12 and his decisions in the proposal, the main specs in `openspec/specs/`, the open changes `dm-containers-and-k2is`, `em-formats-and-extraction` and `parallel-walk`, `design/architecture.md`, `design/requirements.md`, `requirements-pipeline.md` 2.4, and both `AGENTS.md`.

Written by an agent that did not write the change. Every finding was checked against the code. The ones marked CONFIRMED were reproduced with scripts run on `crawler`'s installed packages and the MIME database of all installed collections (core, collapse, em, zarr). The scripts are in this session's scratchpad and are not committed: `exp1.py` (detection of misnamed files), `exp2.py` (a read error while sniffing), `exp3.py` (K2IS grouping when a tag file loses its type), `exp4.py` (fallback types). `openspec validate recognition-checks-content --strict` passes.

Severity, as used here: **high**, the plan does not meet a stated requirement, or a task cannot be done as written; **medium**, a wrong result in a case that can happen; **low**, documents, tests, cleanliness.

## Findings

| # | Severity | Verdict | In plain words |
|---|---|---|---|
| 1 | high | PLAUSIBLE | A broken tag file next to its 8 sector files is treated as "not K2IS", although @weber said such a file is not a stray file |
| 2 | high | CONFIRMED | The collection test requires every format to produce a dataset on a representative fixture. `em/dmw` produces none, so task E.1 cannot pass |
| 3 | medium | CONFIRMED | When K2IS drops one tag file's type, a complete capture next to it can fall apart into single files, and the warning names the wrong capture |
| 4 | medium | CONFIRMED | A read error while finding the new type gives `application/octet-stream` silently and keeps it on later crawls. The design says the error is reported and the directory is recognised again |
| 5 | medium | PLAUSIBLE | Because only the DM4 header counts, a DM3 workspace named `.dmw` becomes a DM3 image whose extraction fails: the F15 symptom this work set out to fix |
| 6 | medium | PLAUSIBLE | The order rule cannot be met as worded, and nothing reports when a format breaks it |
| 7 | medium | CONFIRMED | The documents contradict decision 166: a risk still says the new detection is charged to the budget, and two budget requirements are left as they are |
| 8 | low | PLAUSIBLE | When a failed format call has its types put back, its notes in the basis must go as well. The scenario does not check this |
| 9 | low | CONFIRMED | Three recognition scenarios cannot be tested with the two test formats that task 1.2 defines |
| 10 | low | CONFIRMED | Detection with a type left out is new behaviour of MIME detection, but `mime-database` gets no spec text for it |
| 11 | low | CONFIRMED | Several statements assume the older code and branch state: the `dm-containers` branch, "land together", the K2IS version bump, the backlog entry, the expected files |
| 12 | low | PLAUSIBLE | `not_of_type` changes the directory in place, a second output beside the datasets, which the architecture's plan to run formats in worker processes has to carry |

## Outcomes (2026-11-12, with @weber's decisions 172 to 174)

Each finding verified against `crawler` at 50533f9 before it was acted on.

| # | Outcome | Where |
|---|---|---|
| 1 | Addressed by decision 172: K2IS groups a `.gtg` with 8 sector files of its stem whatever it holds, and checks the header only of a `.gtg` without sector files | proposal "In short" and 172; design Goals, D2, E2, flow B; spec `formats/k2is` (MODIFIED "A K2IS tag file and its sector files form one dataset", scenario "An empty tag file with its 8 sectors"; ADDED "A lone tag file needs the DM4 header"); task 2.3 |
| 2 | Addressed by decision 173: `em/dmw` claims a `.dmw` with a DM header and extracts every tag, so it has a dataset on the representative `dmw_file` | proposal 173; design E1; spec `formats/dm` (ADDED "A .dmw file is described by all its tags"); task 2.2 |
| 3 | Addressed by decision 172: the broken `scan_2_.gtg` is grouped with its own 8 sectors, so `scan_` keeps its own | design E2, flow C; spec `formats/k2is`, scenario "A broken capture next to a complete one"; task 2.3 |
| 4 | Addressed: `detect_with_tie(..., strict=True)` raises a read error, which `_call` reports as the format's failure, puts the types back and marks the directory for the next crawl. The walk's own detection is left as it is, stated out of scope | design Context, D1; spec `mime-database` "A read error is raised when asked", spec `recognition` "A read error while finding the new type"; tasks 1.1, 1.2, 1.6 (backlog), "Not now" |
| 5 | Addressed for `.dmw` by decision 174: the check accepts DM3 and DM4, and a DM3 `.dmw` is a file of interest; flow C of the earlier design (a DM3 image named `.dmw` becomes a DM3 image) is gone. The `.gtg` case stays open | design E1, flows D and E, "Open questions"; spec `formats/dm` scenario "A .dmw file with the DM3 header"; selection by type in E1 |
| 6 | Addressed: the rule is worded "higher than the formats expected to claim its files' new types", and `run_post` warns when an earlier format reacts to a dropped file's new type; `DIRECTORY` formats are the stated blind spot | design D3; spec `recognition` ADDED "A broken format order is reported"; tasks 1.2, 1.6 (TEMPLATE) |
| 7 | Addressed: the risk rewritten to decision 166; MODIFIED "Plain data in, no reach outside the directory" (with the budget scenario) and "A byte budget bounds every format call" (`parallel-walk`'s, so this change archives after it); a scenario for the bound (a second call reads nothing) | design D1, D2, Risks; spec `recognition`; proposal, archive order |
| 8 | Addressed: the notes are put back with the types, and the scenario checks the basis | design D3; spec `recognition` "A format fails after dropping a type" |
| 9 | Addressed: the delta names its test formats (`test/tags`, `test/png`, `test/contradicts`, a raising variant), and the budget scenario reads 4 bytes | spec `recognition`, preamble and scenarios; task 1.2 |
| 10 | Addressed: ADDED requirement "Detection can leave a type out" with the weaker name rule, the left-out content match and the read error | spec `mime-database`; design D1, Risks; task 1.1 |
| 11 | Addressed: no branch `dm-containers` or "fold into" step (the em part is built here); the migration and the K2IS version bump restated; `BACKLOG.md`'s existing item renamed (task 1.6); the K2IS warning keeps its wording, so the expected files with it stay | proposal, design Context, E2, E3, Migration Plan, tasks 1.6, 2.3, 2.5 |
| 12 | Addressed: one paragraph in D1 on what a worker would return | design D1 |

### 1. A broken tag file next to its 8 sectors is treated as "not K2IS" (high, PLAUSIBLE)

**What.** @weber's words that started this change: "A stray file will not have 8 bin files". In other words, a tag file next to 8 sector files of its stem is a broken capture, not a stray file. The proposal (`proposal.md:11`), flow B (`design.md:92-97`) and the new K2IS requirement (`design.md:174-183`, scenario "A capture whose tag file is text") decide the opposite. K2IS checks the header of every `.gtg` before grouping, and a `.gtg` without the DM4 header loses its type even when exactly 8 sector files of its stem sit next to it. So "not K2IS" and "broken" are told apart by the tag file's first 16 bytes, not by whether the capture is there. The first version of this change did it @weber's way: "A K2IS capture whose `.gtg` does not read stays one K2IS record, and the crawl reports its extraction failure" (71be726, proposal). Flow B "with 149" was put to @weber before he answered "149 sounds sensible!" (95d3487), so he may have accepted the reversal. None of the recorded decisions says so, though.

**Where.** `proposal.md:11, 34`; `design.md:47, 92-97, 137, 174-183`; current code `k2is/__init__.py:43-78` (it groups by stem and sector count, and does not read the tag file).

**Failure scenario.** An interrupted copy leaves `Capture7_.gtg` empty or filled with zeros, next to its 8 intact sector files. With this change, `exp4.py` shows the empty file becomes `text/plain` and the zero-filled one `application/octet-stream`. The capture is then 9 single records, and the tag file's record calls it "Plain text document, 1 file, 0 B". The only sign of the damage is the directory warning about sector files without a tag file. Today it is one K2IS record with a reported extraction failure, which is "something is broken". R30 ("an accidental split beats an accidental grouping") argues for the proposal's choice. Here, though, the grouping is not accidental: the 8 sector files' magic is strong evidence.

**Fix.** K2IS groups a `.gtg` with exactly 8 sector files of its stem whatever its header, so a broken tag file fails at extraction as today. It checks the header only of a `.gtg` it does not group (lone, or with the wrong count), and drops that one's type. This also reads fewer files, and it removes finding 3. **Ask** @weber whether flow B stands as written.

### 2. The coverage rule fails for `em/dmw`, so task E.1 cannot pass (high, CONFIRMED)

**What.** The collection plugin's coverage test requires every format of a part to appear as the format of some dataset on a representative fixture: `own_formats <= seen_formats`, where `seen_formats = {d.format for d in result.datasets}` (`python/crawler/src/modama_crawler/testing.py:248, 260, 280`; spec `formats-testing`:46, "the plugin SHALL fail if a rule fires on no representative fixture", recognizers included). E1 says `em/dmw` "yields no datasets" (`design.md:133`). A `.dmw` with the header stays an unclaimed single file with format `""`, as `dm/tests/expected/dmw_file.json` shows today. The drop only happens on reproducer fixtures (`notes.dmw`, `empty.dmw`), which the rule does not count. Task E.1 (`tasks.md:21`) ends with "The coverage rule passes".

**Failure scenario.** Once `em/dmw` is added to `dm.COLLECTION`, `test_coverage` for the dm part fails with "formats without a representative fixture: ['em/dmw']". No fixture can fix that.

**Fix.** Decide one of these before building. (a) `em/dmw` claims each `.dmw` with the header as a dataset of `application/x.dm-dmw`, basis "DM4 header". The record's type stays the same, but every `.dmw` then gets a recognition comment in `records --verbose` (2,036 on staging). (b) The coverage rule also counts a format as seen when it dropped a type on a fixture, and the stray-file fixtures become representative of that. This is a core change with a `formats-testing` spec delta. (c) A declared exemption for checking formats. Whichever is chosen goes into the tasks and spec deltas.

### 3. A dropped tag file can take a complete neighbouring capture down (medium, CONFIRMED)

**What.** K2IS takes the longest stem first. A stem's sector files leave the pool even when their count is wrong (`k2is/__init__.py:46-59`, the fix of finding 3 in `dm-containers-and-k2is`), and that is what keeps `scan_` and `scan_2_` apart. A `.gtg` whose type is dropped no longer has a stem in that loop, so its sector files stay in the pool, and the next shorter stem collects them.

**Failure scenario** (`exp3.py`, with the drop simulated by naming the text tag file `scan_2_.txt`, which K2IS's `d.of_type(TAGS)` does not see either). Take a complete `scan_.gtg` with `scan_1..8.bin`, next to `scan_2_.gtg` holding text and `scan_2_1..8.bin`. Today both are grouped (two K2IS datasets of 9). After the drop, all 18 files are single records, and the only warning is `scan_.gtg: 16 sector files scan_*.bin, a K2IS acquisition has 8`. That warning blames the intact capture. The real cause, `scan_2_.gtg` without a header, is visible only in that file's basis, which no warning points to. Flow B and its spec scenario only cover a directory with a single capture.

**Fix.** The fix of finding 1 removes this, because `scan_2_` would be grouped. If flow B stays, K2IS keeps a dropped tag file's stem in the longest-stem loop to take its sector files out of the pool, and warns for those sector files by that stem. Add the two-capture directory as a fixture and scenario.

### 4. A read error during the new detection is silent and lasts (medium, CONFIRMED)

**What.** D1 says: "A read error propagates to the format, and `_call` handles it as any read error: a warning, and the directory is recognised again next crawl" (`design.md:32`). D1 also reuses `mime.detect_with_tie`, and task 1.1 keeps it "with no change of result" (`tasks.md:5`). But `detect_with_tie` catches `OSError` from the open and the read, and returns `application/octet-stream` (or the tie's resolution) (`python/crawler/src/modama_crawler/mime.py:187-197`). `exp2.py` raises `OSError(EIO)` on the open and gets `('application/octet-stream', None)`, with no exception. Nothing sets `Directory.retry`, so the listing is stored without `retry`, and the next crawl takes the directory over (`walk.py:264-265`) with the wrong type. The crawler README says the opposite: "A directory whose recognition met a read error … is recognised again next crawl" (`README.md:11`). So does `parallel-walk`'s crawl requirement: "the same data gives the same result, or fail".

The same gap already exists in the walk itself. Its `detect` wrapper expects an `OSError` (`walk.py:177-181`) and has a "cannot read" branch (`walk.py:333-337`), but `detect_with_tie` never raises one there, so that branch never runs.

**Failure scenario.** An NFS hiccup during the new detection of `notes.gtg` (the format's own 16-byte read a moment before succeeded) makes it `application/octet-stream` with the basis `single file; em/k2is: not application/x.dm-gtg, no DM4 header`. It stays so on every crawl until the file or the rules change, and no warning is given.

**Fix.** Give `detect_with_tie` a way to raise on a read error, for example a keyword the new detection and the walk both use, and test it with a failing open, as `exp2.py` does. If the walk's dead branch should start working too, that changes what the walk reports, so give it a scenario of its own. Otherwise state it as known and out of scope.

### 5. Accepting only the DM4 header turns a DM3 workspace into a broken DM3 image (medium, PLAUSIBLE)

**What.** Decision 147 keeps the check at DM4 only, until @weber's fresh `.dmw` files (open item 155). He also said "DMW should/could also exist as DM3". A 16-byte header tells the version, not image against workspace, so the check sorts by version:
- A DM3 workspace `conditions.dmw` (tags, no image): `em/dmw` drops it, the new detection gives `application/x.dm3` (`exp4.py`: a DM3 header without a name rule gives `application/x.dm3`), `em/dm3` claims it, and its extraction fails with no `ImageList`. The record then calls it "Gatan Digital Micrograph (DM3)" and the crawl reports a failed extraction. That is the F15 symptom (72 % of staging run 3's extraction failures) and the "broken" label for a file that is not broken. Today, on `crawler`, it is a correct `application/x.dm-dmw` single file. Flow C's last paragraph (`design.md:106`) says so, but treats it as acceptable for now.
- A DM3 image named `.dmw` becomes a DM3 dataset with metadata (flow C), while a DM4 image named `.dmw` keeps the `.dmw` type with no metadata. The existing `dmw_file` fixture is exactly such a DM4 image.

The same holds for a DM3 `.gtg` (E2): a DM3 tag file becomes a DM3 "image" that fails.

**Where.** `design.md:99-106, 132, 134, 138, 150`; `proposal.md:75`; current `dm/__init__.py:78-80` (claims every file of its type without a check).

**Failure scenario.** Older GMS writes a DM3 workspace (the case @weber names). On a crawl it shows up as a broken DM3 image.

**Fix.** Count the DM3 header as "of the type" too (version 3 or 4 at offset 0 with the byte order flag). Then nothing in the DM family is ever turned into a DM image by this change. A DM3 image misnamed `.dmw` keeps the `.dmw` type, as a DM4 one does: a harmless miss, and no false statement. Flow C, which no real file backs, would go. Or keep DM4 only, and change the requirement title "Tag files and workspaces are not DM images" (`design.md:149`) to say it holds only for DM4. **Ask** @weber, with this trade-off.

When implementing E1, also select by type (`d.of_type("application/x.dm-dmw")`), not by a name ending in `.dmw`. The glob is case-insensitive, so `Up.DMW` is typed `application/x.dm-dmw` too (`exp1.py`).

### 6. The order rule cannot be met as worded, and breaking it goes unnoticed (medium, PLAUSIBLE)

**What.** D3: "a format that drops types SHALL have a higher priority than every format of a type its files may fall back to" (`design.md:51`). A dropped file can fall back to any type its content matches, so taken literally, a dropping format must outrank every post-order format there is. Priority 61 works today, because every post-order format is at 60 (`em/dm3`, `em/dm4`, `em/k2is`, `em/empad`, `em/merlin`), and `zarr/zarr` (80) and the `collapse` formats (90) answer in the pre-order call only (`formats/zarr/__init__.py:19-20`, `formats/collapse/__init__.py:21-22`). A future format above 61 that reacts to a type a dropped file can take misses it without any sign, for example a DM series format that groups DM3 images, or anything reacting to `text/plain`. The two order scenarios (`specs/recognition/spec.md:19-26`) test the core with test formats, not the installed formats' priorities. Priorities are also not part of the rule-set fingerprint (`selection.py:155`: ids and recognition versions only). A changed priority without a new version or release leaves taken-over directories with the old outcome. That was already true for claims, and now it holds for types as well.

**Failure scenario.** Someone later adds `em/dmseries` at 70, reacting to `application/x.dm3`. A DM3 image named `.dmw` is dropped to `application/x.dm3` by `em/dmw` (61) after `em/dmseries` has run, and stays a lone DM3 dataset outside the series. Nothing reports it.

**Fix.** Word the rule as "higher than the formats expected to claim its files' fallback types" (TEMPLATE). Have `run_post` warn when a dropped file's new type is in the `reacts_to` of a format that already ran on that directory: "<format> ran before <dropping format> and did not see <file> as <type>". That makes a broken order show up on the first crawl. It is cheap, because `run_post` knows the formats it ran, and one scenario covers it. Formats that react to every directory in the post-order call remain a blind spot. Say so in TEMPLATE.

### 7. The documents contradict decision 166 on the budget (medium, CONFIRMED)

**What.** Decision 166 does not charge the new detection's read to the format's budget, and D1 and the spec delta say so (`design.md:32`, `specs/recognition/spec.md:36`). But:
- The risks still say "each re-detection charges up to 18,730 bytes, so about 56 drops of large files per directory → the format is skipped there with the budget warning" (`design.md:119`). An implementer may follow that.
- The main `recognition` spec keeps "the read counts against the directory's budget" (`openspec/specs/recognition/spec.md:30-32`) and "Each format call … SHALL have a byte budget for reads, enforced while reading" (`:69-70`). `parallel-walk` replaces the latter with "A byte budget bounds every format call" (`changes/parallel-walk/specs/recognition/spec.md:5-6`), with the same wording. This change adds an exception without modifying either one, so after both are archived the specs disagree.

On the brief's question, whether 166 can make a crawl unbounded: no, as long as D2's check comes before the read. A file is checked once, and after the drop `by_name(name)` no longer equals its type, so a second call answers with the "type kept" warning and reads nothing (`design.md:43-45`). That makes at most one read of up to `Mime.magic.maxlen` bytes (18,730 with all installed collections, `exp2.py`) per name-typed file per recognition, which is what the walk reads for any file its name does not decide.

**Fix.** Delete or rewrite the risk at `design.md:119`. Make the budget exemption a MODIFIED requirement of "A byte budget bounds every format call" (in step with `parallel-walk`), and of the scenario "Reading a file within the budget": "the core's detection of a new type is not the format's read". Add a scenario stating the bound: a second `not_of_type` call on the same file reads nothing and warns.

### 8. Putting the types back must also remove the notes (low, PLAUSIBLE)

**What.** D3: "`_call` keeps the entries as they were before the call and puts them back when it discards the call's datasets" (`design.md:53`). D1 also keeps a note per dropped file, which ends up in a basis (`design.md:34`, D4). The design does not say the notes of a discarded call are removed too. The scenario "A format fails after dropping a type" (`specs/recognition/spec.md:38-40`) checks the type and the warning, not the basis.

**Failure scenario.** `test/tags` drops `notes.tags` and then raises. The type is put back to `application/x.test-tags`, but the basis reads `single file; test/tags: not application/x.test-tags, no TAGS header`, which contradicts the type next to it.

**Fix.** Say that the call's notes are removed along with its entries, and add "and the basis `single file`" to the THEN.

### 9. Three scenarios have no test format to run them (low, CONFIRMED)

**What.** Task 1.2 defines two test formats: `test/tags` drops `*.tags` files without `TAGS`, and `test/png` claims `image/png` (`tasks.md:6`). In `specs/recognition/spec.md`:
- "A file without an extension that matches a content rule" (`:31-33`): "a format says it is not of type `image/png`" about `blob`. Neither test format does that.
- "A format fails after dropping a type" (`:38-40`): `test/tags` does not raise as defined. It needs a variant that does.
- "The new type's detection does not use the format's budget" (`:43`): "reads 16 bytes", while task 1.2's `test/tags` "reads those 4 bytes". Harmless, but the scenario and the format should say the same.

**Fix.** Name the extra test formats in task 1.2 (one that calls `not_of_type` on every file of a given type, one that raises after its drop), and use 4 bytes in the scenario.

### 10. Detection with a type left out needs spec text in `mime-database` (low, CONFIRMED)

**What.** `detect_with_tie(path, exclude=…)` is new behaviour of MIME detection (D1): the remaining name rules decide by weight and pattern length, and a sniffed result equal to the left-out type counts as no match. The proposal modifies `recognition`, `records-cli` and `chain-trace`, but not `mime-database` (`proposal.md:53-57`), whose "Names decide, content resolves" describes detection. Two consequences are worth stating:
- A lower-weight name rule now decides without reading. `README.gtg` matches `*.gtg` (weight 50) and `README*` for `text/x-readme` (weight 10) (`exp4.py`). After a drop it is `text/x-readme` by name, whatever its bytes.
- pyxdg's `match_data` returns only the best magic match. If that match is the left-out type, a lower-priority match the content also fits is lost, and the file falls back to text or octet-stream. That cannot happen with `.gtg` and `.dmw`, whose types have no magic, but it can with a future type that has both a glob and magic.

**Fix.** A short MODIFIED or ADDED requirement in `mime-database` with these two scenarios, or one sentence in D1 accepting them.

### 11. Statements that assume the older code or branch state (low, CONFIRMED)

- `design.md:128`: "moves into the change `dm-containers-and-k2is` on branch `dm-containers` once that branch is free". `dm-containers` is merged into `crawler` (`git merge-base --is-ancestor dm-containers crawler`), and `dm-containers-and-k2is` is an open change there, with finding 1 still undecided (`changes/dm-containers-and-k2is/tasks.md:21`). The fold now means editing that change on `crawler`. The same applies to `proposal.md:67, 72` ("on branch `dm-containers`", "the two land together") and `tasks.md:19`.
- `design.md:124`, migration: "When this and `dm-containers` land together … That crawl re-extracts DM files anyway". The DM part has landed already, so the first crawl with this change is not the one that re-extracts DM files. Whether staging has been crawled with the merged DM code is not recorded here (see "Not verified").
- `design.md:139`: the K2IS recognition version bump "so that a staging database crawled with `dm-containers` recognises again. Skip this if …". The new format id `em/dmw` already changes the rule-set fingerprint (`selection.py:155`), so every directory is recognised again either way. The bump does no harm, but the stated reason does not hold. K2IS has no `version` today, so it is the default "1" (`k2is/__init__.py:35-41`).
- `design.md:5`: "line numbers on `crawler` at 99b6f58". 99b6f58 is a commit on this change's branch, not on `crawler`. The line numbers do hold on `crawler` at 5e08245: `mime.py:177-213`, `formats/__init__.py:175-184, 235, 238-239, 242-259, 262-274, 304-305, 366-380`, `walk.py:91-97, 265, 302-303`, `selection.py:138-165`, `cli.py:548-551`, `dm/__init__.py:72`, `k2is/__init__.py:38, 43-78`.
- `tasks.md:13` (task 1.6): "BACKLOG.md: … @weber's idea of tagging suspicious results". It is already in `BACKLOG.md:59` on `crawler`, under the old name "change `extractor-rejects-type`". The task is to rename it there.
- Task E.2 (`tasks.md:22`) changes the wording of K2IS's warning for sector files without a tag file, but does not list the files that hold the old wording: `k2is/tests/expected/other_bin.json`, `expected/sectors_without_tags.json` and `k2is/tests/test_extract.py`.

**Fix.** Update these statements to the current state of `crawler` before the fold.

### 12. `not_of_type` is a second output beside the datasets (low, PLAUSIBLE)

**What.** The architecture keeps a format's input and output as plain data, "so handlers can later run in worker subprocesses with timeouts … without changing them" (`design/architecture.md:21, 102`, G). With D1, a format's call also changes the directory's entries, and the core detects the new type during that call. `Directory.warn` already works the same way, so this does not block a later move to workers. It does mean the new types and the notes have to be sent back with the datasets. D1's alternative (a separate stage that returns `(entry, reason)` pairs) would be plain data by construction.

**Fix.** One sentence in D1 saying what a worker would return (the replaced entries and the notes, beside the datasets and warnings), so that the interface stays movable.

## What is right and should stay

- **Who changes what with a parallel walk.** `run_post` runs once per directory in a walk thread (`walk.py:350-351`), on a `Directory` built for that directory alone (`walk.py:350`). The changes D1 makes to `entries` and the name index are therefore never shared between threads. The new detection runs in that thread, and the walk's matching processes are not involved. `match_in` gives the same result as matching in the thread (`mime.py:135-160`), so the outcome does not depend on `processes`.
- **Nothing new stored, and same data, same result.** The type and basis are stored per dataset already (`store.py:72-79, 280, 299, 372`), and the basis is not published (`records.py` does not read it), so a note moves no datestamp. A directory is taken over only when its listing and those of all directories below it are unchanged (`walk.py:264, 296-303`). The listing digest includes size, mtime and ctime (`walk.py:91-97`), so a replaced file is checked again, as D5 says.
- **`by_name` as a pure function of the name and the database**, with no new field on `Entry`, and one drop per file per crawl. This bounds decision 166's uncharged reads (finding 7).
- **Flow D is right.** A file named `counts` holding big-endian `[4, 7, 9, 0]` is typed `application/x.dm4` by its content (`exp1.py`). Keeping content types is the honest choice, and a weak magic rule then shows up as a failed extraction.
- **The fallback types in flows A and C are as described**: `hello\n` and an empty file become `text/plain`, and a DM3 header without a name rule becomes `application/x.dm3` (`exp4.py`).
- **Case of extensions.** The `*.gtg` and `*.dmw` globs are case-insensitive (`UP.GTG` and `Up.DMW` are typed by name, `exp1.py`), and K2IS already compares `.bin` in any case (`k2is/__init__.py:57`). A check by type covers every case, and the `upper_case` fixture, whose tag file has the header, keeps its outcome.
- **Priority 61 is enough with today's formats** (finding 6), and the id order `em/dm3` < `em/dm4` < `em/dmw` < `em/k2is` is as D3 says.
- **The trace and `records --verbose` read only what is stored or computed already**: `datasets.basis` for the trace's crawler line (`python/search-chain/src/modama_chain/crawler.py:79-91` reads `datasets` already), and the basis of a single file in the existing comment loop (`cli.py:546-552`).
- **The documented alternative to D1** (a separate check stage), with the condition for switching to it.
- **Cutting the first version's extraction-time machinery** (D6): no schema change, no new column, no second detection after extraction.

## Not verified

- Whether staging has been crawled with the merged DM/K2IS code. This decides whether the first crawl with this change is the one that re-extracts DM files (finding 11).
- Whether any real `.dmw` or `.gtg` has a DM3 header (decision 147, open item 155), and whether GMS writes `.GTG` or `.BIN` in upper case.
- Finding 3 was reproduced by naming the text tag file `.txt`, not with the planned `not_of_type`, which does not exist yet. K2IS sees both the same way, since it selects tag files by type.
- The test suites were not run: the change has no code, and the review ran detection and the walk directly.
