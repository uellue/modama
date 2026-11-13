# Hallway test of the crawler developer docs: report (clone-6c)

## 1. For people

- **Task (a), MRC format: done.** Committed as `fc69233`. It recognises `.mrc`/`.map`/`.mrcs` files, and extensionless files by their stamp. It extracts the header with mrcfile 1.5.4 (a new dependency). The person said to skip the independent review, and browse was not possible here, by rule.
- **Task (b), Merlin `UnicodeDecodeError`: done.** Committed as `4d8d40e`. The README and BACKLOG describe a Latin-1 workaround and a fixture `not_utf8`; neither was in the code. I put both back, with a test that failed with the reported error and passes now.
- **Tests:** em, common and crawler suites pass with 0 skipped. search-chain could not run: its submodules are empty in this clone, which has no remote.
- **The three doc gaps that cost the most:**
  1. **The read budget is undocumented.** It is 1 MiB per directory and format; when it runs out, the format is skipped for the whole folder. For MRC that caps a folder at about 4,900 files.
  2. **"Let the reader read from your handle" doesn't cover a reader whose bounded mode isn't bounded.** mrcfile's `header_only` still reads the whole extended header (909 kB for EPU files).
  3. **`openspec validate --strict` fails on the model change too.** The docs don't say whether those warnings are acceptable.

## 2. Setup

- **Time:** start 08:21:22 UTC, end 08:50:09 UTC. About 80 tool calls.
- **`expectations.md`:** written between 08:21:45 and 08:22:22. I first wrote "08:24" in its header from a guess, then corrected it. Additions at 08:25 and 08:33.
- **Given:** the brief, the clone, the scratch folder.
- **Attached unasked by the harness:**
  - the clone's top-level `CLAUDE.md`/`AGENTS.md`, and `python/crawler/AGENTS.md` once I worked there;
  - git status;
  - memory instructions for `~/.claude/projects/-var-tmp-hallway-run2-clone/memory` (not used);
  - a skill list including `format-collection` (read from the clone as a plain file, never invoked), the kaizen skills, and the clone's openspec skills.
- **Hook:** `no-inline-edits` flagged my heredoc appends to scratch files (a warning only).

## 3. Task (a)

**E0.1: install into my own venv.** README promises one line.
- `uv venv --python 3.14 …/venv`, then the four `-e` installs from AGENTS.md.
- 1.5 s. **Matches.**

**E0.2: `modama-crawler records --verbose tests/`.**
- 29 records in 3 s, each with a "why" comment. **Matches.**

**E1: talk with the person (SKILL step 1).**
- I sent six numbered questions. The answers came within minutes.
- No real files; mrcfile approved; skip the review; decide the rest, record leans. **Matches**, but where to write the answers down is a gap (G4).

**E3: MIME type.**
- Checked `/etc/mime.types` (`.mrc` is `application/marc`, as TEMPLATE warns), the vendored freedesktop file (nothing) and one web search (nothing). Chose `application/x.mrc`.
- **Gap (G5):** TEMPLATE doesn't say where else to look.
- `records --verbose` on EMD-3197.map before the change gave `application/octet-stream`, "Unknown, 1 file". **Matches.**
- **Bug:** that file got no `<!-- … basis -->` comment; the text file next to it did.

**E2/E4′: spec.**
- `openspec new change em-mrc` took 0.9 s; `openspec instructions proposal` worked.
- `openspec validate em-mrc --strict` said "has issues" for two requirements over 500 characters. `common-structured`, the model AGENTS.md says to copy, gives four of the same warnings. **Surprising** (G12).

**E5: fixtures.**
- EMD-3197.map from mrcfile 1.5.4's sdist. It is byte-identical to the decompressed `emd_3197.map.gz` from EMDB (sha256 `351d5090…`).
- Licence: CC0, per the EMBL-EBI public data-access statement and the wwPDB advisory (unmodified files may be redistributed). I verified this on the web.
- Generated with mrcfile: `single_image` (mode 0) and `image_stack` (`.mrcs`).
- Composed: `misnamed`, a GNU ld map and a MARC 21 record. **Matches.**

**E7′: first test run.**
- Bugs of mine: the header was a plain ndarray instead of a recarray; `Extracted` requires `subjects` (G10); `.item()` on a 0-d bytes array.
- **Surprising but defensible:** the first run recorded `{"error": "AttributeError"}` into `expected/` for representative fixtures. TEMPLATE step 5 says to delete those and fix the code; I did.
- `--regen-expected` named the change precisely (`voxel_size [11.4…] -> [11.399999618530273…]`). **Matches.**

**E9: testing.**
- `pytest src` (em): 153 passed, 0 skipped, 30 s; the same with `TZ=Europe/Berlin`.
- `records --verbose` on the fixtures folder shows only the fixture on disk; generated ones never appear (G11).
- Lint: `uvx pre-commit run --all-files` failed once on import order (G13), then passed.

