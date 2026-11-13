# Answer key: hallway test of the developer docs (2026-11-13)

Written before the first run, for the blind grader (`grade-brief.md`) and for the main
session's answers during the run. Not for the tester: `setup.sh` removes this folder from
the clone.

What the seed did (`seed.patch`): `merlin.read_header` opens the header with `open(path)`,
in the locale's encoding (UTF-8 in the VM), as RosettaSciIO's `parse_hdr_file` does; the
docstring's Latin-1 explanation is gone. The reproducer is gone: the generator `not_utf8`,
its `fixtures.toml` section, `expected/not_utf8.json`, `test_a_header_that_is_not_utf8`,
and the scenario "A header that is not UTF-8" in
`python/crawler/openspec/changes/em-formats-and-extraction/specs/formats/merlin/spec.md`.
The two date tests use a new fixture `date_order` (the same lines, `µ` written as `u`,
UTF-8). Left as they were, on purpose: the mentions of the fix in the crawler's
`README.md` ("Finding and fixing an issue on real data", the worked example),
`BACKLOG.md` ("Sync with upstream", RosettaSciIO), the decision log, TEMPLATE.md's
checklist and the em package's README. In the seeded clone they describe a fix that is
not in the code; whether the tester finds and uses them is measured, not graded here.

Notation: `$C` is the tester's clone in its final state; `em` is
`$C/python/modama-formats-em`; `$V` a venv of the grader's own with the clone's packages
(the clone's README, "Getting started"; `python/crawler/AGENTS.md`, "Parallel coding
agents"). Each item: what counts as met, then how to check it. Verdicts: met / partly /
not met / not visible in the clone (evidence that lives only in the tester's report).

## (a) A format collection for MRC

Where it should be: an area `em/src/modama_formats_em/mrc/` (MRC is an EM format; a new
package `modama-formats-<domain>` is also acceptable if the tester gives a reason, then
the library items of TEMPLATE.md apply to it).

- **A1 Spec first.** An OpenSpec change under `$C/python/crawler/openspec/changes/<name>/`
  with `proposal.md`, `tasks.md` and `specs/formats/<area>/spec.md`; scenarios for a
  representative file, a broken file, a misnamed file (a `.map` that is not MRC), and an
  entry nobody has seen; the proposal says which behaviour towards the user changes (new
  records, new summary lines). Check: `ls` the change; read the spec's scenarios.
- **A2 Layout and registration.** `mrc/__init__.py` with `COLLECTION = Collection("em", …)`,
  `mrc/<name>.xml`, `mrc/tests/` with `__init__.py`, `test_fixtures.py` (the one import
  line), `fixtures.toml`, `expected/`; the area imported in `modama_formats_em/__init__.py`
  and added to `PARTS`; format id `em/<format>`. Check: read the files; `$V/bin/modama-crawler
  records --verbose em/src/modama_formats_em/mrc/tests/fixtures` names `em/<format>` for
  each MRC fixture (TEMPLATE.md, core requirement 6).
- **A3 MIME rules in the collection's XML, no clash.** A type named after one used in the
  wild, else `application/x.…`, with the reason in an XML comment; never a generic type.
  `.mrc`, `.map`, `.mrcs` covered. `.map` is used by other programs (JavaScript source
  maps, linker maps): it must not decide the type alone; expected is a magic rule (the
  MRC2014 header has `MAP ` at byte 208) with no `*.map` glob (as `merlin.xml` does for
  `*.hdr`), or a glob plus a content check with `d.not_of_type`. No glob that the core or
  another collection already has (the core has none of the three on 2026-11-13). Check:
  read the XML; in a scratch folder, a JSON file `app.js.map` and a text file `notes.mrc`
  through `records --verbose` with all packages installed: neither is typed as MRC;
  an MRC fixture renamed without extension is still MRC where a magic rule exists.
- **A4 The established reader, pinned exactly with a reason.** `mrcfile` in the package's
  `dependencies` as `mrcfile==<the release current on PyPI at the run's date>` (1.5.4 on
  2026-11-13, looked up then), with a comment saying why that version. Check: `grep -n
  mrcfile em/pyproject.toml`; PyPI's release history for the date of the run.
- **A5 Header only, measured.** The extractor reads the header (1024 bytes) and at most the
  extended header (`nsymbt` bytes), never the data block. Expected: `mrcfile.open(…,
  header_only=True)`, or reading the header through an unbuffered or bounded stream;
  `permissive` or not, chosen with a reason. A test with a large file (a sparse data
  block of hundreds of MB or more) measures `rchar` before and after the extraction
  (`modama_formats_em.testing.rchar`) and asserts a bound that does not grow with the
  data. Met: such a test and a bound near what the format needs, or a buffer-sized bound
  (128 KiB, 1 MiB) with the reason stated (README, "Pitfalls"). Partly: a bound but on a
  small file, or a bound of the file's size. Check: read the test; run it with `-s`.
- **A6 `original_metadata` minus one skip list.** Every header field the reader gives
  (`nx`, `ny`, `nz`, `mode`, the starts, `mx`/`my`/`mz`, `cella`, `cellb`, the axis
  mapping, `dmin`/`dmax`/`dmean`/`rms`, `ispg`, `nsymbt`, `exttyp`, `nversion`, `origin`,
  `nlabl`, the labels …) as found, flat names, minus one named skip list (for example the
  `extra` bytes, `map` and `machst` as placeholders, unused labels), the list named in
  code and in the spec with examples; never a list of wanted fields. `mapped_metadata` as
  a second section where something is computed (voxel size, kind: image stack or
  volume). Check: read the module and the spec; the expected JSON of the representative
  fixture.
- **A7 An entry nobody has seen.** A test adds something the fixtures do not have (a
  made-up label text; or, for an extended header, an unknown field) and asserts it
  arrives in `original_metadata`. Check: read the test; run it.
- **A8 The shared checks.** `modama_crawler.formats.values.textual` decides what is not
  suitable for text and `credential` keeps credentials out (the labels are free text);
  no own versions of either. Check: `grep -n "textual\|credential"` in the module.
- **A9 Time zone.** The MRC header has no date field; labels may hold dates as text, kept
  as text, not parsed. If the tester reads any date or time (an FEI extended header's
  timestamp, a label), it is given as the file writes it and a test runs under another
  `TZ`. Met: no date read and none converted, and `TZ=Europe/Berlin pytest src` in `em`
  passes; or a date read with its TZ test. Check: read the module; run the suite under
  both time zones.
- **A10 The summary line.** A few chosen entries as found, a number after its name, no
  units or words of ours, none guessed (the header's cell is in Å by the standard, but a
  unit printed must come from the reader or the file, else "(unit unknown)");
  TEMPLATE.md, "Lessons", "The summary line". Check: the expected JSON's `summary`.
- **A11 Fixtures with licence and provenance.** At least one representative fixture per
  glob and magic rule (`test_coverage` enforces it), small (no fixture over about 1 MB;
  `mrcfile`'s `fei-extended.mrc` and `epu2.9_example.mrc` are 29 and 34 MB and must not
  be committed whole; cut to the header with the cut in `validity`, as the K2IS and
  block-file fixtures were); each with `purpose`, `validity`, `licence`, `source` (and
  `generator` where generated) in `fixtures.toml`; `LICENSE.fixtures` beside fixtures
  under another licence than MIT, saying where each comes from and what was cut. Public
  sources: `mrcfile`'s test data (BSD-3-Clause repository; its `EMD-*` maps fetched from
  EMDB, whose terms the tester must state with a link; the author of this key did not
  check them), or files written with `mrcfile` at test time (then `validity` says so).
  A broken file as a reproducer (`invalid-by-design`). Check: `du -sh` the fixtures;
  read `fixtures.toml` and `LICENSE.fixtures`.
- **A12 One test per spec scenario, named after it.** Check: list the scenario titles and
  the test names side by side.
- **A13 README row.** A row in `em/README.md`'s table (what it is recognised as, what is
  extracted, an example summary line). Check: read it.
