# Design

## Context

What the code does today (`crawler` at 50533f9):

- **Reuse.** A stored extraction is reused while `(extractor, version, stamp)` equals `(format id, Format.extractor_version, dataset stamp)` and the failure, if any, was not an environment failure (`extraction.py:114-121`). New results are stored under the same triple (`:135-140`), in `datasets.extractor`, `datasets.extractor_version` (`store.py:89`). `Extraction.version` holds the label (`formats/__init__.py:52`). The label is a string raised by hand per format: `dm` `"4"` (`modama_formats_em/dm/__init__.py:76`), `k2is` `"3"` (`k2is/__init__.py:41`), `empad` `"2"`, `merlin` `"1"`, default `"1"` (`formats/__init__.py:200`).
- **Taken-over datasets are still checked.** A dataset taken over with its unchanged directory carries its stored extraction, and `extract()` compares it like any other (`extraction.py:114`). So a new identity re-extracts without recognising again: the walk stays a take-over.
- **The rule set** (`selection.fingerprint`, `selection.py:138-165`) covers the format `version`s, the MIME XML, the selection, the exclusions and the versions of the distributions that provide formats. It leaves the extractor versions out on purpose, and it sees no source. The distribution versions are static (`0.0.1.dev0`), and the search stack's image installs the crawler, `modama-formats-em` and `search-chain` editable (`prototypes/search-stack/crawler.Dockerfile`). So a code change without a bump changes neither the rule set nor the extractor's label.
- **Code is shared across formats.** K2IS reads its `.gtg` with DM's reader (`k2is/__init__.py:15`, `from ..dm import parsed`). DM3 and DM4 are one class. RosettaSciIO is pinned exactly (`modama-formats-em/pyproject.toml`), but its own dependencies (numpy, dask, …) are not.
- **Records and datestamps.** Records are rebuilt from the datasets on every crawl. A record's datestamp moves only when its metadata differs (`store.py:470`). The harvest is incremental, and the DAG indexes only what it harvested (`subtree-crawl` design, Context, "Harvest").
- **The timer** starts every crawl as a process of its own (`cli.py:391`), so anything computed at a crawl's start sees the code installed at that time.
- **Staging, run 3** (`design/field-tests/search-stack-staging-findings.md`, Run 3): 177,166 extractions in about 52 minutes on 8 processes. Summed over the processes: DM4 18,294 s, DM3 5,377 s (23,671 s together, about 50 minutes on 8 processes), Merlin 88 s, EMPAD 10 s. The walk took about 17 minutes, the whole crawl 1 h 17 min, the harvest of 1.45 million changed records 5 h 14 min (F16). For about 170,000 DM records, `subtree-crawl` estimates about 40 minutes of harvest and 45 minutes to two hours of indexing at F16's rates (its Non-Goals).
- **A probe in the VM** (2026-11-12, `importlib.metadata` and `hashlib` only, the scratchpad script `identity_probe.py`): 63 distributions, 39 source files of the crawler, `modama-formats-em` and `search-chain` outside `tests/`, about 250 ms, and the same digest on two runs. It found one pitfall. An editable install leaves a stale `*.egg-info` in the source tree, and `importlib.metadata.distributions()` lists it as a second distribution of the same name, without `direct_url.json`. Only the first one found counts, as `importlib.metadata.distribution(name)` resolves it.

## Evidence: the walk-through of 2026-11-12

@weber's question 90 is quoted in the proposal. His answers to the seven scenarios, verbatim:

