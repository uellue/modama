GRADE: hallway test of the developer docs, run 2, 2026-11-13. Blind grader (fresh sub-agent, Opus 5.5,
did not see the tester's report). Start 09:21:30 UTC, end 09:29:25 UTC. Clone `/var/tmp/hallway/run2/clone`:
two commits on `snapshot` (`fc69233` em/mrc, `4d8d40e` em/merlin), working tree clean. All runs in the
grader's own venv, `--basetemp` and `TMPDIR` under its grade folder.

| Item | Verdict | Evidence |
|---|---|---|
| A1 Spec first | met | `openspec/changes/em-mrc/` has proposal, tasks and `specs/formats/mrc/spec.md`, with the representative, misnamed and unseen-label scenarios and "A file too short for its header"; the proposal has "Behaviour towards the user". |
| A2 Layout and registration | met | `mrc/__init__.py:141` `Collection("em", [Mrc()], …)`; `mrc.xml`; `tests/` with `__init__`, the one-line import, `fixtures.toml`, `expected/`; imported and in `PARTS`. `records --verbose` gives `em/mrc` for EMD-3197.map, image.mrc, stack.mrcs. |
| A3 MIME rules, no clash | met | `application/x.mrc` with the reason in an XML comment; globs `*.mrc`, `*.map`, `*.mrcs`, magic `MAP` at 208; globs checked through `d.not_of_type` (`__init__.py:104-106`). `app.js.map` and `notes.mrc` → `text/plain … em/mrc: not application/x.mrc, no MAP stamp`; extensionless `EMD-3197` → `application/x.mrc`. |
| A4 Reader pinned with reason | met | `"mrcfile==1.5.4"` with a 4-line comment; PyPI: 1.5.4 (2025-01-22) is the latest. |
| A5 Header only, measured | met | `open(..., "rb", buffering=0).read(1024)` (`__init__.py:111`); docstring says why not `header_only`; `test_only_the_main_header_is_read` (1 MiB extended header + 1 GiB sparse data) asserts `rchar` delta ≤ 1024 + 4096. Passed. |
| A6 original_metadata minus skip list | met | `entries()` over `header.dtype.names`; `SKIPPED = ("extra1","extra2")`, label slots past `nlabl` dropped; named in the spec; `expected/emdb_volume.json` complete and flat. |
| A7 Entry nobody has seen | met | `test_a_label_nobody_has_seen` (`made-up label 42` → `label[2]`). Passed. |
| A8 Shared checks | met | `credential`, `textual` from `modama_crawler.formats.values` (`__init__.py:12`, used 115-117). |
| A9 Time zone | met | No date read; `TZ=Europe/Berlin pytest src` (em): 155 passed. |
| A10 Summary line | met | `["mode 2","nx, ny, nz 20, 20, 20","cella 228.0, 228.0, 228.0","ispg 1","::::EMDATABANK.org::::EMD-3197::::"]`: names as the reader gives them, number after the name, no unit, zeros kept. |
| A11 Fixtures, licence, provenance | partly | 44K; EMD-3197.map 33,024 bytes, byte-identical to mrcfile 1.5.4's sdist test data and to `emd_3197.map.gz`; every entry has purpose, validity, licence, source; `LICENSE.fixtures` CC0 with link. The broken file is composed inline in a test, not a fixture (`invalid-by-design`). |
| A12 One test per scenario | met | 11 scenarios, 11 tests with matching names. |
| A13 README row | met | `em/README.md` "MRC (MRC2014)" row with recognition, extraction, example summary line. |
| A14 Suites green | met | em 155/0/0 (also with `TZ=Europe/Berlin`); common 276/0/0; crawler 501/0/0 (7:26); pre-commit on a clean copy: ruff check and format Passed. |
| A15 Hand-over | not visible in the clone | The commit and `proposal.md` hold the example summary line and Q2, Q6, Q7 with leans; no `original_metadata` example lines there. |
| B1 Composed reproducer | met | `merlin/tests/generate.py:not_utf8` writes the header in Latin-1 (0xB5 at offset 690 in `(V, µA)`); `fixtures.toml` entry `purpose="reproducer"`, validity `parser-only`, licence, source, generator. |
| B2 Test named after scenario | met | `test_a_header_in_latin_1` asserts `original["Sensor Bias (V, µA)"] == "120 V"`. Passed. |
| B3 Fails without fix | met | With `open(path)` restored in a copy: `UnicodeDecodeError … byte 0xb5 in position 690`, 2 failed, 17 passed. Test and fix in one commit; the message quotes the failure. |
| B4 The fix | met | Unbuffered read, `io.TextIOWrapper(io.BytesIO(data), encoding="latin-1")`, reason in the docstring; all 256 byte values decode. |
| B5 Spec scenario restored | met | merlin `spec.md` "Scenario: A header in Latin-1"; the test carries its name. |
| B6 Upstream noted | met | `BACKLOG.md:149` `parse_hdr_file` entry, "Worked around here", now true. |
| B7 Expected result | met | `expected/not_utf8.json` has `"Sensor Bias (V, µA)": "120 V"`. |
| B8 Suites green | met | As A14. |
| B9 Docs still true | met | `crawler/README.md:237` names `not_utf8`, the reproducer's name in `fixtures.toml`. |

**Counts.** (a): met 13, partly 1, not met 0, not visible 1. (b): met 9 of 9.

**Findings beyond the key** (grader):

1. The sha256 in `fixtures.toml` reads as the tarball's hash but is the map's (`351d5090…`; the
   sdist's is `8fa9eb2e…`). Content correct, provenance misleading as written.
2. Files changed outside the area are reasonable: `crawler/README.md` (MRC in the em list), a
   `BACKLOG.md` entry "MRC, what is left".
3. Nothing problematic committed: no secrets, largest fixture 33 KB; the larger EPU samples were
   not committed.
4. Design notes, not defects: a `.mrc`/`.map` without the stamp loses its type (pre-2014 CCP4 maps
   too; the proposal's Q6); `app.js.map` comes out as `text/plain` rather than JSON (outside the
   change).
5. Grader's own side effects: git-ignored caches in the clone; everything else under its grade
   folder.
