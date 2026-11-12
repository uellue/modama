# Tasks

## 1. The area `structured`

- [x] 1.1 Subpackage `src/modama_formats_common/structured/` with `structured.xml` (`text/x-ini`, `text/x-config`), one import and one `PARTS` entry in the package's `__init__.py`, PyYAML and defusedxml pinned in `pyproject.toml` (current releases looked up on PyPI: PyYAML 6.0.3 with a cp314 manylinux wheel, defusedxml 0.7.1, pure Python). Verify: `pytest src` of the package; `test_collection.py`.
- [x] 1.2 Fixtures: generated (`generate.py`, with `json`, `yaml.safe_dump`, `csv.writer`, `configparser`) and public (qeschema's `PbTiO3_scf.xml`, the TOML 1.0.0 README's example, both MIT, `LICENSE.fixtures`), with `fixtures.toml`. Verify: `test_manifest`, `test_coverage` (every glob and format fires on a representative fixture), `expected/*.json` reviewed.
- [x] 1.3 Recognition with the content checks (spec "A name that lies falls back to the content's type"). Verify: `test_recognize.py`, one test per scenario.
- [x] 1.4 Extraction: the flat entries, several documents, values as written, XML names, CSV, INI, bounds, the summary line, the skip list. Verify: `test_extract.py`, one test per scenario, also under `TZ=Europe/Berlin`; bytes read counted in the bound's tests. Also run over this VM's own files of these extensions (`/usr/share`, `/usr/lib/python3`, `~/.cache`, the checkout; 4,100 files): failures only for JSON with comments, `.cfg` without a section (recognition drops those), a YAML key that is a list; Compose's tags led to the requirement for YAML tags of applications.
- [x] 1.5 README's table rows. Verify: by eye.

## 2. Checks and review

- [ ] 2.1 `pytest src` of `modama-formats-common`, the crawler's suite, `uvx ruff format --check --diff` and `uvx ruff check` from the repository root. Verify: their output in the hand-over.
- [ ] 2.2 Review by an agent that did not write the code (main starts it); findings verified and applied. Verify: the review's findings and the fixes, listed in the hand-over.
- [ ] 2.3 @weber looks at real files with `modama-chain browse` on staging (after main's combined e2e and an image rebuild). Verify: his remarks.