- **A14 All suites green, from the documented commands.** In `em`: `pytest src` and
  `TZ=Europe/Berlin pytest src`; in `python/modama-formats-common`: `pytest src`; in
  `python/crawler`: `pytest`; from the root: `uvx pre-commit run --all-files` (lint, as
  the README's table and CI run it). The search chain's suite needs the EOSC submodules
  and is optional here. Check: run them in `$V` with `--basetemp` and `TMPDIR` under the
  grader's scratch; give passed, failed and skipped counts.
- **A15 Hand-over for people.** The skill's step 6: the format covered, an example
  summary line and a few `original_metadata` lines, the skip list, the new dependency
  with its version, open questions numbered with a lean; and that the independent review
  (step 5) was or was not done. Check: commit messages (`git -C $C log`), the change's
  `proposal.md`; otherwise "not visible in the clone".

## (b) The Merlin header that is not UTF-8

- **B1 A composed reproducer.** A generator in `em/src/modama_formats_em/merlin/tests/
  generate.py` (or a small composed file) that writes a header with `µ` as the single
  byte 0xB5, its lines as the brief gives them; no real file. Its `fixtures.toml` entry
  has `purpose = "reproducer"`, a `validity` that says it is composed (`parser-only`) and
  which lines come from the real file, `licence`, `source`, `generator`. The header must
  contain `Chip ID:` within its first 256 bytes, or `merlin.xml`'s magic does not type it
  as a Merlin header and the test does not reach the extractor (the brief's key list has
  it second). Check: `grep -c $'\xb5'` or `od -c` on the generated header (materialise
  the fixture: run the test with `--basetemp` and look there); the expected JSON shows
  format `em/merlin` and an extraction.
- **B2 The test, named after the scenario.** A test that extracts the fixture and asserts
  the key with `µ` arrives in `original_metadata` with its value (`Sensor Bias (V, µA)`:
  `120 V`) and that the record is described. Check: read it; run it.
- **B3 The test fails without the fix.** On the seeded code the test fails with the
  `UnicodeDecodeError`. Check: in a scratch copy of the clone, put back `with open(path)
  as f:` in `read_header` and run the test: it must fail. Whether the tester showed it
  failing before fixing: commit order (test before fix) or a commit message quoting the
  failure; otherwise "not visible in the clone".
- **B4 The fix.** `read_header` decodes every byte and keeps `µ` as `µ`: Latin-1, or an
  equivalent that never fails and maps 0xB5 to U+00B5. `cp1252` is partly (it fails on
  0x81, 0x8D, 0x8F, 0x90, 0x9D); `errors="replace"` or `"ignore"` is not met (`µ` is
  lost). The docstring says why. Not met: a fix in the copy of RosettaSciIO in the venv.
  Check: read the function; feed it a header line with all 256 byte values in a scratch
  test.
- **B5 The spec scenario restored.** A scenario for a header that is not UTF-8 in the
  Merlin spec (`openspec/changes/em-formats-and-extraction/specs/formats/merlin/spec.md`
  or a new change), its test named after it. Check: read the spec.
- **B6 Upstream noted.** `BACKLOG.md`, "Sync with upstream", has the RosettaSciIO entry
  for `parse_hdr_file` with *worked around here* and how to report it. The seeded clone
  still has the entry from before the seed; met when it is present and true of the code
  after the fix. Check: `grep -n parse_hdr_file $C/python/crawler/BACKLOG.md`.
- **B7 Expected result recorded and reviewed.** `expected/<fixture>.json` for the new
  fixture, with `µ` in the key. Check: read it.
- **B8 Suites green** after (b), as A14.
- **B9 Docs still true.** The README's worked example names the fixture `not_utf8` in
  `fixtures.toml`; met when the reproducer is named so or the README names the new one.
  Check: `grep -n not_utf8` in the README and `fixtures.toml`.

## Answers the main session gives during the run

The tester asks the main session where the docs send it to the person who has the files.
The main session answers as that person, from this list; what is not here it answers with
"decide, write it down as an assumption with your lean, carry on", and notes the question
for the record.

- Real files: none can be given. Assume maps (`.map`, `.mrc`) from processing and
  deposition, and image stacks (`.mrcs`) from collection and processing software; use
  public files or files written with `mrcfile`.
- What a person looks at: the dimensions, the mode (data type), the cell and sampling as
  the header writes them, whether it is an image stack or a volume, the labels. Your
  summary line is fine if it follows TEMPLATE.md.
- What is private or a GUI setting: none known. Labels can hold user names and paths:
  they are what the file says; the credential check applies.
- Names that lie: yes, `.map` is used by other programs (source maps, linker maps).
- The dependency `mrcfile`: approved; pin the current release with the reason, and name
  it in the hand-over.
- The OpenSpec CLI, if missing: write the change's files by hand as the docs describe.
- The independent review (skill step 5): skip it in this test, and say so in the
  hand-over.
- The search stack, browse, Docker: not available in this test (the brief's rule).
- For (b), "ours or upstream's", "which version runs on staging": the staging image
  installs the versions `pyproject.toml` pins; the snapshot's live column ran the
  checkout's code.
- Leans that follow TEMPLATE.md: yes. Anything else: decide, number it as an open
  question with your lean, carry on.