- **S1** (many loops by one developer, `crawl --path` on staging): "yes, that should force recrawl independent of version"
- **S2** (two developers, two clones, deploying in turn): "yes, just updating the hash 'by hand' vs code moving is not obvious. Also, we can't always know what may alter behavior, e.g. RosettaSciIO development."
- **S3** (a refactoring that changes nothing: a hash re-extracts everything of that format, costing only CPU): "It is more important that the search reflects the desired state than to save CPU. On the other side of this we are already making it as cheap as possible to extract -- that's where the effort should go."
- **S4** (RosettaSciIO upgraded, with different output): "Yes exactly. We should consider what is simple and robust to make sure we re-extract, without collisions and without burden to developers and operators."
- **S5** (rolling back to an older image): "In these scenarios we may want to recrawl, re-extract, re-index."
- **S6** (which code goes into the hash; K2IS calls DM's reader): "exactly, we may need to cast a wide net what may be good indicators. Sth simple and robust, and rather re-extract than missing sth important. one CAN also extract a sample and see if anything changed, as a self-test?"
- **S7** (a release reaches a deployment): "you mean we upgrade a deployment (for us currently, we pull git and images), and then ./upprod.sh resp. upstaging.sh? Yes, that should bring everything up to date, or at least prompt the user that specific action is needed in case doing it automatically is difficult or not always the right choice."
- **Monitoring** (added the same day): "that is also sth to monitor in staging and production: Does it work as intended, what actually happens, and why?"

## Goals / Non-Goals

**Goals:** the stored extractions always come from the installed code, or are redone by the next crawl. No developer or operator types an identity. Every crawl shows what it redid, why, and with what effect.

**Non-Goals:** saving re-extractions that turn out to change nothing (S3). Making extraction cheaper is the other side of S3, and it is separate work (F14, `cpu-budget`). Identities that are comparable across deployments.

## Decisions

**D1. The identity is a digest of the installation, a wide net (S6).** The crawl computes it once at its start, in the main process, before the workers are spawned. Workers are spawned from the same interpreter and `sys.path`, so they import the same files. The ingredients, as a JSON object with sorted keys, hashed with SHA-256:

| Ingredient | Catches | Example |
|---|---|---|
| `python`: implementation and version (`cpython 3.14.0`) | a base-image upgrade that changes float formatting or a standard-library parser | `python:3.14-slim-trixie` rebuilt with 3.14.1 |
| `distributions`: name → version of every installed distribution, the first one found per name (Context, the probe) | an upgraded reader or one of its dependencies (S4) | `rosettasciio 0.15.0 -> 0.16.0`; numpy picked newer at an image build |
| `source`: path → SHA-256 of every file of the import packages of two kinds of distribution: those that provide formats (entry-point group `modama.formats`: the crawler itself and `modama-formats-em`), and those installed from a path, an archive or a repository (PEP 610: `direct_url.json` present). Paths are relative to the package's parent directory, and `tests/`, `__pycache__` and `*.pyc` are left out. | code moving without a version (S2): our static `0.0.1.dev0`, an editable checkout, RosettaSciIO installed from a git clone during its development | `modama_formats_em/dm/__init__.py` edited; a K2IS change hidden in DM's reader |

*Why so wide.* An extractor's output depends on code that nobody can list by hand: K2IS imports DM's reader, the DM reader imports RosettaSciIO, and RosettaSciIO imports numpy and dask. Following the imports would be fragile (they are lazy, "in the worker only", `dm/__init__.py:27`). Listing the requirements misses an undeclared import. The whole installation is the simplest net that misses nothing that is installed. *What it does not catch:* system libraries outside Python (libc, the kernel's NFS client), environment variables (D4), and data files that a reader loads from outside its package. *Why the files and not RECORD:* an editable install's RECORD lists only the `.pth` file, not the source. Following the import packages (`packages_distributions()`, which `selection.py` already uses, plus `importlib.util.find_spec`) works for editable and regular installs alike, and hashes the code that is actually imported, wherever the checkout is. *Cost:* about 250 ms per crawl (the probe), and the ingredients take about 5 kB as JSON.

The identity's short form, for people, is its first 12 hexadecimal digits (`6d881430e7c8`). The store keeps the full digest.

*Alternatives:* (a) the hand-raised label: the problem (question 90, S1, S2). (b) An identity per format, from the format's module and the modules it imports: K2IS → DM shows that this misses changes, and the lazy imports make it guesswork. (c) A git commit: there is no git in the image, it does not cover dependencies, and an uncommitted change in a clone has the same commit.

**D2. One identity for all formats.** Every dataset of a format with an extractor is compared against the same identity. A change anywhere in the net extracts all of them again. Today one collection has extractors, so one identity per collection would differ only in leaving out the crawler's own source, which the extractors run in (`_storable` and `Extracted` are in the crawler). *Cost, staging:* all of run 3's 177,166 extractions, about 52 minutes on 8 processes, 50 of them for DM, whatever changed. A change that leaves every output as it was then moves no datestamp, so nothing is harvested or indexed (D6 shows that this happened). *Alternative:* the requirements closure of each format's distribution. This is a question in the proposal, with the chain-tool example.

**D3. Equality only, no ordering, no collisions.** A stored extraction is reused when its stored identity equals the running crawl's identity, and is redone otherwise. "Newer" and "older" are never compared, so a rollback (S5) or a deployment that alternates between two clones (S2) is a change like any other. Two installations that differ in any ingredient get different digests. A SHA-256 collision is not a practical concern. Two installations with the same ingredients get the same digest and rightly share their extractions: two clones at the same commit with the same dependencies. The identity is valid within one deployment (question 90). It is not meant to compare deployments, because their dependencies differ.

**D4. The extraction workers' environment is not an ingredient.** The change `cpu-budget` sets `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` to 1 before the workers start, and counts the usable CPUs. Both change speed, not output: the extractors read headers and do no linear algebra. The memory and time limits (`extraction.py:31`, `:38`) decide failures, and failures of the environment are retried anyway (`retry`). If a measurement ever shows a thread count changing an extractor's output, the variable joins the ingredients. The two changes touch `cli.py` near each other and are otherwise independent. The identity is computed without importing numpy, so it does not depend on the order in which `cpu-budget` sets its variables.

**D5. The self-test (S6): recorded extraction results in the plugin now, a check at crawl start later.** There are three options:
- *(a) As part of the identity*, a fingerprint of the fixtures' outputs. It adds nothing. If the code and the dependencies are unchanged, the outputs are too, so a different output always comes with a different digest. It cannot replace the digest either: the fixtures cover a few files, and a change that matters only for real files (a tag that only ER-C's microscopes write) would be missed. S3 and S6 rule that out ("rather re-extract than missing sth important").
- *(b) In the pytest plugin (lean, this change).* The plugin records each fixture's extraction (summary, subjects, values, or the error's type) next to the recognition result in `tests/expected/<name>.json`, and compares and regenerates it as decision T4 does for recognition. The fixtures and `fixtures.toml` stay as they are, and the hand-written checks in `test_extract.py` stay too. A RosettaSciIO upgrade in `pyproject.toml` then fails CI with the changed fields, at the developer's desk before any deployment (S4). It also gives (c) something to compare with.
- *(c) At crawl start in the deployment*, the T-D idea (`design/testing.md`: an expectation file "evaluated … to detect system changes", decision of 2026-10-16). The crawl extracts the representative fixtures before the tree and reports `self-test: 12 fixtures as recorded`, or names the fixture and the field that differ. A difference means that the deployment's environment is not the one in which the expectations were recorded with the code. It is a check that flags, not part of the identity. It needs the fixtures in the deployment: today only because the image installs editable, since they are not package data. This is a question in the proposal, and "Not now" here.

