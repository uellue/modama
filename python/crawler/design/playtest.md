# Play test of `modama-crawler records` (2026-10-27)

A sub-agent that had read only `requirements.md` built 20 test trees, wrote down its expectations, ran the oracle and compared. It asked three questions, which Claude answered from the design; what could not be answered with confidence went to @weber, whose decisions and their outcome are under *Decisions*. The tester's full report follows at the end. Its test trees and a `run.sh` to repeat each experiment are in the session scratchpad (`playtest/` under `/tmp/claude-20335/…/scratchpad/`), not in the repository.

The first attempt, launched on 2026-10-16 before the vacation, died with that session an hour later after reading the requirements; this run is a fresh start with the same brief.

## What held up

Single files by name and by content, files without extension, venv/`.git`/caches/`node_modules` collapsed with readable bases, Zarr v2 and v3 in every arrangement tried (arrays, groups, nested, no `.zarr` suffix, fake and broken stores), the EMPAD pair with the real header shape including the missing-raw warning and the contention warning, three-level nesting, odd names and encoding, `--from`/`--until` boundaries and error messages, select/ignore precedence, `| head`, no PATH, bad PATH, option placement, listing-order independence (byte-identical runs), FIFOs do not hang, 20 000 files in one directory in 2.6 s.

## Fixed during the test

Each fix has a scenario in the `recognition-core` delta specs and a test. Suite: 161 passing, ruff clean, `openspec validate --strict` valid.

