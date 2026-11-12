# Review of dm-containers-and-k2is, 2026-11-12

Scope: `git diff ff777a6..dm-containers` at 2d9ab8b (commits 4f0a6ec on `dm-handle`, f9b3c9d, ab13b68, 2d9ab8b): `modama-formats-em` (`dm/`, `k2is/`, package `__init__.py`, README) and this change's proposal, design, specs and tasks. By an agent that did not write the code, given the code, the change's spec deltas, the main specs (`recognition`, `crawl`, `mime-database`, `extraction` in `em-formats-and-extraction`), staging findings F14 and F15, decision 71, the values rule in the package README, `formats/TEMPLATE.md`, the repository's `AGENTS.md`, RosettaSciIO 0.15.0 (`rsciio/digitalmicrograph/_api.py`) and LiberTEM's `src/libertem/io/dataset/k2is.py` (master d6aa0fa, 2026-10-22). Every finding below was checked against the code; the ones marked CONFIRMED were reproduced with scripts in the session's scratchpad (`rev-dmk/scripts/`: `cmp.py`, `trees.py`, `tie.py`, `trunc.py`, `fds.py`, `rec.py`), run with the worktree's `modama_crawler` and `modama_formats_em` first on `sys.path` and the MIME database of all installed collections (core, collapse, em, zarr).

Test runs at 2d9ab8b: `modama-formats-em` 45 passed (the coverage test included); crawler suite 267 passed, 0 skipped, 0 failed (PostgreSQL through pytest-postgresql); `uvx ruff check python/` clean, `ruff format --check` clean. Note on the runs: `~/.venv` has both packages installed editable from `/workspaces/data-management-system` (branch `crawler`). The collection suite still tests the worktree's code because pytest's prepend import mode puts the worktree's `src/` first. The crawler suite imports the installed `modama_crawler` unless `PYTHONPATH` points at the worktree, which is how it was run here. The crawler source is identical between ff777a6 and the `crawler` head e35e4b4, so either way it tests the same code.

Severity: **H** a defect at the stated scale or a crash; **M** a defect in a reachable case, or a drift between code and contract; **L** cleanliness, docs, tests. No H findings.

## Findings

| # | Sev | Verdict | Where | Finding |
|---|---|---|---|---|
| 1 | M | CONFIRMED | `dm/dm.xml:28-38`, `k2is/k2is.xml:11-20`, design D1 | `.dmw`/`.gtg` are typed by name alone. The content check that D1 and the XML comments describe never runs, so text and empty files get the Gatan type |
| 2 | M | CONFIRMED | `k2is/__init__.py:22,64-70`, design D4 | The K2IS description lists every leaf of `Microscope Info` (14 phrases, the first of them placeholder zeros), not the voltage and name that D4 names. The date and the detector, which the DM part shows, are left out |
| 3 | L | CONFIRMED | `k2is/__init__.py:36-59` | Grouping edge cases. The warning says "without a .gtg file" when the `.gtg` is right there. An incomplete capture with a longer stem blocks a complete neighbour. `.GTG` is matched in any case, `.bin` only in lower case |
| 4 | L | PLAUSIBLE | `k2is/__init__.py:79-91` | `_group` takes the first group of that name in depth-first pre-order, which depends on tag order, not on depth. LiberTEM reads `.SI Dimensions` at the root only |
| 5 | L | CONFIRMED | `k2is/__init__.py:94-95` (and `dm/__init__.py:89`, pre-existing) | `:g` rounds float tags to 6 significant digits, which goes against "show what the file says" |
| 6 | L | PLAUSIBLE | `dm/__init__.py:31` | `posix_fadvise` errors are not suppressed, as they are in `mime.py:190-192`. An OSError (or a platform without it) fails every DM and K2IS extraction |
| 7 | L | CONFIRMED | `dm/__init__.py:37-58`, `pyproject.toml:14` | The claim that `first_image` matches `file_reader` has no test in the repository, and it relies on private RosettaSciIO classes. The pin's comment names Merlin only. `ImageList` keeps its key position (no effect on output) |
| 8 | L | CONFIRMED | crawler `README.md:119`, `formats/TEMPLATE.md:93` | The documented rule is "read unbuffered"; `dm.parsed` uses a 64 KiB buffer. The pitfall and the template now contradict the code |
| 9 | L | CONFIRMED | `dm/tests/fixtures.toml` `dmw_file`, `k2is/tests/fixtures.toml` `lone_tags`, `capture52` | The `.dmw` and lone `.gtg` fixtures hold an image, so the scenarios' "holds no image" is not met. The `capture52` sectors are cut to 40 bytes but labelled representative. The cut script is gitignored |
| 10 | L | CONFIRMED | `dm/tests/test_extract.py:25-29` | The THEN "its record does not name it a Digital Micrograph image" is not asserted. "Reads no larger than NFS's read size" is checked only as a total |
| 11 | L | CONFIRMED | `proposal.md:16,32`, `design.md:21,26,28`, `tasks.md:11` | Stale or wrong statements in the change's documents: "deleted records" (the crawler publishes none), "not checked on a real .gtg", a reproducer versus representative fixture, the synthetic fixture's numbers |

