# Tasks

## 1. Result and format interface

- [ ] 1.1 Create `formats/__init__.py` with the `Entry`, `Directory`, `Dataset`, `Result` dataclasses and the `Format` base class (`type`, `priority`, `reacts_to`, `collection`, `recognize`); verify with unit tests that a `Dataset` is immutable and that `Directory.read` enforces the byte budget.
- [ ] 1.2 Implement the runner that applies formats to one directory: pre-order call, post-order call, candidate pre-filter by `reacts_to`, priority then id order, exclusive claims, adoption of child datasets, rejection of claims outside the directory, single-file datasets for unclaimed files, nesting warning for non-collection formats, time and byte budgets; verify with synthetic-tree tests covering each `recognition` spec scenario.
- [ ] 1.3 Make the result serialisable to and from JSON with paths relative to a root; verify a round-trip test and that the JSON order is stable across runs.

## 2. Walk

- [ ] 2.1 Implement the post-order walk in `walk.py`: pre-order check, descent, classification of entries, runner call with children's results, collection of tree-level warnings, mtime and ctime per entry, skipping of non-UTF-8 names and unreadable directories; verify with tests for the `crawl` spec scenarios, including the shuffled-listing test (monkeypatched `os.scandir` order).
- [ ] 2.2 Add crawl exclusions (gitignore-style patterns) to the walk; verify an excluded subtree produces no entries.

## 3. MIME database and classification

- [ ] 3.1 Vendor `freedesktop.org.xml` into `formats/core/` with its licence notice and a `LICENSE` note in the collection; verify the file is packaged (`pip install -e .` then the file resolves from the installed package).
- [ ] 3.2 Implement `mimedb.py`: assemble enabled collections' XML into a temporary `mime/packages/`, run `update-mime-database`, point pyxdg at it; verify that a type defined only on the host is not detected and that PNG is detected with only `core` enabled.
- [ ] 3.3 Add tie resolution by `sub-class-of` common ancestor to `mime.py` with the candidates as a warning; verify with a test defining two subtypes of one parent that tie on a glob.
- [ ] 3.4 Remove the EMPAD `*.xml` glob trick from the proof-of-concept definitions; verify that unrelated XML files are not sniffed (count reads in the test).

## 4. Selection and discovery

- [ ] 4.1 Implement `selection.py`: the `modama.formats` entry-point group, loading with duplicate-name rejection, `select`/`ignore` resolution by specificity with ignore winning ties, per-path ignores, configuration file parsing; verify with tests for each `format-selection` spec scenario.
- [ ] 4.2 Register the four in-package collections as entry points in `pyproject.toml`; verify `python -c` listing of the group shows all four after an editable install.

## 5. Records and rendering

- [ ] 5.1 Split `records.py` into record building from a `Dataset` (identifier, browse URL, Dublin Core mapping, `dc:relation` for parts and parent) and `render.py` for `oai_dc` XML shared with `server.py`; verify the existing `test_records.py` and `test_server.py` pass unchanged and new tests cover the collection-relation scenario.
- [ ] 5.2 Implement `store.py` with the new schema and the upsert of a `Result` into `files`, `datasets`, `files_in_datasets` and `records` with the unchanged-datestamp rule; verify with a database test that an unchanged crawl keeps datestamps and a deleted dataset disappears, and that `server.py` serves the stored records (existing client tests).

## 6. Commands

- [ ] 6.1 Implement `cli.py` with `crawl` (walk, store), `serve` (unchanged) and `records [PATH]` (walk, build, filter, render after the walk; diagnostics and `--verbose` on stderr; `--from`, `--until`, `--select`, `--ignore`; non-zero exit on failure); verify with tests for each `records-cli` spec scenario, including schema validation of stdout from a verbose run.
- [ ] 6.2 Update `AGENTS.md` for the new modules, commands and the collection layout; verify the documented commands run as written in the devcontainer.

## 7. Fixture plugin

- [ ] 7.1 Implement `testing.py` as a pytest plugin (`pytest11` entry point): fixture discovery, `fixtures.toml` manifest checks both ways, fixture-tree cleanliness, generated fixtures via a named generator, recorded results in `tests/expected/`, `--regen-expected`, readable diffs, coverage rule over the collection's own XML rules and recognizers; verify with the plugin's own tests on a throwaway collection covering each `formats-testing` spec scenario.
- [ ] 7.2 Write the format template (`formats/TEMPLATE.md` or equivalent) describing the directory layout, the class, the manifest fields and the test commands; verify an agent-style dry run: copy the template into a scratch collection and run its (empty) test suite.

## 8. Collections

- [ ] 8.1 `formats/core`: `core.xml` (empty of own rules) beside the vendored file, collection registration; verify the `formats/core` spec scenarios with small real fixtures (PNG, JSON, Python, plain XML) and the recorded results.
- [ ] 8.2 `formats/collapse`: `Collapse` base and the kinds (venv, conda, `node_modules`, `.git`, `__pycache__`, `.ipynb_checkpoints`) answering pre-order; fixtures generated by `python -m venv` and `git init` at test time; verify the spec scenarios and that no file below a collapsed directory is opened (read counter).
- [ ] 8.3 `formats/zarr`: pre-order recognition of `zarr.json`, bounded read for the broken-store warning; fixtures written by zarr-python at test time (array, group containing an array, corrupt metadata); verify the spec scenarios.
- [ ] 8.4 `formats/empad`: `empad.xml` (header magic, raw globs at weight 80), the recognizer (parse header within budget, find raw sibling, build the pair, warn when missing); the cheat generator (real header reduced to 2×2, zero-filled raw); verify the spec scenarios; validate the generated pair once with LiberTEM's EMPAD reader and `SumUDF` on the inline executor outside the test suite, and record `second-reader: libertem` in the manifest.

## 9. Integration

- [ ] 9.1 Remove `recognition.py`, `tests/test_recognition.py`, `tests/test_crawl.py` and the old `database.py` paths; verify the whole suite passes (`pytest`) and `ruff check` and `ruff format --check` are clean.
- [ ] 9.2 Run `records --verbose` on a directory of `/er-c-data` that contains an EMPAD pair, a Zarr store and a Python environment; verify the output validates against the schemas and the diagnostics name the expected formats; record the directory and the outcome in `design/survey.md`.
- [ ] 9.3 Run `crawl` on the visible `/er-c-data` tree into the development database and `serve`; verify a `ListRecords` harvest with the client tests' libraries completes and note the duration and the warning counts in `design/survey.md`.

## Workflow follow-up

- Review by @weber, @clausen, @shanker on MR !106 before archive.
- Archive the change after review; the delta specs become the first main specs.
