GRADE: hallway test of the developer docs, 2026-11-13. Start 07:32 UTC, end 07:39 UTC (the sandbox clock; the clone's commits are stamped 07:21 and 07:30). I did not modify the clone. Scratch (venv, pytest basetemps, copies) is deleted; only answer-key.md is left in /var/tmp/hallway/grade/.

Clone: 2 commits on `snapshot`. 68d65d5 is (a), em/mrc. 1330279 is (b), the Merlin fix.

| Item | Verdict | Evidence |
|---|---|---|
| A1 Spec first | met | openspec/changes/em-mrc has proposal.md, tasks.md, specs/formats/mrc/spec.md. Scenarios cover EMDB map, mrcfile-written files, renamed copy, linker map named .map, an unseen label, a credential in a label, header-only read. The proposal has "Behaviour towards the user". |
| A2 Layout and registration | met | mrc/__init__.py has `COLLECTION = Collection("em", [Mrc()], ...)`; mrc.xml; tests/ has `__init__.py`, `test_fixtures.py`, `fixtures.toml`, `expected/`. The area is imported and in PARTS. `records --verbose` names `em/mrc`. |
| A3 MIME rules | met | `application/x.mrc`, with a comment on why (media-types gives *.mrc to application/marc). Magic: MAP at 208 plus machine-stamp byte at 212. Globs `*.mrc`, `*.mrcs`, `*.map` plus `d.not_of_type` in `recognize`, which the key allows. Checked: `app.js.map` and `notes.mrc` come out as text/plain; `real.map` and the extensionless copy come out as `application/x.mrc` (basis "MAP at byte 208"). |
| A4 Pin with reason | met | `mrcfile==1.5.4` in pyproject.toml with a 3-line comment: "current release (PyPI, 2026-11-13), a pure-Python wheel". I did not re-check PyPI; the key names 1.5.4. |
| A5 Header only, measured | met | `open(..., buffering=0).read(1024)`, then `MrcInterpreter(BytesIO(head), permissive=True, header_only=True)`. `test_only_the_header_is_read` uses a 1 GiB sparse file and asserts rchar delta <= 1024+4096. The test passes. |
| A6 original_metadata minus skip list | met | `entries()` emits every header field flat (cella.x, label[n], machst, map ...) minus `SKIPPED=("extra1","extra2")`, named in code and spec. mapped_metadata has data_type, voxel_size, kind. The expected JSON is complete. |
| A7 Entry nobody has seen | met | `test_a_label_nobody_has_seen_before` ("made-up label 42 zz" in `label[1]`). Passes. |
| A8 Shared checks | met | Imports `textual` and `credential` from `modama_crawler.formats.values`; a credential test exists. |
| A9 Time zone | met | No date is read. `TZ=Europe/Berlin pytest src` gives 151 passed. |
| A10 Summary line | partly | `nx 20, ny 20, ..., mode 2, ispg 1, cella.x 228.0 ..., ::::EMDATABANK.org::::EMD-3197::::`. It has a number after its name, no units, and nothing guessed. It is a long list (11 entries plus the label), and the first label is added bare, with no name. |
| A11 Fixtures, licence, provenance | met | `du` of fixtures: 52K. EMD-3197.map is 33 KB, unchanged, with sha256, URL and CC0 with an EMDB/wwPDB link in LICENSE.fixtures. The other two fixtures are generated or by hand (MIT). Every entry has purpose, validity, licence and source (generator where generated). The broken file is a reproducer, `invalid-by-design`. |
| A12 One test per scenario | met | All 7 scenarios have a test named after them (test_a_map_from_emdb, test_a_linker_map_named_map, test_only_the_header_is_read ...). |
| A13 README row | met | Row in em/README.md with recognition, extraction and an example summary line. The crawler README lists MRC too. |
| A14 Suites green | met | em `pytest src`: 151 passed, 0 failed, 0 skipped. em with `TZ=Europe/Berlin`: 151 passed. modama-formats-common: 276 passed. crawler: 497 passed, 0 failed, 0 skipped (6:45). `pre-commit run --all-files`: ruff check and ruff format Passed. |
| A15 Hand-over | partly | The commit message has the format covered, dependency with version, fixtures, README and BACKLOG, "Not done: independent review (skipped)". It has no example summary line, no `original_metadata` lines, no open questions with leans. The proposal's "Assumptions and leans" section carries the leans, the skip list and the summary line. The final report is not visible in the clone. |
| B1 Composed reproducer | met | `generate.py:not_utf8` builds the header from single_frame. It writes exactly one 0xB5 (`Sensor Bias (V, \xb5A)\t120 V`). `Chip ID` is at byte 77, within the first 256. The fixtures.toml entry has purpose=reproducer, validity=parser-only and says it is composed and which lines are quoted, plus licence, source and generator. LICENSE.fixtures is present. The expected JSON shows em/merlin and an extraction. |
| B2 Test named after scenario | met | `test_a_header_that_is_not_utf8` asserts `original["Sensor Bias (V, µA)"] == "120 V"` and the Software Version, via `described` (the record is described). Passes. |
| B3 Fails without the fix | met in the clone; "before" not visible | With `open(path)` restored in a copy, the merlin tests fail with `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb5 in position 1265`. The test and the fix are in the same commit. The message says the test fails on the old code "with the staging error" (a claim, not shown). |
| B4 The fix | met | `open(path, encoding="latin-1")`. The docstring says why: the Merlin software writes µ as the single byte 0xB5, and RosettaSciIO's `parse_hdr_file` fails on it. The fix is in our code, not in the venv. Latin-1 maps all 256 bytes; I did not run a separate scratch test of this. |
| B5 Spec scenario restored | met | The "A header that is not UTF-8" scenario was added to the Merlin spec in em-formats-and-extraction (fixture `not_utf8`); the test is named after it. |
| B6 Upstream noted | met | BACKLOG.md line 146 is unchanged from the seed and true after the fix ("*Worked around here* ... not yet reported", fix upstream: `encoding="latin-1"`). |
| B7 Expected result | met | expected/not_utf8.json exists; I confirmed it has `Sensor Bias (V, µA)`: `120 V` and a Merlin Quad extraction (it appears in the failing diff when the fix is removed). |
| B8 Suites green after (b) | met | As A14. The counts above are on the final state, which includes (b). |
| B9 Docs still true | met | The README's worked example names fixture `not_utf8`, and `[not_utf8]` is in fixtures.toml. |

Counts. (a), 15 items: 13 met, 2 partly (A10, A15), 0 not met. (b), 9 items: 9 met. B3's "tester showed it failing before fixing" half is not visible in the clone.

Details for partly items.
- A10: the summary has 11 name-number entries plus the bare first label, not "a few chosen entries". Nothing is guessed and there are no units. The spec and the proposal chose this list on purpose; whether the label belongs in the line is a judgement call.
- A15: the commit message omits an example summary line, a few `original_metadata` lines and numbered open questions with leans, which the skill's step 6 asks for. The proposal covers the leans, the skip list and the summary line. Whether the report did is not visible in the clone.

Findings beyond the key.
- The only files changed are in the mrc area, em `__init__`, pyproject and README, the crawler README, BACKLOG, the OpenSpec change, and the merlin area for (b).
- No secrets and no large files were committed. The clone was clean after the runs.
- The fixtures.toml licence for `not_utf8` is GPL-3.0-or-later (derived from the RosettaSciIO test files), covered by LICENSE.fixtures; this is correct.
- The mrcfile NumPy 2.5 deprecation entry added to BACKLOG says "Not checked whether mrcfile's main branch has it", an honest caveat. It is not verified by me.
- The mrc extractor warns for reader RuntimeWarnings except messages starting "Expected". It is permissive; the reason is in a comment.
- `test_a_renamed_copy` covers the extensionless case.
- The mrcfile dependency is flagged in the commit message and the proposal.