# Dataset recognition: testing and test data

Status: draft for review, 2026-10-15. Covers R3, R4, R5, R8, R13, R14, R27, R28 and the open questions Q8, Q10, Q18 from `requirements.md`. Two research agents read the projects below on 2026-10-15; I re-checked the claims marked ‡. Section F of `architecture.md` points here.

## Starting point

- Two kinds of tests (R13): **per-handler** tests, universal and self-contained, and **per-deployment** tests on real data in a dedicated pipeline, run regularly in CI on self-hosted runners with access to the data, as LiberTEM does with its collection. The transition from deployment tests to monitoring a deployment is fuzzy (Q18).
- This project indexes metadata, not bulk data, so most behaviour can be tested on very small or mocked files. Real-world issues are caught by the deployment pipelines, then turned into small reproducers for the handler tests (R27).
- Small fixtures can be **generated** in code or **shipped** as files. Generating binds content to expectations and makes round-trips easy, but misses the quirks of files written by other software, and generating invalid or arcane files can turn into confusing code. Shipping captures quirks and allows inspection with external tools, but disconnects content from expectations (R28), and a reproducer derived from a real case may be valid only for our parser, not for the originating application, which is hard to check for arcane formats.
- Other projects' accessible collections may be reused instead of rebuilt.

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
6. Licences: usually only the repository licence, which never mentions data. Data-specific licences exist at nitest-balls1 (PDDL), Bio-Formats samples (public domain), LiberTEM's Zenodo records (CC-BY-4.0), PRONOM's skeleton suite (zlib; PRONOM data OGL), Tika (Apache plus per-file notices).

## Reproducers from real-world cases (R27)

**Generic minimisers don't fit binary formats.** halfempty (archived April 2026), afl-tmin, shrinkray and picire delete or overwrite bytes while a script says whether the result is still "interesting". That breaks offsets, length fields and implied frame counts, so nearly every candidate is garbage, and "our parser still fails" is trivially true for garbage. The predicate must be two-sided: *our handler fails the same way* and *an independent reader or validator still accepts the file*. Delta debugging still applies, but over structural units re-serialised by a real writer: HDF5 datasets, TIFF IFDs, DM tags, notebook cells, Zarr chunks. Byte-level tools remain fine for text sidecars (EMPAD XML, `.ipynb`, `.zattrs`) with `xmllint` or `nbformat.validate` as the guard.

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

RosettaSciIO writes HSpy, ZSpy, NeXus, EMD (NCEM), TIFF, MRCZ, MSA, Blockfile, TVIPS, USID and others; it does not write DM3/DM4, EMPAD, Velox EMD, TIA, MIB or Bruker. For those, a reproducer is either a *mask* (full structure, zeroed data, from a format-specific rewriter) or the original kept in the internal store, and it carries the "parser-only" label from R27.

**Scrubbing.** A reproducer from production carries operator names, session IDs, paths and timestamps in DM tags, HDF5 attributes, EMPAD XML and notebook metadata. pydicom's anonymiser calls itself "a starting point"; `exiftool -all=` works for JPEG but on TIFF only strips the Exif IFD. The pattern that generalises: a per-format allow-list of the metadata keys needed to trigger the issue, blank everything else, zero the data arrays, and a reviewer gate before the file enters a repository.

## Options

**T-A. Per-handler fixtures.**
- A1 *generated in code* (h5py style): expectations and content in one place, round-trips trivial, no bytes in git. Misses quirks of other writers; invalid and arcane files need generator code that gets complex; impossible where no writer exists (DM3/DM4, EMPAD).
- A2 *shipped small real files with a companion expectation record*: captures quirks, inspectable with external tools, works for every format; needs a size and licence policy and a scrub step for files from production.
- A3 *synthetic files with metadata encoded in the name or a sidecar* (Bio-Formats `.fake`): for testing recognition logic (priorities, grouping, nesting) without any real format; cheap, and independent of handlers.
- A4 *skeleton files generated from the XDG rules* (PRONOM): the minimal file satisfying a glob or magic rule; free, exact for conflict detection, meaningless for metadata.