| Finding | Fix | Where |
|---|---|---|
| `data.json` came out as `application/json5`: both `application/json` and its subtype `application/schema+json` glob `*.json`, and the tie-breaker climbed to strict ancestors only | A tie resolves to a candidate itself when the others are its subtypes | `mime._common_ancestor`; spec `mime-database`; `test_mime` |
| Every such tie, and every declaration-less `*.xml` (EMPAD's `*.xml` glob), produced an "ambiguous" warning: thousands of lines on a real tree | A tie is reported only when the result is none of the candidates | `mime._resolve`; same spec; decision log |
| `--select nosuch`, `--ignore collapse/vnev`, `--ignore collapse,zarr` were accepted silently; `--select nosuch` disabled every format with exit 0 | Unknown ids are an error naming the installed ids, for the command line, `select`/`ignore` and per-path ignores in the config | `selection.check_ids`, `cli._configure`; spec `format-selection`; `test_selection`, `test_cli` |
| A dataset's own warnings (unparsable `zarr.json`) appeared only inside `--verbose` lines and were not counted | Dataset warnings are logged and counted with the walk's warnings, in `records` and `crawl` | `cli._report`; spec `records-cli` |
| `--config /nope.toml` gave a traceback | Error line with the file name, exit 2 | `cli._configure`; spec `records-cli` |
| `records --help` omitted `--verbose` and `--config` | Both listed on the subcommand | `cli.main`; spec `records-cli` |

A side finding on the test method: the core collection's recorded expectation `expected/mixed.json` had enshrined the json5 bug. Recorded results detect change, not correctness; the review on recording is what has to catch this (`testing.md`).

## Answers given to the tester

1. **JSON tie:** a bug (see above).
2. **EMPAD header shape:** modelled on the acquisition software's output, which has no XML declaration. The file starts with `<root name=`, `<software_version>` appears within the first 400 bytes, and `<raw_file filename="…"/>` names the raw file; only the base name is used, the raw file must be a sibling. A missing raw file is a warning and the header stays a single-file dataset. The raw file's size is not checked.
3. **Symlinks:** no record is intended for now (open question in the backlog); the missing diagnostic is a gap.

## Explained, not changed

- **Identifier length.** The 255-character cap applies to the local part after the last `:` of the OAI identifier, because the EOSC warehouse cuts identifiers there and stores the rest as `VARCHAR(255)`. A 284-character identifier with a 255-character local part is therefore intended (@weber, 2026-10-14).
- **Control characters.** `\x01` in a file name becomes U+FFFD in `dc:title` (XML 1.0 cannot carry it) and `%01` in the identifier and browse URL. Already in the backlog (non-UTF-8 and control characters).
- **Empty files** are `text/plain`. shared-mime-info defines `application/x-zerosize`, but the pyxdg checking order does not use it; the fallback heuristic sees "no control characters" in zero bytes.
- **A header without `.xml`** is recognised: content sniffing runs for every unmatched name, so the EMPAD magic fires. Better than Claude told the tester.

## Decisions (@weber, 2026-10-27) and what followed

The tester's open points, the decision, and the state. "Done" means implemented with a spec scenario and a test the same day; the suite stands at 166 passing.

1. **Unreadable files:** no record, an info line in the log; only the path given on the command line being unreadable is an error. *Done:* the walk skips files it cannot read and directories it cannot list with `INFO <path>: skipped, <reason>`; `records PATH` on an unreadable PATH exits 2 with the path on stderr. The old "cannot list directory" warning is gone.
2. **Symlinks and special files:** skipped and logged like unreadable files. *Done:* formats never see them.
3. **Datestamp of collapsed datasets:** the directory mtime as a baseline, overridable by the format. *Recorded;* the override is added when a format needs it.
4. **Ignoring `__pycache__`-like trees entirely:** a gitignore-like list with defaults proposed by the collections and the actual list per deployment. R1 already has the per-deployment exclusions; collection defaults are new. *Added to R1 and the backlog;* the override syntax (gitignore's `!pattern`) is a small design item.
5. **Collapsed datasets:** contain everything by default; a format may hand back entries that are not its own, as a warning or as separate datasets, to be decided on wild examples. A top-level README belongs to the dataset, for example as a description. *Backlog,* with the search for examples.
6. **`*.raw` as Panasonic:** force the content check with a tie. *Done:* `core/er-c.xml` adds `*.raw` to `application/octet-stream`; a real Panasonic file still matches by magic, everything else is octet-stream, no ambiguity reported. First case of curating the vendored definitions.
7. **`--select core` enabling nothing:** a collection id now also covers the collection's MIME definitions, so the single-file "generic handler" is what `core` selects, and `--ignore empad` drops EMPAD's types as well; ignoring one Python format (`empad/empad`) keeps the definitions. *Done.* The spec said "built from the enabled collections only" and the code had used all installed collections.
8. **Members in a record:** by default mention the referenced files in `dc:description` (several allowed), top-down for nested structures, cut at about 100 entries. *Backlog,* to be refined on examples.
9. **EMPAD in the wild** (checked on the 52 EMPAD directories visible in `/er-c-data`, 26 readable headers): every instrument-written header starts with `<root name=`, software versions 0.7.12 and 1.2.2; one 2017 header (version 0.29, in `libertem-test-data`) names the raw file by an absolute path, which the base-name rule handles; three hand-edited copies there carry an XML declaration. *Done:* the magic now allows the root element within the first 64 bytes, with a fixture for the declaration variant. Software versions seen go into the backlog to watch upstream changes. Raw-size check: only if wrong-size pairs turn up in the wild.
10. **Comma lists in ids:** follow ruff, `--ignore collapse,zarr` is a list (@weber). *Done.*
11. **MIME type names for new formats:** look for an existing type used in the wild first (for example the Debian MIME support list), otherwise invent an unofficial `application/x.…` type; never a misleading generic one such as `text/plain` for MIB. *Recorded in `formats/TEMPLATE.md`.*
12. **Requirements suggestions** from the tester: accepted by @weber with notes and folded into `requirements.md` as R33 to R39 (unknown ids, overrides of generic definitions, what recognition sees, severity model, datestamps, members in a record, identifier limits), R31's testable examples, and open questions Q20 and Q21 (severity details, member representation; both with user testing as a TODO). Comma lists follow ruff (R33).

## Visual check of `records --verbose | less` (2026-10-27)

@weber found that `records --verbose | less` hid the diagnostics, since they went to stderr, and asked for the requirement (now R40) and for a check by eye in a real terminal rather than by parsing text. The mechanism: with `--verbose` the diagnostics become XML comments in the document, in path order, directly before the record they concern (`records-cli` spec). A Sonnet agent drove an xterm under a virtual X server (`tools/xterm-shots.py`: start, keys, type, screenshot; charmbracelet `vhs` was considered in the 2026-11-03 review and rejected, since it renders xterm.js in a headless browser and runs a tape to completion, while this check is specified against a real xterm and was driven interactively) through nine scenarios on the play-test trees and judged only the screenshots; its report and screenshots are in the session scratchpad.

Verdict: the requirement holds. Association by position and by the path in each comment was unambiguous in every scenario, including a saved file, `head`, and 80 columns. Found and fixed the same day, each with a spec scenario and a test, and re-checked by eye:

- **Bare terminal without `--verbose`:** warnings and the summary were printed before the document and scrolled off. They now follow the document on stderr, so they are the last thing on the screen.
- **Large tree:** 557 "image/tiff, single file" comments carried no information and made the diagnostics about 5% of the screen. Single files that no format produced get no comment; the closing comment counts them: `557 records (557 single files by type), 0 warnings, 0 skipped`.
- **Markers:** `WARNING:` and `SKIPPED:` in upper case, searchable in a pager without matching file names.
- **One comment per diagnostic:** a dataset's own warning (an unparsable `zarr.json`) was merged into its recognition comment; it is now a comment of its own, like the walk's warnings.

Not done, in the backlog: shorter recognition comments, the symlink target in `SKIPPED:` comments, colour on stderr when it is a terminal, a non-verbose hint pointing to `--verbose`.

---

## The tester's report: playtest of `modama-crawler records`

Date 2026-10-27, tool from the devcontainer venv (Python 3.14.8, zarr 3.4.1). Judged against `design/requirements.md` only. Disclosure: the harness auto-attached `python/crawler/AGENTS.md` to my context before I started; I did not open it or any other file, but I cannot un-see its architecture summary.

### Setup

All test trees are under this directory (`e01_common` ... `e20_big`). `run.sh NAME ARGS...` runs the tool, saves `NAME.out.xml` and `NAME.err.txt`, and prints one line per record (title, type, format, date, datestamp, relation). Predictions were written before each run. Verdict legend: **matches**, **bug**, **defensible** (surprising but acceptable), **gap** (not implemented), **question**.

### Experiments

#### E01 common single files (`e01_common`)
Expect: six records, one per file, MIME by name/magic (text/plain, image/png, application/json, text/x-python, application/xml, text/csv), title = `/name`, creator = owner, date = mtime, no relation.
Observed: six records as expected except `data.json` -> `application/json5` with `WARNING /data.json: type is ambiguous between application/json, application/schema+json; using application/json5`.
Verdict: **bug** (reported, fixed by main during the test; re-run gives `application/json`, warning still printed in `--verbose`). `--verbose` lines read `... by - , basis: single file`; the dash for "no format" is cryptic.
Command: `modama-crawler records --verbose e01_common`.

#### E02 files without extension (`e02_noext`)
Expect: text -> text/plain, random bytes -> application/octet-stream, `#!/bin/bash` -> shell script, 40 zero bytes -> octet-stream, empty file -> something like `application/x-zerosize` or octet-stream.
Observed: all as expected; empty file -> `text/plain`.
Verdict: **defensible** for the empty file, but an index entry "plain text" for a 0-byte file is misleading; XDG has `application/x-zerosize`.

#### E03 venv, `.git`, caches next to normal files (`e03_boring`, 38 files)
Expect (R11, spike table): venv, `repo/.git`, `__pycache__`, `.ipynb_checkpoints`, `node_modules` each one collapsed record; `analysis.txt`, `nb.ipynb`, `repo/a.txt` individual; 8 records.
Observed: exactly that; basis lines are good ("contains pyvenv.cfg", "directory is named .git"); notebook -> `application/x-ipynb+json`.
Verdict: **matches**. Open question whether `__pycache__`/`.ipynb_checkpoints` should be records at all (R30: nobody searches for them).

#### E04 Zarr v2 and v3 (`e04_zarr`, 83 files)
Expect: one `application/x-zarr` record per store (v2 array, v2 group, v3 array, v3 group with nested group/array), chunks not indexed; `nosuffix_v3` unsure; stray `README.txt` inside a store reported (R22).
Observed: 7 records, all stores collapsed including the one without `.zarr` suffix, basis explains v2/v3 marker. Stray file inside `stray_v3.zarr` absorbed silently, no warning even with `--verbose`.
Verdict: **matches** for recognition; **gap** for the stray file (R22).

#### E05/E05b EMPAD, guessed headers (`e05_empad`, `e05b_empad`)
Expect: a header naming a raw file beside it forms one dataset; missing raw -> warning.
Observed: 15 guessed variants (root attribute `raw_file`, child `<raw_file filename>`, with/without XML declaration) never paired. Every `.xml` without declaration gives `WARNING ... ambiguous between application/x.empad+xml, application/xml; using application/xml`. All `.raw` files not named `scan_x*_y*.raw` come out as `image/x-panasonic-rw`.
Verdict: **question** answered (Q2): the header must start with `<root name=` and contain `<software_version>` in the first 400 bytes. The per-file "ambiguous" warning for every plain XML file is intended but noisy; `image/x-panasonic-rw` for every `.raw` is a **surprise** (R1 says Panasonic is not wanted at ER-C; a search index labelling detector dumps as camera photos is misleading).

#### E17 EMPAD with the real header (`e17_empad`)
Expect: `p_pair` one record anchored at the XML; `q_missing` warning + single-file header; `r_wrongsize` (100-byte raw) warning; `s_stray` extra `notes.txt` and `orphan_x128_y128.raw` reported; `t_twoheaders` contention reported (R5); `u_decl` (XML declaration) unknown; `v_subdir_raw` (`filename="data/scan.raw"`) unknown; `x_noext_header` (header without `.xml`) not recognised per main.
Observed: `p_pair` one record, format `application/x.empad+xml`, raw file not mentioned anywhere in the record (no relation, no member list). `q_missing`: `WARNING ... raw file scan_x128_y128.raw named by the header is missing`. `r_wrongsize`: paired, no warning. `s_stray`: two extra single-file records, no stray warning. `t_twoheaders`: `WARNING /t_twoheaders/two.xml: empad/empad: /t_twoheaders/shared.raw already claimed by empad/empad`, second header stays single. `u_decl`: plain XML. `v_subdir_raw`: "missing" although the file exists in `data/`. `x_noext_header`: recognised and paired (contradicts main's "`.xml` suffix needed", pleasantly).
Verdict: pair/missing/contention **match**; wrong size **gap** (confirmed); stray files **gap**; XML declaration **question**; record not revealing the raw member: **suggestion**.

#### E18 pair date (`e18_pairdate`)
Expect: date = newest member (raw 2024-06-01, header 2021). `--from 2023-01-01` includes it, `--until 2022-01-01` excludes it.
Observed: exactly that. **matches**.

#### E06 series directories (`e06_series`, 557 files)
Expect (R31, spike): 200 `frame_NNNN.tif` -> one group record; 200 `img_NNN.npy` -> one group; 5 tif -> individual; `mixed` (150 tif + overview.png + log.txt) -> group plus the two distinct files.
Observed: 557 individual records; `.npy` -> `application/octet-stream`.
Verdict: **gap** (series not implemented; `.npy` not recognised although R25 names `application/x-npy`). This is the "flooding" outcome R30 calls bad.

#### E07 three levels deep (`e07_nested`)
Observed: 5 records with full relative paths, deep Zarr collapsed. **matches**.

#### E08 odd names (`e08_names`, `e08b_long`)
Expect: titles verbatim, identifiers/URLs percent-encoded, XML well-formed; 300-char name impossible (fs limit 255 bytes, used 250); non-UTF-8 name unknown.
Observed: spaces -> `+`, `:` `'` `?` kept, `%` `+` `#` `&` tab encoded; `\x01` in the name becomes U+FFFD in `dc:title` but `%01` in identifier/URL; non-UTF-8 name: `WARNING /: skipped a name that is not valid UTF-8`, no record; a 600-char path gives a 288-char identifier `.../ddd~82908e48de60c84dcb422ac7022f3518`, a 250-char single name a 284-char identifier without truncation. Output parses.
Verdict: encoding **matches** the stated convention. Long identifier **question**: is the limit 255 bytes of path rather than of identifier? Control char **defensible** (XML 1.0 cannot carry `\x01`), but title and identifier disagree. Non-UTF-8 name **defensible**, though R18 says everything readable is in scope.

#### E09 symlinks (`e09_links`)
Expect: unclear from requirements ("File ... or symlink").
Observed: file link, dir link, dangling link, link outside the tree, self-loop: none appear, no diagnostic even with `--verbose`. 2 records.
Verdict: no record **intended** (answer Q3), no diagnostic **gap**.

#### E10 empty directories
Observed: no records, `DEBUG /empty_dir: 0 datasets`. **matches**.

#### E11 unreadable file and directory (`e11_perm`)
Observed: `locked_dir`: `WARNING ... cannot list directory: Permission denied`. `locked.txt` (chmod 000) silently classified by name as text/plain; `locked.xml` gets the "ambiguous" warning but nothing says it could not be read.
Verdict: directory **matches**; unreadable file **surprise**: R8 wants errors with context; a record exists for content the crawler could not open.

#### E12 `--from`/`--until` (`e12_dates`)
Expect: inclusive bounds, day granularity covers the whole day, errors for bad input.
Observed: all correct: `--until 2023-07-01` includes `2023-07-01T00:00:00Z`; a second-granularity range returns exactly `mid`+`edge`; `from > until`, mixed granularity, `2023-13-45`, missing `Z` -> clear `ERROR`, exit 2. Collapsed trees carry the directory mtime (`store.zarr` 2022 although chunks are 2024; `venv` 2019 although `lib/x.py` 2025).
Verdict: filtering **matches**. Collapsed-tree date **question** (Q5): a harvester using `from` never sees a rewritten Zarr store.

#### E13 `--select`/`--ignore` (`e13_sel`)
Observed: `--ignore collapse` -> `.git` and venv internals indexed (37 records); `--select zarr` -> only zarr; `--select collapse --ignore collapse/venv` -> 5 formats; `--ignore collapse --select collapse/venv` -> 1 (specific wins); `--select core` -> "0 formats enabled", everything single-file; `--select nosuch` -> "0 formats enabled", exit 0; `--ignore collapse/nosuch` silently ignored; `--ignore collapse,zarr` silently ignored (8 formats stay enabled).
Verdict: precedence **matches**. Unknown ids and comma lists silently accepted: **bug** (ruff, the stated model, rejects unknown codes). `--select core` disabling everything: **surprise**.

#### E14/E15 CLI edge cases
`| head -3`: exit 0, no traceback (**matches**). No PATH: cwd (**matches**). Nonexistent PATH / PATH is a file: `ERROR not a directory: ...`, exit 2 (**matches**). `--verbose` and `--from` after PATH work; `-- -dash` works. Two PATHs: usage error, exit 2. `--config x.toml` works; `--config /nope.toml`: Python traceback, exit 1 (**bug**, minor). `records --help` lists neither `--verbose` nor `--config` although both are accepted after `records` (**bug**, minor; they appear only in `modama-crawler --help`).

#### E16 extra formats (`e16_extra`)
DM3/DM4 (correct big-endian version headers, with and without extension) -> `application/octet-stream` (**gap**: the spike's largest population; R25 names `application/x-dm4-tem`). `.ser`/`.emi` -> octet-stream (**gap**). `.mib` -> `text/plain` (**surprise**: text header + binary frames). `.h5/.emd/.nxs` -> `application/x-hdf` (**matches**; Velox/NeXus subtypes a gap). `lying.png` containing text -> `image/png` (**defensible**, name wins per XDG). `broken.zarr` (invalid `zarr.json`) -> claimed as zarr; the message `...; warning: zarr.json cannot be parsed...` appears only inside the `--verbose` line; the plain run says `0 warnings` (**bug**). `not_a_store.zarr` without markers -> not a store (**matches**). `v2_only_zattrs` -> not a store (**matches**). Zarr inside a venv -> hidden by the venv collapse (**defensible**). Nested v2 store inside a v3 group -> one record (**matches**).

#### E19 order independence, FIFO
Three trees run twice: byte-identical apart from `responseDate` (R6 **matches**). Two FIFOs (`pipe.xml`, `pipe_noext`) are skipped without a hang but without a diagnostic (**matches** R12; same silence as symlinks).

#### E20 scale
20 000 `.tif` files in one directory: 2.6 s wall, 17 MB XML; 6 files: 0.8 s (startup). Fine for the oracle; the 20 000 individual records are the series gap again.

### Bugs (ranked)

1. **Series directories are not grouped** (E06): 200 frames -> 200 records, the flooding R30 forbids; the spike calls it "the dominant dataset shape". Also a gap, ranked here for impact.
2. **Unknown `--select`/`--ignore` ids are accepted silently** (E13): a typo (`--ignore collapse/vnev`, `a,b`) changes the deployment without a message; `--select nosuch` disables every format.
3. **Dataset-level warnings are invisible without `--verbose` and not counted** (E16 `broken.zarr`: "0 warnings"), while format warnings (missing raw file) are shown and counted. Hides what R22/R8 want seen.
4. **JSON tie-break picked the common ancestor instead of the parent candidate** (E01). Found, confirmed and fixed during the test.
5. `--config` with a missing file: traceback instead of an error line (E15).
6. `records --help` omits `--verbose` and `--config` (E15).
7. Unreadable regular files produce a normal record and no error (E11); R8 asks for logged errors with context.

### Surprises

- Every `.raw` not named `scan_x*_y*.raw` is `image/x-panasonic-rw` (E05, E17). Wrong more often than right at an EM institute; R1 names Panasonic as not needed.
- `--select core` means "enable nothing" because core has no formats of its own (E13). Users read `core` as "the common files".
- Every plain XML file triggers an "ambiguous" warning in `--verbose` because the EMPAD glob matches `*.xml` (E05). On a real tree: thousands of meaningless lines.
- Empty files are `text/plain` (E02, E16). `.mib` is `text/plain` (E16).
- An EMPAD pair's record does not mention the raw file (E17); `dc:relation`/`dc:source` were never emitted in any run.
- `\x01` in a name: title shows U+FFFD, identifier `%01`; they disagree (E08).
- The 255-character cap applies to the path, not the identifier: a 250-char name yields a 284-char identifier (E08b).
- Collapsed datasets carry the top directory's mtime, not the newest member's (E12), unlike pairs (E18).
- A header without `.xml` suffix is recognised by content (E17), better than main expected.
- Non-UTF-8 names are skipped with a warning (E08); R18 says everything readable is in scope.

### Gaps (not implemented)

Series directories (tif, npy, MIB hdr+mib); DM3/DM4; TIA `.emi`+`.ser`; `.npy` as `application/x-npy`; Velox/NeXus subtypes of HDF5; EMPAD raw-size check; stray-file reporting inside and beside datasets (Zarr store, EMPAD directory); diagnostics for skipped symlinks and special files; EMPAD header with an XML declaration; `dc:relation`/`dc:source` (R32) from any installed format; slowest-format report (R12) not observable from `records`.

### Questions asked and answers

1. **JSON -> json5 intended?** Bug. Rule: a tie resolves to the nearest type every candidate is-a; when one candidate is the parent of the others it wins. Fixed; tie still reported in `--verbose`.
2. **What EMPAD header matches; are missing/wrong-size raw files warned?** Header modelled on the real acquisition software: starts with `<root name=`, `<software_version>` within 400 bytes, `<raw_file filename="..."/>` child (base name only), no XML declaration (whether real headers ever have one is open). Missing raw -> warning, header stays single file. Size not checked (gap; whether worth it is for @weber).
3. **Symlinks silently dropped?** No record: intended for now (a file symlink may get a record later). No diagnostic: gap, on the maintainer's TODO.
4. (Open, not sent) Should `__pycache__`, `.ipynb_checkpoints`, `node_modules` produce records, or be ignored as the spike table's "or to ignore" allows?
5. (Open, not sent) Should a collapsed dataset's date be the newest member or the directory mtime? With the directory mtime, `--from` incremental harvesting misses rewritten stores.

### Suggestions for the requirements

- State what a "file" is for recognition: symlinks, FIFOs, devices, non-UTF-8 names, unreadable files; and that every skipped entry gets a diagnostic (R9's "why" currently covers unclaimed files only).
- Define the datestamp of a multi-file or collapsed dataset (newest member, directory mtime, anchor mtime) and its consequence for incremental harvesting (R10).
- Define how a multi-file dataset is visible in its record: member list, member count, or `dc:relation` for pairs, not only collection/part.
- Say that unknown format ids are an error (R1) and whether comma lists are allowed.
- Define the severity model: which diagnostics appear without `--verbose`, what the summary counts, and the exit status of a run with warnings.
- Say how generic-but-wrong XDG types are handled (`*.raw` -> Panasonic, empty file -> text/plain); a deployment-level "demote these types" list would fit R1.
- Make R31 testable: what happens below 10 members and for the "overview" exception (E06 `mixed` is a ready-made case).
- Document the identifier length rule (bytes of path vs characters of identifier) and the handling of characters XML cannot carry.
- Mention the known limits of EMPAD detection (XML declaration, raw file in a subdirectory) so field cases can be checked against them.