**D6. Monitoring: the report says what was redone, why, and with what effect (R45).** For each dataset, `extract()` already decides between "reuse" and "run". "Run" gets a reason: *new or changed files* (no stored extraction, or another stamp), *retry* (an environment failure), *forced* (a subtree crawl), or *new identity* (only the identity differs). For *new identity*, the crawl groups by format and by the stored identity, and names what changed between that identity's ingredients and the current ones:
- a distribution's version, added or removed: `rosettasciio 0.15.0 -> 0.16.0`;
- source files, grouped by module: `source of modama_formats_em.dm changed`;
- the Python version;
- an identity whose ingredients are not stored (labels from before this change, `"4"`): `earlier identity "4", ingredients unknown`.

More than five differences are cut to five and `and N more` (R36: summarise, don't crowd). The store returns the identifiers of the records whose metadata changed (`RETURNING` on the upsert at `store.py:470`), so the crawl can count, per format, how many of the redone datasets' records changed. The report gets one line per format with such datasets:

```
em/dm4: 150,000 extracted again for a new identity (rosettasciio 0.15.0 -> 0.16.0), 1,200 records changed
```

The counts in this example are round numbers made up for illustration, not measurements. A line with `0 records changed` is a refactoring made visible (S3). Where it shows:
- **the crawl's report and log**: the lines above, plus the run's identity in short form;
- **`runs`**: the run's line ends with `identity 6d881430e7c8` and, when there were any, `extracted again: em/dm4 150,000 (1,200 records changed)`;
- **`modama-chain status`**: the same on its crawl line;
- **`modama-chain trace`**: the crawler line names the dataset's extractor and identity, and whether that is the last finished crawl's (spec `chain-trace`). This answers "why does this record say what it says" for one item;
- **`records`**: its summary names the identity. `records` extracts afresh and has no database, so a note per record would always say the same thing (records-cli, "Routine datasets are counted, not commented").

The self-test's outcome joins the report if (c) is adopted. Where it is checked in practice: the next staging crawls, recorded in the findings file (task 6.2).

**D7. A deployment upgrade (S7): the next crawl does it, and the operator is told.** `./upstaging.sh --build` after `git pull` recreates `crawler` and `crawl-timer` from the new image. Nothing else is needed for extraction. The timer's next crawl (19:00 UTC, or at once if the last finished crawl is more than a day old) computes the new identity and extracts again what it covers (D3). The operator learns what will happen before it happens:
- `modama-crawler runs` prints a note on stderr when the installed identity differs from the last finished crawl's (spec `crawl-runs`). The note names what changed (D6's wording), counts the stored datasets per format whose identity differs (one `GROUP BY` on `datasets`), and estimates the time as their stored `extract_seconds`, summed and divided by the number of extraction processes. For example: `note: extraction identity 6d881430e7c8 differs from the last crawl's 77b1e2d4a0c9 (rosettasciio 0.15.0 -> 0.16.0): the next crawl extracts again em/dm4 150,000, em/dm3 27,000 datasets, about 50 minutes on 8 processes`. The counts here are made up; the 50 minutes is run 3's DM time.
- `upstaging.sh` runs `modama-crawler runs` in the `crawler` container after `up --wait`. It prints its note and, when there is one, the command to start the crawl now (`docker compose -p search-staging … run --rm crawl-timer modama-crawler crawl`, the one-off container of `subtree-crawl` D6). Starting it is the operator's choice (requirements-pipeline 2.4: "what it chose, and why, is visible; overriding it is easy"). Whether the script should start it by itself is a question in the proposal.
- *Downstream:* the re-extraction rewrites the datasets. The records are rebuilt, and only those whose metadata differs get a new datestamp (`store.py:470`). The harvest the crawl triggers is incremental, so the warehouse and the index see only those records. After a refactoring, nothing. After a RosettaSciIO upgrade that changes a number in every DM description, about 170,000 records: about 40 minutes of harvest and 45 minutes to two hours of indexing (Context).
- *Production:* `deploy/upprod.sh` does not start the search stack yet. When the stack moves to `deploy/`, `upprod.sh` gets the same call to `runs` (Not now). The behaviour of the crawl itself is the same there.