### 1. `.dmw` and `.gtg` are typed by name, whatever the content (M, CONFIRMED)

**What.** D1 says: "The name decides; content would say DM4, and the name match, being its subclass, wins". The XML comments say: "a name match that is a subclass of the sniffed type wins". In `mime.py:179-183` a single glob match returns at once, with no content read. The sub-class rule (`mime.py:205-210`) only acts when several globs tie, and nothing makes `*.dmw` or `*.gtg` tie. So `sub-class-of application/x.dm4` has no effect on detection, and any file with these names gets the Gatan type. The spec delta does say "typed by its name", so the code meets the spec, but the design's reasoning and the comments describe a check that does not exist. The result goes against what F15 set out to fix: records that tell a searcher something false. It also goes against the `formats/dm` principle that a name without the header does not get the DM type.

**Failure scenario** (`trees.py`, `rec.py`): `notes.gtg` and `notes.dmw` holding `hello\n`, and an empty `empty.dmw`, are typed `application/x.dm-gtg` and `application/x.dm-dmw`. Their records say "Gatan Digital Micrograph .gtg tag file" and "Gatan Digital Micrograph .dmw file". A text file named `X_.gtg` next to 8 sector files becomes a K2IS dataset, and its extraction then fails with `NotImplementedError` (not DM version 3 or 4).

**Fix.** Force the content check the way `core/er-c.xml` does for `*.raw`: give the fallback type the same globs, for example in `dm.xml`:
```xml
<mime-type type="application/octet-stream">
  <glob pattern="*.dmw"/>
  <glob pattern="*.gtg"/>
</mime-type>
```
The two candidates then tie, the content is sniffed, and the subclass of the sniffed DM4 type wins. Checked with `tie.py`: Capture52_.gtg's content named `a.gtg` or `a.dmw` gives `application/x.dm-gtg` or `application/x.dm-dmw`. Text, empty and DM3 content gives `application/octet-stream`, without a tie warning. A DM3 `.gtg` would then lose the type; staging's 33 have the DM4 header (F15), but that should be decided. Reword the dm spec delta to "named `*.dmw` or `*.gtg` with the DM4 header", and add a scenario and fixture with a text file named `.dmw`. **Ask** @weber, since the spec as written says "by its name".

### 2. The K2IS description: the whole `Microscope Info` group (M, CONFIRMED)

**What.** D4: "the `Microscope Info` voltage and name". The code puts every non-group tag of the group into the summary. The proposal, the spec ("the microscope tags") and the README ("the `SI Dimensions` and `Microscope Info` tags") match the code; the design does not. On Capture52 the description is 16 phrases: `SI Dimensions.Size X 35, SI Dimensions.Size Y 34, Microscope Info.Cs(mm) 0, Microscope Info.Emission Current (µA) 0, … Probe Current (nA) 0, Probe Size (nm) 0, … Voltage 300000`. Four of them are zeros that the FEI Tecnai Remote interface writes as placeholders, and the test pins `Cs(mm) 0` as the third phrase. Showing what the file says is within the values rule, but choosing which tags to show is not editorialising, and dc:description is what the search embeds. The `.gtg` also holds `DataBar.Acquisition Date`/`Time` and `DataBar.Device Name` (`K2-IS-0001`), which the DM part shows for images (date, detector) and which serve R30. A tag that holds an empty string comes back from RosettaSciIO as `[]` (seen in `Session Info` here) and would show as `Microscope Info.Name []`.

**Failure scenario.** Every K2IS record's description starts with a run of zeros, and has no date and no detector.

