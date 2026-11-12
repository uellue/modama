# Tasks

## 1. Requirements and decisions

- [ ] 1.1 Write R44 and R45 into `design/requirements.md` with the wording in `proposal.md` ("Proposed requirement wording"), next to R41 to R43 of the open changes (check that the numbers are still free). Add a row to the decision log in `design/architecture.md`: the identity is derived from the installation (D1, D2), compared for equality only (D3), recorded fixture extractions now and the check at crawl start later (D5), and @weber's answers to the proposal's questions. Verify: the diff, reviewed by @weber.

## 2. The identity

- [ ] 2.1 New module `src/modama_crawler/identity.py`: the ingredients (D1; the first distribution found per name), the digest and its short form, and the differences between two sets of ingredients in D6's wording, cut at five. Verify: `tests/test_identity.py`, one test per scenario of the requirement "The extractor identity is derived from the installation", plus a stale `*.egg-info` ahead of the real distribution and the wording of each kind of difference; computing it in the VM takes under one second (logged at debug level).

## 3. Reuse and storage

- [ ] 3.1 Reuse by identity (D3): `extract()` takes the crawl's identity, and `Extraction.version` becomes `identity`. Remove `Format.extractor_version` from `formats/__init__.py`, from the four `modama-formats-em` formats and from `modama_formats_em/testing.py:99`. Update `formats/TEMPLATE.md` and the README (how a changed extractor reaches the index). Verify: `tests/test_extraction.py`, one test per scenario of the modified requirement "Extraction follows the identified extractor" (identities passed in, two crawls of a test tree); the `em` collection's tests pass.
- [ ] 3.2 Storage (D8): rename `datasets.extractor_version` to `extractor_identity`, and add `crawl_runs.identity`, `identity_ingredients` and `reextracted`, as a migration of `schema-migrations` with its downgrade, or in place in `ensure_tables` if this change ships first. Verify: the migration's test upgrades and downgrades a database with stored extractions without losing rows, and the first crawl after the upgrade reports `earlier identity "4", ingredients unknown` (spec scenario "An identity from before this change").

## 4. Monitoring (R45)

- [ ] 4.1 Re-extraction reasons, report lines per format, the changed records counted from the upsert's returned identifiers, and the counts stored with the run and shown by `runs` (D6). Verify: tests per scenario of "The crawl reports re-extraction and its cause"; `test_runs.py` for the run line.
- [ ] 4.2 The note of `runs` (D7). Verify: `test_runs.py` per scenario of "The runs command says what the next crawl will extract again", including `runs | head -1`; checked by eye in a real terminal (`tools/xterm-shots.py`, `design/playtest.md`).
- [ ] 4.3 The identity in the summary of `records`. Verify: a test per the records-cli scenario; `records --verbose | less` checked by eye (R40).
- [ ] 4.4 `modama-chain trace` and `status` read the new columns, and work against a crawler database without them, as for the table today (`search-chain/src/modama_chain/crawler.py`). Update `python/search-chain/README.md`, which lists the crawler tables it reads. Verify: search-chain tests per scenario of the `chain-trace` delta; `./runtest.sh e2e` in `/prototypes/search-stack/`.

## 5. Recorded fixture extractions (D5 b)

- [ ] 5.1 The pytest plugin records and compares each fixture's extraction next to its recognition result (`testing.py`); regenerate the `em` collection's expected files. Verify: plugin tests per scenario of the formats-testing delta; `pytest` of `modama-formats-em` passes; @weber reviews the diff of the regenerated `expected/*.json`.

## 6. Deployment and the field test

- [ ] 6.1 `prototypes/search-stack/upstaging.sh` runs `modama-crawler runs` in the `crawler` container after `up --wait`, and prints the command to start the crawl now when there is a note (D7). The search stack's README describes the upgrade: what the next crawl does, how to start it now, and how to read the report. Verify: `./uptest.sh` and `./runtest.sh e2e` pass; on staging, @weber runs `./upstaging.sh --build` after an upgrade and the note appears.
- [ ] 6.2 Check R45 on the next staging crawls, recorded in `design/field-tests/search-stack-staging-findings.md` with numbers: the first crawl after this change (everything extracted again, `ingredients unknown`, how many records changed), a deployment that changes no output (`0 records changed`), and one that does (an upgrade or a reverted experiment), each with the report lines, `runs`, `modama-chain status` and one `trace`. Verify: the findings entries, and for each the answer to "does it work as intended, what actually happens, and why".

## 7. The other open changes

- [ ] 7.1 `subtree-crawl`: H3 closed with this change's S1 sequence; its proposal question on the revert answered; D7 reworded ("change the code, rebuild, crawl now"); the README procedure without the bump and without the manual undo step; its revert scenario written. Whichever change is archived second merges the wording of "Extraction follows the identified extractor" (design, Risks). Verify: `openspec validate subtree-crawl --strict` and `openspec validate extractor-identity --strict` pass, and the diff is reviewed by @weber.

## 8. Review and acceptance

- [ ] 8.1 Review by an agent that did not write the code, given the code, the specs, R44 and R45, not this design's conclusions (AGENTS.md: more than a few hundred lines, and a migration); findings verified before they are acted on. Verify: `review.md` in this change, each finding with its outcome.
- [ ] 8.2 Final acceptance with the commands CI and the hook run: `uvx ruff format --check --diff` and `uvx ruff check` from the repository root, `pytest` of the crawler, `modama-formats-em` and `search-chain`, and `./runtest.sh e2e`. Verify: the output, with the number of skipped tests and where the local environment differs from CI's.

## Workflow follow-up

- Archive after `em-formats-and-extraction`, which creates the `extraction` spec this change modifies (`openspec validate` reports today that archiving would refuse the delta until then).