**D8. Storage: one migration.** In the change `schema-migrations` (Alembic), whichever number follows `subtree-crawl`'s `scope` (0002):
- rename `datasets.extractor_version` to `extractor_identity`. The values stay, and no stored label equals a digest, so the first crawl extracts everything once (Migration Plan). The rename keeps the column's name honest for `search-chain`, which reads the crawler's tables as an interface;
- `crawl_runs.identity TEXT` (the digest) and `crawl_runs.identity_ingredients JSONB` (D1's object, about 5 kB per run). D6 looks up the ingredients of a stored identity in the newest run that has that digest;
- `crawl_runs.reextracted JSONB`: per format, the datasets extracted again for a new identity, their changed records and the differences, as reported (D6).

If this change ships before `schema-migrations`, `ensure_tables` adds the columns in place only when they are missing, as `subtree-crawl` D5 does for `scope`. The database is not recreated.

## Sequences of events

The file is `adhoc/libertem/libertem-test-data/dm/a.dm4`. Its stamp S stays the same throughout (the file is not touched). The installation's code is C0, with identity `h0`, and `a.dm4` is stored with C0's description under `h0`. "Nightly crawl" means the timer's full crawl.

**S1 and H3: an experiment with `crawl --path`, then a revert** (replaces the right-hand column of `subtree-crawl` D3's table).

| Step | What is stored for `a.dm4` | Elsewhere in the tree |
|---|---|---|
| 1. DM's reader is changed to C1; the image is rebuilt (identity `h1`); `crawl --path adhoc/libertem/libertem-test-data` | C1's description under `h1`; if it differs from C0's, a new datestamp, harvested | still C0 under `h0` |
| 1a. If the image with C1 stays deployed overnight: the nightly crawl | reused (`h1` = `h1`) | every DM, K2IS, EMPAD and Merlin dataset extracted again under `h1`, about 52 minutes; only changed records harvested |
| 2. Further loops C2, C3, … with `crawl --path` | `h2`, `h3`, …: nothing to raise, nothing to merge | as in 1 or 1a |
| 3. Reverted to C0, the image rebuilt (`h0` again); the nightly crawl, without another `crawl --path` | `h3` ≠ `h0`: extracted again with C0, C0's description is back, a new datestamp, harvested | if 1a happened: everything extracted again under `h0`; otherwise reused |

Reuse never crosses an identity change, so the experiment is undone by itself (H3 resolved). `subtree-crawl`'s forced run stays, for the performance tests @weber wants. It is no longer needed for correctness.

**S5: rolling back an image.** Image v2 (identity `h2`) is deployed after v1 (`h1`).

| Step | Stored | Downstream |
|---|---|---|
| 1. v2 deployed; the next crawl | everything extracted under `h2` | records whose content changed are harvested and indexed |
| 2. A problem with v2; the operator deploys v1 again (with `schema-migrations`, after its downgrade step); `upstaging.sh` prints the note (`h2` → `h1`, what changed, how many) | — | — |
| 3. The next crawl | `h2` ≠ `h1`: everything extracted again with v1 | the records changed in step 1 change back, get new datestamps and are harvested and indexed again: re-crawl, re-extract, re-index (S5) |

With today's labels, step 3 works only if v2 raised the label of every format whose output it changed. If v2's change was in RosettaSciIO's dependencies, nothing would be redone.

**S2: two clones deploying in turn.** Developers A and B deploy their clones to staging on alternate days, with identities `hA` and `hB`. Each nightly crawl after a switch extracts everything again (`hA` ≠ `hB`), and the search shows the deployed clone's output. Nothing is typed, so nothing collides and nothing needs merging. If both deploy the same commit with the same dependencies, the identities are equal and the extractions are reused. *Cost:* about 52 minutes per switch on staging, plus the harvest of what differs. Accepted (S3).

**S4: RosettaSciIO upgraded.** The pin moves from 0.15.0 to 0.16.0 in `modama-formats-em/pyproject.toml`. CI fails where a fixture's output changed (D5 b). The developer reviews the diff and regenerates. After the deployment, the note names `rosettasciio 0.15.0 -> 0.16.0`, the nightly crawl extracts everything again, and the report shows how many records changed per format.

## Risks / Trade-offs

- [Every deployment of any change in the net costs a full re-extraction (about 52 minutes on staging)] → accepted (S3). The report shows when it changed nothing (D6). If it becomes a burden, narrow the net with a concrete example (proposal question).
- [An unpinned dependency picked newer at an image build re-extracts everything, although nobody changed anything] → the note and the report name it (`numpy 2.3.4 -> 2.4.0`). This is S4's case, and it is caught on purpose.
- [A source file edited during a crawl in an editable install: the workers, which are replaced every 100 tasks (`extraction.py:39`), import the new code, while the identity is the old one] → the results are stored under an identity that did not produce them. The next crawl computes the new identity and extracts again, so this heals by itself. It happens only in development.
- [A stale `*.egg-info` in a source tree is a second distribution of the same name] → the first one found counts (D1, the probe). A test covers it.
- [Code outside the net changes output: a system library, a data file loaded from outside its package] → not covered. The recorded fixture results (D5 b) catch it where a fixture exercises it.
- [The first crawl after this change extracts everything, because the stored labels are not digests] → once, reported as `earlier identity "4", ingredients unknown`. About 52 minutes on staging. Production has no extractions stored yet.
- [`subtree-crawl` and this change both modify the requirement "Extraction follows the identified extractor"] → whichever is archived second takes the other's text: `subtree-crawl`'s sentence "In a crawl of the whole tree" and "A subtree crawl reuses no stored result under its path" go into this change's wording, or the other way round (task 7.1).

## Migration Plan

Deploy with `schema-migrations` (the migration of D8) and an image rebuild. The first crawl extracts everything once. Rollback: the migration's downgrade renames the column back and drops the run columns, and the old code then compares its label (`"4"`) with a digest and extracts everything once more. Both directions cost one re-extraction and harvest only what changed.

## Interaction with other changes

- **`em-formats-and-extraction`** (open, on `crawler`): holds the `extraction` spec that this change modifies. It is archived first. Its scenario "A new extractor version" is replaced by the scenarios of the identity.
- **`subtree-crawl`** (open): its finding H3 is resolved by D3 and the S1 sequence. Its proposal's question "Should reverting an experiment undo it by itself?" becomes option B. Its D7 (request 2, "bump the version and crawl now") becomes "change the code, rebuild, crawl now". The procedure in its README (its task 4.2) loses the bump and the manual undo step. Its revert scenario can now be written (task 7.1).
- **`cpu-budget`** (open): D4. Independent apart from neighbouring lines in `cli.py`.
- **`schema-migrations`** (open): D8 is one migration there.

## Not now

- A self-test at crawl start in the deployment (D5 c), with the fixtures as package data; T-D's expectation file of real datasets after it.
- The identity in the rule set, so that a recognition change without a `version` also re-recognises (proposal question).
- An identity per collection or per format, or a net narrowed to the requirements closure (D2, proposal question).
- A forced re-extraction of the whole tree without a code change (`crawl --format`, `subtree-crawl` D7 alternative a).
- `upprod.sh` printing the note, when the search stack moves to `deploy/` (D7).
- Comparing identities across deployments, or publishing the identity in records (`dc:source` of the software).