**Fix.** A short list of exact tag paths, as D4 says, for example `SI Dimensions` Size X/Y, `Microscope Info` Voltage, Name, Indicated Magnification, STEM Camera Length, Operation Mode, and `DataBar` Acquisition Date, Acquisition Time, Device Name. Leave out empty lists. Or, if the whole group is wanted, update D4. **Ask** @weber which.

### 3. Grouping edge cases (L, CONFIRMED)

**What and scenarios** (`trees.py`):
- `X_.gtg` with 7 or with 9 sector files gives the directory warning "7 (9) K2IS sector file(s) without a .gtg file and its 8 sectors". The `.gtg` is there, and nothing names it or says how many sectors it found.
- `scan_.gtg` with `scan_1..8.bin` (complete) next to `scan_2_.gtg` with 7 sectors: the longer stem claims nothing, `scan_` then sees 15 candidates, and both captures fall apart into 17 single files. This matches the spec's wording ("exactly 8 … whose names start with the stem") and LiberTEM, which would refuse `scan_.gtg` too. Still, one missing sector also takes down an unrelated, complete capture.
- `X_.GTG` with `X_1..8.bin` is grouped (shared-mime-info globs are case-insensitive). `X_.gtg` with `X_1..8.BIN` is not (`s.name.endswith(".bin")`, line 43). LiberTEM lower-cases the extension of the path it is given but globs `*.bin` case-sensitively on Linux, so it would behave the same. Whether GMS on Windows ever writes `.BIN` is unknown.

**Fix.** Warn per `.gtg` when its count is wrong, anchored at it: "X_.gtg: 9 sector files X_*.bin, a K2IS acquisition has 8". In the longest-stem-first loop, take a stem's candidates out of the pool even when their count is wrong, so that `scan_` sees only its own 8. That is a deliberate step away from LiberTEM, so record it in D3. Decide whether `.bin` is compared case-insensitively.

### 4. `_group` depends on tag order (L, PLAUSIBLE)

**What.** `_groups` walks the tag tree depth-first in pre-order, so the "first" group of a name is the first in key order, at any depth. A nested group inside an earlier top-level group beats the top-level one. In Capture52 the root holds `Acquisition, Calibration, DataBar, GMS Version, Microscope Info, Session Info, SI Dimensions, SI Image Tags`, so the top-level `Microscope Info` wins over `SI Image Tags.Microscope Info` only because `SI Image Tags` sorts later. `Acquisition`, which sorts earlier and has deep subgroups, holds no `Microscope Info` in this file. LiberTEM reads `.SI Dimensions.Size X/Y` at the root only (`_get_nav_shape`). A nested `SI Dimensions` somewhere else would be shown as if it were the scan shape.

**Failure scenario.** A `.gtg` whose `Acquisition` subtree holds a `Microscope Info` group (not seen; no second real `.gtg` to check) would show that group instead of the root one.

**Fix.** Exact paths: `tags.get("SI Dimensions")` and `tags.get("Microscope Info")` at the root, with `SI Image Tags.Microscope Info` as an explicit fallback if wanted. This also makes finding 2's list simple.

### 5. `:g` rounds values (L, CONFIRMED)

**What.** `_shown` formats floats with `:g`, which keeps 6 significant digits: `1234567.0` becomes `1.23457e+06`, `11767.000891268253` (`Objective focus (um)` in the DM fixture `cl_image_dm4`) becomes `11767`, and `36.65069946289063` (`Field of View (µm)`) becomes `36.6507`. Capture52's values happen to be round, so the test does not show it. The DM part has done the same since `em-formats-and-extraction` (`dm/__init__.py:89`).

**Fix.** `repr(value)` with a trailing `.0` dropped, or `:.15g`; alternatively record the rounding as intended in the README's "Values and units" and the backlog's "Units and meaning".

### 6. `posix_fadvise` without a guard (L, PLAUSIBLE)

**What.** `parsed()` calls `os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_RANDOM)` with no guard. `mime.py:190-192`, the core's use of the same call (parallel-walk D6), wraps it in `contextlib.suppress(OSError)`, because the advice is an optimisation. On a file system that rejects the advice, every DM and K2IS extraction fails, as an environment failure retried on every crawl. On a platform without `posix_fadvise` (macOS, Windows) the call raises `AttributeError`. That is moot for the deployment, since `mime.py` has the same `AttributeError`, but it matters for anyone running the extraction tests there. Not reproduced: no file system here rejects the advice.

**Fix.** `with contextlib.suppress(OSError, AttributeError): os.posix_fadvise(...)`, as in `mime.py`.

