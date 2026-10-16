# Dataset recognition: testing and test data

Status: fourth draft; T1 to T7 and T-A decided by @weber on 2026-10-15 (T3 deferred). The document is organised around the two purposes of test files below. Covers R3, R4, R5, R8, R13, R14, R27, R28 and the open questions Q8, Q10, Q18 from `requirements.md`. Two research agents read the projects below on 2026-10-15; I re-checked the claims marked ‡. Section F of `architecture.md` points here.

## Starting point

- Two kinds of tests (R13): **per-handler** tests, universal and self-contained, and **per-deployment** tests on real data in a dedicated pipeline, run regularly in CI on self-hosted runners with access to the data, as LiberTEM does with its collection. The transition from deployment tests to monitoring a deployment is fuzzy (Q18).
- This project indexes metadata, not bulk data, so most behaviour can be tested on very small or mocked files. Real-world issues are caught by the deployment pipelines, then turned into small reproducers for the handler tests (R27).
- Small fixtures can be **generated** in code or **shipped** as files. Generating binds content to expectations and makes round-trips easy, but misses the quirks of files written by other software, and generating invalid or arcane files can turn into confusing code. Shipping captures quirks and allows inspection with external tools, but disconnects content from expectations (R28), and a reproducer derived from a real case may be valid only for our parser, not for the originating application, which is hard to check for arcane formats.
- Other projects' accessible collections may be reused instead of rebuilt.

## Two purposes of test files

Test files serve two purposes that must not be mixed, because they have different standards of realism, different expected outcomes and different obligations.

**Representative files** show what a handler must recognise and extract. They are realistic files as found in the wild: written by the instrument software, exported by the application, or produced by the library that writes the format in practice (h5py for HDF5, zarr-python for Zarr, nbformat for notebooks, tifffile for TIFF). A file generated in a test counts as representative only when its generator is such a real-world producer; our own code mimicking a format does not count, because it would reproduce our assumptions, not the format. They are minimal in the RosettaSciIO sense (few pixels, non-square, zero signal) but otherwise exactly what the producer writes.

Coverage rule: **every file-specific rule has at least one representative file that matches it**: each glob, each magic rule, each Python handler and each of its branches. The core's test plugin checks this by running recognition over a collection's representative files and recording which rules fired (the same basis output as R9); a rule that no representative file exercises fails the collection's tests. This is the opposite direction from PRONOM's skeletons, where the rule generates the file.

**Reproducers** are files that caused a crash, a hang, a wrong result or an unexpected report because they are invalid, incomplete (a copy in progress, a truncated transfer), corrupted, or a variant the handler didn't expect. They are the only exception from realism: a reproducer may be invalid by nature, and its expected outcome is a behaviour (this warning, this error, no crash, within the time budget), linked to the originating issue. They never count towards the coverage rule. Two kinds end differently: a valid but unexpected variant becomes a representative file once the rules are extended to cover it; a broken file stays a reproducer.

**Rule-processing tests** cover the parameter space of the rule engine: glob weights and case flags, magic offsets, ranges, masks and nested matches, the longest-pattern rule, subclass refinement, priority ties, and the reduction stage over directory groups. They use synthetic inputs and live in the core, never in a handler collection. PRONOM-style skeleton files and Bio-Formats-style `.fake` files belong here and only here: a synthetic file that satisfies a name rule keeps passing after a content rule is added or refined, and would hide exactly the gap the content rule was meant to close.

| | Representative | Reproducer | Rule-processing |
|---|---|---|---|
| Tests | the format and its metadata | robustness against broken input | the engine |
| Realism | as in the wild, minimal | whatever caused the failure | synthetic |
| Expected outcome | type, anchor, members, metadata | behaviour: warning, error, no crash, within budget | engine result |
| Validity field (T5) | `vendor-written`, `validated-by`, `second-reader`; `parser-only` only with a reason | `invalid-by-design: <issue>` | n/a |
| Coverage obligation | at least one per file-specific rule | none | parameter space of the engine |
| Lives in | the handler collection | the handler collection, scrubbed and reviewed (T6) | the core |

