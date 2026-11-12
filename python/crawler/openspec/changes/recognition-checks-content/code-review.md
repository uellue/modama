# Code review of recognition-checks-content, 2026-11-12

Scope: the implementation on branch `worktree-agent-a32d7ef811bf0a9e5`, `git diff 50533f9..29c7d09`: commits 929edcb (mime), 3c8e004 (runner), afdfaea (trace), ec1d4d2 (em part, `records` comment) and 29c7d09 (docs), on top of the planning commit de0caf1. Requirements used: @weber's words and decisions in the proposal (144 to 149, 165 to 168, 172 to 174), the main specs in `openspec/specs/`, this change's deltas, the open changes `parallel-walk`, `dm-containers-and-k2is` and `em-formats-and-extraction`, `design/architecture.md`, both `AGENTS.md`, `formats/TEMPLATE.md` and the coverage rule in `testing.py`.

Written by an agent that did not write the change. Every finding was checked against the code. The ones marked CONFIRMED were reproduced with scripts run against this worktree's sources (`PYTHONPATH` set to its `python/crawler/src` and `python/modama-formats-em/src`), with the MIME database of all installed collections (core, collapse, em, zarr). The scripts are in this session's scratchpad and are not committed: `p1.py` (em cases: a lone DM3 `.gtg`, XML in a `.gtg`, a PNG named `.DMW`, a `.dmw` cut after its header), `p2.py` (the runner with test formats: a claimed file dropped later, a drop followed by a budget overrun, a pair after a drop), `p3.py` (the `.dmw` descriptions of the two stand-in fixtures), `p4.py` (globs of `.gtg`, `.dmw` and `.png` names), `p5.py` (a read error while finding a lone `.gtg`'s new type, next to a complete capture).

Severity, as in `review.md`: **high**, the code does not meet a stated requirement or breaks a case that occurs; **medium**, a wrong result in a case that can happen, or a gap that blocks the merge by the project's rules; **low**, documents, tests, cleanliness.

## Findings

| # | Severity | Verdict | In plain words |
|---|---|---|---|
| 1 | medium | CONFIRMED | One unreadable or vanished stray `.gtg` (or `.dmw`) now takes every K2IS capture (or every `.dmw` dataset) of its directory apart for one crawl. The sector records then stay in the warehouse after the next crawl rebuilds the capture |
| 2 | medium | CONFIRMED | The `formats/dm` delta says a `.gtg` with a DM header is not described as a DM image. A lone `.gtg` with the DM3 header becomes an `em/dm3` image all the same, with the reason "no DM4 header" |
| 3 | medium | CONFIRMED | Task 3.1 has not been run. The `chain-trace` scenario on the e2e tree has no test, the e2e tree holds no `notes.gtg`, and the edited e2e assertion has not run |
| 4 | low | CONFIRMED | A format can drop the type of a file that an earlier format has already claimed. The dataset then keeps its format's type, its basis says it is not of that type, and nothing warns |
| 5 | low | CONFIRMED | Spec `formats/dm` says the `.dmw` description leaves nothing out. Storage cuts each phrase at 4,096 characters and the list at 1,000; the stand-in fixture already has a 6,053-character phrase. The tests check the extractor's output before the cut |
| 6 | low | CONFIRMED | Two code paths have no test: types put back after a drop followed by a budget overrun, and the tie warning of the new detection |
| 7 | low | CONFIRMED | A record of `em/dmw` names the file type in two ways: "Gatan Digital Micrograph workspace" (subject) and "Gatan Digital Micrograph .dmw file" (description) |
| 8 | low | CONFIRMED | Warnings that a call gave before it failed are kept, although the types and notes they talk about are put back |
| 9 | low | CONFIRMED | Documents: the migration plan names a "new distribution version" that does not exist; TEMPLATE does not say that a priority change needs a new recognition `version`; the em README's K2IS row promises a warning for a `.gtg` without sector files |

### 1. A read error on one stray file takes the format's whole directory down for one crawl (medium, CONFIRMED)

**What.** Before this change, K2IS read nothing during recognition. It now reads 16 bytes of each lone `.gtg` (`k2is/__init__.py:77`), and the core detects that file's new type with `strict=True` (`formats/__init__.py:210-212`). An `OSError` from either read propagates out of `recognize`. `_call` (`formats/__init__.py:279-296`) then discards **all** of the call's datasets for the directory, as the spec asks ("A read error SHALL be reported as the format's failure on the directory", requirement "A failed format call leaves every type as it was"). `em/dmw` does the same for every `.dmw` (`dm/__init__.py:198-211`). The blast radius is new: one file that has nothing to do with a capture now decides whether the captures next to it are recognised.

**Where.** `k2is/__init__.py:77-79`, `dm/__init__.py:198-211`, `formats/__init__.py:210-212, 286-296`; spec `recognition` (this change), "A failed format call leaves every type as it was".

**Failure scenario.** A directory holds `Capture52_.gtg` with its 8 sector files and a stray `notes.gtg`. Someone deletes or moves `notes.gtg` between the walk's listing and K2IS's call (ENOENT), or the NFS handle goes stale (ESTALE). `p5.py` simulates the stale handle on the new type's detection:

```
== no error
   /Capture52_.gtg application/x.k2is em/k2is | 8 sector files Capture52_*.bin
   /notes.gtg text/plain - | single file; em/k2is: not application/x.dm-gtg, no DM4 header
== stale handle on the new type's detection
   /Capture52_.gtg application/x.dm-gtg - | single file
   /Capture52_1.bin application/x.k2is-sector - | single file
   ... (8 sector files, each a single file)
   /notes.gtg application/x.dm-gtg - | single file
   W ('/', "em/k2is failed: OSError(116, 'Stale file handle')")
```

The crawl publishes 9 single-file records in place of the capture. The next crawl (`retry`) rebuilds the capture, and the 8 sector records disappear from the crawler. The harvester does not pass deletions on (BACKLOG, "End-to-end test": "no `deletedRecord` yet, and the harvester drops deletions"), so they stay in the warehouse and the search index as stray single files. The same happens to every `.dmw` dataset of a directory when one `.dmw` cannot be read.

**Fix.** Ask @weber. Option A: in `not_of_type`, a read error keeps the file's type, warns at the file, sets `d.retry` and returns the entry unchanged, instead of raising. The other files' outcome then does not depend on it. The format's own `d.read` still fails the call, so K2IS also has to catch `OSError` around its 16-byte check. Option B: keep the spec as it is and record the consequence (a decision-log row, a BACKLOG line next to the missing deletions). Either way, add one scenario with this example.

### 2. A lone DM3 `.gtg` becomes a DM3 image, against the `formats/dm` delta (medium, CONFIRMED)

**What.** The MODIFIED requirement "Tag files and workspaces are not DM images" (`specs/formats/dm/spec.md:6`) says a `.gtg` "SHALL NOT be described or extracted as a DM image, even when its content has a DM header", and only one "without a DM header" gets the fallback type. K2IS drops any lone `.gtg` without the **DM4** header (`k2is/__init__.py:77-79`, spec `formats/k2is` "A lone tag file needs the DM4 header", decision 147). A DM3 header is a DM header, so the two deltas contradict each other. The design lists the case as an open question (`design.md`, "Open questions"), but the spec text does not reflect it.

**Where.** `specs/formats/dm/spec.md:6`, `specs/formats/k2is/spec.md:34-44`, `k2is/__init__.py:77-79`.

**Failure scenario.** `p1.py`, with the DM3 image of the fixture `stem_image_dm3` named `config.gtg`, alone in its directory:

```
/config.gtg application/x.dm3 em/dm3 | Digital Micrograph header; em/k2is: not application/x.dm-gtg, no DM4 header
```

It is described and extracted as a DM3 image. The reason "no DM4 header" is true, but `.gtg` files hold tags, not images (F15). A real DM3 `.gtg` without an image would also fail extraction (there is no `ImageList`), which is the F15 symptom this work set out to remove. No DM3 `.gtg` has been seen, so the case is rare. Still, the spec promises the opposite of what the code does.

**Fix.** Put the open question to @weber (the design's lean: accept the DM3 header for a lone `.gtg`, as for `.dmw`, so that it keeps its `.gtg` type). Until he decides, make the specs agree: either word `formats/dm` for `.gtg` as "without the DM4 header" and add the scenario above with its outcome, or implement the lean and add a scenario for a lone DM3 `.gtg`.

### 3. Integration not done: the e2e scenario has no test and the edited e2e assertion has not run (medium, CONFIRMED)

**What.** Task 3.1 is open (`tasks.md:31`). The first `chain-trace` scenario is "**WHEN** the e2e tree holds `notes.gtg` holding `hello\n`, it has been crawled, and its path is traced". `grep -rn "gtg\|dmw" prototypes/search-stack` finds nothing, so the e2e tree has no such file and no test runs the scenario. `crawler_detail` (`chain.py:200`) is tested only with canned inputs. The edit to `prototypes/search-stack/test_e2e.py:296-299`, which now expects `; basis: ` after the EMPAD member's detail, has not been run (task 1.5 says so). The project's rules count "passing" only from `./runtest.sh e2e`, and they ask for a test per spec scenario.

**Where.** `tasks.md:31`; `specs/chain-trace/spec.md`, first scenario; `prototypes/search-stack/test_e2e.py:296-299`.

**Failure scenario.** If the stack's crawler image installs the em collection differently, or the trace's member line differs, the merge to `crawler` breaks the e2e suite, and nobody notices until the next stack run.

**Fix.** Before the merge: add `notes.gtg` (and `notes.dmw`) to the e2e tree's generator with a trace assertion on the crawler line, and run task 3.1 with `./runtest.sh e2e`, giving the number skipped.

### 4. Dropping the type of a file an earlier format claimed (low, CONFIRMED)

**What.** `not_of_type` does not know which files are already claimed. `run_post` appends every note to the basis of the dataset whose members include the file (`_noted`, `formats/__init__.py:451-456`), even when that dataset's format claimed the file before the drop.

**Where.** `formats/__init__.py:191-221, 364, 451-456`.

**Failure scenario.** `p2.py`: `test/claim` (priority 70) claims `x.tags` as `application/x.test-tags`, then `test/drop` (61) says it is not of that type:

```
/x.tags application/x.test-tags test/claim | claimed; test/drop: not application/x.test-tags, no TAGS header
```

The record says the file's type, and its basis says that it is not of that type. No warning is given, and the order check does not fire either, because `test/claim` does not react to the new type `text/plain`. No installed format does this today: `em/dmw` and `em/k2is` drop only files of their own types, which no other format claims.

**Fix.** In `run_post`, after each call, compare the call's dropped files with `claimed_by`. For one that is already claimed, warn ("`<format>`: `<file>` is claimed by `<earlier>`; type kept"), put its entry and note back, and add one scenario. Or state in TEMPLATE that a format must not drop a type it does not react to, and leave it at that.

### 5. "Leaving nothing out" for `.dmw` tags, but storage cuts them (low, CONFIRMED)

**What.** Spec `formats/dm`, "A .dmw file is described by all its tags", says the extractor yields every tag "with the reader's value … leaving nothing out" (`specs/formats/dm/spec.md:27`). The extraction cuts every stored string at 4,096 characters and every list at 1,000 entries (`extraction.py:43-44, 164-166`). BACKLOG ("`.dmw` description") mentions only the 1,000-phrase cut. The tests count phrases on the extractor's own output (`described` calls `fmt.extract` directly, `modama_formats_em/testing.py:91-100`), so they do not see the cut.

**Where.** `specs/formats/dm/spec.md:27`; `extraction.py:43-44, 164-166`; `BACKLOG.md:46`.

**Failure scenario.** `p3.py` on the stand-in `cl_image_dm4` (the `dmw_file` fixture): 298 phrases, 28,792 characters. The longest are `DocumentObjectList.TagGroup0.ImageDisplayInfo.CLUT [(0, 0, 0), …` (6,053 characters) and `PageSetup.Win32_DevModeW [77, 0, 105, …` (3,614 characters, a printer setting as a byte list). The stored description cuts the CLUT phrase in the middle. A real workspace with more than 1,000 tags loses the rest without a sign.

**Fix.** Word the requirement as "every tag … as the extraction stores it (strings to 4,096 characters, lists to 1,000 entries)", and name both limits in the BACKLOG item. The filter (decision 173's TODO) remains the real remedy.

### 6. Two code paths without a test (low, CONFIRMED)

**What.** (a) The requirement "A failed format call leaves every type as it was" names three causes: a failure, a budget overrun, a read error. Its scenarios and tests cover the failure and the read error, not the budget. `p2.py` shows the code handles it (`drop, then over budget`: `x.tags` stays `application/x.test-tags`, `single file`, warning `test/drop skipped: …`), but nothing guards it. (b) D1: "A tie among the rest is warned about as the walk warns about one" (`formats/__init__.py:213-216`). No test reaches that branch.

**Where.** `tests/test_content_checks.py`; `formats/__init__.py:213-216, 286-292`.

**Fix.** One test for each, in `test_content_checks.py`. The tie needs a MIME file with two equal globs left after the excluded one, for example `*.tags` at weight 60 and two types at weight 50 on `*.tags`.

### 7. Two names for the `.dmw` type in one record (low, CONFIRMED)

**What.** `em/dmw` has `display_name = "Gatan Digital Micrograph workspace"` (`dm/__init__.py:191`), which goes into `dc:subject`. The description's type name comes from the MIME comment, "Gatan Digital Micrograph .dmw file" (`dm/dm.xml`). `test_a_dmw_file_with_the_dm4_header` asserts both. A reader of one record sees two names for one kind of file. The project's wording rule asks for one term.

**Fix.** Use one name in both places. Choose it with @weber when Gatan's own name is confirmed (open item 155).

### 8. Warnings from a discarded call are kept (low, CONFIRMED by reading)

**What.** `_call` puts back `entries`, `notes` and the name index (`formats/__init__.py:289-290`), but not `d.warnings`. A call that warned through `not_of_type` (D2's "type kept", or a tie, `formats/__init__.py:203-216`) and then failed leaves those warnings beside "`<format>` failed".

**Failure scenario.** A format drops `a.tags` and gets the tie warning "type is ambiguous between …; using …", then raises. `a.tags` is back to `application/x.test-tags`, and the crawl still reports a tie for a type it does not carry.

**Fix.** In `_call`, keep the length of `d.warnings` before the call and cut back to it on failure, before adding the failure's own warning. Or leave the warnings as they are and say so in the spec.

### 9. Document inaccuracies (low, CONFIRMED)

- `design.md:161` (Migration Plan): "K2IS's new version and the new distribution version change the rule-set fingerprint". `modama-formats-em/pyproject.toml` still says `0.0.1.dev0`, and the diff does not touch it. The effect holds anyway: the new id `em/dmw`, K2IS's recognition `version` 2 and the changed bytes of `dm.xml` and `k2is.xml` all enter the fingerprint (`selection.py:138-165`).
- TEMPLATE now tells authors to set a priority above the formats that are to claim the new types. It does not say that changing a format's priority needs a new recognition `version`. Priorities are not in the fingerprint (`selection.py:155`), and with D3 a priority decides types as well as claims, so taken-over directories keep the old outcome.
- `modama-formats-em/README.md:10`, K2IS row: "a `.gtg` with other than 8 [sector files] stay[s] single files with a warning". A `.gtg` with none gets no warning (spec `formats/k2is`, "A tag file without sectors"). The wording is older, but this change rewrote the row.

## Outcomes (2026-11-12)

Each finding verified against the code before it was acted on; the coordinator's leans of 2026-11-12 decided 1, 2 and 7.

| # | Outcome | Where |
|---|---|---|
| 1 | Addressed (option A, the lean: the same data gives the same result or a failure; decision 185, a failure is retried by the next regular crawl; transient errors must not change good results). A read error on one file while it is checked keeps that file's type, warns at it (`<format>: cannot read <file>: <error>; type kept`) and sets `retry`; the format's call is not discarded. This changes the spec's earlier scenario "A read error while finding the new type", which made it the format's failure on the directory | `formats/__init__.py` (`Directory.cannot_read`, `not_of_type`), `dm/__init__.py` (`header`, used by `em/dmw` and K2IS); spec `recognition` ADDED "A read error on one file leaves the rest of the result", spec `formats/k2is` "A lone tag file that cannot be read", spec `formats/dm` "A .dmw file that cannot be read"; tests `test_a_read_error_while_finding_the_new_type`, `test_a_read_error_on_one_file_leaves_the_others`, `test_a_lone_tag_file_that_cannot_be_read` (both reads), `test_a_dmw_file_that_cannot_be_read`; design D1, D3; TEMPLATE |
| 2 | Left as it is until question 183; the specs now agree with the code: `formats/dm` excepts a lone `.gtg` without the DM4 header, `formats/k2is` has the scenario with today's outcome; the open question stays in the design | specs `formats/dm`, `formats/k2is`; `k2is/tests/test_with_the_dm_part.py`; design, "Open questions" |
| 3 | Addressed in part: `stray/notes.gtg` in the e2e tree, and a test of both `chain-trace` scenarios; `./runtest.sh e2e` pending (the VM's stack is held by another agent) | `prototypes/search-stack/test_e2e.py` (`STRAY_TAGS`, `test_the_crawler_line_shows_the_datasets_basis`); tasks 3.1, 4.3 |
| 4 | Addressed: the drop is undone, with a warning at the file naming the claiming format | `formats/__init__.py` (`run_post`, `Directory._undrop`); spec `recognition` ADDED "A claimed file keeps its type"; `test_a_file_an_earlier_format_claimed`; TEMPLATE |
| 5 | Addressed: the spec says what is stored (each phrase to 4,096 characters, the list to 1,000), and a test checks the stored form through `extraction.extract` | spec `formats/dm` "A tag longer than storage keeps"; `test_the_stored_dmw_description`; BACKLOG "`.dmw` description"; em README |
| 6 | Addressed: a test for each path | `test_a_format_over_budget_after_a_drop`, `test_a_tie_in_the_new_types_detection` (a `*.pair` rule at weight 60, two at 50); spec `recognition` scenarios for both |
| 7 | Addressed: one name, "Gatan Digital Micrograph workspace" (@weber's "DM workspace"; 184 open for the exact name), the type's comment in `dm.xml`; `em/dmw` has no `display_name`, so the subject uses the comment | `dm/dm.xml`, `dm/__init__.py`; `test_a_dmw_file_with_the_dm4_header`; spec `formats/dm`; design E1 |
| 8 | Addressed: `_call` cuts the warnings back on failure, before adding its own | `formats/__init__.py` (`_call`); spec `recognition` "A warning of a discarded call"; `test_warnings_of_a_discarded_call_go_with_it`, `test_a_format_fails_after_dropping_a_type` |
| 9 | Addressed | design, Migration Plan; TEMPLATE (a changed priority needs a new recognition `version`); em README, K2IS row |

## Notes, no action proposed

- Each drop copies the entry list (`formats/__init__.py:218`), and `_check_order` scans the entries for each dropped file (`formats/__init__.py:441`), so a directory of n entries with k drops costs O(n·k). That is negligible at staging's numbers (2,036 `.dmw` files, all with the DM4 header per F15, so no drops). It would matter only for directories with tens of thousands of misnamed files.
- `test_records_comments_a_single_file_whose_name_type_was_dropped` runs `python -m modama_crawler` in a subprocess, which finds the collections through the installed entry points. Here those come from `~/.venv`'s editable install of the main checkout, and the code comes from the worktree through the inherited `PYTHONPATH`. In CI the two come from the same checkout.

## What is right and should stay

- **Thread safety under the parallel walk.** `run_post` runs in a pool thread on a `Directory` built for one directory (`walk.py:350-351`), so the replaced entries, the name index, `notes` and `_format` are never shared. The new detection runs in that thread without the matching processes. pyxdg's `match_data` only reads its rule lists (`xdg/Mime.py:360-386`), so calling it from threads is safe, and the result equals `match_in`'s.
- **Putting back on failure.** `_call` snapshots `entries` (a new list replaces it on each drop, so the old reference is the state before the call) and a copy of `notes`, and restores them, with the name index, for every exception, including `BudgetExceeded` and `OSError` (`p2.py` confirms the budget case). `_check_order` runs after the restore, so a discarded call gives no order warning.
- **`mime.by_name` and `detect_with_tie(exclude=, strict=)`.** The refactoring keeps the early return for one best glob and leaves the walk's detection unchanged (the 11 existing `test_mime.py` tests pass). `strict` affects only the read. An excluded sniffed type counts as no match. `by_name` returns `str(candidates[0])` exactly as the walk's early return does, so D2's comparison with `entry.mime` is exact.
- **The uncharged read is really tested.** The budget test's database (core plus `*.tags`) has `Mime.magic.maxlen` 18,730 (`p2.py`). A charged detection would therefore exceed the test's 1,000-byte budget, and the test would fail.
- **The order check** fires only for formats that react to the new type, and none of the installed formats gives a false warning: before `em/k2is` run only `collapse` and `zarr` (`DIRECTORY`, excluded) and `em/dmw`, which reacts to its own type only.
- **K2IS keeps its outputs.** The grouping is unchanged. `tag_paths` with `_settings` skips exactly what `_tags` skipped. The seven existing recordings are untouched, and the 307-phrase test passes. Version 2 re-recognises, while extractor version 3 lets extractions be reused.
- **`em/dmw` selects by type**, so `p.DMW` is handled (`p1.py`: a PNG named `.DMW` becomes `image/png` with the note). A `.dmw` cut after its 16-byte header is claimed and fails at extraction (`p1.py`), which is "broken", as TEMPLATE's "check the signature only" intends.
- **Fixtures.** The two copies of RosettaSciIO files keep their GPL-3.0-or-later licence and are named in `LICENSE.fixtures`. The synthetic ones are MIT and `invalid-by-design`. The stand-ins say plainly that they hold an image, which a real workspace does not.
- **Take-over.** The stored type and basis come back through `crawl_tree` against a real database, without a format call, and the datestamps stay (`test_a_second_crawl_of_an_unchanged_directory`).
- **`records --verbose`** puts the basis through `render.comment`, which already makes `--` safe.
- No new dependency.

## Test results

All runs in the VM as user `dev`, with `PATH=~/.venv/bin:$PATH` and `PYTHONPATH` set to this worktree's sources:

- `python/crawler`: `pytest -q -p no:cacheprovider -rs`: **286 passed, 0 skipped**, 2 warnings (oaipmh-scythe deprecations), 160.8 s.
- `python/modama-formats-em`: **75 passed, 0 skipped**, 12.8 s (`test_coverage` included).
- `python/search-chain` (with its `src`): **31 passed, 0 skipped**.
- `uvx ruff format --check --diff` from the worktree root: 318 files already formatted. `uvx ruff check`: 7 errors, all in `prototypes/*.ipynb` (the known failures), none in the change.
- `openspec validate recognition-checks-content --strict`: valid. Three INFO lines say that archive would refuse the deltas until `parallel-walk` and `dm-containers-and-k2is` are archived, which is the archive order the proposal states.

Not run: `./runtest.sh e2e` (task 3.1; the VM's compose project `search-stack` was left alone), the visual check in a real terminal (xvfb, xterm, xdotool and ImageMagick are not installed), and anything on real `.dmw` or DM3 `.gtg` files (none available; the `.dmw` fixtures are stand-ins with an image).