**E10: independent review.** Skipped on the person's instruction; recorded in `tasks.md` and the commit.

**Hand-over for people:**
- Format `em/mrc`, priority 60, one dataset per file.
- Example summary line: `mode 2, nx, ny, nz 20, 20, 20, cella 228.0, 228.0, 228.0, ispg 1, ::::EMDATABANK.org::::EMD-3197::::`
- A few `original_metadata` lines: `cella.x: 228.0`, `machst: [68, 65, 0, 0]`, `map: MAP `, `label[1]: ::::EMDATABANK.org::::EMD-3197::::`, `rms: 2.3999528884887695`.
- Skip list: `extra1`, `extra2`, unused label slots.
- New dependency: `mrcfile==1.5.4`, BSD-3-Clause, pure Python.
- Open questions with my leans:
  - **Q2:** grouping of related MRC files is a later change.
  - **Q6:** files without the `MAP` stamp lose their type (lean: accept until one is seen).
  - **Q7:** budget overflow above about 4,900 files per folder (lean: accept until such a folder is seen).
- Deviation from the docs: I wrote the code before the tests (G18).

## 3. Task (b)

**E13: see it.** Browse is not possible here, by rule. I worked from @weber's quote.

**E14: ours or upstream's?**
- `read_header` uses `open(path)`; RosettaSciIO 0.15.0's `parse_hdr_file` does the same; the locale is `C.UTF-8`.
- So the cause is ours: the workaround the docs describe was missing. README step 2 warns about exactly this. **Matches.**
- With history I would have run `git log -S latin-1` to see when it went.
- **Gap (G15):** nothing says to check the worker's locale.

**E15′: reproducer.**
- New generator `not_utf8`: `date_order`'s staging lines plus `Sensor Bias (V, µA)\t120 V` with µ as the byte 0xB5. `date_order` keeps the same bytes.
- I found no Merlin recipe in `design/testing.md` (G14).

**E16′: red run.**
- The new test failed with `'utf-8' codec can't decode byte 0xb5 in position 690: invalid start byte`, the error @weber reported.
- The plugin recorded nothing for the failing reproducer ("fix the code first"). **Matches** README step 4.

**E17: fix.**
- Unbuffered read, `TextIOWrapper(BytesIO, encoding="latin-1")`, so lines still split as in text mode.
- Merlin tests: 19 passed. The other fixtures' recorded results are unchanged.
- Spec scenario "A header in Latin-1" added to `em-formats-and-extraction`.

**E18: BACKLOG "Sync with upstream".** Already says "worked around here", which is now true again. No change.

**Final suites, after both commits:**
- crawler: 501 passed, 0 skipped, 8 min 48 s (the earlier run: 8 min 11 s, 501 passed).
- em: 155 passed (twice, both time zones); common: 276 passed (twice).
- search-chain: 3 failed, 73 passed. The failures say `submodule not checked out … git submodule update --init …`, as "fail, don't skip" promises.
- Lint passed.
- Where my setup differs from CI: user `dev`; my own venv; CI runs only the lint.

**Hand-over for people:**
- Symptom: `UnicodeDecodeError` on `acq.hdr`.
- Cause: the header was decoded as UTF-8, and the Merlin software writes µ as the single byte 0xB5.
- Fix: read it in Latin-1.
- Reproducer: `not_utf8` with `test_a_header_in_latin_1`, red before the fix and green after.
- The reload in browse on the real file is still for @weber to do.

## 4. Commits in the clone

```
4d8d40e em/merlin: read the header in Latin-1 again, with a reproducer
 merlin spec.md +4, merlin/__init__.py ±10, expected/not_utf8.json +75,
 fixtures.toml +7, generate.py ±82 (refactor + not_utf8), test_extract.py +6
 6 files changed, 153 insertions(+), 31 deletions(-)
fc69233 em/mrc: MRC2014 files (.mrc, .map, .mrcs), one dataset per file
 crawler/BACKLOG.md +1, crawler/README.md ±1, openspec/changes/em-mrc/{proposal,spec,tasks}
 modama-formats-em/{README.md,pyproject.toml,__init__.py}, mrc/{__init__.py,mrc.xml}
 mrc/tests/{fixtures.toml,LICENSE.fixtures,generate.py,test_mrc.py,expected/*.json(4),EMD-3197.map}
 22 files changed, 913 insertions(+), 2 deletions(-)
```

## 5. Doc gaps, ranked by cost