Recommendation: A4 for every rule and A3 for the core's logic, automatically; A2 as the default for format handlers; A1 where a writer exists and a round-trip is the point. Against: three fixture kinds before the first handler is written; mitigated if the core's pytest plugin provides A3 and A4 without handler code.

**T-B. Binding expected outcomes to fixtures (R28).**
- B1 literal asserts in test code: what most projects do; drifts from the files (observation 2).
- B2 a hand-written companion record per fixture (`name.expected.yaml`: type, anchor, members, warnings, selected metadata or the expected error): intentional, reviewable, tedious at hundreds of files.
- B3 recorded on first run and regenerated on purpose (pytest-regressions: diff on failure, `--regen` flag, fail on unused records), bound by the fixture's file stem rather than the test name so renaming a test doesn't orphan it: cheap, catches regressions, can enshrine a bug on first recording unless the diff is reviewed.

Recommendation: B3 with B2's file format, so a record can be written by hand or recorded, and a review of the diff is part of adding a fixture. Against: "recorded and reviewed" relies on discipline; an agent-assisted review of each new record helps (R14).

**T-C. Large and external data.**
- C1 none in per-handler tests: they run offline after installation (R13); anything that doesn't fit the size policy goes to deployment tests or an opt-in tier.
- C2 an opt-in tier with a hash registry in the package and bytes elsewhere (pooch; Zenodo, an institute store, or the collection's own repository at a tagged URL), skipped unless requested, with astropy's strict rule that unmarked tests must not touch the network.
- C3 a sibling store for undistributable files, merged into the same path by CI (Pillow's `test-images`), for data that can't leave the institute.
- C4 reuse of other projects' collections, see the table below, by registry entry with hash and licence, never copied into our repositories.

Recommendation: C1 as the rule, C2 as the opt-in tier, C3 for ER-C's internal reproducers, C4 wherever the licence allows. Against: four tiers to explain; most handlers will only ever use C1.

**T-D. Deployment tests and monitoring (Q10, Q18).** One expectation file per deployment: known-good datasets (anchor paths, optionally expected Dublin Core fields), known-bad cases with the expected report (in the spirit of `pytest.raises`), bounds on unclaimed and generic-only counts per extension (R22), and "no crash, no timeout". Evaluated (a) in CI on a snapshot, either a copy of real files on a self-hosted runner with data access or a captured skeleton tree (listing plus the first N KB of each file), and (b) on the live index after each production crawl, which is the monitoring; only the alerting differs. Against: a skeleton tree can't exercise probes that read beyond N KB, so some deployment tests still need the real files.

**T-E. Validity against the real application.** An optional validator step per format, run in CI over the collection's fixtures, forcing the format module where the tool has one; a second-reader check where no validator exists; the "parser-only" label where neither exists. Nobody does this today, so the cost is unknown; it is cheap to add for TIFF, PNG, JPEG, XML, JSON and notebooks and impossible for DM3/DM4.

**T-F. Size and licence policy.** Numbers to decide: nibabel uses 50 KB compressed per file and 100 MB per repository; RosettaSciIO's largest fixture is a 36 MB zip and it keeps 162 MB in git without reported pain. A licence line per fixture in the companion record (own, CC0, CC-BY-4.0, vendor sample with permission, internal only), required at contribution time.

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

## Decisions needed

- **T1** Offline rule: per-handler tests never download (C1), or may download and cache on first run? Lean: never; downloads only in the opt-in tier and deployment tests.
- **T2** Size policy numbers: per fixture, per collection repository. Lean: 100 KB compressed per fixture, a few MB per collection, exceptions documented in the companion record.
- **T3** Where the deployment pipeline runs and who maintains ER-C's known-good list: a self-hosted iffgit runner with data access exists for LiberTEM; the known-good list could be owned by the data owners, the deployment maintainer, or generated from a reviewed crawl.
- **T4** Expected outcomes recorded and reviewed (B3) or hand-written (B2)? Lean: B3 with review.
- **T5** Validators as an optional CI step (T-E), and "parser-only" as a required label where no independent check exists? Lean: yes to both.
- **T6** Scrubbing and placement: is the allow-list scrub part of the reproducer skill, and are reproducers from production allowed in public handler repositories or only internal ones (C3)?
- **T7** One mechanism for deployment tests and monitoring (T-D)? Lean: yes.
