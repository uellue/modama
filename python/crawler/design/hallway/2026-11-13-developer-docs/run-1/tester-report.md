## 1. For people

- **(a) MRC: done** and committed (`68d65d5`). It adds format `em/mrc` with a spec, fixtures and tests, and passes every suite I could run. The independent review was skipped on your instruction. Browse was not possible here, by rule.
- **(b) Merlin: done** and committed (`1330279`). The `UnicodeDecodeError` came from our own `merlin.read_header`, not from RosettaSciIO. It opened the header in the locale's encoding, while four documents say it reads Latin-1. Fixed, with a reproducer `not_utf8`; the new test failed with the staging error before the fix.
- The three doc gaps that cost most:
  1. **The fixture recorder stores a failure as the expected result.** On the old code `test_fixture` recorded `{"error": "UnicodeDecodeError"}` and asked me to review it and run again. TEMPLATE's "read them, then run again" would have locked the bug in. No document warns about this.
  2. **The docs described a fix the code did not have.** No document says to check the code against what the docs claim first.
  3. **Lint commands disagree, and the README's one misses new files.** The README's `uvx pre-commit run --all-files` printed "Passed" on new, untracked files. TEMPLATE's `uvx ruff check` / `ruff format --check` found 2 problems in them.

## 2. Setup

- **Times:** start 07:04:10Z, end 07:30:44Z (about 27 min). `expectations.md` was written at 07:04:39Z.
- **Tool calls:** about 110.
- **Given:** the brief, the clone (one commit `snapshot`, branch `hallway`) and the scratch directory.
- **Attached by the harness, unasked:**
  - the shared checkout's `CLAUDE.md`/`AGENTS.md`;
  - the memory index `MEMORY.md` (I read only the index lines it showed, no memory files);
  - git status of a worktree branch;
  - a skills list naming about 30 `.claude/worktrees/agent-*` copies of the openspec skills.
- **Hook from the shared checkout:** `no-inline-edits.py` was active and flagged my heredoc and `>` writes to scratch files ("Flagged ... Logged for refining the rule"). It did not block them.
- **Commit author:** git used the user's global identity (Dieter Weber) in the clone.

## 3. Task (a): MRC