### 7. The `file_reader` equivalence is not tested, and the pin's reason is out of date (L, CONFIRMED)

**What.** `first_image` copies `file_reader`'s loop body (0.15.0) without `get_data`, using the private `rsciio.digitalmicrograph._api` classes. The docstring and F14 say "identical results on RosettaSciIO's 98 DM test files", but no test in the repository compares the two, so a RosettaSciIO upgrade that changes `file_reader` (or `ImageObject`) would go unnoticed. `pyproject.toml:14` gives Merlin's private import as the only reason for the exact pin. A small difference was found (`cmp.py`, 7 files that both read: the 5 local RosettaSciIO samples and the two DM fixtures `cl_image_dm4`, `stem_image_dm3`): axes, metadata, original_metadata (as dicts) and mapping (paths and targets) are equal, but the key order of `original_metadata` is not. `file_reader` deletes `ImageList` and inserts it again at the end; `first_image` assigns it in place (line 50). Nothing reads that order today. RGBA (`test-8.dm4`) works where `file_reader(lazy=True)` refuses it; the files that fail (a misnamed text file, a tags-only DM4) fail the same way in both. Not checked: the other files of the 98.

**Fix.** A parametrised test over the DM fixtures: `first_image(p)` against `file_reader(p, lazy=True)[0]` (axes, metadata, original_metadata, mapping keys and targets), with RGBA expected to fail on the `file_reader` side. Name `dm` and `k2is` in the pin's comment. Either move `ImageList` to the end as `file_reader` does, or say "equal as dicts" in the docstring.

### 8. The buffer rule in the docs contradicts the code (L, CONFIRMED)

**What.** The crawler README's pitfall (`README.md:119`) and `TEMPLATE.md:93` say: read file contents unbuffered. `dm.parsed` deliberately uses `buffering=64 KiB` with readahead off, for good reasons (RosettaSciIO reads the tag tree in pieces of 1 to 8 bytes, and production's `rsize` is 64 KiB according to `requirements-benchmark.md`). The reason is in a code comment only. The next format author reads the pitfall and either opens unbuffered or wonders which rule holds.

**Fix.** One sentence in the pitfall (its one home): "or, for a library that reads in tiny pieces, a buffer of NFS's `rsize` (64 KiB) with readahead off, as `modama_formats_em.dm.parsed` does (F14)"; the template points to it.

### 9. Fixtures (L, CONFIRMED)

**What.**
- `dmw_file` and `lone_tags` are the DM4 image `cl_image_dm4` renamed. The spec scenarios say "starts with the DM4 header and holds no image", and staging's `.dmw` files hold none (F15). The test still catches a regression through `d.format == ""`, but the fixture is not the case it names. `Capture52_.gtg` is a real DM4 file with tags only (`get_image_dictionaries()` returns `None`, as with staging's `.dmw` files), under MIT, and would meet the WHEN for both.
- `capture52`'s sector files are each the first 40 bytes of the real file. LiberTEM's `DataBlock.is_valid` also requires `filesize >= offset + BLOCK_SIZE`, so LiberTEM would reject them. The manifest marks them `representative`/"vendor-written", while the proposal's Impact (line 32) planned "a reproducer cut from a real capture". The cut is honestly described in `validity` and agreed (decision 73), so this is about the label and the coverage rule it satisfies. TEMPLATE: representative means "a realistic file as found in the wild".
- `source` names `.claude/field-tests/k2is-fixture.sh`, which is under `/.claude` in `.gitignore` (line 15), so nobody else has it. The `validity` text is enough to redo the cut, so this is minor.

**Fix.** Generate `dmw_file` and `lone_tags` from `Capture52_.gtg` (and update their licence lines to MIT). Either mark `capture52` as a reproducer, with a sentence in the manifest on why the sector magic counts as covered, or note the exception in the TEMPLATE. Drop the script path or commit the script.

### 10. Spec scenarios asserted in part (L, CONFIRMED)

**What.** "A .dmw file with the DM4 header" has the THEN "its record does not name it a Digital Micrograph image". The test checks type and format only. The record says "Gatan Digital Micrograph .dmw file, 1 file, 611.4 kB, in /" (`rec.py`), which is fine, but nothing pins it. The new `em-formats-and-extraction` scenario "in reads no larger than NFS's read size" is checked only as a total (`bytes_read < 100_000`). A check on the largest single read (for example `syscr` and `rchar` from `/proc/self/io`, or a wrapped `FileIO`) would test what the scenario says.