## What other projects do

| Project | Fixtures | Expected outcomes | Large or external data; when absent | Policy |
|---|---|---|---|---|
| [RosettaSciIO](https://raw.githubusercontent.com/hyperspy/rosettasciio/main/CONTRIBUTING.rst) ‡ (EM formats) | 633 real files, 162 MB, in git but not in wheels; fetched by pooch from the tagged release with a sha256 registry | literal asserts; round-trip tests for writers | all data this way; offline needs a local mirror via env var | "generated using third party software", "minimum number of pixels", "non-square grid", "no signal (e.g. zeros)", "available openly"; no licence statement |
| [Bio-Formats](https://bio-formats.readthedocs.io/en/stable/developers/commit-testing.html) | private curated QA repository, nightly; synthetic `.fake` files with metadata in the name for logic tests | one `.bioformats` INI per input, tool-generated (`gen-config`), diffed; MD5 of plane 0 and of a 512² tile | public samples exist but without expected results | bug-report samples go to Zenodo under CC-BY or more open |
| [LiberTEM](https://libertem.github.io/LiberTEM/contributing.html) | mostly synthetic; real corpus unpublished, run by organisation members on a self-hosted agent | literal asserts | skip when `TESTDATA_BASE_PATH` is absent | public Zenodo samples, CC-BY-4.0, 177 MB to 14 GB |
| [nibabel](https://nipy.org/nibabel/devel/add_test_data.html) ‡ | 88 small files, 3 MB, with a provenance README; larger data in 9 git submodules | literal asserts | `needs_nibabel_data` skips; an uninitialised submodule skips silently | "around 50K or less when compressed", "Up to a hundred megabytes in one repository", prefers PDDL 1.0 or CC0 |
| [pydicom](https://raw.githubusercontent.com/pydicom/pydicom/main/src/pydicom/data/data_manager.py) | 176 files in the wheel; 85 more in `pydicom-data` | literal asserts | name-to-hash registry in the package, bytes downloaded on demand; returns `None` on failure, which caused offline bugs | moved data out of the package "to reduce the package download size" |
| [Pillow](https://raw.githubusercontent.com/python-pillow/Pillow/main/Tests/oss-fuzz/build.sh) | 1072 real images, 58 MB, in git and sdist, many from bug reports and advisories; the corpus doubles as fuzzing seed | pixel comparison against reference images | a sibling `test-images` repo for files it "can't distribute", merged into the same path by CI; tests skip without it | none stated |
| [astropy](https://github.com/astropy/pytest-remotedata/blob/main/README.rst) | small files in the package; remote files by name or content hash, cached | literal asserts | `@pytest.mark.remote_data`, run only with `--remote-data`; strict mode fails *unmarked* network use | remote tests "fail sometimes for reasons outside our control" |
| h5py, zarr-python | generated: h5py creates every file in `setUp`, five shipped regression files it can't write itself; zarr v3 regenerates v2 fixtures with a pinned old zarr via `uv run` | compare to the generating code | none | ship bytes only for what you can't produce |
| tifffile | none in the repository; private | literal asserts with the originating issue in a comment | skip if the data directory is absent | outsiders can only run the data-free subset |
| [pytest-regressions](https://pytest-regressions.readthedocs.io/en/latest/overview.html), syrupy | n/a | recorded on first run into a file next to the test, diffed afterwards, regenerated with a flag; syrupy fails on unused snapshots | n/a | hand-written asserts "get old quickly" |
| file/libmagic, PRONOM | `X.testfile` and `X.result` pairs; skeleton files generated from every signature | the result file; the expected PUID in the file name | n/a | one test pair per bug and per new rule |

Observations:

1. Projects that can write a format generate fixtures (h5py, zarr); pure readers ship real files. Hybrids exist: Bio-Formats uses synthetic `.fake` files for logic and real files for formats; zarr pins a foreign writer instead of shipping bytes.
2. Only Bio-Formats and the regression tools make expected outcomes a reviewable artefact next to the input. Everyone else asserts literals in test code, which detaches content from expectations (R28).
3. Everyone skips when data is absent, with different triggers; only astropy enforces that unmarked tests stay offline, and pydicom's "return `None`" semantics caused bugs.
4. Numeric size policy only at nibabel (50 KB compressed per file, 100 MB per repository). No project reported repository-size pain; pydicom and RosettaSciIO moved data out of the *package*, not out of git.
5. Validity comes from an independent producer: vendor software, bug reports, a foreign writer. No project checks a fixture against the real application automatically, beyond round-trip tests.
6. Synthetic files are used by their projects for engine and conflict tests, not as evidence that a format is handled: Bio-Formats' `.fake` files test logic, PRONOM's skeletons find conflicting signatures.
7. Licences: usually only the repository licence, which never mentions data. Data-specific licences exist at nitest-balls1 (PDDL), Bio-Formats samples (public domain), LiberTEM's Zenodo records (CC-BY-4.0), PRONOM's skeleton suite (zlib; PRONOM data OGL), Tika (Apache plus per-file notices).

## Deriving small files from real-world cases (R27)

A large real-world file is shrunk for one of the two purposes, and the purpose decides what must be preserved: for a representative file, validity, so an independent reader or the real application still accepts it; for a reproducer, the failure, so our handler still fails the same way, with the file kept as close as possible to the cause.

**Generic minimisers don't fit binary formats.** halfempty (archived April 2026), afl-tmin, shrinkray and picire delete or overwrite bytes while a script says whether the result is still "interesting". That breaks offsets, length fields and implied frame counts, so nearly every candidate is garbage, and "our parser still fails" is trivially true for garbage. For a reproducer the predicate must be two-sided: *our handler fails the same way* and *the file still resembles the original*, otherwise the minimiser converges on garbage that fails for a different reason; for a representative file the predicate is *an independent reader or validator still accepts it* and *our handler still extracts the same metadata*. Delta debugging still applies, but over structural units re-serialised by a real writer: HDF5 datasets, TIFF IFDs, DM tags, notebook cells, Zarr chunks. Byte-level tools remain fine for text sidecars (EMPAD XML, `.ipynb`, `.zattrs`) with `xmllint` or `nbformat.validate` as the guard.

**Per-format recipes for the spike formats:**

| Format | Shrink | Independent check |
|---|---|---|
| HDF5 | copy the group and attribute tree with h5py, zero-fill or slice datasets, `h5repack --filter=GZIP=9`; structure and attributes stay identical, size drops to KB | `h5dump --enable-error-stack` opens it, `h5diff` on structure; `h5check` is the only spec validator and dates from 2014 |
| Zarr | copy the metadata, delete chunk files: [missing chunks read as `fill_value`](https://zarr.readthedocs.io/en/stable/user-guide/arrays/) ‡ | zarr opens it with `read_missing_chunks=False` for a strict check; no official validator |
| TIFF | rewrite with `tifffile` keeping extra tags; `tiffcrop` may drop private tags | `jhove -m TIFF-hul` (always force the module: a truncated TIFF passes as a byte stream otherwise, [jhove#316](https://github.com/openpreserve/jhove/issues/316) ‡), `tiffinfo -D` |
| Jupyter | `nbstripout`, drop cells | `nbformat.validate` |
| EMPAD | truncate the raw to whole frames (130×128 float32), edit the frame count in the XML | a second reader (RosettaSciIO's `empad`), no validator |
| DM3/DM4 | no maintained open writer; RosettaSciIO reads only; TEMDM offers an unlicensed write-back tool | only Gatan GMS; a second reader (RosettaSciIO, ncempy) is the proxy |
| Python environment, `node_modules` | regenerate a tiny tree with the marker files | none needed |

RosettaSciIO writes HSpy, ZSpy, NeXus, EMD (NCEM), TIFF, MRCZ, MSA, Blockfile, TVIPS, USID and others; it does not write DM3/DM4, EMPAD, Velox EMD, TIA, MIB or Bruker. For those, a small representative file is a *mask* (full structure, zeroed data, from a format-specific rewriter) whose validity can only be confirmed by a second reader or the vendor application, which the validity field records.

**Scrubbing.** A reproducer from production carries operator names, session IDs, paths and timestamps in DM tags, HDF5 attributes, EMPAD XML and notebook metadata. pydicom's anonymiser calls itself "a starting point"; `exiftool -all=` works for JPEG but on TIFF only strips the Exif IFD. Decided (T6): the reproducer skill always scrubs with a per-format allow-list of the metadata keys needed to trigger the issue, blanks everything else, zeroes the data arrays, and requires a human review before the file is committed. A scrubbed and reviewed reproducer goes into the handler's repository by default, public or not; an internal store per deployment is deferred until a case needs it.

## Options

**T-A. Per-handler fixtures, decided.**
- A1 *generated in code by a real-world producer* (h5py, zarr-python, nbformat, tifffile): representative, since the generator is what writes such files in the wild; expectations and content in one place; no bytes in git. Only where such a producer exists and is a test dependency we accept.
- A2 *shipped small real files with a companion expectation record*: representative; captures the quirks of instrument and application output; inspectable with external tools; works for every format; needs the size and licence policy (T2) and, for files from production, the scrub step (T6).
- A3 *synthetic files with metadata encoded in the name or a sidecar* (Bio-Formats `.fake`) and A4 *skeleton files generated from the XDG rules* (PRONOM): confined to the core's rule-processing tests. Not allowed as evidence that a format is handled: they test the engine, not the file type, and they keep passing when a content rule is added or refined.

Decided: representative files are A2 by default and A1 where a real-world producer exists; every file-specific rule has at least one; reproducers are the only exception from realism; A3 and A4 stay in the core. Risk accepted: some formats have no small realistic file and no open writer (DM3/DM4), so their representative file is a mask with a second-reader validity entry.

**T-B. Binding expected outcomes to fixtures (R28).**
- B1 literal asserts in test code: what most projects do; drifts from the files (observation 2).
- B2 a hand-written companion record per fixture (`name.expected.yaml`: purpose, validity, licence and provenance, then for a representative file type, anchor, members, warnings and selected metadata, for a reproducer the expected behaviour and the originating issue): intentional, reviewable, tedious at hundreds of files.
- B3 recorded on first run and regenerated on purpose (pytest-regressions: diff on failure, `--regen` flag, fail on unused records), bound by the fixture's file stem rather than the test name so renaming a test doesn't orphan it: cheap, catches regressions, can enshrine a bug on first recording unless the diff is reviewed.

Decided (T4): B3 with B2's file format, so a record can be written by hand or recorded, and a review of the diff is part of adding a fixture; LiberTEM does the same with notebooks. Risk accepted: "recorded and reviewed" relies on discipline; an agent-assisted review of each new record helps (R14).

Preliminary layout (2026-10-15), kept until the spike shows friction or gaps; it keeps the hand-written part small and the fixture tree clean. The record splits into *provenance* (hand-written once, four keys, one manifest per collection) and the *expected outcome* (the recognition output for the fixture, recorded and reviewed, no schema of its own). A fixture is a directory that contains exactly what the wild contains, because sibling rules, directory markers and stray-file reporting would otherwise see a sidecar; everything else lives beside the tree, bound by the fixture's name:

```
empad/
  empad.xml                  # XDG rules
  empad.py                   # reduction handler
  tests/
    fixtures/
      scan_001/              # exactly as in the wild: scan_001.xml + scan_x256_y256.raw
      truncated_raw/         # reproducer: same, raw cut mid-frame
    fixtures.toml            # provenance: purpose, validity, licence, source per fixture
    expected/
      scan_001.yaml          # recorded recognition output, reviewed
      truncated_raw.yaml
    test_empad.py            # optional, for anything beyond the recorded outcome
```

The core's pytest plugin discovers `fixtures/*`, runs recognition on each directory, compares with `expected/<name>.yaml`, fails on fixtures without a manifest entry or expected files without a fixture, and applies the coverage rule from which rules fired. Bio-Formats mirrors its data tree in a separate config tree for the same reason.

**Automation around fixture trees (R14).** Three layers, from deterministic to judgement-based:

1. *Checks*, deterministic, run by pre-commit locally and by the core's pytest plugin in CI; they fail, they don't fix:
   - every fixture directory has a manifest entry with the four keys, and every manifest entry and every `expected/` file has a fixture;
   - the fixture tree contains only wild files: no sidecars, no `.gitkeep`, no editor leftovers;
   - the size policy (T2), with the override recorded in the manifest;
   - the validity field is consistent with what the collection can check: `validated-by` only where the tool ran, `invalid-by-design` only with `purpose = "reproducer"`;
   - the coverage rule: every file-specific rule fired on at least one representative fixture;
   - the format validators (T5) over representative fixtures where a tool exists;
   - a scrub heuristic: known metadata keys for people and sessions (operator, user, sample owner, session id, host paths) are empty or absent in files that came from production.
2. *Skills*, one agent with judgement, invoked on demand:
   - **add a fixture** from a real file: decide the purpose, shrink accordingly (`Deriving small files` above), scrub (T6), run the validators, record the expected outcome, write the manifest entry, and present the diff for review;
   - **review an expected-outcome diff**: explain what changed in the recorded recognition output and whether it looks like a regression, a legitimate rule change, or a fixture problem, before a human accepts a regenerated record;
   - **triage a failure report** from a deployment (R8, R27): capture the directory as a skeleton tree, reproduce, derive a reproducer or a representative variant, and propose the rule extension or code fix with the test;
   - **find or propose a MIME type** for a new format (backlog).
3. *Workflows*, fanning out over many collections, for maintenance:
   - **audit fixture trees** across all enabled collections: run the checks, summarise, and open a change per collection with proposed fixes (missing manifest entries, stale validity fields, uncovered rules after a rule change);
   - **unclaimed review** (R22): from the deployment's report of unclaimed and generic-only files, find candidates for missing handlers or rule extensions.

The checks are the part that must exist before the first collection has ten fixtures; the skills are what makes R14 real for AI agents; the workflows come when there are enough collections to need them.

**T-C. Large and external data.**
- C1 none in per-handler tests: they run offline after installation (R13); anything that doesn't fit the size policy goes to deployment tests or an opt-in tier.
- C2 an opt-in tier with a hash registry in the package and bytes elsewhere (pooch; Zenodo, an institute store, or the collection's own repository at a tagged URL), skipped unless requested, with astropy's strict rule that unmarked tests must not touch the network.
- C3 a sibling store for undistributable files, merged into the same path by CI (Pillow's `test-images`), for data that can't leave the institute.
- C4 reuse of other projects' collections, see the table below, by registry entry with hash and licence, never copied into our repositories.

Decided (T1): C1 is the rule; the test suite never downloads. C2 as the opt-in tier and C4 wherever the licence allows. C3 (an internal store for undistributable files) is deferred to the backlog until a case needs it (T6). Risk accepted: several tiers to explain; most handlers will only ever use C1.

**T-D. Deployment tests and monitoring (Q10, Q18), decided (T7, refined 2026-10-16).** The expectation file is the deployment's regression test, recorded once the admin is happy with a crawl: a representative sample of datasets from their tree with the outcomes they accepted (type, anchor, members, warnings, optionally Dublin Core fields), known-bad cases with the expected report (in the spirit of `pytest.raises`), and "no crash, no timeout". Its purpose is to tell a change in the *system* (a handler upgrade, a rule edit, a core change) apart from a change in the *data*, so it is evaluated against a frozen snapshot of the sample, a captured skeleton tree (listing plus the first N KB of each file) or copied real files on a runner with data access, in CI and after each production crawl. Data changes are the crawl report's job: unclaimed and generic-only counts by extension and location, with bounds the admin may set (R22). Same evaluator for both, different inputs, different meaning of an alert. Deferred (T3): where the pipeline runs and who owns ER-C's known-good list; the first version is run by hand, automation follows once it exists. Against: a skeleton tree can't exercise probes that read beyond N KB, so some deployment tests still need the real files.

**T-E. Validity against the real application, decided (T5).** An optional validator step per format, run in CI over the collection's fixtures, forcing the format module where the tool has one (`jhove -m TIFF-hul`, `tiffinfo -D`, `nbformat.validate`, `xmllint`, `h5dump`); and a required field in each fixture's companion record saying how its validity is known: `vendor-written`, `validated-by: <tool>`, `second-reader: <library>`, `parser-only` with a reason (the label from R27), or `invalid-by-design: <issue>` for reproducers. Nobody does this today, so the cost is unknown; it is cheap for TIFF, PNG, JPEG, XML, JSON and notebooks and impossible for DM3/DM4, where a second reader is the proxy.

**T-F. Size and licence policy, decided (T2).** 100 KB compressed per fixture and a few MB per collection repository, enforced by a pre-commit check that can be overridden, with the override justified at review and documented in the companion record. For comparison: nibabel uses 50 KB per file and 100 MB per repository; RosettaSciIO keeps 162 MB in git, largest fixture 36 MB, without reported pain. A licence line per fixture in the companion record (own, CC0, CC-BY-4.0, vendor sample with permission, internal only), required at contribution time.

## Reusable collections

| Collection | Access | Data licence as stated | Size | Fetch | Expected results |
|---|---|---|---|---|---|
| LiberTEM internal collection | self-hosted runners, organisation members | internal | large | mounted path | none |
| [LiberTEM Zenodo samples](https://libertem.github.io/LiberTEM/sample_datasets.html) | public | CC-BY-4.0 per Zenodo record | 177 MB to 14 GB | Zenodo DOI | dimensions only |
| [RosettaSciIO test data](https://raw.githubusercontent.com/hyperspy/rosettasciio/main/rsciio/tests/registry.txt) | public | none stated; repository is GPL-3 | 633 files, 162 MB | pooch registry, versioned raw URL | none |
| [Bio-Formats samples](https://downloads.openmicroscopy.org/images/) | public | per-directory readme, e.g. DICOM samples public domain | per-format directories | HTTPS directory | none public |
| [Tika test-documents](https://raw.githubusercontent.com/apache/tika/main/LICENSE.txt) | public | Apache-2.0 plus per-file notices | 1186 files, 147 MB | raw GitHub | in Java tests |
| [PRONOM skeleton suite](https://zenodo.org/api/records/4297109) | public | zlib for the suite, OGL for PRONOM data | 0.7 MB | Zenodo DOI | PUID in the file name |
| pydicom, nibabel, Pillow, h5py, astropy | public | repository licence only, no data statement | small to 60 MB | raw GitHub, registries | none |

Usable for us: LiberTEM's collection for the ER-C deployment pipeline; RosettaSciIO's files for EM formats in an opt-in tier (licence to clarify with them; the repository is GPL-3 but the data has no statement); Bio-Formats samples per directory licence; Tika's documents for office and generic formats. Pillow's and pydicom's corpora are usable in practice but carry no data licence.

## Decisions

Decided by @weber on 2026-10-15 and recorded in the decision log of `architecture.md`:

- **T1** Per-handler tests never download; external data only in the opt-in tier and deployment tests.
- **T2** Size policy: 100 KB compressed per fixture, a few MB per collection, enforced by an overridable pre-commit check with the override justified at review.
- **T3** Deferred: where the deployment pipeline runs and who owns ER-C's known-good list. Run by hand first, automate once it exists.
- **T4** Expected outcomes are recorded on first run and reviewed, bound to the fixture's file stem.
- **T5** An optional validator step per format in CI, and a required validity field per fixture, with `parser-only` where nothing but our parser can check it.
- **T6** Reproducers from production data are always scrubbed and reviewed; they go into the handler's repository by default. An internal store is deferred to the backlog.
- **T7** One expectation file per deployment serves both CI tests on a snapshot and monitoring after each production crawl.
- **T-A** Test files have two purposes, representative files and reproducers. Representative files are realistic files from the wild, shipped or generated by a real-world producer; every file-specific rule has at least one. Reproducers for invalid or incomplete files are the only exception from realism. Synthetic and skeleton files are confined to the core's rule-processing tests.