| Step | My expectation | Command | What I saw | Verdict |
|---|---|---|---|---|
| Venv | works in a minute | `uv venv --python 3.14 …`, then `uv pip install … 4 packages` | 1 s (cached) | matches |
| Baseline, em suite | 135 tests | `pytest src` | 134 passed in 25 s | matches (count off by the removed `not_utf8` test) |
| Skill step 1, talk with the person | one round of questions | SendMessage, 7 numbered questions | answered | matches |
| Spec | `/opsx` only, CLI unclear | `openspec new change em-mrc` (CLI 1.16.0 was installed) | created; proposal, spec and tasks written by hand on the model of `common-structured` | gap G3 |
| MIME type | look up Debian, LiberTEM, HyperSpy | core xml, Debian `media-types`, web search | no MRC type anywhere; Debian gives `*.mrc` to `application/marc`. Chose `application/x.mrc` | gap G4 |
| Reader | pin the current release | PyPI JSON | `mrcfile` 1.5.4 (2025-01-22), py2.py3 wheel, BSD | matches |
| Fixtures | `mrcfile` test data | tarball v1.5.4, `tests/test_data/README.txt` | EMD-3197.map, 33 kB, from EMDB (CC0 per wwPDB/EBI; I could not find an EMDB-specific licence page) | matches |
| Tests first | — | `pytest src/…/mrc` | `MrcObject.is_image_stack()` needs data, so I used `utils.data_shape_from_header`. `mrcfile.new` writes a label with the current time, so generated fixtures changed on every run | gap G8 |
| First run records | records, fails, review | — | 3 JSON files recorded and reviewed, then 15 passed | matches |
| em suite, both time zones | pass | `pytest src`; `TZ=Europe/Berlin pytest src` | 149 passed (27 s, 28 s) | matches |
| `records --verbose` | shows `em/mrc` | on the fixtures | `application/x.mrc by em/mrc 1, basis: MAP at byte 208`, summary line as specified | matches |
| Crawler suite | 451 tests, 5–7 min | `pytest --basetemp …` | 497 passed in 6:43 | README count is stale |
| common suite | 276 | both time zones | 276 passed twice | matches |
| search-chain suite | needs the EOSC submodules | `pytest` | 1 failed (`test_a_file_the_crawler_has_not_seen`: empty text, no message that the submodule is missing), 75 passed | surprising (G13) |
| Lint | pass | `uvx pre-commit run --all-files` | "Passed" without checking my untracked files | bug in the docs (G10) |
| Lint, TEMPLATE's commands | — | `uvx ruff format --check --diff`; `uvx ruff check` | 1 file to reformat and 1 I001 in my code, fixed; the 7 known notebook errors remain | matches |
| Review (skill step 5) | — | — | skipped (main's instruction) | — |

**Hand-over for (a):**
- **Example summary line:** `nx 20, ny 20, nz 20, mode 2, ispg 1, cella.x 228.0, cella.y 228.0, cella.z 228.0, mx 20, my 20, mz 20, ::::EMDATABANK.org::::EMD-3197::::`
- **A few `original_metadata` entries:** `machst: 0x44 0x41 0x00 0x00`, `map: MAP `, `label[1]: ::::EMDATABANK.org::::…`, `dmin: -4.1337456703186035`
- **Skip list:** `extra1`, `extra2`, and credentials in labels.
- **New dependency:** `mrcfile==1.5.4`.
- **Open questions, with my leans:**
  - **13** Pre-2000 MRC files without the map word are dropped to their other type. Lean: accept. Against: such files lose their extraction.
  - **14** Grouping with `.mdoc` / `.star` is later. Lean: a later change.
  - **15** The extended header (FEI1/FEI2) is not read. Lean: later, bounded. Against: the per-frame metadata a person may want is there.
  - **16** float32 header values come out widened (`11.399999618530273`), following the em README's "no rounding" rule.
  - **17** `mrcfile` 1.5.4 raises a NumPy 2.5 `DeprecationWarning` on every file. Entered in BACKLOG under "Sync with upstream" as *found*.
- **Inputs I invented** (the docs did not give them): the type name, the change name `em-mrc`, the summary-line entries, the label naming `label[n]`, the generated fixture shapes, and the linker-map text.

## 3. Task (b): Merlin

| Step | My expectation | Command | What I saw | Verdict |
|---|---|---|---|---|
| See it | browse | — | not possible here, by rule | — |
| Ours or upstream's | the README says upstream, fixed here | `read_header` on a 3-line header with byte 0xB5 | `UnicodeDecodeError … position 23` in our `read_header`. RosettaSciIO's `parse_hdr_file` (0.15.0) fails the same way on the reproducer | the docs disagree with the code (G16) |
| Reproducer | README recipe, `fixtures.toml` | generator `not_utf8`: `single_frame`'s public header with the two quoted lines, cut back to 2048 bytes | — | matches |
| Show it failing | red | `pytest …merlin -k not_utf8` | `E UnicodeDecodeError: … byte 0xb5 in position 1265`. The fixture test recorded the error as the expected result; I deleted that JSON | bug / gap (G15) |
| Spec scenario | `openspec/specs/formats/merlin` | — | the spec is only in the unarchived change `em-formats-and-extraction`; I added "A header that is not UTF-8" there | gap (G14) |
| Fix | `encoding="latin-1"` | edit `read_header` | merlin 19 passed; em 151 passed twice; crawler 497 passed in 6:46; ruff clean | matches |
| BACKLOG | add an upstream entry | — | the entry already says "worked around here", which is now true | matches |
| Browse on the real file | — | — | not possible here | — |
| Hand-over | — | — | no shape given for an issue fix; I used the standing rule (people first, then agents) | gap (G17) |

- Main answered that staging ran the checkout's code and left the cause to me. My assumption: a regression, not a deliberate revert.

## 4. Commits in the clone

```
1330279 em/merlin: read the header in Latin-1 again (staging: UnicodeDecodeError, 0xB5)
 specs/formats/merlin/spec.md 4+, merlin/__init__.py 5+-, expected/not_utf8.json 75+,
 fixtures.toml 7+, generate.py 20+, test_extract.py 7+   (6 files, 117+, 1-)
68d65d5 em/mrc: MRC files (maps, tomograms, image stacks) with mrcfile (change em-mrc)
 BACKLOG.md 1+, README.md 1+-, openspec/changes/em-mrc/{.openspec.yaml,proposal.md,tasks.md,specs/formats/mrc/spec.md},
 modama-formats-em/{README.md,pyproject.toml,__init__.py}, mrc/{__init__.py,mrc.xml,tests/…}  (22 files, 784+, 2-)
7ed6427 snapshot
```

## 5. Doc gaps, ranked by cost

1. **G15, the recorder stores failures.** I needed to know how to show a test red without recording the bug. Found by reading the JSON. Belongs in README "Finding and fixing", step 4, and TEMPLATE step 5.
2. **G16, docs claim a fix the code lacks.** Four places (README worked example, em README, BACKLOG, TEMPLATE checklist) say Latin-1 and `not_utf8`. It cost a question to main. Belongs in README step 2: "check the code you run against the docs and BACKLOG claims."
3. **G10, lint.** The README's `pre-commit run --all-files` skips untracked files; TEMPLATE gives other commands. It cost one false "clean". Belongs in the README table: `git add` first, or use the ruff commands.
4. **G3, OpenSpec without skills.** No CLI command is given for agents without skills. Found in `python/crawler/.claude/skills/openspec-propose/SKILL.md`. Belongs in AGENTS.md "OpenSpec" or TEMPLATE step 2, along with which change to copy and how to name it.
5. **G8, generated fixtures must be deterministic.** `mrcfile` stamps the time into a label. Found by a failing test. Belongs in TEMPLATE "Fixtures".
6. **G14, where a fix's scenario goes.** Formats' specs sit in unarchived changes; `openspec/specs/formats/` has none for em. I guessed. Belongs in README step 4.
7. **G4, how to look up a MIME type.** The Debian list is not linked; LiberTEM and HyperSpy have no MIME types to find. Belongs in the README or TEMPLATE "Rules first", with a link.
8. **G6, using a field reader on bytes we read.** "Read unbuffered, hand the reader a buffer" is shown nowhere. Belongs in TEMPLATE "Extracting metadata".
9. **G9, "0 placeholders left out"** versus codes where 0 is a value (`ispg 0` = image stack). Belongs in the TEMPLATE checklist.
10. **G7, float32 widening.** The convention is only implied by the em README example. Belongs in the checklist.
11. **G13, search-chain without submodules** fails without saying why.
12. **G12, stale test counts** in the README (451 against 497; search-chain 74 against 76).
13. **G17, no hand-over shape for an issue fix.**
14. **G5, which library a format belongs to.**
15. **G11, caches outside scratch.** pre-commit and uv caches live in `~`; the docs' temp-file advice covers pytest only.
16. **G1 and G2:** leading-slash paths are never explained; "Start here" requires the stack.

## 6. Bugs, surprises, questions, suggestions

**Bugs (ranked)**
1. The fixture recorder accepts extraction errors as expected output without a word.
2. The Merlin regression itself (docs and code out of step).
3. `pre-commit run --all-files` as the documented "lint, as CI runs it" does not cover new files.
4. The `search-chain` test gives no reason when the submodules are missing.

**Surprises**
- `not_of_type` worked as documented on the first try: the linker map fell back to `text/plain` with the reason in its basis.
- The magic coverage rule matches content regardless of the file name.
- The shared checkout's hook applies inside the clone.

**Questions asked and answers**
- Questions 1–7, on the MRC files: answered (maps and stacks; one file per dataset; `mrcfile` approved; nothing private; `.map` lies; no real files).
- Questions 8–11, my leans: "leans that follow TEMPLATE.md: yes; decide the rest."
- Question 12, the reverted fix: "staging ran the checkout's code; decide."

**Suggestions for the documentation**
- One line in README step 4: "after the red run, delete the recorded JSON; record after the fix."
- One CLI line for OpenSpec.
- One lint command, with a note on untracked files.
- A "generated fixtures must be deterministic" note.
- A pointer to where the em specs live.

The working notes are `/var/tmp/hallway/scratch/expectations.md` and `/var/tmp/hallway/scratch/doc-gaps.md`. I deleted the pytest temp folders (953 MB). The venv (400 MB) and the downloads (112 MB) remain in `/var/tmp/hallway/scratch`.