**Fix.** Assert `records.description(d)` for the `.dmw` and the lone `.gtg`. Either assert the largest read is at most 64 KiB, or reword the scenario to the total.

### 11. The change's documents (L, CONFIRMED)

- `proposal.md:16`: "Identifiers of the 8 sector files' former records disappear from the OAI-PMH endpoint (deleted records)". The crawler publishes no deletions (`deletedRecord=no`, `server.py:221`, README pitfall line 118), so harvesters keep the 8 stale sector records of every capture already harvested (staging: up to 32 captures, by F15's count of `<stem>_.gtg` files). Say so, or point to the backlog entry on deletions.
- `design.md:26,28` and D4 (line 21) still say the tag names are "not checked on a real `.gtg`" and "no real K2IS capture … in the VM"; task 3.1 has since done both.
- `proposal.md:32` says the K2IS fixture would be a reproducer; see finding 9.
- `tasks.md:11` (2.2) quotes the synthetic fixture's figures (358 bytes of 179,112; 44 passed, 1 failed). That is history, but the line reads as the current verification. Task 3.3 is listed before 3.2.

## What is right and should stay

- **`first_image` is faithful.** On every file tried that `file_reader` reads, the results are equal apart from key order (finding 7). RGBA images now give their tags. Truncated DM and `.gtg` files still fail as the file's failure (`struct.error`), and a tags-only DM4 named `.dm4` fails as before. The `with` block closes the handle on success and on error: `fds.py` found no descriptor leak over 20 good and 20 broken extractions. The image data is never read or mapped, and the `DigitalMicrographReader` is reused for K2IS rather than copied.
- **Re-crawl behaviour is correct.** The rule-set fingerprint (`selection.fingerprint`) hashes the collections' MIME XML and the formats with their versions, so the new globs and the K2IS format cause every directory to be recognised again on the next crawl: `.dmw`/`.gtg` files typed as DM4 do not linger. Raising `extractor_version` to 3 is necessary, since stored file failures are reused, and it is what makes the 604 RGBA failures run again. Expect a full re-extraction of every DM file on that crawl, cheaper per file than before (F14: 132 kB instead of 1,154 kB on the VM's NFS). The `.gtg` anchors keep their identifiers, so those records are updated, not replaced.
- **The sector magic is LiberTEM's block header exactly.** The sync word at 0, width 256 at 20 and height 1860 at 22 match `DataBlock.header_dtype` and `is_valid`. The magic fixes 8 bytes, so a random `.bin` matches with negligible probability. There is no `*.bin` glob, and none exists in any installed collection. All eight fixture headers decode as expected (width 256, height 1860, block size 0x5758). `foo.dm4` holding a sector header is typed as a sector, since the DM types have no globs.
- **Grouping is order-independent and deterministic.** Ties in name length cannot compete for the same sector, the orphan warning names the first orphan in sorted order, and the members come out sorted. Nested stems (`scan_` and `scan_2_`, both complete) group correctly, and so do a `.gtg` plus an unrelated `X_log.bin`, and `X.gtg` next to `X_.gtg`. `Directory.of_type` compares types exactly, so the DM4 format does not take the subtypes. Recognition reads no file.
- **K2IS extraction reads only the `.gtg`** (under 28 kB for a 26,931-byte file), shows tags under their own names with no units added, and takes the subject from the string tag `Name` only.
- **Tests and fixtures.** One test per spec scenario, with recorded expected results that are consistent (`capture.json` was renamed to `capture52.json` with identical content). The real capture comes with a sha256, `LICENSE.fixtures` beside it and a clear statement of what was cut. The coverage rule passes with every glob, magic rule and format fired. The synthetic `other_bin` (`data.bin`, `sector.dat`) covers the content-not-name requirement.
- No new dependency; the K2IS part follows the Merlin part's pattern (types for both kinds of file, longest stem first, one orphan warning per directory).

## Not verified

- F14's NFS figures (bytes and time per file with the 64 KiB buffer). The suite measures `rchar` on a local disk only.
- The "98 RosettaSciIO files identical" claim beyond the 7 files available locally.
- Whether `.gtg` files are ever DM3, whether GMS writes `.BIN`, Gatan's own name for `.dmw`, and whether other software uses `.dmw` or `.gtg`.
- The owner's agreement for Capture52 (decisions 73, 79), taken as recorded.