1. **G6, read budget.** I needed its size and what happens when it runs out. Found in `formats/__init__.py:304,326`. Belongs in TEMPLATE, "Rules first" (next to `d.read`) and the checklist "Read only what is needed".
2. **G7, an "unbounded" bounded mode.** mrcfile's `header_only` reads the extended header. Found in mrcfile's source. Belongs in TEMPLATE, "Extracting metadata": measure the reader's own bounded mode too, or decode the header yourself with the reader's definitions.
3. **G3, MRC already mentioned.** BACKLOG (the `em/de` item: "found by the em/mrc agent") and TEMPLATE (`mrcfile.new`, "MRC's mode 0", "11.399999618530273 for a stored 11.4") describe an MRC format that isn't there. It cost me a search and some doubt whether MRC existed. Belongs: BACKLOG should match the tree.
4. **G12, `--strict` warnings.** Followed the model change. Belongs in AGENTS.md "OpenSpec".
5. **G10, `subjects` is required.** Found from a TypeError. Belongs in TEMPLATE's `Extracted` example.
6. **G15, the locale.** Belongs in README step 2, next to "check which version runs".
7. **G11, generated fixtures by hand.** No way given to look at one with `records`. Belongs in TEMPLATE, "Testing a format".
8. **G16/G17, hand-over and merge for a lone agent.** Where the hand-over goes; what "merge" means without the `crawler` branch. Brief resolved it. Belongs in SKILL step 6 and README step 7.
9. **G5, MIME lookup.** Where to look beyond Debian and freedesktop. Belongs in TEMPLATE.
10. **G14, recipes.** The Merlin recipe is only README's worked example; `testing.md` has none.
11. **G13, import order.** `modama_crawler` sorts as third-party; the lint told me.
12. **G18, red run for a new format.** How to show one before the module exists.
13. **G19, other docs to update.** The crawler README's em list and BACKLOG, found by grep.
14. **G4/G9, the person's answers.** Where to write them down; I used the proposal.
15. **G8, synthetic fixtures.** `openspec/config.yaml` says "Synthetic files only in the core's rule-processing tests"; TEMPLATE allows generated fixtures. I followed TEMPLATE.
16. **G1, paths.** `/workspaces/…`, `~/.venv`, worktrees from `crawler`; the brief resolved them.

## 6. Bugs, surprises, questions, suggestions

**Bugs, ranked:**
1. **Docs vs code drift on the Merlin fix** (README worked example, the em README, BACKLOG) until `4d8d40e`. Nothing but the deleted test guarded it.
2. **BACKLOG mentions a format and an earlier hallway G8 that aren't in the tree.**
3. **`records --verbose` gave no basis comment** for an unclaimed `application/octet-stream` file.
4. **Figures in README "Running tests" are low.** Crawler suite 8–9 min and 466 MB (README: 5–7 min, 390 MB); em 30–35 s and 142 MB (README: 25 s, 130 MB). Measured with other suites running alongside.
5. **The model OpenSpec change fails `--strict`.**

**Surprises:**
- The plugin refuses to record a failing reproducer, and `--regen-expected` names each change. Both very good.
- A representative fixture's first run silently records an `"error"`. It is documented, but easy to commit by mistake.
- mrcfile's `set_data` makes 3-D data a volume (space group 1); a stack needs `set_image_stack()`.

**Question asked:** one message, MRC step 1, items 1–6. Answers: no real files; assume maps and stacks from any software; grouping later; mrcfile approved; summary line from dimensions, mode, cell, kind and labels; labels go through the credential check; old files without the stamp are my call; skip the review; no stack or Docker.

**Inputs I invented:**
- the type `application/x.mrc`;
- the summary line's composition, the skip list, and the `kind` words (taken from mrcfile's method names);
- the change name `em-mrc`;
- the leans on Q6 and Q7;
- the linker map and MARC record fixtures;
- the `not_utf8` header: `date_order`'s lines plus the brief's Sensor Bias line.

**Suggestions for the documentation:**
- Put `BYTE_BUDGET` and its failure mode in TEMPLATE.
- Add "measure the reader's bounded mode" to the "Read-only libraries" checklist item.
- Mark `Extracted.subjects` as required.
- Add the locale check to README step 2.
- Say how to inspect generated fixtures by hand.
- Say whether `--strict` warnings block a change.
- Remove `em/mrc` and earlier-hallway references from BACKLOG/TEMPLATE, or mark them as examples.
- Update the test times and temp sizes in README.

Sources used for the licence and the MIME type:
- [EMBL-EBI public data-access statement](https://www.ebi.ac.uk/pdbe/about/public-data-access-statement)
- [wwPDB advisory](https://files.pdbjlvh2.pdbj.org/pub/pdb/advisory.txt)
- [EMDB policies](https://www.ebi.ac.uk/emdb/documentation/policies)
- [mime-types.pages.dev, `.mrc`](https://mime-types.pages.dev/file-extension/mrc)